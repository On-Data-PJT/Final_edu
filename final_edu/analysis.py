from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from statistics import mean

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing.
    OpenAI = None
from pydantic import BaseModel, Field

from final_edu.config import Settings
from final_edu.extractors import extract_file_asset, extract_voc_asset, extract_youtube_asset
from final_edu.models import (
    AnalysisRun,
    ChunkAssignment,
    CurriculumSection,
    EvidenceSnippet,
    InstructorSubmission,
    InstructorSummary,
    RawTextSegment,
    SectionCoverage,
)
from final_edu.solution_content import build_solution_payload, generate_solution_content
from final_edu.storage import ObjectStorage
from final_edu.youtube_cache import (
    YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE,
    has_youtube_request_limit_warning,
)
from final_edu.utils import (
    build_preserved_segment_chunks,
    build_chunks,
    build_custom_dictionary,
    count_tokens,
    cosine_similarity,
    normalize_text,
    safe_snippet,
    slugify,
    tokenize,
    tokenize_keywords,
)

SECTION_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+[\.\)]?)\s*")
MATERIAL_SOURCE_TYPES = {"pdf", "pptx", "text"}
SPEECH_SOURCE_TYPES = {"youtube"}
RESULT_MODES = ("combined", "material", "speech")
MODE_SOURCE_FILTERS = {
    "combined": None,
    "material": MATERIAL_SOURCE_TYPES,
    "speech": SPEECH_SOURCE_TYPES,
}
NO_ANALYZABLE_TEXT_ERROR_MESSAGE = (
    "분석 가능한 텍스트를 추출하지 못했습니다. 텍스트형 PDF/PPTX 또는 자막/STT 가능한 YouTube URL을 사용해 주세요."
)
VOC_NEGATIVE_RULES = [
    ("강의 속도 조절 필요", ("속도", "빠르", "진도")),
    ("실습 시간과 환경 보완 필요", ("실습", "환경", "오류", "colab", "실행")),
    ("자료 보강 필요", ("자료", "교안", "pdf", "파일")),
    ("질문과 피드백 채널 보완 필요", ("질문", "답변", "피드백")),
    ("난이도와 과제 부담 조절 필요", ("어렵", "난이도", "과제", "부담")),
]
VOC_POSITIVE_HINTS = {
    "친절": "친절한 설명",
    "실습": "실습 중심",
    "체계": "체계적 구성",
    "예시": "예시 풍부",
    "이해": "이해하기 쉬움",
    "피드백": "피드백 충실",
    "복습": "복습 친화적",
}
VOC_NEGATIVE_HINTS = {
    "속도": "강의 속도",
    "빠르": "강의 속도",
    "실습": "실습 시간 부족",
    "환경": "실습 환경",
    "오류": "실습 환경",
    "자료": "자료 부족",
    "질문": "질문 시간 부족",
    "답변": "질문 시간 부족",
    "과제": "과제 부담",
    "부담": "과제 부담",
    "어렵": "난이도 부담",
    "난이도": "난이도 부담",
}
VOC_SUGGESTION_MAP = {
    "강의 속도 조절 필요": {
        "priority": "high",
        "label": "강의 속도 조절",
        "body": "핵심 개념 뒤 체크포인트와 짧은 질의 시간을 추가해 이해 격차를 줄여 보세요.",
    },
    "실습 시간과 환경 보완 필요": {
        "priority": "high",
        "label": "실습 환경 보강",
        "body": "실습 전 환경 점검 체크리스트와 추가 실습 시간을 함께 제공해 오류와 대기 시간을 줄여 보세요.",
    },
    "자료 보강 필요": {
        "priority": "medium",
        "label": "복습 자료 보강",
        "body": "교안, 코드 파일, 실습 결과 예시를 함께 배포해 수강생이 복습 경로를 놓치지 않게 하세요.",
    },
    "질문과 피드백 채널 보완 필요": {
        "priority": "medium",
        "label": "질문 채널 운영",
        "body": "수업 중 질문 채널이나 종료 후 Q&A 시간을 정례화해 피드백 밀도를 높여 보세요.",
    },
    "난이도와 과제 부담 조절 필요": {
        "priority": "medium",
        "label": "난이도 단계화",
        "body": "기초/심화 과제를 분리하고 선행지식 안내를 명확히 해 부담을 분산해 보세요.",
    },
}
VOC_WEEK_RE = re.compile(r"(\d+\s*(?:주차|주|차시))")
YOUTUBE_GENERIC_LABEL_RE = re.compile(r"^youtube\s+[0-9a-z_-]{11}$", re.IGNORECASE)
YOUTUBE_TITLE_CHAPTER_RE = re.compile(r"\[[^\]]+\]\s*(.+)$")
MATERIAL_FRAGMENT_SPLIT_RE = re.compile(
    r"\s*(?::|/|&|·|\||,|\(|\)|(?:\s+-\s+)|(?:\s+및\s+)|(?:\s+and\s+))\s*",
    re.IGNORECASE,
)
MATERIAL_CHAPTER_PREFIX_RE = re.compile(
    r"^\s*(?:chapter|part|lesson|lecture)\s*\d+\s*[:\-]?\s*",
    re.IGNORECASE,
)
MATERIAL_TOTAL_LECTURES_RE = re.compile(r"총\s*\d+\s*강", re.IGNORECASE)
SPEECH_FRAGMENT_SPLIT_RE = re.compile(
    r"\s*(?::|/|&|·|\||,|\(|\)|(?:\s+-\s+)|(?:\s+및\s+)|(?:\s+and\s+))\s*",
    re.IGNORECASE,
)
SPEECH_SECTION_CHAPTER_INDEX_RE = re.compile(r"\bchapter\s*(\d+)\b", re.IGNORECASE)
SPEECH_SOURCE_CHAPTER_INDEX_RE = re.compile(r"\[(\d+)(?:\s*[-–]\s*\d+)?\]")
SPEECH_CHAPTER_PREFIX_RE = re.compile(
    r"^\s*(?:chapter|part|lesson|lecture)\s*\d+\s*[:\-]?\s*",
    re.IGNORECASE,
)
SPEECH_TOTAL_LECTURES_RE = re.compile(r"총\s*\d+\s*강", re.IGNORECASE)
SPEECH_ACRONYM_SUFFIX_RE = re.compile(r"^(?P<lemma>.+?)\s+(?P<acronym>[A-Z]{2,8})$")
SPEECH_TITLE_INDEX_ONLY_SCORE = 0.25
SPEECH_TITLE_PRIOR_BONUS_MAX = 0.06
SPEECH_TITLE_PRIOR_MAX_TRANSCRIPT_DELTA = 0.03
MATERIAL_STRUCTURAL_TOKENS = {
    "chapter",
    "part",
    "lesson",
    "lecture",
    "lectures",
    "course",
    "courses",
    "week",
    "weeks",
    "class",
    "classes",
    "session",
    "sessions",
    "총",
    "강",
    "주차",
    "차시",
}
MATERIAL_LOW_SIGNAL_TOKENS = {
    "motivation",
    "motivations",
    "basic",
    "basics",
    "overview",
    "intro",
    "introduction",
    "summary",
    "wrap",
    "up",
    "application",
    "applications",
}
SPEECH_STRUCTURAL_TOKENS = {
    "chapter",
    "part",
    "lesson",
    "lecture",
    "lectures",
    "course",
    "courses",
    "week",
    "weeks",
    "class",
    "classes",
    "session",
    "sessions",
    "introduction",
    "intro",
    "overview",
    "총",
    "강",
}
SPEECH_LOW_SIGNAL_TOKENS = {
    "motivation",
    "motivations",
    "basic",
    "basics",
    "overview",
    "intro",
    "introduction",
    "summary",
    "wrap",
    "up",
}
SPEECH_SINGULAR_TOKEN_MAP = {
    "trees": "tree",
    "nodes": "node",
    "machines": "machine",
    "networks": "network",
    "models": "model",
    "classifiers": "classifier",
}
SPEECH_PLURALIZABLE_LAST_TOKENS = {
    "tree",
    "node",
    "machine",
    "network",
    "model",
    "classifier",
}
SPEECH_SUBCHUNK_MAX_TOKENS = 24
SPEECH_NONVERBAL_MARKER_RE = re.compile(
    r"\[(?:음악|박수|웃음|환호|노래|효과음|music|applause|laughter|cheers?)\]",
    re.IGNORECASE,
)
SPEECH_NONVERBAL_ONLY_RE = re.compile(
    r"^(?:\[(?:음악|박수|웃음|환호|노래|효과음|music|applause|laughter|cheers?)\]\s*)+$",
    re.IGNORECASE,
)
SPEECH_LLM_ADJUDICATION_MAX_CANDIDATES = 3
SPEECH_LLM_ADJUDICATION_MIN_TOKENS = 18
SECTION_ALIAS_GLOSSARY = {
    "인공지능-및-기계학습-개요": [
        "인공지능",
        "기계학습",
        "머신러닝",
        "machine learning",
        "지도학습",
        "비지도학습",
    ],
    "의학-진단-예제": [
        "의학 진단",
        "의료 진단",
        "진단 예제",
        "medical diagnosis",
    ],
    "support-vector-machine": [
        "support vector machine",
        "svm",
        "서포트 벡터 머신",
        "커널 svm",
    ],
    "결정-트리": [
        "결정 트리",
        "decision tree",
        "decision trees",
        "의사결정나무",
        "엔트로피",
        "entropy",
        "정보 이득",
        "information gain",
        "지니",
        "gini impurity",
        "gini",
        "가지치기",
        "pruning",
        "분기",
        "split criterion",
        "root node",
        "leaf node",
        "tree induction",
    ],
    "신경망-모델": [
        "신경망",
        "neural network",
        "neural networks",
        "퍼셉트론",
        "역전파",
        "backpropagation",
    ],
    "deep-learning-and-boltzmann-machine": [
        "딥러닝",
        "딥 러닝",
        "deep learning",
        "볼츠만",
        "boltzmann",
        "제한적 볼츠만 기계",
        "restricted boltzmann machine",
        "rbm",
        "dropout",
        "드롭아웃",
        "batch normalization",
        "배치 정규화",
        "정규화",
    ],
    "랜덤-포레스트-오토인코더": [
        "랜덤 포레스트",
        "random forest",
        "오토인코더",
        "autoencoder",
        "앙상블",
    ],
    "강좌-종합-정리": [
        "강좌 종합 정리",
        "종합 정리",
        "요약",
        "summary",
    ],
}
SPEECH_STRICT_ANCHOR_GLOSSARY = {
    "인공지능-및-기계학습-개요": [
        "인공지능 및 기계학습 개요",
        "machine learning overview",
        "지도학습",
        "비지도학습",
    ],
    "의학-진단-예제": [
        "의학 진단",
        "의료 진단",
        "medical diagnosis",
    ],
    "support-vector-machine": [
        "support vector machine",
        "support vector",
        "svm",
        "서포트 벡터 머신",
        "서포트 팩터 머신",
        "서포트 팩트 머신",
        "soft margin",
        "hard margin",
        "kernel trick",
        "kkt",
    ],
    "결정-트리": [
        "결정 트리",
        "decision tree",
        "decision trees",
        "의사결정나무",
        "디시전트리",
        "entropy",
        "엔트로피",
        "information gain",
        "정보 이득",
        "gini impurity",
        "gini",
        "지니",
        "pruning",
        "가지치기",
        "root node",
        "leaf node",
    ],
    "신경망-모델": [
        "신경망",
        "neural network",
        "neural networks",
        "퍼셉트론",
        "역전파",
        "backpropagation",
    ],
    "deep-learning-and-boltzmann-machine": [
        "deep learning",
        "딥러닝",
        "딥 러닝",
        "boltzmann",
        "restricted boltzmann machine",
        "rbm",
        "볼츠만",
        "제한적 볼츠만 기계",
    ],
    "랜덤-포레스트-오토인코더": [
        "random forest",
        "랜덤 포레스트",
        "autoencoder",
        "오토인코더",
    ],
    "강좌-종합-정리": [
        "강좌 종합 정리",
        "course summary",
        "wrap up",
        "summary",
        "종합 정리",
    ],
}


class InsightCardSchema(BaseModel):
    category: str
    title: str
    issue: str
    evidence: str
    recommendation: str
    icon: str = "lightbulb"


class InsightBundleSchema(BaseModel):
    cards: list[InsightCardSchema] = Field(min_length=5, max_length=5)


class SpeechChunkDecisionSchema(BaseModel):
    section_id: str = ""
    confidence: str = ""


def _analysis_no_text_error(warnings: list[str]) -> str:
    if has_youtube_request_limit_warning(warnings):
        return YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE
    return NO_ANALYZABLE_TEXT_ERROR_MESSAGE


