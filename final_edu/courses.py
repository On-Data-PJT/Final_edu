from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing.
    OpenAI = None
from pydantic import BaseModel, Field
from pypdf import PdfReader

from final_edu.config import Settings
from final_edu.models import (
    CourseRecord,
    CurriculumPreviewEvidence,
    CurriculumPreviewResult,
    CurriculumPreviewSection,
    CurriculumSection,
)
from final_edu.storage import ObjectStorage
from final_edu.utils import build_safe_storage_name, normalize_text, slugify

NUMBER_PREFIX_RE = re.compile(r"^\s*(?:[-*]|\d+[\.\)]?)\s*")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:시간|시수|hr|hrs|hour|hours)")
WEEK_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:주차|주|weeks?)")
DAY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:일|days?)")
SECTION_SPLIT_RE = re.compile(r"[|:：]\s*")
IGNORE_TOKENS = (
    "강사",
    "평가",
    "교재",
    "비고",
    "운영",
    "공지",
    "문의",
    "출결",
    "과정명",
)
CURRICULUM_HINT_TOKENS = (
    "강의계획",
    "강의 계획",
    "강의개요",
    "커리큘럼",
    "교육목표",
    "학습목표",
    "과정개요",
    "교과목",
    "주차",
    "시수",
    "수업목표",
    "학습내용",
    "학습성과",
)
NON_CURRICULUM_HINT_TOKENS = (
    "이력서",
    "자기소개",
    "경력사항",
    "면접",
    "지원동기",
    "포트폴리오",
)
GENERIC_SECTION_TITLES = {
    "강의계획서",
    "강의 계획서",
    "강의계획안",
    "강의 계획안",
    "커리큘럼",
    "교육과정",
    "교육 계획",
}


class CurriculumClassificationEvidenceSchema(BaseModel):
    page: int | None = None
    snippet: str = ""
    reason: str = ""


class CurriculumClassificationSchema(BaseModel):
    document_kind: Literal["curriculum", "curriculum_like", "not_curriculum", "unreadable"]
    confidence: float = Field(ge=0.0, le=1.0)
    has_section_structure: bool = False
    has_explicit_weight_signals: bool = False
    has_derivable_weight_signals: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=6)
    blocking_reasons: list[str] = Field(default_factory=list, max_length=6)
    evidence: list[CurriculumClassificationEvidenceSchema] = Field(default_factory=list, max_length=6)


class CurriculumExtractionSectionSchema(BaseModel):
    title: str
    description: str
    source_pages: list[int] = Field(default_factory=list, max_length=6)
    source_snippets: list[str] = Field(default_factory=list, max_length=3)
    weight_source: Literal["percent", "hours", "weeks", "days", "none"] = "none"
    raw_weight_value: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CurriculumExtractionSchema(BaseModel):
    sections: list[CurriculumExtractionSectionSchema] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=8)


class LocalCourseRepository:
    def __init__(self, settings: Settings) -> None:
        self.root = settings.runtime_dir / "courses"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: CourseRecord) -> None:
        path = self.root / f"{record.id}.json"
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, course_id: str) -> CourseRecord | None:
        path = self.root / f"{course_id}.json"
        if not path.exists():
            return None
        return CourseRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_all(self) -> list[CourseRecord]:
        records = [
            CourseRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in self.root.glob("*.json")
        ]
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return records


def preview_course_pdf(path: Path, max_sections: int, settings: Settings) -> CurriculumPreviewResult:
    page_records, warnings = _extract_pdf_pages(path)
    raw_text = "\n".join(record["text"] for record in page_records).strip()
    if not raw_text:
        return CurriculumPreviewResult(
            decision="rejected",
            document_kind="unreadable",
            document_confidence=0.0,
            weight_status="missing",
            raw_curriculum_text="",
            warnings=warnings,
            blocking_reasons=["텍스트형 PDF가 아니어서 커리큘럼 구조를 읽지 못했습니다."],
        )

    preview = _preview_with_openai(page_records, raw_text, warnings, max_sections, settings)
    if preview is not None:
        return preview
    return _preview_without_openai(page_records, raw_text, warnings, max_sections)


