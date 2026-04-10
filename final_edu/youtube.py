from __future__ import annotations

import math
import time
from dataclasses import dataclass
from itertools import islice
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL

from final_edu.config import Settings, get_settings
from final_edu.extractors import extract_youtube_asset
from final_edu.storage import ObjectStorage
from final_edu.utils import count_tokens
from final_edu.youtube_cache import (
    YoutubeCache,
    is_youtube_request_limited_error,
    mark_youtube_request_limited,
    throttle_youtube_requests,
)

YOUTUBE_HOSTS = {
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
}

YOUTUBE_METADATA_SOCKET_TIMEOUT_SECONDS = 15


@dataclass(slots=True)
class ResolvedYoutubeVideo:
    video_id: str
    title: str
    url: str
    duration_seconds: int = 0

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "url": self.url,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(slots=True)
class ResolvedYoutubeInput:
    input_url: str
    kind: str
    title: str
    source_id: str
    videos: list[ResolvedYoutubeVideo]
    total_video_count: int

    @property
    def is_playlist(self) -> bool:
        return self.kind == "playlist"

    @property
    def total_duration_seconds(self) -> int:
        return sum(max(0, int(video.duration_seconds or 0)) for video in self.videos)

    def to_summary_dict(self) -> dict:
        return {
            "input_url": self.input_url,
            "kind": self.kind,
            "title": self.title,
            "source_id": self.source_id,
            "video_count": self.total_video_count,
            "expanded_video_count": len(self.videos),
            "total_duration_seconds": self.total_duration_seconds,
        }


def is_youtube_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    return host in YOUTUBE_HOSTS


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def is_explicit_playlist_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return False

    path = (parsed.path or "").strip("/")
    query = parse_qs(parsed.query or "")
    has_video_selector = bool(query.get("v")) or host == "youtu.be" or path.startswith("shorts/") or path.startswith("live/") or path.startswith("embed/")
    if has_video_selector:
        return False
    return path == "playlist" and bool(query.get("list"))


def resolve_youtube_input(url: str, *, max_videos: int) -> ResolvedYoutubeInput:
    return _resolve_youtube_input_with_settings(url, max_videos=max_videos, settings=None)


def summarize_youtube_inputs(
    raw_urls: list[str],
    *,
    settings: Settings,
    instructor_count: int,
    section_count: int,
    storage: ObjectStorage | None = None,
) -> dict:
    resolved_inputs: list[ResolvedYoutubeInput] = []
    warnings: list[str] = []
    expanded_urls: list[str] = []
    has_playlist = False

    for raw_url in raw_urls:
        normalized_url = str(raw_url or "").strip()
        if not normalized_url:
            continue
        if not is_youtube_url(normalized_url):
            warnings.append(f"{normalized_url}: YouTube URL 형식이 아니어서 분석 시 실패할 수 있습니다.")
            continue
        resolved = _resolve_youtube_input_with_settings(
            normalized_url,
            max_videos=settings.playlist_hard_limit,
            settings=settings,
            storage=storage,
        )
        resolved_inputs.append(resolved)
        has_playlist = has_playlist or resolved.is_playlist
        expanded_urls.extend(video.url for video in resolved.videos if video.url)

    expanded_video_count = len(expanded_urls)
    total_duration_seconds = sum(item.total_duration_seconds for item in resolved_inputs)
    probe_sample_size, probe_policy_warnings = _resolve_probe_sample_size(
        expanded_video_count=expanded_video_count,
        settings=settings,
    )
    probe = probe_transcript_samples(
        resolved_inputs,
        sample_size=probe_sample_size,
        settings=settings,
        storage=storage,
    )
    warnings.extend(probe_policy_warnings)
    warnings.extend(probe["warnings"])
    warnings = _dedupe_strings(warnings)
    estimated_tokens = _estimate_transcript_tokens(probe, total_duration_seconds, expanded_video_count)
    estimated_chunks = int(math.ceil(estimated_tokens / max(1, settings.chunk_target_tokens))) if estimated_tokens else 0
    recommended_mode = recommend_analysis_mode(
        settings=settings,
        expanded_video_count=expanded_video_count,
        estimated_chunk_count=estimated_chunks,
        estimated_transcript_tokens=estimated_tokens,
    )
    estimated_processing_seconds = estimate_processing_seconds(
        expanded_video_count=expanded_video_count,
        estimated_chunk_count=estimated_chunks,
        average_fetch_seconds=probe["average_fetch_seconds"],
        fetch_concurrency=settings.youtube_fetch_concurrency,
    )
    estimated_cost = estimate_openai_cost_usd(
        settings=settings,
        analysis_mode=recommended_mode,
        transcript_tokens=estimated_tokens,
        instructor_count=instructor_count,
        section_count=section_count,
    )

    return {
        "resolved_inputs": resolved_inputs,
        "playlist_summaries": [item.to_summary_dict() for item in resolved_inputs if item.is_playlist],
        "warnings": warnings,
        "expanded_urls": expanded_urls,
        "has_playlist": has_playlist,
        "expanded_video_count": expanded_video_count,
        "total_duration_seconds": total_duration_seconds,
        "caption_probe_sample_count": probe["sample_count"],
        "caption_probe_success_count": probe["success_count"],
        "estimated_transcript_tokens": estimated_tokens,
        "estimated_chunk_count": estimated_chunks,
        "recommended_analysis_mode": recommended_mode,
        "estimated_processing_seconds": estimated_processing_seconds,
        "estimated_cost_usd": estimated_cost,
    }


