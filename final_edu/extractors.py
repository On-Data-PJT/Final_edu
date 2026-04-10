from __future__ import annotations

import re
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing.
    OpenAI = None
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pypdf import PdfReader
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi

from final_edu.config import Settings, get_settings
from final_edu.models import RawTextSegment, SourceAsset, UploadedAsset
from final_edu.storage import ObjectStorage, create_object_storage
from final_edu.utils import format_seconds, normalize_text
from final_edu.youtube_cache import (
    YOUTUBE_STALE_TRANSCRIPT_WARNING,
    YOUTUBE_STT_BUDGET_EXCEEDED_WARNING,
    YOUTUBE_STT_DISABLED_WARNING,
    YOUTUBE_STT_FALLBACK_WARNING,
    YOUTUBE_STT_FILE_TOO_LARGE_WARNING,
    YoutubeCache,
    build_youtube_scraperapi_http_client,
    is_youtube_request_limited_error,
    is_youtube_stt_fallback_error,
    mark_youtube_request_limited,
    summarize_youtube_fetch_error,
    throttle_youtube_requests,
)

YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([0-9A-Za-z_-]{11})")


def extract_file_asset(
    asset: UploadedAsset,
    instructor_name: str,
) -> tuple[SourceAsset, list[RawTextSegment], list[str]]:
    suffix = asset.path.suffix.lower()
    source = SourceAsset(
        id=uuid.uuid4().hex[:12],
        instructor_name=instructor_name,
        asset_type=suffix.lstrip(".") or "file",
        label=asset.original_name,
        origin=asset.original_name,
    )

    if suffix == ".pdf":
        segments, warnings = _extract_pdf(asset.path, source, instructor_name)
    elif suffix == ".pptx":
        segments, warnings = _extract_pptx(asset.path, source, instructor_name)
    elif suffix == ".csv":
        segments, warnings = _extract_csv_file(asset.path, source, instructor_name)
    elif suffix in {".txt", ".md"}:
        segments, warnings = _extract_text_file(asset.path, source, instructor_name)
    else:
        segments = []
        warnings = [f"{asset.original_name}: 지원하지 않는 파일 형식입니다."]

    source.warnings.extend(warnings)
    return source, segments, warnings


def extract_youtube_asset(
    url: str,
    instructor_name: str,
    settings: Settings | None = None,
    storage: ObjectStorage | None = None,
    allow_stt_fallback: bool = True,
) -> tuple[SourceAsset, list[RawTextSegment], list[str]]:
    settings = settings or get_settings()
    video_id = _extract_video_id(url)
    source = SourceAsset(
        id=uuid.uuid4().hex[:12],
        instructor_name=instructor_name,
        asset_type="youtube",
        label=f"YouTube {video_id or 'unknown'}",
        origin=url,
    )

    if not video_id:
        warning = f"{url}: 올바른 YouTube URL을 인식하지 못했습니다."
        source.warnings.append(warning)
        return source, [], [warning]

    warnings: list[str] = []
    try:
        transcript, fetch_warnings = _fetch_youtube_transcript(video_id, settings, storage=storage)
        warnings.extend(fetch_warnings)
    except Exception as exc:  # noqa: BLE001
        if is_youtube_stt_fallback_error(exc):
            if not allow_stt_fallback:
                warning = (
                    f"{url}: 준비 단계 샘플 자막 확인에서는 공개 자막을 찾지 못했습니다. "
                    "본분석에서는 STT fallback 대상이 될 수 있습니다."
                )
                source.warnings.append(warning)
                return source, [], [warning]
            stt_segments, stt_warnings = _try_youtube_stt_fallback(
                url,
                video_id,
                source,
                instructor_name,
                settings,
                storage=storage,
            )
            if stt_segments:
                source.warnings.extend(stt_warnings)
                return source, stt_segments, stt_warnings
            if stt_warnings:
                source.warnings.extend(stt_warnings)
                return source, [], stt_warnings
        warning = summarize_youtube_fetch_error(url, exc)
        source.warnings.append(warning)
        return source, [], [warning]

    segments: list[RawTextSegment] = []
    for item in transcript:
        text = normalize_text(_transcript_text(item))
        if not text:
            continue
        locator = format_seconds(_transcript_start(item))
        segments.append(
            RawTextSegment(
                source_id=source.id,
                instructor_name=instructor_name,
                source_label=source.label,
                source_type=source.asset_type,
                locator=locator,
                text=text,
            )
        )

    if not segments:
        warnings.append(f"{url}: 자막은 조회됐지만 실제 분석 가능한 텍스트가 없습니다.")

    source.warnings.extend(warnings)

    return source, segments, warnings


