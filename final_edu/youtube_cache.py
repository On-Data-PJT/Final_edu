from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import quote_plus, urlparse, parse_qs
from uuid import uuid4

from requests import RequestException, Session
import urllib3
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
YOUTUBE_SCRAPERAPI_KEY_REQUIRED_ERROR_MESSAGE = (
    "ScraperAPI trial 사용이 활성화됐지만 ScraperAPI API key 환경 변수가 비어 있습니다."
)
YOUTUBE_STT_FALLBACK_WARNING = "공개 자막이 없어 STT fallback 결과를 사용했습니다."
YOUTUBE_STT_DISABLED_WARNING = (
    "공개 자막이 없지만 STT fallback 이 비활성화되어 있어 분석하지 못했습니다."
)
YOUTUBE_STT_BUDGET_EXCEEDED_WARNING = "월간 STT 예산을 초과해 STT fallback을 건너뛰었습니다."
YOUTUBE_STT_FILE_TOO_LARGE_WARNING = "STT fallback용 오디오 크기가 상한을 초과해 건너뛰었습니다."

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
_STT_FALLBACK_ERRORS = (
    NoTranscriptFound,
    TranscriptsDisabled,
)
_THROTTLE_LOCK = Lock()
_NEXT_REQUEST_AT = 0.0
_COOLDOWN_UNTIL = 0.0
_REDIS_CLIENTS: dict[str, Any] = {}
_REDIS_CLIENTS_LOCK = Lock()
_REDIS_THROTTLE_LOCK_KEY = "final-edu:youtube:throttle:lock"
_REDIS_THROTTLE_NEXT_AT_KEY = "final-edu:youtube:throttle:next-at"
_REDIS_THROTTLE_COOLDOWN_KEY = "final-edu:youtube:throttle:cooldown-until"
_SCRAPERAPI_PROXY_HOST = "proxy-server.scraperapi.com"


@dataclass(slots=True)
class CachedYoutubeValue:
    value: Any
    is_stale: bool


class YoutubeRequestCooldown(RuntimeError):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = max(0.0, float(retry_after_seconds or 0.0))
        super().__init__(YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE)


def has_youtube_request_limit_warning(messages: list[str]) -> bool:
    return any(
        YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE in str(message or "")
        or YOUTUBE_STALE_TRANSCRIPT_WARNING in str(message or "")
        for message in messages
    )


def is_youtube_request_limited_error(exc: Exception) -> bool:
    if isinstance(exc, YoutubeRequestCooldown):
        return True
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


def is_youtube_stt_fallback_error(exc: Exception) -> bool:
    return isinstance(exc, _STT_FALLBACK_ERRORS)


def build_youtube_scraperapi_proxy_url(settings: Settings, *, session_seed: str | None = None) -> str | None:
    if not settings.youtube_scraperapi_enabled:
        return None

    api_key = str(settings.youtube_scraperapi_key or "").strip()
    if not api_key:
        raise RuntimeError(YOUTUBE_SCRAPERAPI_KEY_REQUIRED_ERROR_MESSAGE)

    username_parts = ["scraperapi"]
    if settings.youtube_scraperapi_session_sticky and session_seed:
        username_parts.append(f"session_number={_scraperapi_session_number(session_seed)}")
    if settings.youtube_scraperapi_max_cost is not None:
        username_parts.append(f"max_cost={max(1, int(settings.youtube_scraperapi_max_cost))}")

    username = ".".join(username_parts)
    password = quote_plus(api_key)
    port = max(1, int(settings.youtube_scraperapi_proxy_port or 8001))
    return f"http://{username}:{password}@{_SCRAPERAPI_PROXY_HOST}:{port}"


def build_youtube_scraperapi_http_client(settings: Settings, *, session_seed: str) -> Session | None:
    proxy_url = build_youtube_scraperapi_proxy_url(settings, session_seed=session_seed)
    if proxy_url is None:
        return None

    client = Session()
    client.proxies = {"http": proxy_url, "https": proxy_url}
    # ScraperAPI proxy port requires disabled certificate verification unless a CA bundle is installed.
    client.verify = False
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return client


def build_youtube_request_session_seed(url: str) -> str:
    normalized = str(url or "").strip()
    if not normalized:
        return "youtube"

    parsed = urlparse(normalized)
    query = parse_qs(parsed.query or "")
    video_id = (query.get("v") or [None])[0]
    playlist_id = (query.get("list") or [None])[0]
    if video_id:
        return f"video:{video_id}"
    if playlist_id:
        return f"playlist:{playlist_id}"
    if parsed.hostname == "youtu.be":
        path_video_id = (parsed.path or "").strip("/").split("/", maxsplit=1)[0]
        if path_video_id:
            return f"video:{path_video_id}"
    return normalized