def create_course_record(
    *,
    name: str,
    curriculum_pdf_path: Path,
    curriculum_pdf_name: str,
    sections_payload: list[dict],
    instructor_names: list[str],
    raw_curriculum_text: str,
    storage: ObjectStorage,
) -> CourseRecord:
    now = _now_iso()
    course_id = uuid.uuid4().hex[:12]
    safe_pdf_name = build_safe_storage_name(
        curriculum_pdf_name,
        default_stem="curriculum",
        default_ext=".pdf",
        max_basename_chars=72,
    )
    storage_key = f"courses/{course_id}/curriculum/{uuid.uuid4().hex[:8]}-{safe_pdf_name}"
    storage.put_file(storage_key, curriculum_pdf_path, content_type="application/pdf")
    sections = normalize_course_sections(sections_payload)
    return CourseRecord(
        id=course_id,
        name=name.strip() or "이름 없는 과정",
        curriculum_pdf_key=storage_key,
        sections=sections,
        instructor_names=[item for item in instructor_names if item],
        raw_curriculum_text=raw_curriculum_text,
        created_at=now,
        updated_at=now,
    )


def normalize_course_sections(sections_payload: list[dict]) -> list[CurriculumSection]:
    sections: list[CurriculumSection] = []
    used_ids: set[str] = set()
    total = 0.0

    for index, item in enumerate(sections_payload, start=1):
        title = normalize_text(str(item.get("title", "") or ""))
        description = normalize_text(str(item.get("description", "") or "")) or title
        if not title:
            continue
        raw_weight = item.get("target_weight")
        if raw_weight in {None, ""}:
            raise ValueError("대주제 비중을 모두 입력해 주세요.")
        target_weight = _safe_float(raw_weight, -1.0)
        if target_weight <= 0:
            raise ValueError("대주제 비중은 0보다 커야 합니다.")
        section_id = slugify(title)
        if not section_id or section_id in used_ids:
            section_id = f"section-{index}"
        used_ids.add(section_id)
        sections.append(
            CurriculumSection(
                id=section_id,
                title=title,
                description=description,
                target_weight=target_weight,
            )
        )
        total += target_weight

    if not sections:
        raise ValueError("저장 가능한 대주제 초안을 찾지 못했습니다.")
    if total <= 0:
        raise ValueError("대주제 비중을 모두 입력해 주세요.")

    running_total = 0.0
    for section in sections:
        section.target_weight = round(max(0.0, section.target_weight) / total * 100, 2)
        running_total += section.target_weight

    sections[-1].target_weight = round(sections[-1].target_weight + (100 - running_total), 2)
    return sections


def section_to_dict(section: CurriculumSection) -> dict:
    return {
        "id": section.id,
        "title": section.title,
        "description": section.description,
        "target_weight": section.target_weight,
    }


def _extract_pdf_pages(path: Path) -> tuple[list[dict], list[str]]:
    page_records: list[dict] = []
    warnings: list[str] = []
    for index, page in enumerate(PdfReader(str(path)).pages, start=1):
        raw_text = page.extract_text() or ""
        normalized = normalize_text(raw_text)
        if not normalized:
            warnings.append(f"p.{index}: 텍스트를 읽지 못했습니다.")
            continue
        page_records.append({"page": index, "text": normalized})
    return page_records, warnings


