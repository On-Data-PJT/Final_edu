from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from final_edu.config import get_settings
from final_edu.storage import create_object_storage
from final_edu.youtube import (
    ResolvedYoutubeInput,
    ResolvedYoutubeVideo,
    _resolve_youtube_input_with_settings,
    is_explicit_playlist_url,
    summarize_youtube_inputs,
)


class _FakeYoutubeDL:
    last_options: dict | None = None
    last_process: bool | None = None

    def __init__(self, options: dict) -> None:
        type(self).last_options = dict(options)
        self.options = options

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False, process: bool = True) -> dict:
        type(self).last_process = process
        if self.options.get("noplaylist"):
            return {
                "id": "U5De-0aglaE",
                "title": "Single Video",
                "duration": 120,
                "webpage_url": "https://www.youtube.com/watch?v=U5De-0aglaE",
            }
        return {
            "id": "PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI",
            "title": "BigData_53",
            "playlist_count": 447,
            "entries": [
                {"id": "video-a", "title": "Video A", "duration": 60},
                {"id": "video-b", "title": "Video B", "duration": 90},
            ],
        }


class _ExplodingYoutubeDL:
    def __init__(self, options: dict) -> None:
        self.options = dict(options)

    def __enter__(self) -> "_ExplodingYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False, process: bool = True) -> dict:
        raise RuntimeError("Requested format is not available")


