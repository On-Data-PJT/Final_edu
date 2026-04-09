from __future__ import annotations

import math
import time
from dataclasses import dataclass
from itertools import islice
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from final_edu.config import Settings
from final_edu.extractors import extract_youtube_asset
from final_edu.utils import count_tokens

YOUTUBE_HOSTS = {
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
}


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


def resolve_youtube_input(url: str, *, max_videos: int) -> ResolvedYoutubeInput:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("빈 YouTube URL입니다.")

    ydl_options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "lazy_playlist": False,
        "noplaylist": False,
        "playlistend": max_videos + 1,
    }
    with YoutubeDL(ydl_options) as ydl:
        info = ydl.extract_info(normalized_url, download=False)

    if info is None:
        raise ValueError(f"{normalized_url}: YouTube 정보를 읽지 못했습니다.")

    entries = list(islice(info.get("entries") or [], max_videos + 1))
    if entries:
        total_count = int(info.get("playlist_count") or len(entries))
        if total_count > max_videos or len(entries) > max_videos:
            raise ValueError(
                f"{normalized_url}: 재생목록 영상 수가 현재 지원 상한 {max_videos}개를 초과합니다."
            )
        videos = [_normalize_video_entry(entry) for entry in entries]
        return ResolvedYoutubeInput(
            input_url=normalized_url,
            kind="playlist",
            title=str(info.get("title") or "YouTube Playlist"),
            source_id=str(info.get("id") or ""),
            videos=[video for video in videos if video.video_id],
            total_video_count=total_count,
        )

    video = _normalize_video_entry(info)
    if not video.video_id:
        raise ValueError(f"{normalized_url}: 올바른 YouTube 영상 ID를 찾지 못했습니다.")
    return ResolvedYoutubeInput(
        input_url=normalized_url,
        kind="video",
        title=video.title,
        source_id=video.video_id,
        videos=[video],
        total_video_count=1,
    )


def summarize_youtube_inputs(
    raw_urls: list[str],
    *,
    settings: Settings,
    instructor_count: int,
    section_count: int,
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
        resolved = resolve_youtube_input(normalized_url, max_videos=settings.playlist_hard_limit)
        resolved_inputs.append(resolved)
        has_playlist = has_playlist or resolved.is_playlist
        expanded_urls.extend(video.url for video in resolved.videos if video.url)

    expanded_video_count = len(expanded_urls)
    total_duration_seconds = sum(item.total_duration_seconds for item in resolved_inputs)
    probe = probe_transcript_samples(
        resolved_inputs,
        sample_size=settings.playlist_probe_sample_size,
    )
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


def probe_transcript_samples(resolved_inputs: list[ResolvedYoutubeInput], *, sample_size: int) -> dict:
    videos = [video for item in resolved_inputs for video in item.videos]
    sampled_videos = _sample_videos(videos, sample_size)
    success_count = 0
    successful_token_total = 0
    successful_duration_total = 0
    fetch_times: list[float] = []

    for video in sampled_videos:
        started = time.perf_counter()
        _source, segments, _warnings = extract_youtube_asset(video.url, "__probe__")
        fetch_times.append(max(0.0, time.perf_counter() - started))
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
    if sample_size <= 0 or len(videos) <= sample_size:
        return videos
    picked: list[ResolvedYoutubeVideo] = []
    for offset in range(sample_size):
        index = round(offset * (len(videos) - 1) / max(1, sample_size - 1))
        picked.append(videos[index])
    unique: dict[str, ResolvedYoutubeVideo] = {}
    for video in picked:
        unique[video.video_id] = video
    return list(unique.values())