def summarize_youtube_fetch_error(url: str, exc: Exception) -> str:
    if is_youtube_request_limited_error(exc):
        return f"{url}: {YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE}"
    compact_reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return (
        f"{url}: 자막을 가져오지 못했습니다. 자막이 없는 영상은 STT fallback 설정이 있어야 "
        f"분석할 수 있습니다. ({compact_reason})"
    )


def throttle_youtube_requests(settings: Settings) -> None:
    _throttle_distributed_youtube_requests(settings)
    _throttle_process_local_youtube_requests(settings)


def mark_youtube_request_limited(settings: Settings) -> None:
    cooldown_seconds = max(0.0, float(settings.youtube_cooldown_seconds or 0.0))
    if cooldown_seconds <= 0:
        return

    cooldown_until = time.time() + cooldown_seconds
    global _COOLDOWN_UNTIL
    _COOLDOWN_UNTIL = max(_COOLDOWN_UNTIL, cooldown_until)

    redis_client = _get_redis_client(settings)
    if redis_client is None:
        return
    try:
        redis_client.set(
            _REDIS_THROTTLE_COOLDOWN_KEY,
            str(cooldown_until),
            ex=max(60, int(cooldown_seconds) + 60),
        )
        redis_client.set(
            _REDIS_THROTTLE_NEXT_AT_KEY,
            str(cooldown_until),
            ex=max(60, int(cooldown_seconds) + 60),
        )
    except Exception:  # noqa: BLE001
        return


def _throttle_process_local_youtube_requests(settings: Settings) -> None:
    interval_seconds = max(0.0, float(settings.youtube_request_min_interval_seconds or 0.0))
    if interval_seconds <= 0:
        return

    global _COOLDOWN_UNTIL, _NEXT_REQUEST_AT
    with _THROTTLE_LOCK:
        now_wall = time.time()
        if _COOLDOWN_UNTIL > now_wall:
            raise YoutubeRequestCooldown(_COOLDOWN_UNTIL - now_wall)

        now = time.monotonic()
        wait_seconds = _NEXT_REQUEST_AT - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        _NEXT_REQUEST_AT = max(now, _NEXT_REQUEST_AT) + interval_seconds


def _throttle_distributed_youtube_requests(settings: Settings) -> None:
    interval_seconds = max(0.0, float(settings.youtube_distributed_min_interval_seconds or 0.0))
    if interval_seconds <= 0:
        return

    redis_client = _get_redis_client(settings)
    if redis_client is None:
        return

    token = uuid4().hex
    acquired = False
    try:
        while not acquired:
            acquired = bool(redis_client.set(_REDIS_THROTTLE_LOCK_KEY, token, nx=True, ex=60))
            if not acquired:
                time.sleep(0.05)

        now = time.time()
        cooldown_until = _coerce_float(redis_client.get(_REDIS_THROTTLE_COOLDOWN_KEY))
        if cooldown_until > now:
            raise YoutubeRequestCooldown(cooldown_until - now)

        next_request_at = _coerce_float(redis_client.get(_REDIS_THROTTLE_NEXT_AT_KEY))
        wait_seconds = next_request_at - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.time()
        redis_client.set(
            _REDIS_THROTTLE_NEXT_AT_KEY,
            str(max(now, next_request_at) + interval_seconds),
            ex=max(60, int(interval_seconds) + 60),
        )
    except YoutubeRequestCooldown:
        raise
    except Exception:  # noqa: BLE001
        return
    finally:
        if acquired:
            _release_redis_lock(redis_client, token)


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


def _import_redis():
    try:
        from redis import Redis
    except Exception:  # noqa: BLE001
        return None
    return Redis


def _get_redis_client(settings: Settings):
    if not settings.redis_url:
        return None
    Redis = _import_redis()
    if Redis is None:
        return None

    with _REDIS_CLIENTS_LOCK:
        client = _REDIS_CLIENTS.get(settings.redis_url)
        if client is None:
            client = Redis.from_url(settings.redis_url)
            _REDIS_CLIENTS[settings.redis_url] = client
        return client


def _release_redis_lock(redis_client, token: str) -> None:  # noqa: ANN001
    try:
        redis_client.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            end
            return 0
            """,
            1,
            _REDIS_THROTTLE_LOCK_KEY,
            token,
        )
    except Exception:  # noqa: BLE001
        return


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _scraperapi_session_number(seed: str) -> int:
    digest = hashlib.sha256(str(seed or "").encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 9_999_999) + 1
