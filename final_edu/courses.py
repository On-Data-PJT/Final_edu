from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from final_edu.config import Settings
from final_edu.models import CourseRecord, CurriculumSection
from final_edu.storage import ObjectStorage
from final_edu.utils import normalize_text, slugify

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


def preview_course_pdf(path: Path, max_sections: int) -> dict:
    page_texts = []
    warnings: list[str] = []
    for index, page in enumerate(PdfReader(str(path)).pages, start=1):
        raw_text = page.extract_text() or ""
        if not raw_text.strip():
            warnings.append(f"p.{index}: 텍스트를 읽지 못했습니다.")
            continue
        page_texts.append(raw_text)

    raw_text = "\n".join(page_texts).strip()
    if not raw_text:
        return {
            "raw_curriculum_text": "",
            "sections": [section_to_dict(section) for section in _default_sections()],
            "warnings": warnings + ["커리큘럼 텍스트를 추출하지 못해 기본 섹션 초안을 생성했습니다."],
        }

    sections = _extract_sections_from_text(raw_text, max_sections)
    if not sections:
        sections = _default_sections()
        warnings.append("커리큘럼 구조를 명확히 추출하지 못해 기본 섹션 초안을 생성했습니다.")

    return {
        "raw_curriculum_text": raw_text,
        "sections": [section_to_dict(section) for section in sections],
        "warnings": warnings,
    }


def create_course_record(
    *,
    name: str,
    curriculum_pdf_path: Path,
    curriculum_pdf_name: str,
    sections_payload: list[dict],
    raw_curriculum_text: str,
    storage: ObjectStorage,
) -> CourseRecord:
    now = _now_iso()
    course_id = uuid.uuid4().hex[:12]
    storage_key = f"courses/{course_id}/curriculum/{uuid.uuid4().hex[:8]}-{Path(curriculum_pdf_name).name}"
    storage.put_file(storage_key, curriculum_pdf_path, content_type="application/pdf")
    sections = normalize_course_sections(sections_payload)
    return CourseRecord(
        id=course_id,
        name=name.strip() or "이름 없는 과정",
        curriculum_pdf_key=storage_key,
        sections=sections,
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
        target_weight = _safe_float(item.get("target_weight"), 0.0)
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
        total += max(0.0, target_weight)

    if not sections:
        return _default_sections()

    if total <= 0:
        even_weight = round(100 / len(sections), 2)
        for section in sections:
            section.target_weight = even_weight
        _rebalance_last_section(sections)
        return sections

    running_total = 0.0
    for section in sections:
        section.target_weight = round(max(0.0, section.target_weight) / total * 100, 2)
        running_total += section.target_weight

    if sections:
        sections[-1].target_weight = round(sections[-1].target_weight + (100 - running_total), 2)

    return sections


def section_to_dict(section: CurriculumSection) -> dict:
    return {
        "id": section.id,
        "title": section.title,
        "description": section.description,
        "target_weight": section.target_weight,
    }


def _extract_sections_from_text(raw_text: str, max_sections: int) -> list[CurriculumSection]:
    scored_lines: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    for index, raw_line in enumerate(raw_text.splitlines()):
        line = normalize_text(raw_line)
        if not line or len(line) < 4:
            continue
        if any(token in line for token in IGNORE_TOKENS):
            continue
        score = _line_score(raw_line, line)
        if score <= 0:
            continue
        fingerprint = line.lower()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        scored_lines.append((index, score, line))

    scored_lines.sort(key=lambda item: (-item[1], item[0]))
    chosen = sorted(scored_lines[:max_sections], key=lambda item: item[0])
    sections = [_section_from_line(line, order) for order, (_index, _score, line) in enumerate(chosen, start=1)]
    sections = [section for section in sections if section.title]

    if sections:
        _normalize_section_weights(sections)
        return sections

    fallback_lines = [
        normalize_text(part)
        for part in re.split(r"[\n\.]+", raw_text)
        if normalize_text(part)
    ]
    fallback_sections = [
        CurriculumSection(
            id=f"section-{index}",
            title=_trim_title(line),
            description=line,
            target_weight=1.0,
        )
        for index, line in enumerate(fallback_lines[: max(3, min(max_sections, 5))], start=1)
    ]
    if fallback_sections:
        _normalize_section_weights(fallback_sections)
    return fallback_sections


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


def _section_from_line(line: str, order: int) -> CurriculumSection:
    cleaned = NUMBER_PREFIX_RE.sub("", line).strip()
    metric_value = _extract_weight_metric(cleaned)
    parts = [part.strip() for part in SECTION_SPLIT_RE.split(cleaned, maxsplit=1)]
    if len(parts) == 2 and parts[0]:
        title, description = parts[0], parts[1] or parts[0]
    else:
        title = _trim_title(_strip_metric_tokens(cleaned))
        description = cleaned
    if not title:
        title = f"섹션 {order}"
    return CurriculumSection(
        id=f"section-{order}",
        title=title,
        description=description,
        target_weight=metric_value,
    )


def _extract_weight_metric(text: str) -> float:
    match = PERCENT_RE.search(text)
    if match:
        return float(match.group(1))
    for pattern in (TIME_RE, WEEK_RE, DAY_RE):
        metric_match = pattern.search(text)
        if metric_match:
            return float(metric_match.group(1))
    return 1.0


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


def _normalize_section_weights(sections: list[CurriculumSection]) -> None:
    total = sum(max(0.0, section.target_weight) for section in sections)
    if total <= 0:
        for section in sections:
            section.target_weight = 1.0
        total = float(len(sections))
    for section in sections:
        section.target_weight = round(max(0.0, section.target_weight) / total * 100, 2)
    _rebalance_last_section(sections)


def _rebalance_last_section(sections: list[CurriculumSection]) -> None:
    if not sections:
        return
    total = sum(section.target_weight for section in sections)
    sections[-1].target_weight = round(sections[-1].target_weight + (100 - total), 2)


def _default_sections() -> list[CurriculumSection]:
    sections = [
        CurriculumSection(id="foundation", title="도입 및 배경", description="과정 배경과 문제 맥락", target_weight=34.0),
        CurriculumSection(id="core", title="핵심 개념", description="핵심 이론과 개념 설명", target_weight=33.0),
        CurriculumSection(id="practice", title="실습 및 적용", description="예제와 실습 중심 적용", target_weight=33.0),
    ]
    _rebalance_last_section(sections)
    return sections


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
