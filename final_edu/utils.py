from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path

from kiwipiepy import Kiwi

from final_edu.models import ExtractedChunk, RawTextSegment

WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?。！？])\s+")
SAFE_FILENAME_RE = re.compile(r"[^0-9A-Za-z._-]+")
SAFE_EXTENSION_RE = re.compile(r"\.[a-z0-9]{1,16}")
KIWI_USER_TERM_RE = re.compile(r"[^A-Za-z가-힣]+")
KIWI_VALID_TAGS = {"NNG", "NNP", "SL", "SN"}
MATERIAL_SOURCE_TYPES = {"pdf", "pptx", "text"}
MATERIAL_SEMANTIC_SPLIT_RE = re.compile(
    r"(?=(?:■|□|▪|▫|▷|▶|◆|◇|Q\d+\s*[.:]|(?:\d+\s*주차)|(?:주차\s*\d+)|(?:chapter\s*\d+)|(?:part\s*\d+)))",
    re.IGNORECASE,
)
MATERIAL_QUESTION_RE = re.compile(r"(?:^|\s)Q\d+\s*[.:]", re.IGNORECASE)
MATERIAL_ANSWER_RE = re.compile(r"(?:답\s*[:：]|정답)")
MATERIAL_PLACEHOLDER_RE = re.compile(r"[_＿]{3,}")
MATERIAL_SUBCHUNK_MAX_TOKENS = 36
MATERIAL_NOISE_PHRASES = (
    "확인 문제",
    "빈칸 채우기",
    "필기 공간",
    "자유 메모",
    "check point",
    "checkpoint",
)
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
_KIWI: Kiwi | None = None
_REGISTERED_KIWI_TERMS: set[str] = set()


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def _get_kiwi() -> Kiwi:
    global _KIWI
    if _KIWI is None:
        _KIWI = Kiwi(num_workers=1)
    return _KIWI


def _append_chunk_token(tokens: list[str], current_chunk: list[str]) -> None:
    if not current_chunk:
        return
    chunk = "".join(current_chunk).strip()
    current_chunk.clear()
    if len(chunk) <= 1:
        return
    lowered = chunk.lower()
    if lowered not in STOP_WORDS:
        tokens.append(lowered)


def _token_span_length(token) -> int:
    token_len = getattr(token, "len", None)
    if isinstance(token_len, int) and token_len > 0:
        return token_len
    return len(str(getattr(token, "form", "")))


def build_custom_dictionary(titles: list[str]) -> None:
    kiwi = _get_kiwi()
    for title in titles:
        clean_title = KIWI_USER_TERM_RE.sub(" ", str(title or "")).strip()
        if not clean_title:
            continue
        for term in clean_title.split():
            if len(term) < 2:
                continue
            term_key = term.lower()
            if term_key in _REGISTERED_KIWI_TERMS:
                continue
            kiwi.add_user_word(term, "NNP", 10.0)
            _REGISTERED_KIWI_TERMS.add(term_key)


def tokenize(text: str) -> list[str]:
    kiwi = _get_kiwi()
    clean_text = re.sub(r"([A-Za-z가-힣])-([0-9])", r"\1\2", str(text or ""))
    tokens: list[str] = []
    current_chunk: list[str] = []
    previous_end = 0

    for token in kiwi.tokenize(clean_text):
        token_start = getattr(token, "start", previous_end)
        if not isinstance(token_start, int):
            token_start = previous_end
        if current_chunk and token_start > previous_end:
            _append_chunk_token(tokens, current_chunk)

        if getattr(token, "tag", "") in KIWI_VALID_TAGS:
            current_chunk.append(str(getattr(token, "form", "")))
        else:
            _append_chunk_token(tokens, current_chunk)

        previous_end = token_start + _token_span_length(token)

    _append_chunk_token(tokens, current_chunk)
    return tokens


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


def build_preserved_segment_chunks(
    segments: list[RawTextSegment],
    target_tokens: int,
) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    for segment in segments:
        text = normalize_text(segment.text)
        if not text:
            continue
        if str(segment.source_type or "").lower() in MATERIAL_SOURCE_TYPES:
            chunks.extend(_split_material_segment_into_chunks(segment, target_tokens))
            continue
        if count_tokens(text) <= target_tokens:
            chunks.append(_chunk_from_segments([segment]))
            continue
        chunks.extend(_split_segment_into_chunks(segment, target_tokens))
    return chunks