def _preview_with_openai(
    page_records: list[dict],
    raw_text: str,
    warnings: list[str],
    max_sections: int,
    settings: Settings,
) -> CurriculumPreviewResult | None:
    if not settings.openai_api_key or OpenAI is None:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    candidate_excerpt = _build_preview_candidate_excerpt(page_records, settings)
    if not candidate_excerpt:
        return CurriculumPreviewResult(
            decision="rejected",
            document_kind="unreadable",
            document_confidence=0.0,
            weight_status="missing",
            raw_curriculum_text=raw_text,
            warnings=warnings,
            blocking_reasons=["문서에서 커리큘럼 판단에 필요한 텍스트를 충분히 찾지 못했습니다."],
        )

    try:
        classification = client.responses.parse(
            model=settings.openai_curriculum_model,
            instructions=(
                "You validate whether a PDF text is a real course curriculum or syllabus. "
                "Reject resumes, interview materials, proposals, reports, admin notices, or generic documents. "
                "Return only facts grounded in the provided text. "
                "Mark unreadable when the text is too sparse or noisy to trust. "
                "Do not approve documents as curriculum unless there is clear course structure evidence."
            ),
            input=candidate_excerpt,
            text_format=CurriculumClassificationSchema,
            max_output_tokens=900,
        ).output_parsed
    except Exception as exc:  # noqa: BLE001
        fallback_warnings = list(warnings)
        fallback_warnings.append(f"커리큘럼 검증 API 호출에 실패해 검토 필요 모드로 전환했습니다. ({exc})")
        return _preview_without_openai(page_records, raw_text, fallback_warnings, max_sections)

    decision = _resolve_preview_decision(classification, settings)
    preview_warnings = list(warnings) + list(classification.warnings)
    blocking_reasons = list(classification.blocking_reasons)
    evidence = [
        CurriculumPreviewEvidence(page=item.page, snippet=item.snippet, reason=item.reason)
        for item in classification.evidence
        if item.snippet or item.reason
    ]

    if decision == "rejected":
        return CurriculumPreviewResult(
            decision=decision,
            document_kind=classification.document_kind,
            document_confidence=classification.confidence,
            weight_status="missing",
            raw_curriculum_text=raw_text,
            warnings=preview_warnings,
            blocking_reasons=blocking_reasons or ["커리큘럼 문서로 신뢰할 근거가 부족합니다."],
            evidence=evidence,
        )

    try:
        extracted = client.responses.parse(
            model=settings.openai_curriculum_model,
            instructions=(
                "Extract only trustworthy curriculum sections from the provided PDF text. "
                "Use explicit evidence. Do not invent missing sections. "
                "Ignore instructor bio, admin notices, evaluation, references, copyright, or personal profile content. "
                "Each section must have a concise title, a short description, source pages/snippets, and weight evidence when present. "
                "If weight evidence is absent for a section, set weight_source to 'none' and raw_weight_value to null."
            ),
            input=(
                f"Maximum sections: {max_sections}\n"
                "Extract curriculum sections only when they are explicitly supported.\n\n"
                f"{candidate_excerpt}"
            ),
            text_format=CurriculumExtractionSchema,
            max_output_tokens=1800,
        ).output_parsed
    except Exception as exc:  # noqa: BLE001
        preview_warnings.append(f"구조화 추출 API 호출에 실패해 검토 필요 모드로 전환했습니다. ({exc})")
        return _preview_without_openai(page_records, raw_text, preview_warnings, max_sections)

    preview_sections = _postprocess_extracted_sections(extracted.sections, max_sections)
    preview_warnings.extend(extracted.warnings)
    weight_status = _determine_weight_status(preview_sections)
    if not preview_sections:
        return CurriculumPreviewResult(
            decision="review_required",
            document_kind=classification.document_kind,
            document_confidence=classification.confidence,
            weight_status="missing",
            raw_curriculum_text=raw_text,
            warnings=preview_warnings,
            blocking_reasons=["대주제를 신뢰할 수준으로 추출하지 못했습니다. PDF를 교체하거나 직접 수정해 주세요."],
            evidence=evidence,
        )

    if weight_status in {"missing", "inconsistent"} and decision == "accepted":
        decision = "review_required"

    if decision == "review_required" and not blocking_reasons:
        blocking_reasons = ["자동 추출 결과를 그대로 저장하지 말고 대주제와 비중을 검토해 주세요."]

    return CurriculumPreviewResult(
        decision=decision,
        document_kind=classification.document_kind,
        document_confidence=classification.confidence,
        weight_status=weight_status,
        raw_curriculum_text=raw_text,
        sections=preview_sections,
        warnings=preview_warnings,
        blocking_reasons=blocking_reasons,
        evidence=evidence,
    )


def _preview_without_openai(
    page_records: list[dict],
    raw_text: str,
    warnings: list[str],
    max_sections: int,
) -> CurriculumPreviewResult:
    heuristic_sections = _extract_heuristic_sections(raw_text, max_sections)
    curriculum_score = _heuristic_curriculum_score(raw_text)
    if curriculum_score < 2 or not heuristic_sections:
        return CurriculumPreviewResult(
            decision="rejected",
            document_kind="not_curriculum",
            document_confidence=min(0.49, max(0.0, curriculum_score / 10)),
            weight_status="missing",
            raw_curriculum_text=raw_text,
            warnings=warnings + ["자동 검증 API를 사용하지 못해 신뢰할 수 있는 커리큘럼 판별을 완료하지 못했습니다."],
            blocking_reasons=["커리큘럼 문서로 확신할 수 없어 저장을 차단했습니다."],
        )

    preview_sections = _postprocess_extracted_sections(heuristic_sections, max_sections)
    weight_status = _determine_weight_status(preview_sections)
    review_reasons = ["자동 검증 API가 없어서 수동 검토 후 저장해야 합니다."]
    if weight_status in {"missing", "inconsistent"}:
        review_reasons.append("비중 근거가 충분하지 않아 목표 비중을 직접 입력해야 합니다.")
    return CurriculumPreviewResult(
        decision="review_required",
        document_kind="curriculum_like",
        document_confidence=min(0.74, 0.42 + (curriculum_score / 20)),
        weight_status=weight_status,
        raw_curriculum_text=raw_text,
        sections=preview_sections,
        warnings=warnings,
        blocking_reasons=review_reasons,
    )


