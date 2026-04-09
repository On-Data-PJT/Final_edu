from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from youtube_transcript_api._errors import IpBlocked

from final_edu import youtube_cache as youtube_cache_module
from final_edu.analysis import analyze_submissions
from final_edu.config import get_settings
from final_edu.extractors import extract_youtube_asset
from final_edu.models import CurriculumSection, InstructorSubmission
from final_edu.storage import create_object_storage
from final_edu.youtube import _resolve_youtube_input_with_settings, summarize_youtube_inputs
from final_edu.youtube_cache import (
    YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE,
    YOUTUBE_STALE_TRANSCRIPT_WARNING,
    YoutubeCache,
    throttle_youtube_requests,
)


class _FakeYoutubeDL:
    call_count = 0

    def __init__(self, options: dict) -> None:
        self.options = dict(options)

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
        type(self).call_count += 1
        return {
            "id": "U5De-0aglaE",
            "title": "Single Video",
            "duration": 120,
            "webpage_url": "https://www.youtube.com/watch?v=U5De-0aglaE",
        }


class _ExplodingYoutubeDL:
    def __init__(self, options: dict) -> None:
        self.options = dict(options)

    def __enter__(self) -> "_ExplodingYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
        raise AssertionError("yt-dlp should not be called on a metadata cache hit")


class _CountingTranscriptApi:
    fetch_count = 0

    def __init__(self, proxy_config=None, http_client=None) -> None:
        pass

    def fetch(self, video_id: str, languages=None):
        type(self).fetch_count += 1
        return [{"text": "데이터 분석 실습", "start": 0.0, "duration": 4.0}]


class _BlockedTranscriptApi:
    def __init__(self, proxy_config=None, http_client=None) -> None:
        pass

    def fetch(self, video_id: str, languages=None):
        raise IpBlocked(video_id)


class _ExplodingTranscriptApi:
    def __init__(self, proxy_config=None, http_client=None) -> None:
        raise AssertionError("transcript api should not be instantiated on a transcript cache hit")


def _sample_sections() -> list[CurriculumSection]:
    return [
        CurriculumSection(
            id="data-analysis",
            title="데이터 분석",
            description="sql pandas 전처리",
            target_weight=100,
        )
    ]


class YoutubeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        youtube_cache_module._NEXT_REQUEST_AT = 0.0

    def test_metadata_cache_hit_skips_ytdlp(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                youtube_request_min_interval_seconds=0.0,
            )
            storage = create_object_storage(settings)
            _FakeYoutubeDL.call_count = 0

            with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL):
                first = _resolve_youtube_input_with_settings(
                    "https://www.youtube.com/watch?v=U5De-0aglaE",
                    max_videos=500,
                    settings=settings,
                    storage=storage,
                )

            with patch("final_edu.youtube.YoutubeDL", _ExplodingYoutubeDL):
                second = _resolve_youtube_input_with_settings(
                    "https://www.youtube.com/watch?v=U5De-0aglaE",
                    max_videos=500,
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(_FakeYoutubeDL.call_count, 1)
        self.assertEqual(first.videos[0].video_id, second.videos[0].video_id)

    def test_transcript_cache_hit_is_reused_between_prepare_and_analysis(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                openai_api_key=None,
                chunk_target_tokens=64,
                chunk_overlap_segments=0,
                youtube_request_min_interval_seconds=0.0,
            )
            storage = create_object_storage(settings)
            _CountingTranscriptApi.fetch_count = 0

            with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL), patch(
                "final_edu.extractors.YouTubeTranscriptApi",
                _CountingTranscriptApi,
            ):
                summary = summarize_youtube_inputs(
                    [url],
                    settings=settings,
                    instructor_count=1,
                    section_count=1,
                    storage=storage,
                )

            with patch("final_edu.extractors.YouTubeTranscriptApi", _ExplodingTranscriptApi):
                result = analyze_submissions(
                    course_id="course-1",
                    course_name="AI 데이터 과정",
                    sections=_sample_sections(),
                    submissions=[InstructorSubmission(name="강사 A", youtube_urls=summary["expanded_urls"])],
                    settings=settings,
                    storage=storage,
                    analysis_mode="lexical",
                )

        self.assertEqual(_CountingTranscriptApi.fetch_count, 1)
        self.assertEqual(len(result.instructors), 1)
        self.assertGreater(result.instructors[0].total_tokens, 0)

    def test_stale_transcript_cache_is_used_when_youtube_is_limited(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                youtube_request_min_interval_seconds=0.0,
                youtube_transcript_cache_ttl_seconds=-1,
            )
            storage = create_object_storage(settings)
            cache = YoutubeCache(settings, storage=storage)
            cache.put_transcript(
                video_id="U5De-0aglaE",
                value=[{"text": "데이터 분석 실습", "start": 0.0, "duration": 3.0}],
            )

            with patch("final_edu.extractors.YouTubeTranscriptApi", _BlockedTranscriptApi):
                _source, segments, warnings = extract_youtube_asset(
                    url,
                    "강사 A",
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(len(segments), 1)
        self.assertTrue(any(YOUTUBE_STALE_TRANSCRIPT_WARNING in warning for warning in warnings))

    def test_rate_limited_transcript_without_cache_returns_explicit_warning(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                youtube_request_min_interval_seconds=0.0,
            )
            storage = create_object_storage(settings)

            with patch("final_edu.extractors.YouTubeTranscriptApi", _BlockedTranscriptApi):
                _source, segments, warnings = extract_youtube_asset(
                    url,
                    "강사 A",
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(segments, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn(YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE, warnings[0])

    def test_throttle_enforces_minimum_interval(self) -> None:
        settings = replace(
            get_settings(),
            youtube_request_min_interval_seconds=1.5,
        )
        youtube_cache_module._NEXT_REQUEST_AT = 0.0

        with patch(
            "final_edu.youtube_cache.time.monotonic",
            side_effect=[0.0, 0.4, 1.6],
        ), patch("final_edu.youtube_cache.time.sleep") as sleep_mock:
            throttle_youtube_requests(settings)
            throttle_youtube_requests(settings)

        sleep_mock.assert_called_once()
        self.assertAlmostEqual(float(sleep_mock.call_args.args[0]), 1.1, places=4)


if __name__ == "__main__":
    unittest.main()
