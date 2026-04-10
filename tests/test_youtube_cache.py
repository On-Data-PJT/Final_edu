from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from youtube_transcript_api._errors import IpBlocked, TranscriptsDisabled

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
    build_youtube_scraperapi_proxy_url,
    throttle_youtube_requests,
)


class _FakeYoutubeDL:
    call_count = 0
    last_options: dict | None = None
    last_process: bool | None = None

    def __init__(self, options: dict) -> None:
        type(self).last_options = dict(options)
        self.options = dict(options)

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False, process: bool = True) -> dict:
        type(self).call_count += 1
        type(self).last_process = process
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

    def extract_info(self, url: str, download: bool = False, process: bool = True) -> dict:
        raise AssertionError("yt-dlp should not be called on a metadata cache hit")


class _CountingTranscriptApi:
    fetch_count = 0
    last_http_client = None

    def __init__(self, proxy_config=None, http_client=None) -> None:
        type(self).last_http_client = http_client

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


class _NoTranscriptApi:
    def __init__(self, proxy_config=None, http_client=None) -> None:
        pass

    def fetch(self, video_id: str, languages=None):
        raise TranscriptsDisabled(video_id)


class _FakeDownloadedYoutubeDL:
    last_options: dict | None = None

    def __init__(self, options: dict) -> None:
        type(self).last_options = dict(options)
        self.options = dict(options)

    def __enter__(self) -> "_FakeDownloadedYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
        output = Path(str(self.options["outtmpl"]).replace("%(id)s", "U5De-0aglaE").replace("%(ext)s", "m4a"))
        output.write_bytes(b"fake-audio")
        return {
            "id": "U5De-0aglaE",
            "duration": 120,
            "requested_downloads": [{"filepath": str(output)}],
        }


class _ExplodingYoutubeDownload:
    def __init__(self, options: dict) -> None:
        self.options = dict(options)

    def __enter__(self) -> "_ExplodingYoutubeDownload":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
        raise AssertionError("yt-dlp download should not run for this test")


class _FakeOpenAITranscriptionClient:
    last_model = None

    def __init__(self, api_key: str | None = None) -> None:
        self.audio = self
        self.transcriptions = self

    def create(self, *, file, model: str, response_format: str = "text", **kwargs):
        type(self).last_model = model
        return "딥러닝 실습 데이터 분석"


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def get(self, key: str):
        return self.store.get(key)

    def eval(self, script: str, numkeys: int, key: str, token: str):
        if self.store.get(key) == token:
            self.store.pop(key, None)
            return 1
        return 0


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
        youtube_cache_module._COOLDOWN_UNTIL = 0.0
        youtube_cache_module._REDIS_CLIENTS.clear()

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

    def test_scraperapi_proxy_is_applied_only_to_transcript_fetch(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                youtube_request_min_interval_seconds=0.0,
                youtube_distributed_min_interval_seconds=0.0,
                youtube_scraperapi_enabled=True,
                youtube_scraperapi_key="scraperapi-key",
                youtube_scraperapi_proxy_port=8001,
                youtube_scraperapi_session_sticky=True,
                youtube_scraperapi_max_cost=1,
            )
            storage = create_object_storage(settings)
            _CountingTranscriptApi.last_http_client = None

            with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL), patch(
                "final_edu.extractors.YouTubeTranscriptApi",
                _CountingTranscriptApi,
            ):
                summarize_youtube_inputs(
                    [url],
                    settings=settings,
                    instructor_count=1,
                    section_count=1,
                    storage=storage,
                )

        expected_proxy_url = build_youtube_scraperapi_proxy_url(
            settings,
            session_seed="video:U5De-0aglaE",
        )
        self.assertNotIn("proxy", _FakeYoutubeDL.last_options)
        self.assertNotIn("nocheckcertificate", _FakeYoutubeDL.last_options)
        self.assertTrue(_FakeYoutubeDL.last_options["ignoreconfig"])
        self.assertEqual(_FakeYoutubeDL.last_process, False)
        self.assertIsNotNone(_CountingTranscriptApi.last_http_client)
        self.assertEqual(
            _CountingTranscriptApi.last_http_client.proxies,
            {"http": expected_proxy_url, "https": expected_proxy_url},
        )
        self.assertFalse(_CountingTranscriptApi.last_http_client.verify)

    def test_selective_stt_fallback_runs_for_missing_transcript(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                youtube_request_min_interval_seconds=0.0,
                youtube_distributed_min_interval_seconds=0.0,
                openai_api_key="test-key",
                youtube_stt_enabled=True,
                youtube_stt_max_file_bytes=1024 * 1024,
                youtube_scraperapi_enabled=True,
                youtube_scraperapi_key="scraperapi-key",
            )
            storage = create_object_storage(settings)
            _FakeDownloadedYoutubeDL.last_options = None

            with patch("final_edu.extractors.YouTubeTranscriptApi", _NoTranscriptApi), patch(
                "final_edu.extractors.YoutubeDL",
                _FakeDownloadedYoutubeDL,
            ), patch("final_edu.extractors.OpenAI", _FakeOpenAITranscriptionClient):
                _source, segments, warnings = extract_youtube_asset(
                    url,
                    "강사 A",
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(len(segments), 1)
        self.assertTrue(any("STT fallback" in warning for warning in warnings))
        self.assertEqual(_FakeOpenAITranscriptionClient.last_model, settings.youtube_stt_model)
        self.assertNotIn("proxy", _FakeDownloadedYoutubeDL.last_options)

    def test_rate_limited_transcript_does_not_trigger_stt_fallback(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(
                get_settings(),
                runtime_dir=Path(runtime_dir),
                youtube_request_min_interval_seconds=0.0,
                youtube_distributed_min_interval_seconds=0.0,
                openai_api_key="test-key",
                youtube_stt_enabled=True,
            )
            storage = create_object_storage(settings)

            with patch("final_edu.extractors.YouTubeTranscriptApi", _BlockedTranscriptApi), patch(
                "final_edu.extractors.YoutubeDL",
                _ExplodingYoutubeDownload,
            ):
                _source, segments, warnings = extract_youtube_asset(
                    url,
                    "강사 A",
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(segments, [])
        self.assertTrue(any(YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE in warning for warning in warnings))

    def test_distributed_throttle_uses_redis_shared_next_request(self) -> None:
        fake_redis = _FakeRedis()
        now = [100.0]
        slept: list[float] = []
        settings = replace(
            get_settings(),
            youtube_request_min_interval_seconds=0.0,
            youtube_distributed_min_interval_seconds=2.5,
            redis_url="redis://example.test:6379/0",
        )

        def _fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        with patch("final_edu.youtube_cache._get_redis_client", return_value=fake_redis), patch(
            "final_edu.youtube_cache.time.time",
            side_effect=lambda: now[0],
        ), patch("final_edu.youtube_cache.time.sleep", side_effect=_fake_sleep):
            throttle_youtube_requests(settings)
            throttle_youtube_requests(settings)

        self.assertEqual(slept, [2.5])

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