def _extract_pdf(
    path: Path,
    source: SourceAsset,
    instructor_name: str,
) -> tuple[list[RawTextSegment], list[str]]:
    warnings: list[str] = []
    reader = PdfReader(str(path))
    segments: list[RawTextSegment] = []
    empty_pages = 0

    for index, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if not text:
            empty_pages += 1
            continue
        segments.append(
            RawTextSegment(
                source_id=source.id,
                instructor_name=instructor_name,
                source_label=source.label,
                source_type=source.asset_type,
                locator=f"p.{index}",
                text=text,
            )
        )

    if empty_pages:
        warnings.append(
            f"{source.label}: 텍스트가 추출되지 않은 페이지 {empty_pages}개를 제외했습니다. "
            "스캔 PDF인 경우 정확도가 떨어질 수 있습니다."
        )
    if not segments:
        warnings.append(
            f"{source.label}: 분석 가능한 텍스트를 찾지 못했습니다. 텍스트형 PDF만 안정적으로 지원합니다."
        )

    return segments, warnings


def _extract_pptx(
    path: Path,
    source: SourceAsset,
    instructor_name: str,
) -> tuple[list[RawTextSegment], list[str]]:
    warnings: list[str] = []
    presentation = Presentation(str(path))
    segments: list[RawTextSegment] = []
    empty_slides = 0

    for index, slide in enumerate(presentation.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            parts.extend(_shape_texts(shape))

        text = normalize_text(" ".join(part for part in parts if part))
        if not text:
            empty_slides += 1
            continue

        segments.append(
            RawTextSegment(
                source_id=source.id,
                instructor_name=instructor_name,
                source_label=source.label,
                source_type=source.asset_type,
                locator=f"s.{index}",
                text=text,
            )
        )

    if empty_slides:
        warnings.append(
            f"{source.label}: 텍스트가 없는 슬라이드 {empty_slides}개를 제외했습니다. "
            "이미지 중심 슬라이드는 반영되지 않을 수 있습니다."
        )
    if not segments:
        warnings.append(f"{source.label}: PPTX에서 분석 가능한 텍스트를 찾지 못했습니다.")

    return segments, warnings


def _extract_text_file(
    path: Path,
    source: SourceAsset,
    instructor_name: str,
) -> tuple[list[RawTextSegment], list[str]]:
    text = normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    if not text:
        warning = f"{source.label}: 텍스트 파일이 비어 있습니다."
        return [], [warning]

    segment = RawTextSegment(
        source_id=source.id,
        instructor_name=instructor_name,
        source_label=source.label,
        source_type="text",
        locator="full",
        text=text,
    )
    return [segment], []


def _extract_csv_file(
    path: Path,
    source: SourceAsset,
    instructor_name: str,
) -> tuple[list[RawTextSegment], list[str]]:
    import csv

    warnings: list[str] = []
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    rows = list(csv.reader(raw_text.splitlines()))
    if not rows:
        return [], [f"{source.label}: CSV 파일이 비어 있습니다."]

    header = rows[0] if rows else []
    data_rows = rows[1:] if len(rows) > 1 else []
    segments: list[RawTextSegment] = []

    for index, row in enumerate(data_rows or rows, start=1):
        row_text = normalize_text(" | ".join(cell for cell in row if cell))
        if not row_text:
            continue
        if header and data_rows:
            pairs = []
            for header_cell, value in zip(header, row):
                clean_header = normalize_text(header_cell)
                clean_value = normalize_text(value)
                if clean_value:
                    label = clean_header or "column"
                    pairs.append(f"{label}: {clean_value}")
            row_text = normalize_text(" | ".join(pairs)) or row_text
        segments.append(
            RawTextSegment(
                source_id=source.id,
                instructor_name=instructor_name,
                source_label=source.label,
                source_type="csv",
                locator=f"row.{index}",
                text=row_text,
            )
        )

    if not segments:
        warnings.append(f"{source.label}: CSV에서 분석 가능한 텍스트를 찾지 못했습니다.")

    return segments, warnings


def _shape_texts(shape) -> list[str]:  # noqa: ANN001
    texts: list[str] = []

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            texts.extend(_shape_texts(child))

    if getattr(shape, "has_text_frame", False):
        text = normalize_text(shape.text or "")
        if text:
            texts.append(text)

    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            for cell in row.cells:
                text = normalize_text(cell.text or "")
                if text:
                    texts.append(text)

    return texts


def _fetch_youtube_transcript(
    video_id: str,
    settings: Settings,
    *,
    storage: ObjectStorage | None = None,
):
    cache = YoutubeCache(settings, storage=storage)
    cached_transcript = cache.get_transcript(video_id=video_id, allow_stale=False)
    if cached_transcript is not None:
        return list(cached_transcript.value or []), []

    stale_transcript = cache.get_transcript(video_id=video_id, allow_stale=True)
    http_client = build_youtube_scraperapi_http_client(settings, session_seed=f"video:{video_id}")
    try:
        throttle_youtube_requests(settings)
        transcript = YouTubeTranscriptApi(http_client=http_client).fetch(
            video_id,
            languages=["ko", "en", "en-US"],
        )
    except Exception as exc:  # noqa: BLE001
        if is_youtube_request_limited_error(exc):
            mark_youtube_request_limited(settings)
        if stale_transcript is not None and is_youtube_request_limited_error(exc):
            warning = f"{_video_url(video_id)}: {YOUTUBE_STALE_TRANSCRIPT_WARNING}"
            return list(stale_transcript.value or []), [warning]
        raise

    serialized = [
        {
            "text": _transcript_text(item),
            "start": _transcript_start(item),
            "duration": _transcript_duration(item),
        }
        for item in transcript
    ]
    cache.put_transcript(video_id=video_id, value=serialized)
    return serialized, []


def _extract_video_id(url: str) -> str | None:
    direct_match = YOUTUBE_ID_RE.search(url)
    if direct_match:
        return direct_match.group(1)

    parsed = urlparse(url)
    if parsed.hostname in {"www.youtube.com", "youtube.com"}:
        return parse_qs(parsed.query).get("v", [None])[0]
    return None


def _transcript_text(item) -> str:  # noqa: ANN001
    if isinstance(item, dict):
        return str(item.get("text", ""))
    return str(getattr(item, "text", ""))


def _transcript_start(item) -> float:  # noqa: ANN001
    if isinstance(item, dict):
        return float(item.get("start", 0.0))
    return float(getattr(item, "start", 0.0))


def _transcript_duration(item) -> float:  # noqa: ANN001
    if isinstance(item, dict):
        return float(item.get("duration", 0.0))
    return float(getattr(item, "duration", 0.0))


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _try_youtube_stt_fallback(
    url: str,
    video_id: str,
    source: SourceAsset,
    instructor_name: str,
    settings: Settings,
    *,
    storage: ObjectStorage | None = None,
) -> tuple[list[RawTextSegment], list[str]]:
    if not settings.youtube_stt_enabled:
        return [], [f"{url}: {YOUTUBE_STT_DISABLED_WARNING}"]
    if OpenAI is None or not settings.openai_api_key:
        return [], [f"{url}: STT fallback에 필요한 OpenAI 설정이 없습니다."]

    active_storage = storage or create_object_storage(settings)
    duration_seconds = _lookup_cached_youtube_duration(url, video_id, settings, active_storage)
    if _stt_budget_exceeded(duration_seconds, settings, active_storage):
        return [], [f"{url}: {YOUTUBE_STT_BUDGET_EXCEEDED_WARNING}"]

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path, downloaded_duration_seconds = _download_youtube_audio_for_stt(
                url,
                settings,
                destination_dir=Path(temp_dir),
            )
            if not audio_path.exists():
                return [], [f"{url}: STT fallback용 오디오를 저장하지 못했습니다."]
            if audio_path.stat().st_size > settings.youtube_stt_max_file_bytes:
                size_mb = audio_path.stat().st_size / (1024 * 1024)
                return [], [f"{url}: {YOUTUBE_STT_FILE_TOO_LARGE_WARNING} ({size_mb:.1f}MB)"]

            transcript_text = _transcribe_audio_path(audio_path, settings)
    except Exception as exc:  # noqa: BLE001
        return [], [f"{url}: STT fallback에 실패했습니다. ({type(exc).__name__}: {exc})"]

    normalized_text = normalize_text(transcript_text)
    if not normalized_text:
        return [], [f"{url}: STT fallback 결과에서 분석 가능한 텍스트를 찾지 못했습니다."]

    effective_duration_seconds = max(duration_seconds, downloaded_duration_seconds)
    if effective_duration_seconds > 0:
        _record_stt_usage(effective_duration_seconds, settings, active_storage)

    return [
        RawTextSegment(
            source_id=source.id,
            instructor_name=instructor_name,
            source_label=source.label,
            source_type=source.asset_type,
            locator="stt",
            text=normalized_text,
        )
    ], [f"{url}: {YOUTUBE_STT_FALLBACK_WARNING}"]


def _download_youtube_audio_for_stt(
    url: str,
    _settings: Settings,
    *,
    destination_dir: Path,
) -> tuple[Path, int]:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio[ext=webm]/bestaudio[ext=mp3]/bestaudio",
        "outtmpl": str(destination_dir / "%(id)s.%(ext)s"),
        "restrictfilenames": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = _resolve_downloaded_media_path(info, destination_dir)
            duration_seconds = int((info or {}).get("duration") or 0)
            return path, duration_seconds
    except Exception as exc:  # noqa: BLE001
        raise


def _resolve_downloaded_media_path(info: dict | None, destination_dir: Path) -> Path:
    payload = info or {}
    for item in payload.get("requested_downloads") or []:
        filepath = str(item.get("filepath") or item.get("_filename") or "").strip()
        if filepath:
            path = Path(filepath)
            if path.exists():
                return path

    file_candidates = sorted(destination_dir.glob("*"))
    if file_candidates:
        return file_candidates[0]
    raise RuntimeError("yt-dlp가 오디오 파일 경로를 반환하지 않았습니다.")


def _transcribe_audio_path(audio_path: Path, settings: Settings) -> str:
    client = OpenAI(api_key=settings.openai_api_key)
    with audio_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            file=audio_file,
            model=settings.youtube_stt_model,
            response_format="text",
        )
    return str(response or "")


