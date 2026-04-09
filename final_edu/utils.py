from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path

from final_edu.models import ExtractedChunk, RawTextSegment

WORD_RE = re.compile(r"[0-9A-Za-z가-힣_]+")
WHITESPACE_RE = re.compile(r"\s+")
SAFE_FILENAME_RE = re.compile(r"[^0-9A-Za-z._-]+")
SAFE_EXTENSION_RE = re.compile(r"\.[a-z0-9]{1,16}")
STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "of",
    "is",
    "are",
    "this",
    "that",
    "with",
    "in",
    "on",
    "as",
    "by",
    "from",
    "수업",
    "강의",
    "설명",
    "내용",
    "대한",
    "그리고",
    "에서",
    "합니다",
    "있는",
    "하는",
    "하기",
    "자료",
    "이해했나요",
    "여러분",
    "우리",
    "같이",
    "그러면",
    "해서",
    "이렇게",
    "저렇게",
    "어떻게",
    "이런",
    "저런",
    "그런",
    "그럼",
    "그래서",
    "근데",
    "하지만",
    "이제",
    "일단",
    "조금",
    "많이",
    "아직",
    "다시",
    "계속",
    "여기",
    "저기",
    "거기",
    "지금",
    "오늘",
    "내일",
    "시간",
    "경우",
    "문제",
    "질문",
    "답변",
    "학생",
    "선생님",
    "교수",
    "때문",
    "관련",
    "부분",
    "정도",
    "확인",
    "진행",
    "어떤",
    "우리가",
    "제가",
    "여러분이",
    "이게",
    "저게",
    "그게",
    "이거",
    "저거",
    "그거",
    "여기서",
    "저기서",
    "거기서",
    "여러분들",
    "거예요",
    "겁니다",
    "거죠",
    "거야",
    "입니다",
    "있습니다",
    "없습니다",
    "같아요",
    "같습니다",
    "그러니까",
    "또한",
    "왜냐하면",
    "사실",
    "만약",
    "자세히",
    "간단히",
    "다들",
    "아마",
    "혹시",
    "대부분",
    "보통",
    "기본",
    "이해",
    "알겠나요",
    "넘어갈게요",
    "봅시다",
    "보겠습니다",
    "해볼게요",
    "할게요",
    "하겠습니다",
    "물론",
    "아주",
    "매우",
    "가장",
    "일반",
    "아니면",
    "그다음에",
    "다음에",
    "나중에",
    "먼저",
    "보시면",
    "여러분들이",
    "거의",
    "어떤가요",
    "어떠신가요",
}


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in WORD_RE.findall(text)]
    return [token for token in tokens if token not in STOP_WORDS and len(token) > 1]


def count_tokens(text: str) -> int:
    tokens = tokenize(text)
    return max(1, len(tokens))


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "-", value.strip().lower())
    return cleaned.strip("-") or "section"


def build_safe_storage_name(
    original_name: str,
    *,
    default_stem: str,
    default_ext: str = "",
    max_basename_chars: int = 80,
) -> str:
    raw_name = Path(str(original_name or "")).name
    raw_stem = Path(raw_name).stem
    raw_ext = Path(raw_name).suffix.lower()

    default_stem_clean = SAFE_FILENAME_RE.sub("-", str(default_stem or "file").strip().lower()).strip("._-") or "file"
    stem = SAFE_FILENAME_RE.sub("-", raw_stem.strip().lower()).strip("._-") or default_stem_clean
    stem = re.sub(r"-{2,}", "-", stem)

    ext_candidate = raw_ext if SAFE_EXTENSION_RE.fullmatch(raw_ext) else ""
    if not ext_candidate and default_ext:
        normalized_default_ext = str(default_ext).lower()
        if not normalized_default_ext.startswith("."):
            normalized_default_ext = f".{normalized_default_ext}"
        if SAFE_EXTENSION_RE.fullmatch(normalized_default_ext):
            ext_candidate = normalized_default_ext

    hash_source = raw_name or f"{default_stem_clean}{ext_candidate}"
    digest = hashlib.sha1(hash_source.encode("utf-8")).hexdigest()[:10]
    suffix = f"-{digest}{ext_candidate}"
    available_chars = max(8, max_basename_chars - len(suffix))
    bounded_stem = stem[:available_chars].rstrip("._-") or default_stem_clean
    return f"{bounded_stem}{suffix}"


def fingerprint_text(text: str) -> str:
    normalized = normalize_text(text).lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def safe_snippet(text: str, limit: int = 220) -> str:
    cleaned = normalize_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}…"


def format_seconds(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_chunks(
    segments: list[RawTextSegment],
    target_tokens: int,
    overlap_segments: int,
) -> list[ExtractedChunk]:
    if not segments:
        return []

    chunks: list[ExtractedChunk] = []
    current: list[RawTextSegment] = []
    current_tokens = 0

    for segment in segments:
        segment_tokens = count_tokens(segment.text)
        if current and current_tokens + segment_tokens > target_tokens:
            chunks.append(_chunk_from_segments(current))
            if overlap_segments > 0:
                current = current[-overlap_segments:].copy()
                current_tokens = sum(count_tokens(item.text) for item in current)
            else:
                current = []
                current_tokens = 0
        current.append(segment)
        current_tokens += segment_tokens

    if current:
        chunks.append(_chunk_from_segments(current))

    return chunks


def _chunk_from_segments(segments: list[RawTextSegment]) -> ExtractedChunk:
    first = segments[0]
    last = segments[-1]
    text = normalize_text(" ".join(segment.text for segment in segments))
    locator = first.locator if first.locator == last.locator else f"{first.locator} -> {last.locator}"
    return ExtractedChunk(
        id=f"{first.source_id}-{fingerprint_text(locator + text)[:10]}",
        source_id=first.source_id,
        instructor_name=first.instructor_name,
        source_label=first.source_label,
        source_type=first.source_type,
        locator=locator,
        text=text,
        token_count=count_tokens(text),
        fingerprint=fingerprint_text(text),
    )