class YoutubeInputTests(unittest.TestCase):
    def _playlist_input(self, video_count: int) -> ResolvedYoutubeInput:
        videos = [
            ResolvedYoutubeVideo(
                video_id=f"video-{index:03d}",
                title=f"Video {index}",
                url=f"https://www.youtube.com/watch?v=video-{index:03d}",
                duration_seconds=120,
            )
            for index in range(video_count)
        ]
        return ResolvedYoutubeInput(
            input_url="https://www.youtube.com/playlist?list=test-playlist",
            kind="playlist",
            title="Test Playlist",
            source_id="test-playlist",
            videos=videos,
            total_video_count=video_count,
        )

    def test_watch_url_inside_playlist_is_not_treated_as_playlist(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE&list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI&index=7"
        self.assertFalse(is_explicit_playlist_url(url))

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(get_settings(), runtime_dir=Path(runtime_dir))
            storage = create_object_storage(settings)

            with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL):
                resolved = _resolve_youtube_input_with_settings(
                    url,
                    max_videos=500,
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(resolved.kind, "video")
        self.assertEqual(resolved.total_video_count, 1)
        self.assertEqual(len(resolved.videos), 1)
        self.assertEqual(resolved.videos[0].video_id, "U5De-0aglaE")
        self.assertEqual(_FakeYoutubeDL.last_options["noplaylist"], True)
        self.assertTrue(_FakeYoutubeDL.last_options["ignoreconfig"])
        self.assertEqual(_FakeYoutubeDL.last_process, False)

    def test_playlist_url_is_expanded_as_playlist(self) -> None:
        url = "https://www.youtube.com/playlist?list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI"
        self.assertTrue(is_explicit_playlist_url(url))

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(get_settings(), runtime_dir=Path(runtime_dir))
            storage = create_object_storage(settings)

            with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL):
                resolved = _resolve_youtube_input_with_settings(
                    url,
                    max_videos=500,
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(resolved.kind, "playlist")
        self.assertEqual(resolved.total_video_count, 447)
        self.assertEqual(len(resolved.videos), 2)
        self.assertEqual(_FakeYoutubeDL.last_options["noplaylist"], False)
        self.assertEqual(_FakeYoutubeDL.last_options["playlistend"], 501)
        self.assertTrue(_FakeYoutubeDL.last_options["ignoreconfig"])
        self.assertEqual(_FakeYoutubeDL.last_process, False)

    def test_youtu_be_url_with_playlist_query_stays_single_video(self) -> None:
        url = "https://youtu.be/U5De-0aglaE?list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI"
        self.assertFalse(is_explicit_playlist_url(url))

    def test_summarize_keeps_watch_url_as_single_video(self) -> None:
        settings = replace(get_settings(), openai_api_key=None, chunk_target_tokens=200)
        url = "https://www.youtube.com/watch?v=U5De-0aglaE&list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI&index=7"

        with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL), patch(
            "final_edu.youtube.probe_transcript_samples",
            return_value={
                "sample_count": 1,
                "success_count": 0,
                "average_tokens_per_second": 0.0,
                "average_fetch_seconds": 1.0,
                "warnings": [],
            },
        ):
            summary = summarize_youtube_inputs(
                [url],
                settings=settings,
                instructor_count=1,
                section_count=3,
            )

        self.assertEqual(summary["expanded_video_count"], 1)
        self.assertFalse(summary["has_playlist"])
        self.assertEqual(summary["expanded_urls"], ["https://www.youtube.com/watch?v=U5De-0aglaE"])

    def test_probe_threshold_keeps_full_probe_up_to_30_videos(self) -> None:
        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=200,
            playlist_probe_full_threshold=30,
            playlist_probe_partial_sample_size=3,
            playlist_probe_disable_threshold=200,
        )

        with patch(
            "final_edu.youtube._resolve_youtube_input_with_settings",
            return_value=self._playlist_input(30),
        ), patch(
            "final_edu.youtube.probe_transcript_samples",
            return_value={
                "sample_count": 20,
                "success_count": 0,
                "average_tokens_per_second": 0.0,
                "average_fetch_seconds": 1.0,
                "warnings": [],
            },
        ) as mock_probe:
            summarize_youtube_inputs(
                ["https://www.youtube.com/playlist?list=test"],
                settings=settings,
                instructor_count=1,
                section_count=3,
            )

        self.assertEqual(mock_probe.call_args.kwargs["sample_size"], settings.playlist_probe_sample_size)

    def test_probe_threshold_reduces_probe_above_30_videos(self) -> None:
        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=200,
            playlist_probe_full_threshold=30,
            playlist_probe_partial_sample_size=3,
            playlist_probe_disable_threshold=200,
        )

        with patch(
            "final_edu.youtube._resolve_youtube_input_with_settings",
            return_value=self._playlist_input(31),
        ), patch(
            "final_edu.youtube.probe_transcript_samples",
            return_value={
                "sample_count": 3,
                "success_count": 0,
                "average_tokens_per_second": 0.0,
                "average_fetch_seconds": 1.0,
                "warnings": [],
            },
        ) as mock_probe:
            summary = summarize_youtube_inputs(
                ["https://www.youtube.com/playlist?list=test"],
                settings=settings,
                instructor_count=1,
                section_count=3,
            )

        self.assertEqual(mock_probe.call_args.kwargs["sample_size"], 3)
        self.assertTrue(any("축소" in warning for warning in summary["warnings"]))

    def test_probe_threshold_skips_probe_above_200_videos(self) -> None:
        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=200,
            playlist_probe_full_threshold=30,
            playlist_probe_partial_sample_size=3,
            playlist_probe_disable_threshold=200,
        )

        with patch(
            "final_edu.youtube._resolve_youtube_input_with_settings",
            return_value=self._playlist_input(201),
        ), patch(
            "final_edu.youtube.probe_transcript_samples",
            return_value={
                "sample_count": 0,
                "success_count": 0,
                "average_tokens_per_second": 0.0,
                "average_fetch_seconds": 1.2,
                "warnings": [],
            },
        ) as mock_probe:
            summary = summarize_youtube_inputs(
                ["https://www.youtube.com/playlist?list=test"],
                settings=settings,
                instructor_count=1,
                section_count=3,
            )

        self.assertEqual(mock_probe.call_args.kwargs["sample_size"], 0)
        self.assertTrue(any("생략" in warning for warning in summary["warnings"]))

    def test_single_video_metadata_failure_falls_back_to_url_parsed_video_id(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(get_settings(), runtime_dir=Path(runtime_dir))
            storage = create_object_storage(settings)

            with patch("final_edu.youtube.YoutubeDL", _ExplodingYoutubeDL):
                resolved = _resolve_youtube_input_with_settings(
                    url,
                    max_videos=500,
                    settings=settings,
                    storage=storage,
                )

        self.assertEqual(resolved.kind, "video")
        self.assertEqual(resolved.source_id, "U5De-0aglaE")
        self.assertEqual(resolved.videos[0].video_id, "U5De-0aglaE")
        self.assertEqual(resolved.videos[0].duration_seconds, 0)

    def test_playlist_metadata_failure_becomes_user_facing_value_error(self) -> None:
        url = "https://www.youtube.com/playlist?list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI"

        with tempfile.TemporaryDirectory() as runtime_dir:
            settings = replace(get_settings(), runtime_dir=Path(runtime_dir))
            storage = create_object_storage(settings)

            with patch("final_edu.youtube.YoutubeDL", _ExplodingYoutubeDL):
                with self.assertRaises(ValueError) as context:
                    _resolve_youtube_input_with_settings(
                        url,
                        max_videos=500,
                        settings=settings,
                        storage=storage,
                    )

        self.assertIn("재생목록 메타데이터", str(context.exception))


if __name__ == "__main__":
    unittest.main()