def _build_preview_candidate_excerpt(page_records: list[dict], settings: Settings) -> str:
    candidate_lines: list[tuple[int, int, str]] = []
    for record in page_records:
        page = record["page"]
        for raw_line in record["text"].splitlines():
            line = normalize_text(raw_line)
            if not line or len(line) < 4:
                continue
            score = _candidate_line_score(raw_line, line)
            if score <= 0:
                continue
            candidate_lines.append((score, page, line))

    candidate_lines.sort(key=lambda item: (-item[0], item[1], item[2]))
    grouped: dict[int, list[str]] = {}
    char_budget = settings.curriculum_preview_max_chars
    for _score, page, line in candidate_lines:
        page_lines = grouped.setdefault(page, [])
        if line in page_lines or len(page_lines) >= 12:
            continue
        next_block = f"[p.{page}] {line}\n"
        if char_budget - len(next_block) < 0:
            break
        page_lines.append(line)
        char_budget -= len(next_block)

    if not grouped:
        for record in page_records[:4]:
            snippet = record["text"][: max(0, settings.curriculum_preview_max_chars // 4)]
            if snippet:
                grouped[record["page"]] = [snippet]

    parts: list[str] = []
    for page in sorted(grouped):
        parts.append(f"[Page {page}]")
        parts.extend(grouped[page])
        parts.append("")
    return "\n".join(parts).strip()


def _candidate_line_score(raw_line: str, line: str) -> int:
    score = _line_score(raw_line, line)
    lowered = line.lower()
    score += sum(3 for token in CURRICULUM_HINT_TOKENS if token in line)
    score -= sum(4 for token in NON_CURRICULUM_HINT_TOKENS if token in line)
    if "목표" in line or "개요" in line or "학습" in line:
        score += 2
    if len(lowered) > 120:
        score -= 1
    return score


def _resolve_preview_decision(
    classification: CurriculumClassificationSchema,
    settings: Settings,
) -> str:
    if classification.document_kind in {"not_curriculum", "unreadable"}:
        return "rejected"
    if classification.confidence < settings.curriculum_review_confidence:
        return "rejected"
    if (
        classification.confidence < settings.curriculum_accept_confidence
        or not classification.has_section_structure
        or not (classification.has_explicit_weight_signals or classification.has_derivable_weight_signals)
    ):
        return "review_required"
    return "accepted"


def _extract_heuristic_sections(raw_text: str, max_sections: int) -> list[CurriculumPreviewSection]:
    scored_lines: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    for index, raw_line in enumerate(raw_text.splitlines()):
        line = normalize_text(raw_line)
        if not line or len(line) < 4:
            continue
        if any(token in line for token in IGNORE_TOKENS):
            continue
        score = _candidate_line_score(raw_line, line)
        if score <= 1:
            continue
        fingerprint = line.lower()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        scored_lines.append((index, score, line))

    scored_lines.sort(key=lambda item: (-item[1], item[0]))
    chosen = sorted(scored_lines[:max_sections], key=lambda item: item[0])
    sections = [
        _heuristic_section_from_line(line, order)
        for order, (_index, _score, line) in enumerate(chosen, start=1)
    ]
    return [section for section in sections if section.title]


def _heuristic_curriculum_score(raw_text: str) -> int:
    score = 0
    lowered = raw_text.lower()
    for token in CURRICULUM_HINT_TOKENS:
        if token in raw_text:
            score += 2
    for token in NON_CURRICULUM_HINT_TOKENS:
        if token in raw_text:
            score -= 3
    if "주차" in raw_text or "시수" in raw_text:
        score += 3
    if "%" in raw_text:
        score += 2
    if "교과목" in raw_text or "과정" in raw_text:
        score += 1
    if lowered.count("면접") >= 2:
        score -= 4
    return score


def _postprocess_extracted_sections(
    sections: list[CurriculumExtractionSectionSchema | CurriculumPreviewSection],
    max_sections: int,
) -> list[CurriculumPreviewSection]:
    normalized: list[CurriculumPreviewSection] = []
    seen_titles: set[str] = set()

    for index, item in enumerate(sections[:max_sections], start=1):
        if isinstance(item, CurriculumPreviewSection):
            section = item
        else:
            raw_weight_value = float(item.raw_weight_value) if item.raw_weight_value is not None else None
            section = CurriculumPreviewSection(
                id=f"section-{index}",
                title=_trim_title(str(item.title or "")),
                description=normalize_text(item.description or item.title or ""),
                target_weight=raw_weight_value,
                weight_source=item.weight_source,
                raw_weight_value=raw_weight_value,
                confidence=float(item.confidence or 0.0),
                source_pages=[int(page) for page in item.source_pages if isinstance(page, int) or str(page).isdigit()],
                source_snippets=[normalize_text(snippet) for snippet in item.source_snippets if normalize_text(snippet)],
                needs_weight_input=item.weight_source == "none" or raw_weight_value is None,
            )
        if not section.title:
            continue
        if _is_generic_section_title(section.title):
            continue
        title_key = section.title.lower()
        if title_key in seen_titles:
            continue
        if not section.source_snippets:
            section.source_snippets = [section.description] if section.description else []
        if not section.source_snippets:
            continue
        seen_titles.add(title_key)
        section.id = section.id or f"section-{index}"
        normalized.append(section)

    if normalized and _determine_weight_status(normalized) in {"explicit", "derivable"}:
        _normalize_preview_weights(normalized)
    return normalized


def _determine_weight_status(sections: list[CurriculumPreviewSection]) -> str:
    if not sections:
        return "missing"
    source_kinds = {section.weight_source for section in sections}
    has_none = any(section.weight_source == "none" or section.raw_weight_value is None for section in sections)
    has_explicit = any(section.weight_source == "percent" for section in sections)
    has_derived = any(section.weight_source in {"hours", "weeks", "days"} for section in sections)
    if has_none and (has_explicit or has_derived):
        return "inconsistent"
    if has_none:
        return "missing"
    if has_explicit and not (source_kinds - {"percent"}):
        return "explicit"
    return "derivable"


def _heuristic_section_from_line(line: str, order: int) -> CurriculumPreviewSection:
    cleaned = NUMBER_PREFIX_RE.sub("", line).strip()
    raw_weight_value, weight_source = _extract_weight_metric(cleaned)
    parts = [part.strip() for part in SECTION_SPLIT_RE.split(cleaned, maxsplit=1)]
    if len(parts) == 2 and parts[0]:
        title, description = parts[0], parts[1] or parts[0]
    else:
        title = _trim_title(_strip_metric_tokens(cleaned))
        description = cleaned
    return CurriculumPreviewSection(
        id=f"section-{order}",
        title=title or f"섹션 {order}",
        description=description or title or f"섹션 {order}",
        target_weight=raw_weight_value,
        weight_source=weight_source,
        raw_weight_value=raw_weight_value,
        confidence=0.42,
        source_snippets=[cleaned],
        needs_weight_input=raw_weight_value is None,
    )


def _extract_weight_metric(text: str) -> tuple[float | None, str]:
    match = PERCENT_RE.search(text)
    if match:
        return float(match.group(1)), "percent"
    for pattern, label in (
        (TIME_RE, "hours"),
        (WEEK_RE, "weeks"),
        (DAY_RE, "days"),
    ):
        metric_match = pattern.search(text)
        if metric_match:
            return float(metric_match.group(1)), label
    return None, "none"


def _line_score(raw_line: str, line: str) -> int:
    score = 0
    if NUMBER_PREFIX_RE.match(raw_line):
        score += 4
    if PERCENT_RE.search(line):
        score += 5
    if TIME_RE.search(line):
        score += 4
    if WEEK_RE.search(line) or DAY_RE.search(line):
        score += 3
    if SECTION_SPLIT_RE.search(line):
        score += 2
    if len(line) <= 80:
        score += 1
    if 4 <= len(line.split()) <= 20:
        score += 1
    return score


def _strip_metric_tokens(text: str) -> str:
    cleaned = PERCENT_RE.sub("", text)
    cleaned = TIME_RE.sub("", cleaned)
    cleaned = WEEK_RE.sub("", cleaned)
    cleaned = DAY_RE.sub("", cleaned)
    return normalize_text(cleaned)


def _trim_title(text: str) -> str:
    text = _strip_metric_tokens(text)
    if len(text) <= 40:
        return text
    parts = [part.strip() for part in re.split(r"[,·\-–—]", text) if part.strip()]
    return parts[0] if parts else text[:40].strip()


def _is_generic_section_title(title: str) -> bool:
    normalized = normalize_text(title)
    return normalized in GENERIC_SECTION_TITLES


def _normalize_preview_weights(sections: list[CurriculumPreviewSection]) -> None:
    total = sum(max(0.0, float(section.raw_weight_value or 0.0)) for section in sections)
    if total <= 0:
        return
    running_total = 0.0
    for section in sections:
        section.target_weight = round(max(0.0, float(section.raw_weight_value or 0.0)) / total * 100, 2)
        section.needs_weight_input = False
        running_total += section.target_weight
    sections[-1].target_weight = round((sections[-1].target_weight or 0.0) + (100 - running_total), 2)


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