def _dedupe_terms(terms: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = normalize_text(term)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _section_alias_terms(section: CurriculumSection) -> list[str]:
    keys = {
        str(section.id or "").strip().lower(),
        slugify(section.title),
        slugify(section.description),
        slugify(f"{section.title} {section.description}"),
    }
    aliases: list[str] = []
    for key, terms in SECTION_ALIAS_GLOSSARY.items():
        if key in keys:
            aliases.extend(terms)

    combined_text = normalize_text(f"{section.title} {section.description}").lower()
    if "boltzmann" in combined_text or "딥러닝" in combined_text or "deep learning" in combined_text:
        aliases.extend(SECTION_ALIAS_GLOSSARY["deep-learning-and-boltzmann-machine"])
    if "autoencoder" in combined_text or "오토인코더" in combined_text:
        aliases.extend(SECTION_ALIAS_GLOSSARY["랜덤-포레스트-오토인코더"])
    if "svm" in combined_text or "support vector machine" in combined_text:
        aliases.extend(SECTION_ALIAS_GLOSSARY["support-vector-machine"])

    return _dedupe_terms(aliases)


def _section_assignment_text(section: CurriculumSection) -> str:
    return "\n".join(
        _dedupe_terms(
            [
                section.title,
                section.description,
                *_section_material_anchor_terms(section),
            ]
        )
    )


def _build_section_assignment_texts(sections: list[CurriculumSection]) -> dict[str, str]:
    return {section.id: _section_assignment_text(section) for section in sections}


def _clean_material_fragment(text: str) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        return ""
    cleaned = MATERIAL_TOTAL_LECTURES_RE.sub(" ", cleaned)
    cleaned = MATERIAL_CHAPTER_PREFIX_RE.sub("", cleaned)
    return normalize_text(cleaned.strip(" -–:/|,·()"))


def _normalize_material_fragment_token(token: str) -> str:
    lowered = normalize_text(token).lower()
    if not lowered or lowered.isdigit():
        return ""
    lowered = SPEECH_SINGULAR_TOKEN_MAP.get(lowered, lowered)
    if lowered in MATERIAL_STRUCTURAL_TOKENS:
        return ""
    return lowered


def _material_fragment_key(text: str) -> str:
    tokens = [
        normalized
        for token in tokenize(_clean_material_fragment(text))
        if (normalized := _normalize_material_fragment_token(token))
    ]
    if not tokens or all(token in MATERIAL_LOW_SIGNAL_TOKENS for token in tokens):
        return ""
    return " ".join(tokens)


def _material_fragment_terms(text: str) -> list[str]:
    cleaned = _clean_material_fragment(text)
    if not cleaned:
        return []

    candidates = [cleaned]
    candidates.extend(part for part in MATERIAL_FRAGMENT_SPLIT_RE.split(cleaned) if part)

    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _material_fragment_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        terms.append(key)

        acronym_match = SPEECH_ACRONYM_SUFFIX_RE.match(candidate)
        if acronym_match:
            lemma_key = _material_fragment_key(acronym_match.group("lemma"))
            acronym_key = _material_fragment_key(acronym_match.group("acronym"))
            for variant in (lemma_key, acronym_key):
                if variant and variant not in seen:
                    seen.add(variant)
                    terms.append(variant)

    return terms


def _section_material_anchor_terms(section: CurriculumSection) -> list[str]:
    anchors: list[str] = []
    anchors.extend(_material_fragment_terms(section.title))
    anchors.extend(_material_fragment_terms(section.description))
    for alias in _section_alias_terms(section):
        anchors.extend(_material_fragment_terms(alias))
    return _dedupe_terms(anchors)


def _rank_scored_sections(scored: list[tuple[CurriculumSection, float]]) -> list[tuple[CurriculumSection, float]]:
    return sorted(scored, key=lambda item: item[1], reverse=True)


def _split_section_title_anchor_terms(title: str) -> list[str]:
    normalized_title = normalize_text(title)
    if not normalized_title:
        return []
    terms = [normalized_title]
    for separator in (" / ", "/", " 및 ", " and ", " | ", "|", ","):
        if separator in normalized_title:
            terms.extend(part.strip() for part in normalized_title.split(separator))
    return _dedupe_terms([term for term in terms if len(normalize_text(term)) >= 4])


def _clean_speech_fragment(text: str) -> str:
    cleaned = normalize_text(text)
    if not cleaned:
        return ""
    cleaned = SPEECH_TOTAL_LECTURES_RE.sub(" ", cleaned)
    cleaned = SPEECH_CHAPTER_PREFIX_RE.sub("", cleaned)
    cleaned = normalize_text(cleaned.strip(" -–:/|,·()"))
    return cleaned


def _normalize_speech_fragment_token(token: str) -> str:
    lowered = normalize_text(token).lower()
    if not lowered or lowered.isdigit():
        return ""
    lowered = SPEECH_SINGULAR_TOKEN_MAP.get(lowered, lowered)
    if lowered in SPEECH_STRUCTURAL_TOKENS:
        return ""
    return lowered


def _speech_fragment_key(text: str) -> str:
    tokens = [
        normalized
        for token in tokenize(_clean_speech_fragment(text))
        if (normalized := _normalize_speech_fragment_token(token))
    ]
    if not tokens or all(token in SPEECH_LOW_SIGNAL_TOKENS for token in tokens):
        return ""
    return " ".join(tokens)


def _speech_fragment_terms(text: str) -> list[str]:
    cleaned = _clean_speech_fragment(text)
    if not cleaned:
        return []

    candidates = [cleaned]
    candidates.extend(part for part in SPEECH_FRAGMENT_SPLIT_RE.split(cleaned) if part)

    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _speech_fragment_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        terms.append(key)

        acronym_match = SPEECH_ACRONYM_SUFFIX_RE.match(candidate)
        if acronym_match:
            lemma_key = _speech_fragment_key(acronym_match.group("lemma"))
            acronym_key = _speech_fragment_key(acronym_match.group("acronym"))
            for variant in (lemma_key, acronym_key):
                if variant and variant not in seen:
                    seen.add(variant)
                    terms.append(variant)

        tokens = key.split()
        if len(tokens) >= 2 and tokens[-1] in SPEECH_PLURALIZABLE_LAST_TOKENS:
            plural_key = " ".join([*tokens[:-1], f"{tokens[-1]}s"])
            if plural_key not in seen:
                seen.add(plural_key)
                terms.append(plural_key)

    return terms


def _section_chapter_index(section: CurriculumSection) -> int | None:
    match = SPEECH_SECTION_CHAPTER_INDEX_RE.search(normalize_text(section.title))
    if not match:
        return None
    return int(match.group(1))


def _source_title_chapter_index(source_label: str) -> int | None:
    normalized = normalize_text(str(source_label or ""))
    if not normalized:
        return None
    match = SPEECH_SOURCE_CHAPTER_INDEX_RE.search(normalized)
    if match:
        return int(match.group(1))
    return None


def _section_speech_anchor_terms(section: CurriculumSection) -> list[str]:
    keys = {
        str(section.id or "").strip().lower(),
        slugify(section.title),
        slugify(section.description),
        slugify(f"{section.title} {section.description}"),
    }
    anchors: list[str] = []
    anchors.extend(_speech_fragment_terms(section.title))
    anchors.extend(_speech_fragment_terms(section.description))
    for key, terms in SPEECH_STRICT_ANCHOR_GLOSSARY.items():
        if key in keys:
            anchors.extend(terms)

    combined_text = normalize_text(f"{section.title} {section.description}").lower()
    if "boltzmann" in combined_text or "딥러닝" in combined_text or "deep learning" in combined_text:
        anchors.extend(SPEECH_STRICT_ANCHOR_GLOSSARY["deep-learning-and-boltzmann-machine"])
    if "autoencoder" in combined_text or "오토인코더" in combined_text:
        anchors.extend(SPEECH_STRICT_ANCHOR_GLOSSARY["랜덤-포레스트-오토인코더"])
    if "svm" in combined_text or "support vector machine" in combined_text:
        anchors.extend(SPEECH_STRICT_ANCHOR_GLOSSARY["support-vector-machine"])
    return _dedupe_terms(anchors)


def _normalize_speech_segment_text(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    if SPEECH_NONVERBAL_ONLY_RE.fullmatch(normalized):
        return ""
    stripped = normalize_text(SPEECH_NONVERBAL_MARKER_RE.sub(" ", normalized))
    return stripped


def _prepare_speech_segments(segments: list[RawTextSegment]) -> list[RawTextSegment]:
    prepared: list[RawTextSegment] = []
    for segment in segments:
        text = _normalize_speech_segment_text(segment.text)
        if not text:
            continue
        prepared.append(
            RawTextSegment(
                source_id=segment.source_id,
                instructor_name=segment.instructor_name,
                source_label=segment.source_label,
                source_type=segment.source_type,
                locator=segment.locator,
                text=text,
            )
        )
    return prepared


def _anchor_token_sequence(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return []
    return tokenize(normalized_text)


def _count_anchor_occurrences(text: str, anchor: str) -> int:
    text_tokens = _anchor_token_sequence(text)
    anchor_tokens = _anchor_token_sequence(anchor)
    if not text_tokens or not anchor_tokens:
        return 0
    anchor_len = len(anchor_tokens)
    return sum(
        1
        for index in range(len(text_tokens) - anchor_len + 1)
        if text_tokens[index : index + anchor_len] == anchor_tokens
    )


def _speech_anchor_counts(*, text: str, anchors: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for anchor in anchors:
        count = _count_anchor_occurrences(text, anchor)
        if count > 0:
            counts[anchor] = count
    return counts


def _material_anchor_counts(*, text: str, anchors: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for anchor in anchors:
        count = _count_anchor_occurrences(text, anchor)
        if count > 0:
            counts[anchor] = count
    return counts


def _material_anchor_counts_by_section(
    *,
    chunk,
    sections: list[CurriculumSection],
) -> dict[str, dict[str, int]]:
    if chunk.source_type not in MATERIAL_SOURCE_TYPES:
        return {}
    return {
        section.id: _material_anchor_counts(
            text=chunk.text,
            anchors=_section_material_anchor_terms(section),
        )
        for section in sections
    }


def _material_candidate_section_ids(
    *,
    material_anchor_counts: dict[str, dict[str, int]],
) -> set[str]:
    return {
        section_id
        for section_id, counts in material_anchor_counts.items()
        if counts
    }


def _speech_transcript_anchor_counts_by_section(
    *,
    chunk,
    sections: list[CurriculumSection],
) -> dict[str, dict[str, int]]:
    if chunk.source_type not in SPEECH_SOURCE_TYPES:
        return {}
    return {
        section.id: _speech_anchor_counts(
            text=chunk.text,
            anchors=_section_speech_anchor_terms(section),
        )
        for section in sections
    }


def _speech_transcript_candidate_section_ids(
    *,
    transcript_anchor_counts: dict[str, dict[str, int]],
    sections: list[CurriculumSection],
) -> set[str]:
    candidate_ids: set[str] = set()
    sections_by_id = {section.id: section for section in sections}
    for section_id, counts in transcript_anchor_counts.items():
        if len(counts) >= 2 or max(counts.values(), default=0) >= 2:
            candidate_ids.add(section_id)
            continue
        section = sections_by_id.get(section_id)
        if section is not None:
            title_anchor_terms = set(_speech_fragment_terms(section.title))
            if any(anchor in title_anchor_terms and count >= 1 for anchor, count in counts.items()):
                candidate_ids.add(section_id)
    return candidate_ids


def _score_speech_title_sections(
    *,
    sections: list[CurriculumSection],
    source_label: str,
) -> list[tuple[CurriculumSection, float]]:
    title_text = _speech_title_text(source_label)
    if not title_text:
        return []
    title_keys = set(_speech_fragment_terms(title_text))
    source_chapter_index = _source_title_chapter_index(source_label)

    scored: list[tuple[CurriculumSection, float]] = []
    for section in sections:
        anchors = _section_speech_anchor_terms(section)
        exact_matches = _speech_anchor_counts(text=title_text, anchors=anchors)
        score = float(sum(exact_matches.values()))
        anchor_keys = set(anchors)
        fragment_matches = title_keys & anchor_keys
        if fragment_matches:
            score = max(score, 1.0 + (0.1 * len(fragment_matches)))
        if source_chapter_index is not None and _section_chapter_index(section) == source_chapter_index:
            score += SPEECH_TITLE_INDEX_ONLY_SCORE
        if score > 0:
            scored.append((section, score))
    return scored


def _resolve_speech_title_rescue(
    *,
    chunk,
    transcript_scored: list[tuple[CurriculumSection, float]],
    title_scored: list[tuple[CurriculumSection, float]],
    transcript_anchor_counts: dict[str, dict[str, int]],
    min_score: float,
    min_margin: float,
) -> tuple[str | None, str | None]:
    if chunk.source_type not in SPEECH_SOURCE_TYPES or not title_scored:
        return None, None

    transcript_ranked = _rank_scored_sections(transcript_scored)
    transcript_best_section, transcript_best_score = transcript_ranked[0]
    transcript_runner_score = transcript_ranked[1][1] if len(transcript_ranked) > 1 else 0.0
    transcript_is_ambiguous = (
        transcript_best_score < min_score
        or (transcript_best_score - transcript_runner_score) < min_margin
    )

    title_ranked = _rank_scored_sections(title_scored)
    title_best_section, title_best_score = title_ranked[0]
    transcript_score_map = {section.id: score for section, score in transcript_scored}
    title_section_transcript_score = float(transcript_score_map.get(title_best_section.id, 0.0))
    transcript_delta = transcript_best_score - title_section_transcript_score
    title_section_anchor_counts = transcript_anchor_counts.get(title_best_section.id, {})
    title_is_exact_match = title_best_score >= 1.0
    transcript_is_plausible = title_section_transcript_score >= max(0.0, min_score - 0.03)
    transcript_is_strongly_plausible = title_section_transcript_score >= min_score

    rescue_section_id = None
    if title_section_anchor_counts and (
        transcript_is_ambiguous
        or transcript_is_plausible
        or (
            title_is_exact_match
            and title_section_transcript_score >= max(0.0, min_score - 0.05)
        )
    ):
        rescue_section_id = title_best_section.id
    elif title_is_exact_match and (
        transcript_is_ambiguous
        or (
            transcript_is_plausible
            and transcript_delta <= SPEECH_TITLE_PRIOR_MAX_TRANSCRIPT_DELTA
        )
    ):
        rescue_section_id = title_best_section.id
    elif (
        0.0 < title_best_score < 1.0
        and transcript_is_ambiguous
        and transcript_is_strongly_plausible
    ):
        rescue_section_id = title_best_section.id

    warning = None
    if (
        rescue_section_id is None
        and title_is_exact_match
        and transcript_delta > SPEECH_TITLE_PRIOR_MAX_TRANSCRIPT_DELTA
    ):
        warning = (
            f"{chunk.source_label}: 영상 제목은 '{title_best_section.title}'에 가깝지만 "
            "발화 transcript는 다른 주제로 읽혔습니다."
        )
    return rescue_section_id, warning


def _restrict_scored_sections_to_candidates(
    *,
    scored: list[tuple[CurriculumSection, float]],
    candidate_ids: set[str],
) -> list[tuple[CurriculumSection, float]]:
    if not candidate_ids:
        return [(section, 0.0) for section, _score in scored]
    return [
        (section, score if section.id in candidate_ids else 0.0)
        for section, score in scored
    ]


def _speech_title_text(source_label: str) -> str:
    normalized = normalize_text(str(source_label or ""))
    if not normalized or YOUTUBE_GENERIC_LABEL_RE.fullmatch(normalized):
        return ""
    chapter_match = YOUTUBE_TITLE_CHAPTER_RE.search(normalized)
    if chapter_match:
        chapter_title = normalize_text(chapter_match.group(1))
        if chapter_title:
            return chapter_title
    return normalized


def _speech_title_prior_bonus(title_signal_score: float) -> float:
    bounded_signal = max(0.0, min(title_signal_score, 2.0))
    return min(SPEECH_TITLE_PRIOR_BONUS_MAX, 0.02 + (bounded_signal * 0.02))


def _apply_speech_title_prior(
    *,
    chunk,
    transcript_scored: list[tuple[CurriculumSection, float]],
    title_scored: list[tuple[CurriculumSection, float]],
    transcript_anchor_counts: dict[str, dict[str, int]],
    min_score: float,
    min_margin: float,
) -> tuple[list[tuple[CurriculumSection, float]], str | None]:
    adjusted_scored = list(transcript_scored)
    rescue_section_id, warning = _resolve_speech_title_rescue(
        chunk=chunk,
        transcript_scored=transcript_scored,
        title_scored=title_scored,
        transcript_anchor_counts=transcript_anchor_counts,
        min_score=min_score,
        min_margin=min_margin,
    )
    if rescue_section_id is not None:
        rescue_score = next(
            (score for section, score in title_scored if section.id == rescue_section_id),
            1.0,
        )
        bonus = _speech_title_prior_bonus(rescue_score)
        adjusted_scored = [
            (section, score + bonus if section.id == rescue_section_id else score)
            for section, score in transcript_scored
        ]
    return adjusted_scored, warning


def _single_speech_candidate_rescue(
    *,
    sections: list[CurriculumSection],
    transcript_scored: list[tuple[CurriculumSection, float]],
    candidate_ids: set[str],
    transcript_anchor_counts: dict[str, dict[str, int]],
    min_score: float,
) -> str | None:
    if len(candidate_ids) != 1:
        return None
    candidate_id = next(iter(candidate_ids))
    section = next((item for item in sections if item.id == candidate_id), None)
    if section is None:
        return None
    title_anchor_terms = set(_speech_fragment_terms(section.title))
    counts = transcript_anchor_counts.get(candidate_id, {})
    if not any(anchor in title_anchor_terms and count >= 1 for anchor, count in counts.items()):
        return None
    transcript_score_map = {item.id: score for item, score in transcript_scored}
    if float(transcript_score_map.get(candidate_id, 0.0)) < max(0.0, min_score - 0.04):
        return None
    return candidate_id


def _adjudicate_ambiguous_speech_chunk(
    *,
    chunk,
    sections: list[CurriculumSection],
    candidate_ids: set[str],
    settings: Settings,
) -> str | None:
    if (
        not settings.openai_api_key
        or OpenAI is None
        or len(candidate_ids) < 2
        or len(candidate_ids) > SPEECH_LLM_ADJUDICATION_MAX_CANDIDATES
        or count_tokens(chunk.text) < SPEECH_LLM_ADJUDICATION_MIN_TOKENS
    ):
        return None

    candidate_sections = [
        {
            "section_id": section.id,
            "title": section.title,
            "description": section.description,
        }
        for section in sections
        if section.id in candidate_ids
    ]
    if len(candidate_sections) < 2:
        return None

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        parsed = client.responses.parse(
            model=settings.openai_insight_model,
            instructions=(
                "You are adjudicating an ambiguous lecture transcript chunk against a small set of curriculum sections. "
                "Use only the transcript text and the candidate section titles/descriptions. "
                "If one section is clearly the best grounded match, return its exact section_id with confidence 'high'. "
                "If the match is weak or ambiguous, return an empty section_id with confidence 'low'. "
                "Return JSON only."
            ),
            input=json.dumps(
                {
                    "source_label": chunk.source_label,
                    "locator": chunk.locator,
                    "transcript_text": chunk.text,
                    "candidates": candidate_sections,
                },
                ensure_ascii=False,
            ),
            text_format=SpeechChunkDecisionSchema,
            max_output_tokens=120,
            temperature=0,
        )
        section_id = str(parsed.output_parsed.section_id or "").strip()
        confidence = str(parsed.output_parsed.confidence or "").strip().lower()
        if confidence != "high" or section_id not in candidate_ids:
            return None
        return section_id
    except Exception:  # noqa: BLE001
        return None


def _rescue_speech_assignment(
    *,
    chunk,
    sections: list[CurriculumSection],
    transcript_scored: list[tuple[CurriculumSection, float]],
    scored: list[tuple[CurriculumSection, float]],
    candidate_ids: set[str],
    transcript_anchor_counts: dict[str, dict[str, int]],
    settings: Settings,
    min_score: float,
    min_margin: float,
) -> ChunkAssignment:
    assignment = _best_assignment(chunk, scored, min_score=min_score, min_margin=min_margin)
    if not assignment.is_unmapped:
        return assignment

    rescued_section_id = _single_speech_candidate_rescue(
        sections=sections,
        transcript_scored=transcript_scored,
        candidate_ids=candidate_ids,
        transcript_anchor_counts=transcript_anchor_counts,
        min_score=min_score,
    )
    rationale = "직접 발화 anchor 근거로 보정되었습니다."
    if rescued_section_id is None:
        rescued_section_id = _adjudicate_ambiguous_speech_chunk(
            chunk=chunk,
            sections=sections,
            candidate_ids=candidate_ids,
            settings=settings,
        )
        rationale = "애매한 발화를 추가 판정으로 배정했습니다."
    if rescued_section_id is None:
        return assignment

    ranked = _rank_scored_sections(transcript_scored)
    score_map = {section.id: score for section, score in transcript_scored}
    rescued_section = next(section for section in sections if section.id == rescued_section_id)
    runner_up_score = next(
        (score for section, score in ranked if section.id != rescued_section_id),
        0.0,
    )
    return ChunkAssignment(
        chunk=chunk,
        section_id=rescued_section.id,
        section_title=rescued_section.title,
        score=max(float(score_map.get(rescued_section_id, 0.0)), min_score),
        runner_up_score=runner_up_score,
        rationale_short=rationale,
    )


def analyze_submissions(
    *,
    course_id: str,
    course_name: str,
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    settings: Settings,
    storage: ObjectStorage | None = None,
    progress_callback=None,
    analysis_mode: str = "auto",
) -> AnalysisRun:
    started = time.perf_counter()
    normalized_sections = _normalize_target_weights(sections)
    build_custom_dictionary(
        [
            term
            for section in normalized_sections
            for term in [
                section.title,
                *_section_alias_terms(section),
                *_section_material_anchor_terms(section),
            ]
        ]
    )
    active_submissions = [
        submission
        for submission in submissions
        if submission.files or submission.youtube_urls or submission.voc_files
    ]
    if len(active_submissions) < 1:
        raise ValueError("최소 1명의 강사 자료가 필요합니다.")

    voc_analyses_by_instructor, voc_summary, voc_analysis_warnings = _analyze_voc_submissions(
        submissions=active_submissions,
        settings=settings,
    )

    normalized_mode = str(analysis_mode or "auto").strip().lower()
    if normalized_mode == "lexical":
        return _analyze_submissions_lexical_streaming(
            course_id=course_id,
            course_name=course_name,
            sections=normalized_sections,
            submissions=active_submissions,
            settings=settings,
            storage=storage,
            started=started,
            progress_callback=progress_callback,
            voc_analyses_by_instructor=voc_analyses_by_instructor,
            voc_summary=voc_summary,
            voc_analysis_warnings=voc_analysis_warnings,
        )

    all_chunks = []
    warnings: list[str] = list(voc_analysis_warnings)
    instructor_assets: dict[str, int] = defaultdict(int)
    instructor_warnings: dict[str, list[str]] = defaultdict(list)
    total_youtube_videos = sum(len(submission.youtube_urls) for submission in active_submissions)
    processed_youtube_videos = 0
    caption_success_count = 0
    caption_failure_count = 0

    _emit_progress(
        progress_callback,
        phase="transcript_fetching",
        progress_current=0,
        progress_total=total_youtube_videos,
        expanded_video_count=total_youtube_videos,
        processed_video_count=0,
        caption_success_count=0,
        caption_failure_count=0,
    )

    for submission in active_submissions:
        for upload in submission.files:
            source, segments, source_warnings = extract_file_asset(upload, submission.name)
            warnings.extend(source_warnings)
            instructor_warnings[submission.name].extend(source_warnings)
            if segments:
                instructor_assets[submission.name] += 1
                all_chunks.extend(_build_chunks_for_source_segments(segments, settings))

        for youtube_url in submission.youtube_urls:
            source, segments, source_warnings = extract_youtube_asset(
                youtube_url,
                submission.name,
                settings=settings,
                storage=storage,
            )
            warnings.extend(source_warnings)
            instructor_warnings[submission.name].extend(source_warnings)
            processed_youtube_videos += 1
            if segments:
                caption_success_count += 1
                instructor_assets[submission.name] += 1
                all_chunks.extend(_build_chunks_for_source_segments(segments, settings))
            else:
                caption_failure_count += 1
            _emit_progress(
                progress_callback,
                phase="transcript_fetching",
                progress_current=processed_youtube_videos,
                progress_total=total_youtube_videos,
                expanded_video_count=total_youtube_videos,
                processed_video_count=processed_youtube_videos,
                caption_success_count=caption_success_count,
                caption_failure_count=caption_failure_count,
            )

    _emit_progress(
        progress_callback,
        phase="chunking",
        progress_current=len(all_chunks),
        progress_total=max(1, len(all_chunks)),
        expanded_video_count=total_youtube_videos,
        processed_video_count=processed_youtube_videos,
        caption_success_count=caption_success_count,
        caption_failure_count=caption_failure_count,
    )
    deduped_chunks, dedupe_warnings = _dedupe_chunks(all_chunks)
    warnings.extend(dedupe_warnings)
    if not deduped_chunks:
        if voc_analyses_by_instructor:
            return _build_voc_only_run(
                course_id=course_id,
                course_name=course_name,
                sections=normalized_sections,
                submissions=active_submissions,
                warnings=warnings,
                started=started,
                scorer_mode="voc-only",
                voc_analyses_by_instructor=voc_analyses_by_instructor,
                voc_summary=voc_summary,
            )
        raise ValueError(_analysis_no_text_error(warnings))

    assignments, scorer_mode, scorer_warnings = _assign_chunks(
        deduped_chunks,
        normalized_sections,
        settings,
        progress_callback=progress_callback,
        progress_context=_build_progress_context(
            expanded_video_count=total_youtube_videos,
            processed_video_count=processed_youtube_videos,
            caption_success_count=caption_success_count,
            caption_failure_count=caption_failure_count,
        ),
    )
    warnings.extend(scorer_warnings)
    summaries = _build_instructor_summaries(
        sections=normalized_sections,
        submissions=active_submissions,
        assignments=assignments,
        instructor_assets=instructor_assets,
        instructor_warnings=instructor_warnings,
        max_evidence=settings.max_evidence_per_section,
    )
    (
        mode_series,
        average_series_by_mode,
        line_series_by_mode,
        available_source_modes,
        source_mode_stats,
        mode_unmapped_series,
    ) = _build_mode_series(
        sections=normalized_sections,
        submissions=active_submissions,
        assignments=assignments,
    )
    rose_series_by_mode = _build_rose_series_by_mode(
        mode_series=mode_series,
        sections=normalized_sections,
    )
    (
        keywords_by_mode,
        off_curriculum_keywords_by_mode,
        average_keywords_by_mode,
    ) = _build_keyword_payloads_by_mode(
        chunks=deduped_chunks,
        sections=normalized_sections,
    )
    keywords_by_instructor = keywords_by_mode.get("combined", {})
    rose_series_by_instructor = rose_series_by_mode.get("combined", {})
    _emit_progress(
        progress_callback,
        phase="insight_generating",
        progress_current=1,
        progress_total=1,
        expanded_video_count=total_youtube_videos,
        processed_video_count=processed_youtube_videos,
        caption_success_count=caption_success_count,
        caption_failure_count=caption_failure_count,
    )
    insights, insight_generation_mode, insight_warnings = _build_insights(
        course_name=course_name,
        sections=normalized_sections,
        summaries=summaries,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        off_curriculum_keywords_by_instructor=off_curriculum_keywords_by_mode.get("combined", {}),
        settings=settings,
    )
    warnings.extend(insight_warnings)

    attached_summaries = _attach_voc_to_summaries(
        summaries=summaries,
        submissions=active_submissions,
        voc_analyses_by_instructor=voc_analyses_by_instructor,
    )
    solution_content, solution_generation_mode, solution_generation_warning, external_trends_status = (
        _build_precomputed_solution_fields(
            sections=normalized_sections,
            summaries=attached_summaries,
            voc_summary=voc_summary,
            settings=settings,
        )
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisRun(
        sections=normalized_sections,
        instructors=attached_summaries,
        warnings=_dedupe_messages(warnings),
        scorer_mode=scorer_mode,
        duration_ms=duration_ms,
        course={
            "id": course_id,
            "name": course_name,
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "description": section.description,
                    "target_weight": section.target_weight,
                }
                for section in normalized_sections
            ],
        },
        available_source_modes=available_source_modes,
        source_mode_stats=source_mode_stats,
        mode_unmapped_series=mode_unmapped_series,
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        average_keywords_by_mode=average_keywords_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        keywords_by_mode=keywords_by_mode,
        rose_series_by_instructor=rose_series_by_instructor,
        rose_series_by_mode=rose_series_by_mode,
        line_series_by_mode=line_series_by_mode,
        insights=insights,
        voc_summary=voc_summary,
        insight_generation_mode=insight_generation_mode,
        solution_content=solution_content,
        solution_generation_mode=solution_generation_mode,
        solution_generation_warning=solution_generation_warning,
        external_trends_status=external_trends_status,
    )


def _analyze_submissions_lexical_streaming(
    *,
    course_id: str,
    course_name: str,
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    settings: Settings,
    storage: ObjectStorage | None,
    started: float,
    progress_callback=None,
    voc_analyses_by_instructor: dict[str, dict] | None = None,
    voc_summary: dict | None = None,
    voc_analysis_warnings: list[str] | None = None,
) -> AnalysisRun:
    warnings: list[str] = list(voc_analysis_warnings or [])
    instructor_assets: dict[str, int] = defaultdict(int)
    instructor_warnings: dict[str, list[str]] = defaultdict(list)
    total_youtube_videos = sum(len(submission.youtube_urls) for submission in submissions)
    processed_youtube_videos = 0
    caption_success_count = 0
    caption_failure_count = 0
    keyword_counters_by_mode: dict[str, dict[str, Counter[str]]] = {
        mode: defaultdict(Counter) for mode in RESULT_MODES
    }
    off_curriculum_counters_by_mode: dict[str, dict[str, Counter[str]]] = {
        mode: defaultdict(Counter) for mode in RESULT_MODES
    }
    keyword_documents_by_mode: dict[str, list[set[str]]] = {
        mode: [] for mode in RESULT_MODES
    }
    off_curriculum_keyword_documents_by_mode: dict[str, list[set[str]]] = {
        mode: [] for mode in RESULT_MODES
    }
    curriculum_tokens = set()
    for section in sections:
        curriculum_tokens.update(tokenize_keywords(section.search_text))
    lexical_index = _build_lexical_index(sections)
    dedupe_seen: set[tuple[str, str]] = set()
    removed_duplicates = 0
    mode_aggregates = _init_mode_aggregates(sections, submissions)
    evidence_map: dict[str, dict[str, list[ChunkAssignment]]] = defaultdict(lambda: defaultdict(list))
    assigning_progress_state = {"current": 0, "total": 0}

    _emit_progress(
        progress_callback,
        phase="transcript_fetching",
        progress_current=0,
        progress_total=total_youtube_videos,
        expanded_video_count=total_youtube_videos,
        processed_video_count=0,
        caption_success_count=0,
        caption_failure_count=0,
    )

    for submission in submissions:
        for upload in submission.files:
            source, segments, source_warnings = extract_file_asset(upload, submission.name)
            warnings.extend(source_warnings)
            instructor_warnings[submission.name].extend(source_warnings)
            if not segments:
                continue
            instructor_assets[submission.name] += 1
            removed_count, assignment_warnings = _stream_segments_into_aggregates(
                segments=segments,
                instructor_name=submission.name,
                settings=settings,
                sections=sections,
                lexical_index=lexical_index,
                dedupe_seen=dedupe_seen,
                mode_aggregates=mode_aggregates,
                evidence_map=evidence_map,
                keyword_counters_by_mode=keyword_counters_by_mode,
                off_curriculum_counters_by_mode=off_curriculum_counters_by_mode,
                keyword_documents_by_mode=keyword_documents_by_mode,
                off_curriculum_keyword_documents_by_mode=off_curriculum_keyword_documents_by_mode,
                curriculum_tokens=curriculum_tokens,
                max_evidence=settings.max_evidence_per_section,
                progress_callback=progress_callback,
                progress_state=assigning_progress_state,
                progress_context=_build_progress_context(
                    expanded_video_count=total_youtube_videos,
                    processed_video_count=processed_youtube_videos,
                    caption_success_count=caption_success_count,
                    caption_failure_count=caption_failure_count,
                ),
            )
            removed_duplicates += removed_count
            warnings.extend(assignment_warnings)
            instructor_warnings[submission.name].extend(assignment_warnings)

        for youtube_url in submission.youtube_urls:
            source, segments, source_warnings = extract_youtube_asset(
                youtube_url,
                submission.name,
                settings=settings,
                storage=storage,
            )
            warnings.extend(source_warnings)
            instructor_warnings[submission.name].extend(source_warnings)
            processed_youtube_videos += 1
            if segments:
                caption_success_count += 1
                instructor_assets[submission.name] += 1
                removed_count, assignment_warnings = _stream_segments_into_aggregates(
                    segments=segments,
                    instructor_name=submission.name,
                    settings=settings,
                    sections=sections,
                    lexical_index=lexical_index,
                    dedupe_seen=dedupe_seen,
                    mode_aggregates=mode_aggregates,
                    evidence_map=evidence_map,
                    keyword_counters_by_mode=keyword_counters_by_mode,
                    off_curriculum_counters_by_mode=off_curriculum_counters_by_mode,
                    keyword_documents_by_mode=keyword_documents_by_mode,
                    off_curriculum_keyword_documents_by_mode=off_curriculum_keyword_documents_by_mode,
                    curriculum_tokens=curriculum_tokens,
                    max_evidence=settings.max_evidence_per_section,
                    progress_callback=progress_callback,
                    progress_state=assigning_progress_state,
                    progress_context=_build_progress_context(
                        expanded_video_count=total_youtube_videos,
                        processed_video_count=processed_youtube_videos,
                        caption_success_count=caption_success_count,
                        caption_failure_count=caption_failure_count,
                    ),
                )
                removed_duplicates += removed_count
                warnings.extend(assignment_warnings)
                instructor_warnings[submission.name].extend(assignment_warnings)
            else:
                caption_failure_count += 1
            _emit_progress(
                progress_callback,
                phase="transcript_fetching",
                progress_current=processed_youtube_videos,
                progress_total=total_youtube_videos,
                expanded_video_count=total_youtube_videos,
                processed_video_count=processed_youtube_videos,
                caption_success_count=caption_success_count,
                caption_failure_count=caption_failure_count,
            )

    if removed_duplicates:
        warnings.append(f"반복 텍스트 청크 {removed_duplicates}개를 중복 제거했습니다.")

    combined_aggregates = mode_aggregates["combined"]
    if not any(combined_aggregates.get(submission.name, {}).get("total_tokens", 0) for submission in submissions):
        if voc_analyses_by_instructor:
            return _build_voc_only_run(
                course_id=course_id,
                course_name=course_name,
                sections=sections,
                submissions=submissions,
                warnings=warnings,
                started=started,
                scorer_mode="voc-only",
                voc_analyses_by_instructor=voc_analyses_by_instructor,
                voc_summary=voc_summary or {},
            )
        raise ValueError(_analysis_no_text_error(warnings))

    summaries = _build_summaries_from_aggregates(
        sections=sections,
        submissions=submissions,
        combined_aggregates=combined_aggregates,
        evidence_map=evidence_map,
        instructor_assets=instructor_assets,
        instructor_warnings=instructor_warnings,
    )
    (
        mode_series,
        average_series_by_mode,
        line_series_by_mode,
        available_source_modes,
        source_mode_stats,
        mode_unmapped_series,
    ) = _build_mode_series_from_aggregates(
        sections=sections,
        submissions=submissions,
        mode_aggregates=mode_aggregates,
    )
    rose_series_by_mode = _build_rose_series_by_mode(
        mode_series=mode_series,
        sections=sections,
    )
    (
        keywords_by_mode,
        off_curriculum_keywords_by_mode,
        average_keywords_by_mode,
    ) = _build_keywords_by_mode_from_counters(
        grouped_by_mode=keyword_counters_by_mode,
        grouped_off_curriculum_by_mode=off_curriculum_counters_by_mode,
        documents_by_mode=keyword_documents_by_mode,
        off_curriculum_documents_by_mode=off_curriculum_keyword_documents_by_mode,
    )
    keywords_by_instructor = keywords_by_mode.get("combined", {})
    rose_series_by_instructor = rose_series_by_mode.get("combined", {})
    _emit_progress(
        progress_callback,
        phase="insight_generating",
        progress_current=1,
        progress_total=1,
        expanded_video_count=total_youtube_videos,
        processed_video_count=processed_youtube_videos,
        caption_success_count=caption_success_count,
        caption_failure_count=caption_failure_count,
    )
    insights, insight_generation_mode, insight_warnings = _build_insights(
        course_name=course_name,
        sections=sections,
        summaries=summaries,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        off_curriculum_keywords_by_instructor=off_curriculum_keywords_by_mode.get("combined", {}),
        settings=replace(settings, openai_api_key=None),
    )
    warnings.extend(insight_warnings)
    attached_summaries = _attach_voc_to_summaries(
        summaries=summaries,
        submissions=submissions,
        voc_analyses_by_instructor=voc_analyses_by_instructor or {},
    )
    solution_content, solution_generation_mode, solution_generation_warning, external_trends_status = (
        _build_precomputed_solution_fields(
            sections=sections,
            summaries=attached_summaries,
            voc_summary=voc_summary or {},
            settings=settings,
        )
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisRun(
        sections=sections,
        instructors=attached_summaries,
        warnings=_dedupe_messages(warnings),
        scorer_mode="lexical-streaming",
        duration_ms=duration_ms,
        course={
            "id": course_id,
            "name": course_name,
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "description": section.description,
                    "target_weight": section.target_weight,
                }
                for section in sections
            ],
        },
        available_source_modes=available_source_modes,
        source_mode_stats=source_mode_stats,
        mode_unmapped_series=mode_unmapped_series,
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        average_keywords_by_mode=average_keywords_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        keywords_by_mode=keywords_by_mode,
        rose_series_by_instructor=rose_series_by_instructor,
        rose_series_by_mode=rose_series_by_mode,
        line_series_by_mode=line_series_by_mode,
        insights=insights,
        voc_summary=voc_summary or {},
        insight_generation_mode=insight_generation_mode,
        solution_content=solution_content,
        solution_generation_mode=solution_generation_mode,
        solution_generation_warning=solution_generation_warning,
        external_trends_status=external_trends_status,
    )


def analyze_voc_assets(
    *,
    instructor_name: str,
    uploads: list,
    settings: Settings,
) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    collected_segments = []
    analyzed_files: list[str] = []
    response_count = 0
    question_score_batches: list[list[dict]] = []

    for upload in uploads:
        extraction = extract_voc_asset(upload, instructor_name)
        warnings.extend(extraction.warnings)
        if not extraction.segments and not extraction.question_scores:
            continue
        analyzed_files.append(upload.original_name)
        collected_segments.extend(extraction.segments)
        response_count += max(
            extraction.response_count,
            max((int(item.get("response_count", 0) or 0) for item in extraction.question_scores), default=0),
            len(extraction.segments),
        )
        if extraction.question_scores:
            question_score_batches.append(extraction.question_scores)

    if not collected_segments and not question_score_batches:
        raise ValueError("VOC 파일에서 분석 가능한 텍스트를 추출하지 못했습니다.")

    if collected_segments:
        structured, generation_warning = _generate_voc_analysis(
            instructor_name=instructor_name,
            segments=collected_segments,
            settings=settings,
        )
        if generation_warning:
            warnings.append(generation_warning)
    else:
        structured = _empty_voc_text_analysis()

    file_name = ""
    if len(analyzed_files) == 1:
        file_name = analyzed_files[0]
    elif analyzed_files:
        file_name = f"{analyzed_files[0]} 외 {len(analyzed_files) - 1}개"

    analysis = {
        "file_name": file_name,
        "analyzed_at": datetime.now(UTC).astimezone().strftime("%Y-%m-%d"),
        "response_count": max(response_count, len(collected_segments)),
        "question_scores": _aggregate_question_scores(question_score_batches),
        "sentiment": structured["sentiment"],
        "repeated_complaints": structured["repeated_complaints"],
        "next_suggestions": structured["next_suggestions"],
    }
    return analysis, _dedupe_messages(warnings)


def _analyze_voc_submissions(
    *,
    submissions: list[InstructorSubmission],
    settings: Settings,
) -> tuple[dict[str, dict], dict, list[str]]:
    analyses: dict[str, dict] = {}
    warnings: list[str] = []

    for submission in submissions:
        if not submission.voc_files:
            continue
        try:
            analysis, analysis_warnings = analyze_voc_assets(
                instructor_name=submission.name,
                uploads=submission.voc_files,
                settings=settings,
            )
            analyses[submission.name] = analysis
            warnings.extend(analysis_warnings)
        except ValueError as exc:
            warnings.append(f"{submission.name}: {exc}")

    return analyses, _build_voc_summary(analyses), _dedupe_messages(warnings)


def _build_voc_only_run(
    *,
    course_id: str,
    course_name: str,
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    warnings: list[str],
    started: float,
    scorer_mode: str,
    voc_analyses_by_instructor: dict[str, dict],
    voc_summary: dict,
) -> AnalysisRun:
    summaries = _attach_voc_to_summaries(
        summaries=_build_instructor_summaries(
            sections=sections,
            submissions=submissions,
            assignments=[],
            instructor_assets=defaultdict(int),
            instructor_warnings=defaultdict(list),
            max_evidence=0,
        ),
        submissions=submissions,
        voc_analyses_by_instructor=voc_analyses_by_instructor,
    )
    (
        mode_series,
        average_series_by_mode,
        line_series_by_mode,
        available_source_modes,
        source_mode_stats,
        mode_unmapped_series,
    ) = _build_mode_series(
        sections=sections,
        submissions=submissions,
        assignments=[],
    )
    rose_series_by_mode = _build_rose_series_by_mode(
        mode_series=mode_series,
        sections=sections,
    )
    keywords_by_mode = _empty_keywords_by_mode(submissions)
    average_keywords_by_mode = _empty_average_keywords_by_mode()
    duration_ms = int((time.perf_counter() - started) * 1000)
    solution_content, solution_generation_mode, solution_generation_warning, external_trends_status = (
        _build_precomputed_solution_fields(
            sections=sections,
            summaries=summaries,
            voc_summary=voc_summary,
            settings=settings,
        )
    )
    return AnalysisRun(
        sections=sections,
        instructors=summaries,
        warnings=_dedupe_messages(
            list(warnings) + ["커버리지 분석 자료가 없어 VOC 결과만 생성했습니다."]
        ),
        scorer_mode=scorer_mode,
        duration_ms=duration_ms,
        course={
            "id": course_id,
            "name": course_name,
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "description": section.description,
                    "target_weight": section.target_weight,
                }
                for section in sections
            ],
        },
        available_source_modes=available_source_modes,
        source_mode_stats=source_mode_stats,
        mode_unmapped_series=mode_unmapped_series,
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        average_keywords_by_mode=average_keywords_by_mode,
        keywords_by_instructor=keywords_by_mode.get("combined", {}),
        keywords_by_mode=keywords_by_mode,
        rose_series_by_instructor=rose_series_by_mode.get("combined", {}),
        rose_series_by_mode=rose_series_by_mode,
        line_series_by_mode=line_series_by_mode,
        insights=[],
        voc_summary=voc_summary,
        insight_generation_mode="deterministic-fallback",
        solution_content=solution_content,
        solution_generation_mode=solution_generation_mode,
        solution_generation_warning=solution_generation_warning,
        external_trends_status=external_trends_status,
    )


def _attach_voc_to_summaries(
    *,
    summaries: list[InstructorSummary],
    submissions: list[InstructorSubmission],
    voc_analyses_by_instructor: dict[str, dict],
) -> list[InstructorSummary]:
    voc_counts = {submission.name: len(submission.voc_files) for submission in submissions}
    return [
        replace(
            summary,
            voc_file_count=voc_counts.get(summary.name, 0),
            voc_analysis=voc_analyses_by_instructor.get(summary.name, {}),
        )
        for summary in summaries
    ]


def _empty_keywords_by_mode(submissions: list[InstructorSubmission]) -> dict[str, dict[str, list[dict]]]:
    payload: dict[str, dict[str, list[dict]]] = {}
    for mode in RESULT_MODES:
        payload[mode] = {}
        for submission in submissions:
            payload[mode][submission.name] = []
    return payload


def _empty_average_keywords_by_mode() -> dict[str, list[dict]]:
    return {mode: [] for mode in RESULT_MODES}


def _estimate_voc_response_count(source_type: str, segments: list) -> int:
    if source_type in {"csv", "xlsx", "xls"}:
        return len(segments)
    if source_type == "text":
        return sum(max(1, len([line for line in segment.text.split("|") if line.strip()])) for segment in segments)
    return len(segments)


def _empty_voc_text_analysis() -> dict:
    return {
        "sentiment": {"positive": [], "negative": []},
        "repeated_complaints": [],
        "next_suggestions": [],
    }


def _aggregate_question_scores(question_score_batches: list[list[dict]]) -> list[dict]:
    aggregates: dict[tuple[str, str, str, int], dict] = {}
    order: list[tuple[str, str, str, int]] = []

    for batch in question_score_batches:
        for item in batch:
            question_id = str(item.get("question_id", "")).strip().upper()
            group = str(item.get("group", "")).strip().upper()
            label = normalize_text(str(item.get("label", "")).strip())
            scale_max = int(item.get("scale_max", 5) or 5)
            response_count = max(0, int(item.get("response_count", 0) or 0))
            average = float(item.get("average", 0.0) or 0.0)
            if not question_id or not label or response_count <= 0:
                continue
            key = (group or question_id, question_id, label, scale_max)
            if key not in aggregates:
                aggregates[key] = {
                    "question_id": question_id,
                    "group": group or question_id,
                    "label": label,
                    "scale_max": scale_max,
                    "response_count": 0,
                    "total_score": 0.0,
                }
                order.append(key)
            aggregates[key]["response_count"] += response_count
            aggregates[key]["total_score"] += average * response_count

    payload: list[dict] = []
    for key in order:
        item = aggregates[key]
        response_count = int(item["response_count"])
        if response_count <= 0:
            continue
        payload.append(
            {
                "question_id": item["question_id"],
                "group": item["group"],
                "label": item["label"],
                "average": round(float(item["total_score"]) / response_count, 2),
                "response_count": response_count,
                "scale_max": int(item["scale_max"]),
            }
        )
    return payload


def _generate_voc_analysis(
    *,
    instructor_name: str,
    segments: list,
    settings: Settings,
) -> tuple[dict, str | None]:
    lines = [normalize_text(segment.text) for segment in segments if normalize_text(segment.text)]
    if not lines:
        return _empty_voc_text_analysis(), None
    fallback = _fallback_voc_analysis(lines)
    if not settings.openai_api_key or OpenAI is None:
        return fallback, None

    client = OpenAI(api_key=settings.openai_api_key)
    compact_text = "\n".join(lines[:120])
    try:
        response = client.chat.completions.create(
            model=settings.openai_insight_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 교육 과정 VOC 분석가입니다. 강의 평가서 내용을 읽고 JSON만 반환하세요. "
                        "반환 형식은 sentiment, repeated_complaints, next_suggestions 필드를 반드시 포함해야 합니다. "
                        "positive와 negative는 짧은 한국어 키워드 배열이고, complaints는 최대 3개, suggestions는 최대 3개만 반환하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"강사명: {instructor_name}\n"
                        "아래 VOC를 분석해서 JSON만 반환하세요.\n"
                        f"{compact_text[:12000]}"
                    ),
                },
            ],
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        return _normalize_voc_analysis_payload(raw, fallback), None
    except Exception as exc:  # noqa: BLE001
        return fallback, f"VOC LLM 분석에 실패해 규칙 기반 결과를 사용했습니다. ({exc})"