def _split_material_segment_into_chunks(
    segment: RawTextSegment,
    target_tokens: int,
) -> list[ExtractedChunk]:
    normalized_text = normalize_text(segment.text)
    if not normalized_text:
        return []

    if not _should_semantically_split_material(normalized_text, target_tokens):
        return [_chunk_from_segments([segment])]

    semantic_target = max(18, min(target_tokens, MATERIAL_SUBCHUNK_MAX_TOKENS))
    semantic_blocks = _split_material_text_into_blocks(normalized_text)
    filtered_parts: list[str] = []

    for block in semantic_blocks:
        cleaned_block = _filter_material_block_text(block)
        if not cleaned_block:
            continue
        if count_tokens(cleaned_block) <= semantic_target:
            filtered_parts.append(cleaned_block)
            continue
        filtered_parts.extend(_split_text_by_token_budget(cleaned_block, semantic_target))

    normalized_parts = [normalize_text(part) for part in filtered_parts if normalize_text(part)]
    if not normalized_parts:
        return []
    if len(normalized_parts) == 1 and normalized_parts[0] == normalized_text:
        return [_chunk_from_segments([segment])]

    return _chunks_from_split_parts(segment, normalized_parts)


def _split_segment_into_chunks(
    segment: RawTextSegment,
    target_tokens: int,
) -> list[ExtractedChunk]:
    parts = _split_text_by_token_budget(segment.text, target_tokens)
    if len(parts) <= 1:
        return [_chunk_from_segments([segment])]

    return _chunks_from_split_parts(segment, parts)


def _chunks_from_split_parts(segment: RawTextSegment, parts: list[str]) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    total_parts = len(parts)
    for index, part in enumerate(parts, start=1):
        split_segment = RawTextSegment(
            source_id=segment.source_id,
            instructor_name=segment.instructor_name,
            source_label=segment.source_label,
            source_type=segment.source_type,
            locator=segment.locator if total_parts == 1 else f"{segment.locator} ({index}/{total_parts})",
            text=part,
        )
        chunks.append(_chunk_from_segments([split_segment]))
    return chunks


def _should_semantically_split_material(text: str, target_tokens: int) -> bool:
    semantic_target = max(18, min(target_tokens, MATERIAL_SUBCHUNK_MAX_TOKENS))
    return (
        bool(MATERIAL_SEMANTIC_SPLIT_RE.search(text))
        or any(phrase in text.lower() for phrase in MATERIAL_NOISE_PHRASES)
        or count_tokens(text) > semantic_target * 2
    )


def _split_material_text_into_blocks(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    if MATERIAL_SEMANTIC_SPLIT_RE.search(normalized):
        candidates = [
            normalize_text(part)
            for part in MATERIAL_SEMANTIC_SPLIT_RE.split(normalized)
            if normalize_text(part)
        ]
    else:
        candidates = [normalized]

    blocks: list[str] = []
    for candidate in candidates:
        blocks.extend(_split_text_by_token_budget(candidate, MATERIAL_SUBCHUNK_MAX_TOKENS))
    return [block for block in blocks if block]


def _filter_material_block_text(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""

    lowered = normalized.lower()
    if any(phrase in lowered for phrase in MATERIAL_NOISE_PHRASES):
        return ""
    if MATERIAL_QUESTION_RE.search(normalized) and (
        MATERIAL_ANSWER_RE.search(normalized) or MATERIAL_PLACEHOLDER_RE.search(normalized)
    ):
        return ""
    if MATERIAL_PLACEHOLDER_RE.search(normalized) and MATERIAL_ANSWER_RE.search(normalized):
        return ""
    return normalized


def _split_text_by_token_budget(text: str, target_tokens: int) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    sentence_candidates = [part.strip() for part in SENTENCE_BOUNDARY_RE.split(normalized) if part.strip()]
    if len(sentence_candidates) <= 1:
        sentence_candidates = [part.strip() for part in normalized.split("  ") if part.strip()]
    if len(sentence_candidates) <= 1:
        sentence_candidates = [normalized]

    parts: list[str] = []
    current_sentences: list[str] = []
    current_text = ""

    for sentence in sentence_candidates:
        candidate = normalize_text(" ".join([*current_sentences, sentence]))
        if current_sentences and count_tokens(candidate) > target_tokens:
            parts.append(current_text)
            current_sentences = [sentence]
            current_text = normalize_text(sentence)
            continue
        current_sentences.append(sentence)
        current_text = candidate

    if current_text:
        parts.append(current_text)

    if len(parts) == 1 and count_tokens(parts[0]) > target_tokens:
        return _split_text_by_words(parts[0], target_tokens)

    normalized_parts: list[str] = []
    for part in parts:
        if count_tokens(part) <= target_tokens:
            normalized_parts.append(part)
            continue
        normalized_parts.extend(_split_text_by_words(part, target_tokens))
    return normalized_parts


def _split_text_by_words(text: str, target_tokens: int) -> list[str]:
    words = [word for word in normalize_text(text).split(" ") if word]
    if not words:
        return []

    parts: list[str] = []
    current_words: list[str] = []
    current_text = ""

    for word in words:
        candidate = normalize_text(" ".join([*current_words, word]))
        if current_words and count_tokens(candidate) > target_tokens:
            parts.append(current_text)
            current_words = [word]
            current_text = word
            continue
        current_words.append(word)
        current_text = candidate

    if current_text:
        parts.append(current_text)
    return parts


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