def recommend_analysis_mode(
    *,
    settings: Settings,
    expanded_video_count: int,
    estimated_chunk_count: int,
    estimated_transcript_tokens: int,
) -> str:
    if not settings.openai_api_key:
        return "lexical"
    if expanded_video_count > settings.small_youtube_video_threshold:
        return "lexical"
    if estimated_chunk_count > settings.small_youtube_chunk_threshold:
        return "lexical"
    if estimated_transcript_tokens > settings.small_youtube_token_threshold:
        return "lexical"
    return "openai"


def estimate_processing_seconds(
    *,
    expanded_video_count: int,
    estimated_chunk_count: int,
    average_fetch_seconds: float,
    fetch_concurrency: int,
) -> int:
    if expanded_video_count <= 0:
        return 0
    fetch_seconds = average_fetch_seconds * expanded_video_count / max(1, fetch_concurrency)
    assign_seconds = estimated_chunk_count * 0.03
    return int(math.ceil(fetch_seconds + assign_seconds + 20))


def estimate_openai_cost_usd(
    *,
    settings: Settings,
    analysis_mode: str,
    transcript_tokens: int,
    instructor_count: int,
    section_count: int,
) -> float:
    if analysis_mode != "openai" or transcript_tokens <= 0:
        return 0.0
    embeddings_cost = (
        transcript_tokens / 1_000_000
    ) * settings.openai_embedding_rate_per_million_input_tokens
    estimated_insight_input_tokens = max(3000, 900 * max(1, instructor_count) + 450 * max(1, section_count))
    estimated_insight_output_tokens = 1200
    insights_cost = (
        (estimated_insight_input_tokens / 1_000_000) * settings.openai_insight_input_rate_per_million_tokens
        + (estimated_insight_output_tokens / 1_000_000) * settings.openai_insight_output_rate_per_million_tokens
    )
    return round(embeddings_cost + insights_cost, 4)


def probe_transcript_samples(
    resolved_inputs: list[ResolvedYoutubeInput],
    *,
    sample_size: int,
    settings: Settings,
    storage: ObjectStorage | None = None,
) -> dict:
    videos = [video for item in resolved_inputs for video in item.videos]
    sampled_videos = _sample_videos(videos, sample_size)
    success_count = 0
    successful_token_total = 0
    successful_duration_total = 0
    fetch_times: list[float] = []
    warnings: list[str] = []

    for video in sampled_videos:
        started = time.perf_counter()
        _source, segments, sample_warnings = extract_youtube_asset(
            video.url,
            "__probe__",
            settings=settings,
            storage=storage,
            allow_stt_fallback=False,
        )
        fetch_times.append(max(0.0, time.perf_counter() - started))
        warnings.extend(sample_warnings)
        if not segments:
            continue
        success_count += 1
        successful_token_total += sum(count_tokens(segment.text) for segment in segments)
        successful_duration_total += max(0, int(video.duration_seconds or 0))

    average_tokens_per_second = 0.0
    if success_count and successful_token_total > 0:
        if successful_duration_total > 0:
            average_tokens_per_second = successful_token_total / successful_duration_total
        else:
            average_tokens_per_second = successful_token_total / success_count / 3600

    average_fetch_seconds = (
        sum(fetch_times) / len(fetch_times)
        if fetch_times else 1.2
    )
    return {
        "sample_count": len(sampled_videos),
        "success_count": success_count,
        "average_tokens_per_second": average_tokens_per_second,
        "average_fetch_seconds": average_fetch_seconds,
        "warnings": _dedupe_strings(warnings),
    }


def _estimate_transcript_tokens(probe: dict, total_duration_seconds: int, expanded_video_count: int) -> int:
    if expanded_video_count <= 0:
        return 0
    average_tokens_per_second = float(probe.get("average_tokens_per_second", 0.0) or 0.0)
    if average_tokens_per_second > 0 and total_duration_seconds > 0:
        return int(math.ceil(total_duration_seconds * average_tokens_per_second))
    if int(probe.get("success_count", 0)) > 0:
        average_tokens_per_video = 6500
        return int(math.ceil(expanded_video_count * average_tokens_per_video))
    return 0


