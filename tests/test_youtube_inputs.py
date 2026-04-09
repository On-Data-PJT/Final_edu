from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from final_edu.config import get_settings
from final_edu.youtube import is_explicit_playlist_url, resolve_youtube_input, summarize_youtube_inputs


class _FakeYoutubeDL:
    last_options: dict | None = None

    def __init__(self, options: dict) -> None:
        type(self).last_options = dict(options)
        self.options = options

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
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


class YoutubeInputTests(unittest.TestCase):
    def test_watch_url_inside_playlist_is_not_treated_as_playlist(self) -> None:
        url = "https://www.youtube.com/watch?v=U5De-0aglaE&list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI&index=7"
        self.assertFalse(is_explicit_playlist_url(url))

        with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL):
            resolved = resolve_youtube_input(url, max_videos=500)

        self.assertEqual(resolved.kind, "video")
        self.assertEqual(resolved.total_video_count, 1)
        self.assertEqual(len(resolved.videos), 1)
        self.assertEqual(resolved.videos[0].video_id, "U5De-0aglaE")
        self.assertEqual(_FakeYoutubeDL.last_options["noplaylist"], True)

    def test_playlist_url_is_expanded_as_playlist(self) -> None:
        url = "https://www.youtube.com/playlist?list=PLIYf0rAjO5mY-xE36xaBCJdZzLFH6QjKI"
        self.assertTrue(is_explicit_playlist_url(url))

        with patch("final_edu.youtube.YoutubeDL", _FakeYoutubeDL):
            resolved = resolve_youtube_input(url, max_videos=500)

        self.assertEqual(resolved.kind, "playlist")
        self.assertEqual(resolved.total_video_count, 447)
        self.assertEqual(len(resolved.videos), 2)
        self.assertEqual(_FakeYoutubeDL.last_options["noplaylist"], False)
        self.assertEqual(_FakeYoutubeDL.last_options["playlistend"], 501)

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


if __name__ == "__main__":
    unittest.main()
