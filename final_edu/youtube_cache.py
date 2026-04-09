from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from requests import RequestException
from yt_dlp.utils import DownloadError
from youtube_transcript_api._errors import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)

from final_edu.config import Settings
from final_edu.storage import ObjectStorage, create_object_storage

YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE = (
    "YouTube 요청이 일시적으로 제한되었습니다. 잠시 후 다시 시도하거나 동일 영상을 다시 분석할 때는 "
    "캐시된 결과가 사용될 수 있습니다."
)
YOUTUBE_STALE_TRANSCRIPT_WARNING = "YouTube 요청 제한으로 캐시된 자막을 사용했습니다."

_CACHE_SCHEMA_VERSION = 1
_RATE_LIMIT_MARKERS = (
    "429",
    "too many requests",
    "temporarily unavailable",
    "rate limit",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "try again later",
    "blocked",
)
_NON_RETRIABLE_TRANSCRIPT_ERRORS = (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    AgeRestricted,
    PoTokenRequired,
)
_THROTTLE_LOCK = Lock()
_NEXT_REQUEST_AT = 0.0


@dataclass(slots=True)
class CachedYoutubeValue:
    value: Any
    is_stale: bool


def has_youtube_request_limit_warning(messages: list[str]) -> bool:
    return any(
        YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE in str(message or "")
        or YOUTUBE_STALE_TRANSCRIPT_WARNING in str(message or "")
        for message in messages
    )


def is_youtube_request_limited_error(exc: Exception) -> bool:
    if isinstance(exc, (IpBlocked, RequestBlocked)):
        return True
    if isinstance(exc, _NON_RETRIABLE_TRANSCRIPT_ERRORS):
        return False
    message = str(exc).lower()
    if "blocking requests from your ip" in message:
        return True
    if isinstance(exc, (DownloadError, YouTubeRequestFailed, RequestException, OSError)):
        return any(marker in message for marker in _RATE_LIMIT_MARKERS)
    return any(marker in message for marker in _RATE_LIMIT_MARKERS)


def summarize_youtube_fetch_error(url: str, exc: Exception) -> str:
    if is_youtube_request_limited_error(exc):
        return f"{url}: {YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE}"
    compact_reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return (
        f"{url}: 자막을 가져오지 못했습니다. 현재 MVP는 자막 없는 영상의 STT fallback을 "
        f"기본 지원하지 않습니다. ({compact_reason})"
    )


def throttle_youtube_requests(settings: Settings) -> None:
    interval_seconds = max(0.0, float(settings.youtube_request_min_interval_seconds or 0.0))
    if interval_seconds <= 0:
        return

    global _NEXT_REQUEST_AT
    with _THROTTLE_LOCK:
        now = time.monotonic()
        wait_seconds = _NEXT_REQUEST_AT - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        _NEXT_REQUEST_AT = max(now, _NEXT_REQUEST_AT) + interval_seconds


class YoutubeCache:
    def __init__(self, settings: Settings, storage: ObjectStorage | None = None) -> None:
        self.settings = settings
        self.storage = storage or create_object_storage(settings)

    def get_metadata(
        self,
        *,
        url: str,
        max_videos: int,
        treat_as_playlist: bool,
        allow_stale: bool,
    ) -> CachedYoutubeValue | None:
        return self._read(
            self._metadata_storage_key(
                url=url,
                max_videos=max_videos,
                treat_as_playlist=treat_as_playlist,
            ),
            allow_stale=allow_stale,
        )

    def put_metadata(self, *, url: str, max_videos: int, treat_as_playlist: bool, value: dict) -> None:
        self._write(
            self._metadata_storage_key(
                url=url,
                max_videos=max_videos,
                treat_as_playlist=treat_as_playlist,
            ),
            value=value,
            ttl_seconds=self.settings.youtube_metadata_cache_ttl_seconds,
        )

    def get_transcript(self, *, video_id: str, allow_stale: bool) -> CachedYoutubeValue | None:
        return self._read(self._transcript_storage_key(video_id), allow_stale=allow_stale)

    def put_transcript(self, *, video_id: str, value: list[dict]) -> None:
        self._write(
            self._transcript_storage_key(video_id),
            value=value,
            ttl_seconds=self.settings.youtube_transcript_cache_ttl_seconds,
        )

    def _metadata_storage_key(self, *, url: str, max_videos: int, treat_as_playlist: bool) -> str:
        digest = self._hash_key(
            f"url={str(url or '').strip()}|playlist={int(treat_as_playlist)}|max_videos={int(max_videos)}"
        )
        return f"youtube-cache/metadata/{digest[:2]}/{digest}.json"

    def _transcript_storage_key(self, video_id: str) -> str:
        digest = self._hash_key(str(video_id or "").strip())
        return f"youtube-cache/transcripts/{digest[:2]}/{digest}.json"

    def _hash_key(self, raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _read(self, storage_key: str, *, allow_stale: bool) -> CachedYoutubeValue | None:
        try:
            payload = self.storage.get_json(storage_key)
        except Exception:  # noqa: BLE001
            return None

        if int(payload.get("schema_version", 0) or 0) != _CACHE_SCHEMA_VERSION:
            return None

        expires_at_ts = float(payload.get("expires_at_ts", 0.0) or 0.0)
        is_stale = expires_at_ts > 0 and expires_at_ts <= time.time()
        if is_stale and not allow_stale:
            return None

        return CachedYoutubeValue(value=payload.get("value"), is_stale=is_stale)

    def _write(self, storage_key: str, *, value: Any, ttl_seconds: int) -> None:
        now = time.time()
        ttl = max(0, int(ttl_seconds or 0))
        self.storage.put_json(
            storage_key,
            {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "stored_at_ts": now,
                "expires_at_ts": now + ttl,
                "value": value,
            },
        )