def _normalize_video_entry(entry: dict | None) -> ResolvedYoutubeVideo:
    payload = entry or {}
    video_id = str(payload.get("id") or payload.get("url") or "").strip()
    title = str(payload.get("title") or payload.get("alt_title") or video_id or "YouTube Video").strip()
    duration_seconds = int(payload.get("duration") or payload.get("duration_seconds") or 0)
    if video_id.startswith("http"):
        parsed = urlparse(video_id)
        if parsed.hostname in YOUTUBE_HOSTS and parsed.path.strip("/"):
            video_id = parsed.path.strip("/").split("/")[-1]
    url = canonical_youtube_url(video_id) if video_id else ""
    return ResolvedYoutubeVideo(
        video_id=video_id,
        title=title,
        url=url,
        duration_seconds=duration_seconds,
    )


def _sample_videos(videos: list[ResolvedYoutubeVideo], sample_size: int) -> list[ResolvedYoutubeVideo]:
    if sample_size <= 0:
        return []
    if len(videos) <= sample_size:
        return videos
    picked: list[ResolvedYoutubeVideo] = []
    for offset in range(sample_size):
        index = round(offset * (len(videos) - 1) / max(1, sample_size - 1))
        picked.append(videos[index])
    unique: dict[str, ResolvedYoutubeVideo] = {}
    for video in picked:
        unique[video.video_id] = video
    return list(unique.values())


def _resolve_youtube_input_with_settings(
    url: str,
    *,
    max_videos: int,
    settings: Settings | None,
    storage: ObjectStorage | None = None,
) -> ResolvedYoutubeInput:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("빈 YouTube URL입니다.")

    active_settings = settings or get_settings()
    treat_as_playlist = is_explicit_playlist_url(normalized_url)
    try:
        info = _extract_youtube_info(
            normalized_url,
            max_videos=max_videos,
            treat_as_playlist=treat_as_playlist,
            settings=active_settings,
            storage=storage,
        )
    except Exception as exc:  # noqa: BLE001
        if not treat_as_playlist:
            fallback = _build_single_video_fallback(normalized_url)
            if fallback is not None:
                return fallback
        raise ValueError(_summarize_youtube_metadata_error(normalized_url, exc, treat_as_playlist=treat_as_playlist)) from exc

    entries = list(islice(info.get("entries") or [], max_videos + 1))
    if entries:
        total_count = int(info.get("playlist_count") or len(entries))
        if total_count > max_videos or len(entries) > max_videos:
            raise ValueError(
                f"{normalized_url}: 재생목록 영상 수가 현재 지원 상한 {max_videos}개를 초과합니다."
            )
        videos = [video for video in (_normalize_video_entry(entry) for entry in entries) if video.video_id]
        _seed_single_video_metadata_cache(videos=videos, settings=active_settings, storage=storage)
        return ResolvedYoutubeInput(
            input_url=normalized_url,
            kind="playlist",
            title=str(info.get("title") or "YouTube Playlist"),
            source_id=str(info.get("id") or ""),
            videos=videos,
            total_video_count=total_count,
        )

    video = _normalize_video_entry(info)
    if not video.video_id:
        raise ValueError(f"{normalized_url}: 올바른 YouTube 영상 ID를 찾지 못했습니다.")
    _seed_single_video_metadata_cache(videos=[video], settings=active_settings, storage=storage)
    return ResolvedYoutubeInput(
        input_url=normalized_url,
        kind="video",
        title=video.title,
        source_id=video.video_id,
        videos=[video],
        total_video_count=1,
    )


def _extract_youtube_info(
    url: str,
    *,
    max_videos: int,
    treat_as_playlist: bool,
    settings: Settings | None,
    storage: ObjectStorage | None = None,
) -> dict:
    active_settings = settings or get_settings()
    cache = YoutubeCache(active_settings, storage=storage)
    cached_info = cache.get_metadata(
        url=url,
        max_videos=max_videos,
        treat_as_playlist=treat_as_playlist,
        allow_stale=False,
    )
    if cached_info is not None:
        return dict(cached_info.value or {})

    stale_info = cache.get_metadata(
        url=url,
        max_videos=max_videos,
        treat_as_playlist=treat_as_playlist,
        allow_stale=True,
    )
    ydl_options = _build_ydl_options(
        url=url,
        max_videos=max_videos,
        treat_as_playlist=treat_as_playlist,
        settings=active_settings,
    )
    try:
        throttle_youtube_requests(active_settings)
        with YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
    except Exception as exc:  # noqa: BLE001
        if is_youtube_request_limited_error(exc):
            mark_youtube_request_limited(active_settings)
        if stale_info is not None and is_youtube_request_limited_error(exc):
            return dict(stale_info.value or {})
        raise

    if info is None:
        raise ValueError(f"{url}: YouTube 정보를 읽지 못했습니다.")
    serialized = _serialize_info_for_cache(info)
    cache.put_metadata(
        url=url,
        max_videos=max_videos,
        treat_as_playlist=treat_as_playlist,
        value=serialized,
    )
    return serialized