def _normalize_voc_analysis_payload(raw: dict, fallback: dict) -> dict:
    sentiment = raw.get("sentiment", {}) if isinstance(raw, dict) else {}
    complaints = raw.get("repeated_complaints", []) if isinstance(raw, dict) else []
    suggestions = raw.get("next_suggestions", []) if isinstance(raw, dict) else []

    normalized = {
        "sentiment": {
            "positive": [str(item).strip() for item in sentiment.get("positive", []) if str(item).strip()][:6],
            "negative": [str(item).strip() for item in sentiment.get("negative", []) if str(item).strip()][:6],
        },
        "repeated_complaints": [
            {
                "pattern": str(item.get("pattern", "")).strip(),
                "count": max(1, int(item.get("count", 1))),
                "week": str(item.get("week", "")).strip(),
            }
            for item in complaints
            if isinstance(item, dict) and str(item.get("pattern", "")).strip()
        ][:3],
        "next_suggestions": [
            {
                "priority": str(item.get("priority", "low")).strip().lower() or "low",
                "label": str(item.get("label", "")).strip(),
                "body": str(item.get("body", "")).strip(),
            }
            for item in suggestions
            if isinstance(item, dict) and str(item.get("label", "")).strip() and str(item.get("body", "")).strip()
        ][:3],
    }

    if not normalized["sentiment"]["positive"]:
        normalized["sentiment"]["positive"] = fallback["sentiment"]["positive"]
    if not normalized["sentiment"]["negative"]:
        normalized["sentiment"]["negative"] = fallback["sentiment"]["negative"]
    if not normalized["repeated_complaints"]:
        normalized["repeated_complaints"] = fallback["repeated_complaints"]
    if not normalized["next_suggestions"]:
        normalized["next_suggestions"] = fallback["next_suggestions"]
    return normalized


