from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from final_edu.models import ExtractedChunk, RawTextSegment

WORD_RE = re.compile(r"[0-9A-Za-z가-힣_]+")
WHITESPACE_RE = re.compile(r"\s+")
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
