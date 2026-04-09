from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pypdf import PdfReader
from youtube_transcript_api import YouTubeTranscriptApi

from final_edu.config import Settings, get_settings
from final_edu.models import RawTextSegment, SourceAsset, UploadedAsset
from final_edu.storage import ObjectStorage
from final_edu.utils import format_seconds, normalize_text
from final_edu.youtube_cache import (
    YOUTUBE_STALE_TRANSCRIPT_WARNING,
    YoutubeCache,
    is_youtube_request_limited_error,
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
    try:
        throttle_youtube_requests(settings)
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["ko", "en", "en-US"])
    except Exception as exc:  # noqa: BLE001
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