def _fallback_voc_analysis(lines: list[str]) -> dict:
    combined = " ".join(lines)
    tokens = tokenize(combined)
    token_counts = Counter(tokens)

    positive_counts: Counter[str] = Counter()
    negative_counts: Counter[str] = Counter()
    complaint_counts: Counter[str] = Counter()
    complaint_weeks: dict[str, str] = {}

    for line in lines:
        for needle, label in VOC_POSITIVE_HINTS.items():
            if needle in line:
                positive_counts[label] += 1
        for needle, label in VOC_NEGATIVE_HINTS.items():
            if needle in line:
                negative_counts[label] += 1
        for label, needles in VOC_NEGATIVE_RULES:
            if any(needle in line for needle in needles):
                complaint_counts[label] += 1
                complaint_weeks.setdefault(label, _extract_voc_week(line))

    positive = [label for label, _count in positive_counts.most_common(4)]
    negative = [label for label, _count in negative_counts.most_common(4)]
    if not positive:
        positive = [token for token, _count in token_counts.most_common(4)]
    if not negative:
        negative = ["강의 속도", "자료 부족"] if lines else []

    repeated_complaints = [
        {
            "pattern": label,
            "count": count,
            "week": complaint_weeks.get(label, ""),
        }
        for label, count in complaint_counts.most_common(3)
    ]
    if not repeated_complaints and negative:
        repeated_complaints = [
            {
                "pattern": f"{negative[0]} 관련 피드백 반복",
                "count": max(1, len(lines) // 3),
                "week": "",
            }
        ]

    next_suggestions = []
    for complaint in repeated_complaints:
        suggestion = VOC_SUGGESTION_MAP.get(complaint["pattern"])
        if suggestion:
            next_suggestions.append(suggestion)
    if not next_suggestions:
        next_suggestions = [
            {
                "priority": "medium",
                "label": "VOC 정기 점검",
                "body": "반복 피드백이 쌓이는 구간을 기준으로 수업 속도와 자료 구성을 다시 점검해 보세요.",
            }
        ]

    return {
        "sentiment": {
            "positive": positive[:4],
            "negative": negative[:4],
        },
        "repeated_complaints": repeated_complaints[:3],
        "next_suggestions": next_suggestions[:3],
    }


def _build_voc_summary(analyses: dict[str, dict]) -> dict:
    positive_counts: Counter[str] = Counter()
    negative_counts: Counter[str] = Counter()
    complaint_counts: Counter[str] = Counter()
    complaint_weeks: dict[str, str] = {}
    suggestion_counts: Counter[str] = Counter()
    suggestion_payloads: dict[str, dict] = {}
    question_score_batches: list[list[dict]] = []

    for analysis in analyses.values():
        sentiment = analysis.get("sentiment", {})
        positive_counts.update(sentiment.get("positive", []))
        negative_counts.update(sentiment.get("negative", []))
        question_score_batches.append(list(analysis.get("question_scores", []) or []))
        for item in analysis.get("repeated_complaints", []):
            pattern = str(item.get("pattern", "")).strip()
            if not pattern:
                continue
            complaint_counts[pattern] += int(item.get("count", 1) or 1)
            complaint_weeks.setdefault(pattern, str(item.get("week", "")).strip())
        for item in analysis.get("next_suggestions", []):
            label = str(item.get("label", "")).strip()
            body = str(item.get("body", "")).strip()
            if not label or not body:
                continue
            suggestion_counts[label] += 1
            suggestion_payloads.setdefault(
                label,
                {
                    "priority": str(item.get("priority", "low")).strip().lower() or "low",
                    "label": label,
                    "body": body,
                },
            )

    return {
        "question_scores": _aggregate_question_scores(question_score_batches),
        "positive": [label for label, _count in positive_counts.most_common(6)],
        "negative": [label for label, _count in negative_counts.most_common(6)],
        "repeated_complaints": [
            {
                "pattern": pattern,
                "count": count,
                "week": complaint_weeks.get(pattern, ""),
            }
            for pattern, count in complaint_counts.most_common(4)
        ],
        "next_suggestions": [
            suggestion_payloads[label]
            for label, _count in suggestion_counts.most_common(4)
            if label in suggestion_payloads
        ],
    }


def _extract_voc_week(text: str) -> str:
    match = VOC_WEEK_RE.search(str(text or ""))
    return match.group(1) if match else ""


def _dedupe_messages(messages: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for message in messages:
        normalized = str(message or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def parse_curriculum_sections(curriculum_text: str, max_sections: int) -> list[CurriculumSection]:
    lines = [normalize_text(line) for line in curriculum_text.splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < 2:
        raise ValueError("표준 커리큘럼은 최소 2개 이상의 대단원을 입력해 주세요.")
    if len(lines) > max_sections:
        raise ValueError(f"표준 커리큘럼은 최대 {max_sections}개까지만 입력할 수 있습니다.")

    sections: list[CurriculumSection] = []
    used_ids: set[str] = set()

    for raw_line in lines:
        line = SECTION_LINE_RE.sub("", raw_line)
        title, description = _split_curriculum_line(line)
        section_id = slugify(title)
        if section_id in used_ids:
            section_id = f"{section_id}-{len(used_ids) + 1}"
        used_ids.add(section_id)
        sections.append(CurriculumSection(id=section_id, title=title, description=description))

    return _normalize_target_weights(sections)


def _emit_progress(progress_callback, **payload) -> None:
    if callable(progress_callback):
        progress_callback(**payload)


def _build_progress_context(
    *,
    expanded_video_count: int,
    processed_video_count: int,
    caption_success_count: int,
    caption_failure_count: int,
) -> dict[str, int]:
    return {
        "expanded_video_count": int(expanded_video_count),
        "processed_video_count": int(processed_video_count),
        "caption_success_count": int(caption_success_count),
        "caption_failure_count": int(caption_failure_count),
    }


def _emit_phase_progress(
    progress_callback,
    *,
    phase: str,
    progress_current: int,
    progress_total: int,
    progress_context: dict[str, int] | None = None,
) -> None:
    payload = {
        "phase": phase,
        "progress_current": int(progress_current),
        "progress_total": max(1, int(progress_total)),
    }
    if progress_context:
        payload.update(progress_context)
    _emit_progress(progress_callback, **payload)


def _build_lexical_index(sections: list[CurriculumSection]) -> dict:
    section_assignment_texts = _build_section_assignment_texts(sections)
    return {
        "section_counters": {
            section.id: Counter(tokenize(section_assignment_texts[section.id])) for section in sections
        },
        "section_titles": {section.id: set(tokenize(section.title)) for section in sections},
    }


def _init_mode_aggregates(sections: list[CurriculumSection], submissions: list[InstructorSubmission]) -> dict:
    section_ids = [section.id for section in sections]
    return {
        mode: {
            submission.name: {
                "total_tokens": 0,
                "unmapped_tokens": 0,
                "section_tokens": {section_id: 0 for section_id in section_ids},
            }
            for submission in submissions
        }
        for mode in RESULT_MODES
    }


def _stream_segments_into_aggregates(
    *,
    segments: list,
    instructor_name: str,
    settings: Settings,
    sections: list[CurriculumSection],
    lexical_index: dict,
    dedupe_seen: set[tuple[str, str]],
    mode_aggregates: dict,
    evidence_map: dict,
    keyword_counters_by_mode: dict[str, dict[str, Counter[str]]],
    off_curriculum_counters_by_mode: dict[str, dict[str, Counter[str]]],
    keyword_documents_by_mode: dict[str, list[set[str]]],
    off_curriculum_keyword_documents_by_mode: dict[str, list[set[str]]],
    curriculum_tokens: set[str],
    max_evidence: int,
    progress_callback=None,
    progress_state: dict[str, int] | None = None,
    progress_context: dict[str, int] | None = None,
) -> tuple[int, list[str]]:
    removed_duplicates = 0
    warnings: list[str] = []
    warning_keys: set[tuple[str, str]] = set()
    chunks = _build_chunks_for_source_segments(segments, settings)
    if progress_state is not None and chunks:
        progress_state["total"] = int(progress_state.get("total", 0)) + len(chunks)
        _emit_phase_progress(
            progress_callback,
            phase="assigning",
            progress_current=int(progress_state.get("current", 0)),
            progress_total=int(progress_state.get("total", 0)),
            progress_context=progress_context,
        )
    for chunk in chunks:
        dedupe_key = (chunk.instructor_name, chunk.fingerprint)
        if dedupe_key in dedupe_seen:
            removed_duplicates += 1
            if progress_state is not None:
                progress_state["current"] = int(progress_state.get("current", 0)) + 1
                _emit_phase_progress(
                    progress_callback,
                    phase="assigning",
                    progress_current=int(progress_state.get("current", 0)),
                    progress_total=int(progress_state.get("total", 0)),
                    progress_context=progress_context,
                )
            continue
        dedupe_seen.add(dedupe_key)

        assignment, title_warning = _assign_chunk_lexical(chunk, sections, lexical_index, settings)
        keyword_counts = _keyword_counter_for_text(chunk.text)
        off_curriculum_counts = Counter(
            {
                token: value
                for token, value in keyword_counts.items()
                if token not in curriculum_tokens
            }
        )
        for mode in _modes_for_source_type(chunk.source_type):
            if keyword_counts:
                keyword_counters_by_mode[mode][instructor_name].update(keyword_counts)
                keyword_documents_by_mode[mode].append(set(keyword_counts))
            if off_curriculum_counts:
                off_curriculum_counters_by_mode[mode][instructor_name].update(off_curriculum_counts)
                off_curriculum_keyword_documents_by_mode[mode].append(set(off_curriculum_counts))
            aggregate = mode_aggregates[mode][instructor_name]
            aggregate["total_tokens"] += chunk.token_count
            if assignment.is_unmapped:
                aggregate["unmapped_tokens"] += chunk.token_count
            else:
                aggregate["section_tokens"][assignment.section_id] += chunk.token_count
        if not assignment.is_unmapped and max_evidence > 0:
            bucket = evidence_map[instructor_name][assignment.section_id]
            bucket.append(assignment)
            bucket.sort(key=lambda item: (item.score, item.chunk.token_count), reverse=True)
            del bucket[max_evidence:]
        if title_warning:
            warning_key = (chunk.source_label, title_warning)
            if warning_key not in warning_keys:
                warning_keys.add(warning_key)
                warnings.append(title_warning)
        if progress_state is not None:
            progress_state["current"] = int(progress_state.get("current", 0)) + 1
            _emit_phase_progress(
                progress_callback,
                phase="assigning",
                progress_current=int(progress_state.get("current", 0)),
                progress_total=int(progress_state.get("total", 0)),
                progress_context=progress_context,
            )
    return removed_duplicates, warnings


def _modes_for_source_type(source_type: str) -> list[str]:
    if source_type in MATERIAL_SOURCE_TYPES:
        return ["combined", "material"]
    if source_type in SPEECH_SOURCE_TYPES:
        return ["combined", "speech"]
    return ["combined"]


def _assign_chunk_lexical(chunk, sections, lexical_index: dict, settings: Settings) -> tuple[ChunkAssignment, str | None]:
    section_counters = lexical_index["section_counters"]
    section_titles = lexical_index["section_titles"]
    chunk_counter = Counter(tokenize(chunk.text))
    chunk_tokens = set(chunk_counter)
    scored = _score_sections_lexical(
        sections=sections,
        text_counter=chunk_counter,
        text_tokens=chunk_tokens,
        section_counters=section_counters,
        section_titles=section_titles,
    )
    transcript_scored = list(scored)
    title_warning = None
    if chunk.source_type in MATERIAL_SOURCE_TYPES:
        scored = _restrict_scored_sections_to_candidates(
            scored=scored,
            candidate_ids=_material_candidate_section_ids(
                material_anchor_counts=_material_anchor_counts_by_section(
                    chunk=chunk,
                    sections=sections,
                )
            ),
        )
    elif chunk.source_type in SPEECH_SOURCE_TYPES:
        transcript_anchor_counts = _speech_transcript_anchor_counts_by_section(
            chunk=chunk,
            sections=sections,
        )
        candidate_ids = _speech_transcript_candidate_section_ids(
            transcript_anchor_counts=transcript_anchor_counts,
            sections=sections,
        )
        title_scored = _score_speech_title_sections(
            sections=sections,
            source_label=chunk.source_label,
        )
        if title_scored:
            scored, title_warning = _apply_speech_title_prior(
                chunk=chunk,
                transcript_scored=transcript_scored,
                title_scored=title_scored,
                transcript_anchor_counts=transcript_anchor_counts,
                min_score=0.07,
                min_margin=0.01,
            )
            rescue_section_id, _ = _resolve_speech_title_rescue(
                chunk=chunk,
                transcript_scored=transcript_scored,
                title_scored=title_scored,
                transcript_anchor_counts=transcript_anchor_counts,
                min_score=0.07,
                min_margin=0.01,
            )
            if rescue_section_id:
                candidate_ids.add(rescue_section_id)
            scored = _restrict_scored_sections_to_candidates(
                scored=scored,
                candidate_ids=candidate_ids,
            )
            return (
                _rescue_speech_assignment(
                    chunk=chunk,
                    sections=sections,
                    transcript_scored=transcript_scored,
                    scored=scored,
                    candidate_ids=candidate_ids,
                    transcript_anchor_counts=transcript_anchor_counts,
                    settings=settings,
                    min_score=0.07,
                    min_margin=0.01,
                ),
                title_warning,
            )

    return _best_assignment(chunk, scored, min_score=0.07, min_margin=0.01), title_warning


def _build_summaries_from_aggregates(
    *,
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    combined_aggregates: dict,
    evidence_map: dict,
    instructor_assets: dict[str, int],
    instructor_warnings: dict[str, list[str]],
) -> list[InstructorSummary]:
    summaries: list[InstructorSummary] = []
    average_shares: dict[str, float] = {}

    for submission in submissions:
        aggregate = combined_aggregates.get(
            submission.name,
            {"total_tokens": 0, "unmapped_tokens": 0, "section_tokens": {}},
        )
        total_tokens = int(aggregate.get("total_tokens", 0))
        unmapped_tokens = int(aggregate.get("unmapped_tokens", 0))
        mapped_tokens = max(total_tokens - unmapped_tokens, 0)
        section_tokens = aggregate.get("section_tokens", {})
        coverages: list[SectionCoverage] = []

        for section in sections:
            token_count_value = int(section_tokens.get(section.id, 0))
            share = (token_count_value / mapped_tokens) if mapped_tokens else 0.0
            coverages.append(
                SectionCoverage(
                    section_id=section.id,
                    section_title=section.title,
                    token_count=token_count_value,
                    token_share=share,
                    evidence_snippets=[
                        EvidenceSnippet(
                            source_label=evidence.chunk.source_label,
                            locator=evidence.chunk.locator,
                            text=safe_snippet(evidence.chunk.text),
                            score=evidence.score,
                        )
                        for evidence in evidence_map.get(submission.name, {}).get(section.id, [])
                    ],
                )
            )

        summaries.append(
            InstructorSummary(
                name=submission.name,
                total_tokens=total_tokens,
                asset_count=instructor_assets.get(submission.name, 0),
                section_coverages=coverages,
                unmapped_tokens=unmapped_tokens,
                unmapped_share=(unmapped_tokens / total_tokens) if total_tokens else 0.0,
                warnings=instructor_warnings.get(submission.name, []),
            )
        )

    for section in sections:
        shares = [
            next((coverage.token_share for coverage in summary.section_coverages if coverage.section_id == section.id), 0.0)
            for summary in summaries
        ]
        average_shares[section.id] = mean(shares) if shares else 0.0

    for summary in summaries:
        for coverage in summary.section_coverages:
            coverage.deviation_from_average = coverage.token_share - average_shares[coverage.section_id]

    return summaries


def _build_mode_series_from_aggregates(
    *,
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    mode_aggregates: dict,
) -> tuple[dict, dict, dict, list[str], dict, dict]:
    mode_series: dict[str, dict] = {}
    average_series_by_mode: dict[str, list[dict]] = {}
    line_series_by_mode: dict[str, dict] = {}
    source_mode_stats: dict[str, dict[str, int]] = {}
    mode_unmapped_series: dict[str, dict] = {}
    asset_counts = _count_source_assets_by_mode(submissions)

    for mode in RESULT_MODES:
        aggregates = mode_aggregates.get(mode, {})
        average_values: list[dict] = []
        instructor_values: dict[str, list[dict]] = {}

        for submission in submissions:
            aggregate = aggregates.get(
                submission.name,
                {
                    "total_tokens": 0,
                    "unmapped_tokens": 0,
                    "section_tokens": {section.id: 0 for section in sections},
                },
            )
            total_tokens = int(aggregate.get("total_tokens", 0))
            unmapped_tokens = int(aggregate.get("unmapped_tokens", 0))
            mapped_tokens = max(total_tokens - unmapped_tokens, 0)
            section_tokens = aggregate.get("section_tokens", {})
            instructor_values[submission.name] = [
                {
                    "section_id": section.id,
                    "section_title": section.title,
                    "share": round((int(section_tokens.get(section.id, 0)) / mapped_tokens), 6) if mapped_tokens else 0.0,
                }
                for section in sections
            ]

        for section in sections:
            shares = [
                next(
                    (item["share"] for item in instructor_values.get(submission.name, []) if item["section_id"] == section.id),
                    0.0,
                )
                for submission in submissions
            ]
            average_values.append(
                {
                    "section_id": section.id,
                    "section_title": section.title,
                    "share": round(mean(shares), 6) if shares else 0.0,
                }
            )

        mode_series[mode] = {
            "average": average_values,
            "instructors": instructor_values,
        }
        mode_unmapped_series[mode] = {
            "average": round(
                mean(
                    [
                        (
                            int(aggregates.get(submission.name, {}).get("unmapped_tokens", 0))
                            / int(aggregates.get(submission.name, {}).get("total_tokens", 0))
                        )
                        if int(aggregates.get(submission.name, {}).get("total_tokens", 0)) > 0
                        else 0.0
                        for submission in submissions
                    ]
                ),
                6,
            )
            if submissions
            else 0.0,
            "instructors": {
                submission.name: round(
                    (
                        int(aggregates.get(submission.name, {}).get("unmapped_tokens", 0))
                        / int(aggregates.get(submission.name, {}).get("total_tokens", 0))
                    ),
                    6,
                )
                if int(aggregates.get(submission.name, {}).get("total_tokens", 0)) > 0
                else 0.0
                for submission in submissions
            },
        }
        average_series_by_mode[mode] = average_values
        line_series_by_mode[mode] = {
            "target": [
                {
                    "section_id": section.id,
                    "section_title": section.title,
                    "share": round(section.target_weight / 100, 6),
                }
                for section in sections
            ],
            "instructors": instructor_values,
        }
        source_mode_stats[mode] = {
            "asset_count": int(asset_counts.get(mode, 0)),
            "total_tokens": sum(
                int(aggregates.get(submission.name, {}).get("total_tokens", 0))
                for submission in submissions
            ),
            "mapped_tokens": sum(
                max(
                    int(aggregates.get(submission.name, {}).get("total_tokens", 0))
                    - int(aggregates.get(submission.name, {}).get("unmapped_tokens", 0)),
                    0,
                )
                for submission in submissions
            ),
        }

    available_source_modes = [
        mode for mode in RESULT_MODES if _mode_has_available_source(source_mode_stats.get(mode))
    ]
    return (
        mode_series,
        average_series_by_mode,
        line_series_by_mode,
        available_source_modes,
        source_mode_stats,
        mode_unmapped_series,
    )


def _keyword_counter_for_text(text: str) -> Counter[str]:
    raw_counts = Counter(tokenize_keywords(text))
    weighted = Counter()
    for token, count in raw_counts.items():
        weighted[token] = count * 2 if count >= 3 else count
    return weighted


def _apply_current_run_tfidf_weights(
    counts: Counter[str],
    documents: list[set[str]],
    *,
    min_docs: int = 3,
) -> Counter[str]:
    if not counts or len(documents) < min_docs:
        return Counter(counts)

    document_frequencies: Counter[str] = Counter()
    for document in documents:
        document_frequencies.update(document)

    document_total = len(documents)
    weighted = Counter()
    for token, value in counts.items():
        df = document_frequencies.get(token, 0)
        idf = math.log((1 + document_total) / (1 + df)) + 1.0
        weighted[token] = value * idf
    return weighted


def _build_keywords_from_counters(
    grouped: dict[str, Counter[str]],
    grouped_off_curriculum: dict[str, Counter[str]],
    documents: list[set[str]] | None = None,
    off_curriculum_documents: list[set[str]] | None = None,
) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    keywords: dict[str, list[dict]] = {}
    off_curriculum_keywords: dict[str, list[dict]] = {}
    for instructor_name, counts in grouped.items():
        off_counts = grouped_off_curriculum.get(instructor_name, Counter())

        tfidf_counts = _apply_current_run_tfidf_weights(counts, documents or [])
        tfidf_off_counts = _apply_current_run_tfidf_weights(
            off_counts,
            off_curriculum_documents or [],
        )

        # 커리큘럼 기반 단어에 가중치 크게 부여
        boosted = Counter()
        for token, score in tfidf_counts.items():
            if token not in off_counts:
                boosted[token] = score * 5
            else:
                boosted[token] = score

        ranked_tokens = sorted(
            boosted.items(),
            key=lambda item: (-item[1], item[0]),
        )
        best_tokens = [
            token
            for token, _ in ranked_tokens
            if counts.get(token, 0) >= 2
        ][:25]
        if len(best_tokens) < min(8, len(ranked_tokens)):
            seen = set(best_tokens)
            for token, _ in ranked_tokens:
                if token in seen:
                    continue
                seen.add(token)
                best_tokens.append(token)
                if len(best_tokens) >= 25:
                    break

        keywords[instructor_name] = [
            {"text": token, "value": int(counts[token])}
            for token in best_tokens
        ]

        ranked_off_curriculum = sorted(
            tfidf_off_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        top_off_curriculum = [
            token
            for token, _ in ranked_off_curriculum
            if off_counts.get(token, 0) >= 2
        ][:15]
        if len(top_off_curriculum) < min(5, len(ranked_off_curriculum)):
            seen_off = set(top_off_curriculum)
            for token, _ in ranked_off_curriculum:
                if token in seen_off:
                    continue
                seen_off.add(token)
                top_off_curriculum.append(token)
                if len(top_off_curriculum) >= 15:
                    break
        off_curriculum_keywords[instructor_name] = [
            {"text": token, "value": int(off_counts.get(token, 0))}
            for token in top_off_curriculum
        ]
    return keywords, off_curriculum_keywords


def _build_average_keywords(keyword_lists_by_instructor: dict[str, list[dict]]) -> list[dict]:
    instructor_names = [name for name in keyword_lists_by_instructor if name]
    if not instructor_names:
        return []
    if len(instructor_names) == 1:
        return [
            {
                "text": str(item.get("text", "")),
                "value": int(item.get("value", 0)),
            }
            for item in keyword_lists_by_instructor.get(instructor_names[0], [])[:25]
        ]

    totals: Counter[str] = Counter()
    for keyword_items in keyword_lists_by_instructor.values():
        for item in keyword_items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            totals[text] += int(item.get("value", 0))

    return [
        {"text": text, "value": int(value)}
        for text, value in sorted(
            totals.items(),
            key=lambda item: (-item[1], item[0]),
        )[:25]
    ]


def _build_keywords_by_mode_from_counters(
    *,
    grouped_by_mode: dict[str, dict[str, Counter[str]]],
    grouped_off_curriculum_by_mode: dict[str, dict[str, Counter[str]]],
    documents_by_mode: dict[str, list[set[str]]] | None = None,
    off_curriculum_documents_by_mode: dict[str, list[set[str]]] | None = None,
) -> tuple[dict[str, dict[str, list[dict]]], dict[str, dict[str, list[dict]]], dict[str, list[dict]]]:
    keywords_by_mode: dict[str, dict[str, list[dict]]] = {}
    off_curriculum_keywords_by_mode: dict[str, dict[str, list[dict]]] = {}
    average_keywords_by_mode: dict[str, list[dict]] = {}
    for mode in RESULT_MODES:
        keywords, off_curriculum = _build_keywords_from_counters(
            grouped_by_mode.get(mode, {}),
            grouped_off_curriculum_by_mode.get(mode, {}),
            documents=(documents_by_mode or {}).get(mode, []),
            off_curriculum_documents=(off_curriculum_documents_by_mode or {}).get(mode, []),
        )
        keywords_by_mode[mode] = keywords
        off_curriculum_keywords_by_mode[mode] = off_curriculum
        average_keywords_by_mode[mode] = _build_average_keywords(keywords)
    return keywords_by_mode, off_curriculum_keywords_by_mode, average_keywords_by_mode


def _normalize_target_weights(sections: list[CurriculumSection]) -> list[CurriculumSection]:
    if not sections:
        return []

    normalized = [
        CurriculumSection(
            id=section.id,
            title=section.title,
            description=section.description,
            target_weight=max(0.0, float(section.target_weight or 0.0)),
        )
        for section in sections
    ]
    total = sum(section.target_weight for section in normalized)
    if total <= 0:
        even_weight = round(100 / len(normalized), 2)
        for section in normalized:
            section.target_weight = even_weight
        _rebalance_last_weight(normalized)
        return normalized

    running_total = 0.0
    for section in normalized:
        section.target_weight = round(section.target_weight / total * 100, 2)
        running_total += section.target_weight
    _rebalance_last_weight(normalized, running_total)
    return normalized


def _split_curriculum_line(line: str) -> tuple[str, str]:
    for separator in ("|", "::", " - ", ":"):
        if separator in line:
            title, description = [part.strip() for part in line.split(separator, maxsplit=1)]
            if title:
                return title, description or title
    return line, line


def _dedupe_chunks(chunks):
    seen: dict[tuple[str, str], str] = {}
    deduped = []
    warnings: list[str] = []
    removed = 0

    for chunk in chunks:
        key = (chunk.instructor_name, chunk.fingerprint)
        if key in seen:
            removed += 1
            continue
        seen[key] = chunk.id
        deduped.append(chunk)

    if removed:
        warnings.append(f"반복 텍스트 청크 {removed}개를 중복 제거했습니다.")

    return deduped, warnings


def _build_chunks_for_source_segments(segments, settings: Settings):
    if not segments:
        return []
    source_type = str(getattr(segments[0], "source_type", "") or "").lower()
    if source_type in MATERIAL_SOURCE_TYPES:
        return build_preserved_segment_chunks(
            segments,
            target_tokens=settings.chunk_target_tokens,
        )
    if source_type in SPEECH_SOURCE_TYPES:
        prepared_segments = _prepare_speech_segments(list(segments))
        if not prepared_segments:
            return []
        return build_chunks(
            prepared_segments,
            target_tokens=max(18, min(settings.chunk_target_tokens, SPEECH_SUBCHUNK_MAX_TOKENS)),
            overlap_segments=0,
        )
    return build_chunks(
        segments,
        target_tokens=settings.chunk_target_tokens,
        overlap_segments=settings.chunk_overlap_segments,
    )


def _assign_chunks(
    chunks,
    sections,
    settings: Settings,
    *,
    progress_callback=None,
    progress_context: dict[str, int] | None = None,
):
    if settings.openai_api_key and OpenAI is not None:
        try:
            assignments, assignment_warnings = _assign_with_openai(
                chunks,
                sections,
                settings,
                progress_callback=progress_callback,
                progress_context=progress_context,
            )
            return assignments, "openai-embeddings", assignment_warnings
        except Exception as exc:  # noqa: BLE001
            warning = f"OpenAI 임베딩 호출에 실패해 lexical similarity로 fallback 했습니다. ({exc})"
            assignments, assignment_warnings = _assign_with_lexical(
                chunks,
                sections,
                settings,
                progress_callback=progress_callback,
                progress_context=progress_context,
            )
            return assignments, "lexical-fallback", [warning, *assignment_warnings]

    assignments, assignment_warnings = _assign_with_lexical(
        chunks,
        sections,
        settings,
        progress_callback=progress_callback,
        progress_context=progress_context,
    )
    return assignments, "lexical", assignment_warnings


def _assign_with_lexical(
    chunks,
    sections,
    settings: Settings,
    *,
    progress_callback=None,
    progress_context: dict[str, int] | None = None,
):
    section_assignment_texts = _build_section_assignment_texts(sections)
    section_counters = {
        section.id: Counter(tokenize(section_assignment_texts[section.id])) for section in sections
    }
    section_titles = {section.id: set(tokenize(section.title)) for section in sections}
    assignments = []
    warnings: list[str] = []
    warning_keys: set[tuple[str, str]] = set()
    speech_title_scores = {
        chunk.source_label: _score_speech_title_sections(
            sections=sections,
            source_label=chunk.source_label,
        )
        for chunk in chunks
        if chunk.source_type in SPEECH_SOURCE_TYPES and _speech_title_text(chunk.source_label)
    }

    _emit_phase_progress(
        progress_callback,
        phase="assigning",
        progress_current=0,
        progress_total=len(chunks),
        progress_context=progress_context,
    )
    for index, chunk in enumerate(chunks, start=1):
        chunk_counter = Counter(tokenize(chunk.text))
        chunk_tokens = set(chunk_counter)
        scored = _score_sections_lexical(
            sections=sections,
            text_counter=chunk_counter,
            text_tokens=chunk_tokens,
            section_counters=section_counters,
            section_titles=section_titles,
        )
        transcript_scored = list(scored)
        title_warning = None
        if chunk.source_type in MATERIAL_SOURCE_TYPES:
            scored = _restrict_scored_sections_to_candidates(
                scored=scored,
                candidate_ids=_material_candidate_section_ids(
                    material_anchor_counts=_material_anchor_counts_by_section(
                        chunk=chunk,
                        sections=sections,
                    )
                ),
            )
        elif chunk.source_type in SPEECH_SOURCE_TYPES:
            transcript_anchor_counts = _speech_transcript_anchor_counts_by_section(
                chunk=chunk,
                sections=sections,
            )
            candidate_ids = _speech_transcript_candidate_section_ids(
                transcript_anchor_counts=transcript_anchor_counts,
                sections=sections,
            )
            title_scored = speech_title_scores.get(chunk.source_label) or []
            if title_scored:
                scored, title_warning = _apply_speech_title_prior(
                    chunk=chunk,
                    transcript_scored=transcript_scored,
                    title_scored=title_scored,
                    transcript_anchor_counts=transcript_anchor_counts,
                    min_score=0.07,
                    min_margin=0.01,
                )
                rescue_section_id, _ = _resolve_speech_title_rescue(
                    chunk=chunk,
                    transcript_scored=transcript_scored,
                    title_scored=title_scored,
                    transcript_anchor_counts=transcript_anchor_counts,
                    min_score=0.07,
                    min_margin=0.01,
                )
                if rescue_section_id:
                    candidate_ids.add(rescue_section_id)
            scored = _restrict_scored_sections_to_candidates(
                scored=scored,
                candidate_ids=candidate_ids,
            )
            assignments.append(
                _rescue_speech_assignment(
                    chunk=chunk,
                    sections=sections,
                    transcript_scored=transcript_scored,
                    scored=scored,
                    candidate_ids=candidate_ids,
                    transcript_anchor_counts=transcript_anchor_counts,
                    settings=settings,
                    min_score=0.07,
                    min_margin=0.01,
                )
            )
            if title_warning:
                warning_key = (chunk.source_label, title_warning)
                if warning_key not in warning_keys:
                    warning_keys.add(warning_key)
                    warnings.append(title_warning)
            _emit_phase_progress(
                progress_callback,
                phase="assigning",
                progress_current=index,
                progress_total=len(chunks),
                progress_context=progress_context,
            )
            continue
        assignments.append(_best_assignment(chunk, scored, min_score=0.07, min_margin=0.01))
        if title_warning:
            warning_key = (chunk.source_label, title_warning)
            if warning_key not in warning_keys:
                warning_keys.add(warning_key)
                warnings.append(title_warning)
        _emit_phase_progress(
            progress_callback,
            phase="assigning",
            progress_current=index,
            progress_total=len(chunks),
            progress_context=progress_context,
        )

    return assignments, warnings


def _assign_with_openai(
    chunks,
    sections,
    settings: Settings,
    *,
    progress_callback=None,
    progress_context: dict[str, int] | None = None,
):
    client = OpenAI(api_key=settings.openai_api_key)
    section_assignment_texts = _build_section_assignment_texts(sections)
    section_inputs = [section_assignment_texts[section.id] for section in sections]
    chunk_inputs = [chunk.text for chunk in chunks]
    section_batches = _build_embedding_batches(section_inputs)
    chunk_batches = _build_embedding_batches(chunk_inputs)
    embedding_progress_state = {
        "current": 0,
        "total": len(section_batches) + len(chunk_batches),
    }
    _emit_phase_progress(
        progress_callback,
        phase="embedding",
        progress_current=0,
        progress_total=int(embedding_progress_state["total"]),
        progress_context=progress_context,
    )
    section_vectors = _embed_batches(
        client,
        section_batches,
        settings.openai_embedding_model,
        progress_callback=progress_callback,
        progress_state=embedding_progress_state,
        progress_context=progress_context,
    )
    chunk_vectors = _embed_batches(
        client,
        chunk_batches,
        settings.openai_embedding_model,
        progress_callback=progress_callback,
        progress_state=embedding_progress_state,
        progress_context=progress_context,
    )
    assignments = []
    warnings: list[str] = []
    warning_keys: set[tuple[str, str]] = set()
    speech_title_scores = {
        chunk.source_label: _score_speech_title_sections(
            sections=sections,
            source_label=chunk.source_label,
        )
        for chunk in chunks
        if chunk.source_type in SPEECH_SOURCE_TYPES and _speech_title_text(chunk.source_label)
    }

    _emit_phase_progress(
        progress_callback,
        phase="assigning",
        progress_current=0,
        progress_total=len(chunks),
        progress_context=progress_context,
    )
    for index, (chunk, chunk_vector) in enumerate(zip(chunks, chunk_vectors, strict=True), start=1):
        scored = _score_sections_openai(
            sections=sections,
            text_vector=chunk_vector,
            section_vectors=section_vectors,
        )
        transcript_scored = list(scored)
        title_warning = None
        if chunk.source_type in MATERIAL_SOURCE_TYPES:
            scored = _restrict_scored_sections_to_candidates(
                scored=scored,
                candidate_ids=_material_candidate_section_ids(
                    material_anchor_counts=_material_anchor_counts_by_section(
                        chunk=chunk,
                        sections=sections,
                    )
                ),
            )
        elif chunk.source_type in SPEECH_SOURCE_TYPES:
            transcript_anchor_counts = _speech_transcript_anchor_counts_by_section(
                chunk=chunk,
                sections=sections,
            )
            candidate_ids = _speech_transcript_candidate_section_ids(
                transcript_anchor_counts=transcript_anchor_counts,
                sections=sections,
            )
            title_scored = speech_title_scores.get(chunk.source_label) or []
            if title_scored:
                scored, title_warning = _apply_speech_title_prior(
                    chunk=chunk,
                    transcript_scored=transcript_scored,
                    title_scored=title_scored,
                    transcript_anchor_counts=transcript_anchor_counts,
                    min_score=0.23,
                    min_margin=0.025,
                )
                rescue_section_id, _ = _resolve_speech_title_rescue(
                    chunk=chunk,
                    transcript_scored=transcript_scored,
                    title_scored=title_scored,
                    transcript_anchor_counts=transcript_anchor_counts,
                    min_score=0.23,
                    min_margin=0.025,
                )
                if rescue_section_id:
                    candidate_ids.add(rescue_section_id)
            scored = _restrict_scored_sections_to_candidates(
                scored=scored,
                candidate_ids=candidate_ids,
            )
            assignments.append(
                _rescue_speech_assignment(
                    chunk=chunk,
                    sections=sections,
                    transcript_scored=transcript_scored,
                    scored=scored,
                    candidate_ids=candidate_ids,
                    transcript_anchor_counts=transcript_anchor_counts,
                    settings=settings,
                    min_score=0.23,
                    min_margin=0.025,
                )
            )
            if title_warning:
                warning_key = (chunk.source_label, title_warning)
                if warning_key not in warning_keys:
                    warning_keys.add(warning_key)
                    warnings.append(title_warning)
            _emit_phase_progress(
                progress_callback,
                phase="assigning",
                progress_current=index,
                progress_total=len(chunks),
                progress_context=progress_context,
            )
            continue
        assignments.append(_best_assignment(chunk, scored, min_score=0.23, min_margin=0.025))
        if title_warning:
            warning_key = (chunk.source_label, title_warning)
            if warning_key not in warning_keys:
                warning_keys.add(warning_key)
                warnings.append(title_warning)
        _emit_phase_progress(
            progress_callback,
            phase="assigning",
            progress_current=index,
            progress_total=len(chunks),
            progress_context=progress_context,
        )

    return assignments, warnings


def _score_sections_lexical(
    *,
    sections: list[CurriculumSection],
    text_counter: Counter[str],
    text_tokens: set[str],
    section_counters: dict[str, Counter[str]],
    section_titles: dict[str, set[str]],
) -> list[tuple[CurriculumSection, float]]:
    scored = []
    for section in sections:
        cosine = cosine_similarity(text_counter, section_counters[section.id])
        title_tokens = section_titles[section.id]
        title_overlap = len(text_tokens & title_tokens) / max(1, len(title_tokens))
        score = (cosine * 0.75) + (title_overlap * 0.25)
        scored.append((section, score))
    return scored


def _score_sections_openai(
    *,
    sections: list[CurriculumSection],
    text_vector: list[float],
    section_vectors: list[list[float]],
) -> list[tuple[CurriculumSection, float]]:
    scored = []
    for section, section_vector in zip(sections, section_vectors, strict=True):
        score = _vector_cosine(text_vector, section_vector)
        scored.append((section, max(0.0, score)))
    return scored


def _build_embedding_batches(texts: list[str]) -> list[list[str]]:
    if not texts:
        return []
    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_batch_tokens = 0
    for text in texts:
        estimated_tokens = max(1, count_tokens(text))
        if current_batch and (current_batch_tokens + estimated_tokens > 120000 or len(current_batch) >= 128):
            batches.append(current_batch)
            current_batch = []
            current_batch_tokens = 0
        current_batch.append(text)
        current_batch_tokens += estimated_tokens
    if current_batch:
        batches.append(current_batch)
    return batches


def _embed_batches(
    client,  # noqa: ANN001
    batches: list[list[str]],
    model: str,
    *,
    progress_callback=None,
    progress_state: dict[str, int] | None = None,
    progress_context: dict[str, int] | None = None,
):
    vectors: list[list[float]] = []
    for batch in batches:
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend(item.embedding for item in response.data)
        if progress_state is not None:
            progress_state["current"] = int(progress_state.get("current", 0)) + 1
            _emit_phase_progress(
                progress_callback,
                phase="embedding",
                progress_current=int(progress_state.get("current", 0)),
                progress_total=int(progress_state.get("total", 0)),
                progress_context=progress_context,
            )
    return vectors


def _embed_texts(
    client,
    texts: list[str],
    model: str,
    *,
    progress_callback=None,
    progress_state: dict[str, int] | None = None,
    progress_context: dict[str, int] | None = None,
):  # noqa: ANN001
    batches = _build_embedding_batches(texts)
    return _embed_batches(
        client,
        batches,
        model,
        progress_callback=progress_callback,
        progress_state=progress_state,
        progress_context=progress_context,
    )


def _vector_cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _best_assignment(chunk, scored, min_score: float, min_margin: float):
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    best_section, best_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < min_score or (best_score - runner_up_score) < min_margin:
        return ChunkAssignment(
            chunk=chunk,
            section_id=None,
            section_title="Other / Unmapped",
            score=best_score,
            runner_up_score=runner_up_score,
            rationale_short="여러 대단원과 비슷하거나 분류 근거가 약해 보류되었습니다.",
        )

    return ChunkAssignment(
        chunk=chunk,
        section_id=best_section.id,
        section_title=best_section.title,
        score=best_score,
        runner_up_score=runner_up_score,
        rationale_short=f"{best_section.title}와의 유사도가 가장 높습니다.",
    )


def _build_instructor_summaries(
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    assignments: list[ChunkAssignment],
    instructor_assets: dict[str, int],
    instructor_warnings: dict[str, list[str]],
    max_evidence: int,
    allowed_source_types: set[str] | None = None,
) -> list[InstructorSummary]:
    grouped_assignments: dict[str, list[ChunkAssignment]] = defaultdict(list)
    for assignment in assignments:
        if allowed_source_types is not None and assignment.chunk.source_type not in allowed_source_types:
            continue
        grouped_assignments[assignment.chunk.instructor_name].append(assignment)

    summaries: list[InstructorSummary] = []
    average_shares: dict[str, float] = {}

    for submission in submissions:
        instructor_assignments = grouped_assignments.get(submission.name, [])
        total_tokens = sum(assignment.chunk.token_count for assignment in instructor_assignments)
        section_tokens = defaultdict(int)
        evidence_map: dict[str, list[ChunkAssignment]] = defaultdict(list)
        unmapped_tokens = 0

        for assignment in instructor_assignments:
            if assignment.is_unmapped:
                unmapped_tokens += assignment.chunk.token_count
                continue
            section_tokens[assignment.section_id] += assignment.chunk.token_count
            evidence_map[assignment.section_id].append(assignment)

        mapped_tokens = max(total_tokens - unmapped_tokens, 0)

        coverages: list[SectionCoverage] = []
        for section in sections:
            token_count_value = section_tokens[section.id]
            share = (token_count_value / mapped_tokens) if mapped_tokens else 0.0
            ranked_evidence = sorted(
                evidence_map[section.id],
                key=lambda item: (item.score, item.chunk.token_count),
                reverse=True,
            )[:max_evidence]
            coverages.append(
                SectionCoverage(
                    section_id=section.id,
                    section_title=section.title,
                    token_count=token_count_value,
                    token_share=share,
                    evidence_snippets=[
                        EvidenceSnippet(
                            source_label=evidence.chunk.source_label,
                            locator=evidence.chunk.locator,
                            text=safe_snippet(evidence.chunk.text),
                            score=evidence.score,
                        )
                        for evidence in ranked_evidence
                    ],
                )
            )

        summaries.append(
            InstructorSummary(
                name=submission.name,
                total_tokens=total_tokens,
                asset_count=instructor_assets.get(submission.name, 0),
                section_coverages=coverages,
                unmapped_tokens=unmapped_tokens,
                unmapped_share=(unmapped_tokens / total_tokens) if total_tokens else 0.0,
                warnings=instructor_warnings.get(submission.name, []),
            )
        )

    for section in sections:
        section_values = []
        for summary in summaries:
            for coverage in summary.section_coverages:
                if coverage.section_id == section.id:
                    section_values.append(coverage.token_share)
                    break
        average_shares[section.id] = mean(section_values) if section_values else 0.0

    for summary in summaries:
        for coverage in summary.section_coverages:
            coverage.deviation_from_average = coverage.token_share - average_shares[coverage.section_id]

    return summaries


def _build_mode_series(
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    assignments: list[ChunkAssignment],
) -> tuple[dict, dict, dict, list[str], dict, dict]:
    mode_series: dict[str, dict] = {}
    average_series_by_mode: dict[str, list[dict]] = {}
    line_series_by_mode: dict[str, dict] = {}
    source_mode_stats: dict[str, dict[str, int]] = {}
    mode_unmapped_series: dict[str, dict] = {}
    asset_counts = _count_source_assets_by_mode(submissions)

    for mode, allowed_types in MODE_SOURCE_FILTERS.items():
        summaries = _build_instructor_summaries(
            sections=sections,
            submissions=submissions,
            assignments=assignments,
            instructor_assets=defaultdict(int),
            instructor_warnings=defaultdict(list),
            max_evidence=0,
            allowed_source_types=allowed_types,
        )
        average_values: list[dict] = []
        instructor_values: dict[str, list[dict]] = {}
        for section in sections:
            shares = [
                next(
                    (coverage.token_share for coverage in summary.section_coverages if coverage.section_id == section.id),
                    0.0,
                )
                for summary in summaries
            ]
            average_values.append(
                {
                    "section_id": section.id,
                    "section_title": section.title,
                    "share": round(mean(shares), 6) if shares else 0.0,
                }
            )

        for summary in summaries:
            instructor_values[summary.name] = [
                {
                    "section_id": coverage.section_id,
                    "section_title": coverage.section_title,
                    "share": round(coverage.token_share, 6),
                }
                for coverage in summary.section_coverages
            ]

        mode_series[mode] = {
            "average": average_values,
            "instructors": instructor_values,
        }
        mode_unmapped_series[mode] = {
            "average": round(mean([summary.unmapped_share for summary in summaries]), 6) if summaries else 0.0,
            "instructors": {
                summary.name: round(summary.unmapped_share, 6)
                for summary in summaries
            },
        }
        average_series_by_mode[mode] = average_values
        line_series_by_mode[mode] = {
            "target": [
                {
                    "section_id": section.id,
                    "section_title": section.title,
                    "share": round(section.target_weight / 100, 6),
                }
                for section in sections
            ],
            "instructors": instructor_values,
        }
        source_mode_stats[mode] = {
            "asset_count": int(asset_counts.get(mode, 0)),
            "total_tokens": sum(int(summary.total_tokens) for summary in summaries),
            "mapped_tokens": sum(
                max(int(summary.total_tokens) - int(summary.unmapped_tokens), 0)
                for summary in summaries
            ),
        }

    available_source_modes = [
        mode for mode in RESULT_MODES if _mode_has_available_source(source_mode_stats.get(mode))
    ]
    return (
        mode_series,
        average_series_by_mode,
        line_series_by_mode,
        available_source_modes,
        source_mode_stats,
        mode_unmapped_series,
    )


def _count_source_assets_by_mode(submissions: list[InstructorSubmission]) -> dict[str, int]:
    material_asset_count = sum(len(submission.files) for submission in submissions)
    speech_asset_count = sum(len(submission.youtube_urls) for submission in submissions)
    return {
        "combined": material_asset_count + speech_asset_count,
        "material": material_asset_count,
        "speech": speech_asset_count,
    }


def _mode_has_available_source(stats: dict | None) -> bool:
    if not isinstance(stats, dict):
        return False
    return int(stats.get("asset_count", 0)) > 0 and int(stats.get("total_tokens", 0)) > 0


def _build_keywords_by_instructor(chunks, sections: list[CurriculumSection]) -> dict[str, list[dict]]:
    return _build_keyword_payloads_by_mode(chunks, sections)[0].get("combined", {})


def _build_keywords_by_mode(chunks, sections: list[CurriculumSection]) -> dict[str, dict[str, list[dict]]]:
    return _build_keyword_payloads_by_mode(chunks, sections)[0]


def _build_keyword_payloads_by_mode(
    chunks,
    sections: list[CurriculumSection],
) -> tuple[dict[str, dict[str, list[dict]]], dict[str, dict[str, list[dict]]], dict[str, list[dict]]]:
    curriculum_tokens = set()
    for section in sections:
        curriculum_tokens.update(tokenize_keywords(section.search_text))

    grouped_by_mode: dict[str, dict[str, Counter[str]]] = {
        mode: defaultdict(Counter) for mode in RESULT_MODES
    }
    grouped_off_curriculum_by_mode: dict[str, dict[str, Counter[str]]] = {
        mode: defaultdict(Counter) for mode in RESULT_MODES
    }
    documents_by_mode: dict[str, list[set[str]]] = {
        mode: [] for mode in RESULT_MODES
    }
    off_curriculum_documents_by_mode: dict[str, list[set[str]]] = {
        mode: [] for mode in RESULT_MODES
    }
    for chunk in chunks:
        keyword_counts = _keyword_counter_for_text(chunk.text)
        if not keyword_counts:
            continue

        off_curriculum_counts = Counter(
            {
                token: value
                for token, value in keyword_counts.items()
                if token not in curriculum_tokens
            }
        )
        keyword_document = set(keyword_counts)
        off_curriculum_document = set(off_curriculum_counts)

        for mode in _modes_for_source_type(chunk.source_type):
            grouped_by_mode[mode][chunk.instructor_name].update(keyword_counts)
            grouped_off_curriculum_by_mode[mode][chunk.instructor_name].update(off_curriculum_counts)
            documents_by_mode[mode].append(keyword_document)
            if off_curriculum_document:
                off_curriculum_documents_by_mode[mode].append(off_curriculum_document)

    return _build_keywords_by_mode_from_counters(
        grouped_by_mode=grouped_by_mode,
        grouped_off_curriculum_by_mode=grouped_off_curriculum_by_mode,
        documents_by_mode=documents_by_mode,
        off_curriculum_documents_by_mode=off_curriculum_documents_by_mode,
    )


def _build_rose_series(summaries: list[InstructorSummary]) -> dict[str, list[dict]]:
    return {
        summary.name: [
            {
                "name": coverage.section_title,
                "value": round(coverage.token_share * 100, 2),
                "section_id": coverage.section_id,
            }
            for coverage in summary.section_coverages
        ]
        for summary in summaries
    }


def _build_rose_series_by_mode(
    *,
    mode_series: dict[str, dict],
    sections: list[CurriculumSection],
) -> dict[str, dict[str, list[dict]]]:
    section_titles = {section.id: section.title for section in sections}
    rose_by_mode: dict[str, dict[str, list[dict]]] = {}
    for mode in RESULT_MODES:
        instructor_series = mode_series.get(mode, {}).get("instructors", {})
        rose_by_mode[mode] = {
            instructor_name: [
                {
                    "name": item.get("section_title") or section_titles.get(item.get("section_id", ""), ""),
                    "value": round(float(item.get("share", 0.0)) * 100, 2),
                    "section_id": item.get("section_id"),
                }
                for item in series_items
            ]
            for instructor_name, series_items in instructor_series.items()
        }
    return rose_by_mode


def _build_insights(
    *,
    course_name: str,
    sections: list[CurriculumSection],
    summaries: list[InstructorSummary],
    average_series_by_mode: dict[str, list[dict]],
    keywords_by_instructor: dict[str, list[dict]],
    off_curriculum_keywords_by_instructor: dict[str, list[dict]],
    settings: Settings,
) -> tuple[list[dict], str, list[str]]:
    metrics = _compute_insight_metrics(
        course_name=course_name,
        sections=sections,
        summaries=summaries,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        off_curriculum_keywords_by_instructor=off_curriculum_keywords_by_instructor,
    )
    fallback_cards = _deterministic_insight_cards(metrics)

    if not settings.openai_api_key or OpenAI is None:
        return fallback_cards, "deterministic-fallback", []

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        parsed = client.responses.parse(
            model=settings.openai_insight_model,
            instructions=(
                "You are generating concise Korean insight cards for an education curriculum coverage dashboard. "
                "Return exactly 5 cards. Be specific, practical, and grounded in the provided metrics. "
                "Do not invent unsupported facts."
            ),
            input=json.dumps(metrics, ensure_ascii=False),
            text_format=InsightBundleSchema,
            max_output_tokens=1200,
        )
        cards = [
            {
                "category": item.category,
                "title": item.title,
                "issue": item.issue,
                "evidence": item.evidence,
                "recommendation": item.recommendation,
                "icon": item.icon,
            }
            for item in parsed.output_parsed.cards
        ]
        if len(cards) != 5:
            raise ValueError("expected exactly 5 insight cards")
        return cards, f"llm:{settings.openai_insight_model}", []
    except Exception as exc:  # noqa: BLE001
        return (
            fallback_cards,
            "deterministic-fallback",
            [f"솔루션 인사이트 LLM 생성에 실패해 fallback 카드를 사용했습니다. ({exc})"],
        )


def _compute_insight_metrics(
    *,
    course_name: str,
    sections: list[CurriculumSection],
    summaries: list[InstructorSummary],
    average_series_by_mode: dict[str, list[dict]],
    keywords_by_instructor: dict[str, list[dict]],
    off_curriculum_keywords_by_instructor: dict[str, list[dict]],
) -> dict:
    target_map = {section.id: section.target_weight / 100 for section in sections}
    combined_average = {item["section_id"]: item["share"] for item in average_series_by_mode.get("combined", [])}

    strongest_target_gap = None
    strongest_avg_gap = None
    drift_gap = None

    for summary in summaries:
        total_abs_avg_gap = 0.0
        for coverage in summary.section_coverages:
            target_gap = coverage.token_share - target_map.get(coverage.section_id, 0.0)
            avg_gap = coverage.token_share - combined_average.get(coverage.section_id, 0.0)
            target_candidate = {
                "instructor": summary.name,
                "section_title": coverage.section_title,
                "actual_share": coverage.token_share,
                "target_share": target_map.get(coverage.section_id, 0.0),
                "gap": target_gap,
            }
            avg_candidate = {
                "instructor": summary.name,
                "section_title": coverage.section_title,
                "actual_share": coverage.token_share,
                "average_share": combined_average.get(coverage.section_id, 0.0),
                "gap": avg_gap,
            }
            if strongest_target_gap is None or abs(target_gap) > abs(strongest_target_gap["gap"]):
                strongest_target_gap = target_candidate
            if drift_gap is None or abs(combined_average.get(coverage.section_id, 0.0) - target_map.get(coverage.section_id, 0.0)) > abs(drift_gap["gap"]):
                drift_gap = {
                    "section_title": coverage.section_title,
                    "average_share": combined_average.get(coverage.section_id, 0.0),
                    "target_share": target_map.get(coverage.section_id, 0.0),
                    "gap": combined_average.get(coverage.section_id, 0.0) - target_map.get(coverage.section_id, 0.0),
                }
            total_abs_avg_gap += abs(avg_gap)
        if strongest_avg_gap is None or total_abs_avg_gap > strongest_avg_gap["total_abs_gap"]:
            strongest_avg_gap = {
                "instructor": summary.name,
                "total_abs_gap": total_abs_avg_gap,
            }

    individual_off_curriculum = []
    common_off_curriculum_counter: Counter[str] = Counter()
    for summary in summaries:
        off_curriculum = off_curriculum_keywords_by_instructor.get(summary.name, [])
        if off_curriculum:
            individual_off_curriculum.append(
                {
                    "instructor": summary.name,
                    "keywords": off_curriculum[:5],
                }
            )
            common_off_curriculum_counter.update(item["text"] for item in off_curriculum[:8])

    common_off_curriculum = [
        {"text": token, "count": count}
        for token, count in common_off_curriculum_counter.items()
        if count >= 2
    ]
    common_off_curriculum.sort(key=lambda item: (-item["count"], item["text"]))

    return {
        "course_name": course_name,
        "targets": [
            {"section_title": section.title, "target_share": round(section.target_weight / 100, 6)}
            for section in sections
        ],
        "strongest_target_gap": strongest_target_gap,
        "strongest_avg_gap": strongest_avg_gap,
        "curriculum_drift": drift_gap,
        "individual_off_curriculum": individual_off_curriculum,
        "common_off_curriculum": common_off_curriculum[:5],
    }


def _deterministic_insight_cards(metrics: dict) -> list[dict]:
    target_gap = metrics.get("strongest_target_gap") or {}
    avg_gap = metrics.get("strongest_avg_gap") or {}
    drift = metrics.get("curriculum_drift") or {}
    individual = metrics.get("individual_off_curriculum") or []
    common = metrics.get("common_off_curriculum") or []

    first_off_curriculum = individual[0] if individual else {"instructor": "특정 강사", "keywords": []}
    common_keywords_text = ", ".join(item["text"] for item in common[:3]) or "공통 외부 주제 없음"
    individual_keywords_text = ", ".join(item["text"] for item in first_off_curriculum.get("keywords", [])[:3]) or "특이 키워드 없음"

    return [
        {
            "category": "target-gap",
            "title": "목표 대비 가장 큰 비중 차이를 먼저 조정하세요",
            "issue": f"{target_gap.get('instructor', '특정 강사')} 강사는 `{target_gap.get('section_title', '특정 대주제')}`에서 목표 대비 차이가 가장 큽니다.",
            "evidence": f"실제 {round(target_gap.get('actual_share', 0) * 100, 1)}%, 목표 {round(target_gap.get('target_share', 0) * 100, 1)}%, 차이 {round(target_gap.get('gap', 0) * 100, 1)}%p",
            "recommendation": "해당 대주제의 강의 시간 배분과 자료 구성을 다시 맞추고, 부족/과잉 구간을 보강할 공통 가이드 자료를 제공하세요.",
            "icon": "target",
        },
        {
            "category": "avg-gap",
            "title": "평균 패턴에서 가장 벗어난 강사를 우선 코칭하세요",
            "issue": f"{avg_gap.get('instructor', '특정 강사')} 강사는 전체 강사 평균과의 편차 총합이 가장 큽니다.",
            "evidence": f"대주제별 평균 패턴과의 절대 편차 합이 가장 커 표준 강의 운영 흐름에서 가장 멀리 있습니다.",
            "recommendation": "평균 패턴과 크게 어긋나는 단원을 중심으로 강의 진행 순서와 강조 포인트를 표준안에 맞춰 재정렬하세요.",
            "icon": "users",
        },
        {
            "category": "off-curriculum-individual",
            "title": "개별 강사의 비공통 강조 주제를 점검하세요",
            "issue": f"{first_off_curriculum.get('instructor', '특정 강사')} 강사는 커리큘럼 바깥 키워드를 상대적으로 더 많이 강조합니다.",
            "evidence": f"대표 키워드: {individual_keywords_text}",
            "recommendation": "이 주제가 실제로 필요한 확장 학습인지, 아니면 표준 커리큘럼에서 벗어난 개인화 설명인지 구분하고 필요 시 별도 보충 자료로 분리하세요.",
            "icon": "spark",
        },
        {
            "category": "curriculum-drift",
            "title": "현장 평균과 다른 커리큘럼 목표치는 재설계 후보입니다",
            "issue": f"`{drift.get('section_title', '특정 대주제')}`는 전체 강사 평균과 목표 비중 사이 차이가 큽니다.",
            "evidence": f"강사 평균 {round(drift.get('average_share', 0) * 100, 1)}%, 목표 {round(drift.get('target_share', 0) * 100, 1)}%, 차이 {round(drift.get('gap', 0) * 100, 1)}%p",
            "recommendation": "실제 교육 현장에서 반복적으로 더 많은 시간이 필요한 주제라면, 차기 커리큘럼 개편 시 목표 비중 자체를 조정하세요.",
            "icon": "refresh",
        },
        {
            "category": "off-curriculum-common",
            "title": "여러 강사가 공통으로 다루는 외부 주제를 표준안에 반영하세요",
            "issue": "여러 강사가 커리큘럼 밖의 동일한 개념을 반복적으로 다루고 있습니다.",
            "evidence": f"공통 후보 키워드: {common_keywords_text}",
            "recommendation": "공통적으로 등장하는 주제는 현장 필요도가 높다는 뜻이므로, 정식 커리큘럼 부록이나 신규 단원으로 편입하는 방안을 검토하세요.",
            "icon": "lightbulb",
        },
    ]


def _rebalance_last_weight(sections: list[CurriculumSection], running_total: float | None = None) -> None:
    if not sections:
        return
    total = running_total if running_total is not None else sum(section.target_weight for section in sections)
    sections[-1].target_weight = round(sections[-1].target_weight + (100 - total), 2)
def _build_precomputed_solution_fields(
    *,
    sections: list[CurriculumSection],
    summaries: list[InstructorSummary],
    voc_summary: dict,
    settings: Settings,
) -> tuple[dict, str, str | None, str]:
    result_like = {
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "description": section.description,
                "target_weight": section.target_weight,
            }
            for section in sections
        ],
        "instructors": summaries,
        "voc_summary": voc_summary,
    }
    solution_payload = build_solution_payload(result_like)
    solution_content, solution_generation_mode, solution_generation_warning = generate_solution_content(
        solution_payload,
        settings,
    )
    return (
        solution_content,
        solution_generation_mode,
        solution_generation_warning,
        "reflected" if solution_content else "planned",
    )