def _lookup_cached_youtube_duration(
    url: str,
    video_id: str,
    settings: Settings,
    storage: ObjectStorage,
) -> int:
    cache = YoutubeCache(settings, storage=storage)
    for candidate_url in (url, _video_url(video_id)):
        cached = cache.get_metadata(
            url=candidate_url,
            max_videos=1,
            treat_as_playlist=False,
            allow_stale=True,
        )
        if cached is None:
            continue
        try:
            return int((cached.value or {}).get("duration") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
    return 0


def _stt_budget_exceeded(duration_seconds: int, settings: Settings, storage: ObjectStorage) -> bool:
    budget_minutes = max(0, int(settings.youtube_stt_monthly_minutes_budget or 0))
    if budget_minutes <= 0 or duration_seconds <= 0:
        return False
    payload = _load_stt_usage(storage)
    used_minutes = float(payload.get("used_minutes", 0.0) or 0.0)
    requested_minutes = duration_seconds / 60.0
    return (used_minutes + requested_minutes) > budget_minutes


def _record_stt_usage(duration_seconds: int, settings: Settings, storage: ObjectStorage) -> None:
    budget_minutes = max(0, int(settings.youtube_stt_monthly_minutes_budget or 0))
    if budget_minutes <= 0 or duration_seconds <= 0:
        return
    payload = _load_stt_usage(storage)
    payload["used_minutes"] = round(float(payload.get("used_minutes", 0.0) or 0.0) + (duration_seconds / 60.0), 4)
    storage.put_json(_stt_usage_key(), payload)


def _load_stt_usage(storage: ObjectStorage) -> dict:
    try:
        payload = storage.get_json(_stt_usage_key())
    except Exception:  # noqa: BLE001
        return {"month": _stt_usage_month(), "used_minutes": 0.0}
    if payload.get("month") != _stt_usage_month():
        return {"month": _stt_usage_month(), "used_minutes": 0.0}
    return payload


def _stt_usage_key() -> str:
    return f"youtube-usage/stt/{_stt_usage_month()}.json"


def _stt_usage_month() -> str:
    return time.strftime("%Y-%m")