def _build_ydl_options(*, url: str, max_videos: int, treat_as_playlist: bool, settings: Settings) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": not treat_as_playlist,
        "ignoreconfig": True,
        "socket_timeout": YOUTUBE_METADATA_SOCKET_TIMEOUT_SECONDS,
    }
    if treat_as_playlist:
        options.update(
            {
                "extract_flat": "in_playlist",
                "lazy_playlist": False,
                "playlistend": max_videos + 1,
            }
        )
    return options


def _build_single_video_fallback(url: str) -> ResolvedYoutubeInput | None:
    video_id = _extract_video_id_from_url(url)
    if not video_id:
        return None
    video = ResolvedYoutubeVideo(
        video_id=video_id,
        title=f"YouTube Video ({video_id})",
        url=canonical_youtube_url(video_id),
        duration_seconds=0,
    )
    return ResolvedYoutubeInput(
        input_url=url,
        kind="video",
        title=video.title,
        source_id=video_id,
        videos=[video],
        total_video_count=1,
    )


def _extract_video_id_from_url(url: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query or "")

    video_id = (query.get("v") or [None])[0]
    if video_id:
        return str(video_id).strip() or None

    path = (parsed.path or "").strip("/")
    if host == "youtu.be" and path:
        return path.split("/", maxsplit=1)[0]
    for prefix in ("shorts/", "live/", "embed/"):
        if path.startswith(prefix):
            remainder = path[len(prefix):].strip("/")
            if remainder:
                return remainder.split("/", maxsplit=1)[0]
    return None


def _summarize_youtube_metadata_error(url: str, exc: Exception, *, treat_as_playlist: bool) -> str:
    compact_reason = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    if treat_as_playlist:
        return (
            f"{url}: YouTube 재생목록 메타데이터를 읽지 못했습니다. 잠시 후 다시 시도하거나 "
            f"단일 영상 URL로 나눠서 제출해 주세요. ({compact_reason})"
        )
    return (
        f"{url}: YouTube 메타데이터를 읽지 못했고 URL에서 단일 영상 정보를 복구하지 못했습니다. "
        f"({compact_reason})"
    )


def _serialize_info_for_cache(info: dict | None) -> dict:
    payload = info or {}
    entries = payload.get("entries") or []
    if entries:
        return {
            "id": str(payload.get("id") or ""),
            "title": str(payload.get("title") or "YouTube Playlist"),
            "playlist_count": int(payload.get("playlist_count") or len(entries)),
            "entries": [
                {
                    "id": str((entry or {}).get("id") or (entry or {}).get("url") or ""),
                    "title": str((entry or {}).get("title") or ""),
                    "duration": int((entry or {}).get("duration") or 0),
                }
                for entry in entries
            ],
        }
    return {
        "id": str(payload.get("id") or payload.get("url") or ""),
        "title": str(payload.get("title") or payload.get("alt_title") or "YouTube Video"),
        "duration": int(payload.get("duration") or payload.get("duration_seconds") or 0),
    }


def _resolve_probe_sample_size(*, expanded_video_count: int, settings: Settings) -> tuple[int, list[str]]:
    if expanded_video_count <= 0:
        return 0, []
    if expanded_video_count > settings.playlist_probe_disable_threshold:
        return 0, [
            (
                "대용량 재생목록이라 준비 단계의 샘플 자막 확인을 생략했습니다. "
                "실분석은 worker 에서 계속 진행됩니다."
            )
        ]
    if expanded_video_count > settings.playlist_probe_full_threshold:
        return settings.playlist_probe_partial_sample_size, [
            (
                "재생목록 규모가 커서 준비 단계의 샘플 자막 확인을 일부 영상으로 축소했습니다."
            )
        ]
    return settings.playlist_probe_sample_size, []


def _seed_single_video_metadata_cache(
    *,
    videos: list[ResolvedYoutubeVideo],
    settings: Settings,
    storage: ObjectStorage | None = None,
) -> None:
    if not videos:
        return
    cache = YoutubeCache(settings, storage=storage)
    for video in videos:
        if not video.url or not video.video_id:
            continue
        cache.put_metadata(
            url=video.url,
            max_videos=1,
            treat_as_playlist=False,
            value={
                "id": video.video_id,
                "title": video.title,
                "duration": int(video.duration_seconds or 0),
            },
        )


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value or "").strip()))
