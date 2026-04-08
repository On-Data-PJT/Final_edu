from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from statistics import mean

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing.
    OpenAI = None
from pydantic import BaseModel, Field

from final_edu.config import Settings
from final_edu.extractors import extract_file_asset, extract_youtube_asset
from final_edu.models import (
    AnalysisRun,
    ChunkAssignment,
    CurriculumSection,
    EvidenceSnippet,
    InstructorSubmission,
    InstructorSummary,
    SectionCoverage,
)
from final_edu.utils import (
    build_chunks,
    cosine_similarity,
    normalize_text,
    safe_snippet,
    slugify,
    tokenize,
)

SECTION_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+[\.\)]?)\s*")
MATERIAL_SOURCE_TYPES = {"pdf", "pptx", "text"}
SPEECH_SOURCE_TYPES = {"youtube"}


class InsightCardSchema(BaseModel):
    category: str
    title: str
    issue: str
    evidence: str
    recommendation: str
    icon: str = "lightbulb"


class InsightBundleSchema(BaseModel):
    cards: list[InsightCardSchema] = Field(min_length=5, max_length=5)


def analyze_submissions(
    *,
    course_id: str,
    course_name: str,
    sections: list[CurriculumSection],
    submissions: list[InstructorSubmission],
    settings: Settings,
) -> AnalysisRun:
    started = time.perf_counter()
    normalized_sections = _normalize_target_weights(sections)
    active_submissions = [submission for submission in submissions if submission.files or submission.youtube_urls]
    if len(active_submissions) < 2:
        raise ValueError("최소 2명의 강사 자료가 필요합니다.")

    all_chunks = []
    warnings: list[str] = []
    instructor_assets: dict[str, int] = defaultdict(int)
    instructor_warnings: dict[str, list[str]] = defaultdict(list)

    for submission in active_submissions:
        for upload in submission.files:
            source, segments, source_warnings = extract_file_asset(upload, submission.name)
            warnings.extend(source_warnings)
            instructor_warnings[submission.name].extend(source_warnings)
            if segments:
                instructor_assets[submission.name] += 1
                all_chunks.extend(
                    build_chunks(
                        segments,
                        target_tokens=settings.chunk_target_tokens,
                        overlap_segments=settings.chunk_overlap_segments,
                    )
                )

        for youtube_url in submission.youtube_urls:
            source, segments, source_warnings = extract_youtube_asset(youtube_url, submission.name)
            warnings.extend(source_warnings)
            instructor_warnings[submission.name].extend(source_warnings)
            if segments:
                instructor_assets[submission.name] += 1
                all_chunks.extend(
                    build_chunks(
                        segments,
                        target_tokens=settings.chunk_target_tokens,
                        overlap_segments=settings.chunk_overlap_segments,
                    )
                )

    deduped_chunks, dedupe_warnings = _dedupe_chunks(all_chunks)
    warnings.extend(dedupe_warnings)
    if not deduped_chunks:
        raise ValueError("분석 가능한 텍스트를 추출하지 못했습니다. 텍스트형 PDF/PPTX 또는 자막 있는 YouTube URL을 사용해 주세요.")

    assignments, scorer_mode, scorer_warnings = _assign_chunks(deduped_chunks, normalized_sections, settings)
    warnings.extend(scorer_warnings)
    summaries = _build_instructor_summaries(
        sections=normalized_sections,
        submissions=active_submissions,
        assignments=assignments,
        instructor_assets=instructor_assets,
        instructor_warnings=instructor_warnings,
        max_evidence=settings.max_evidence_per_section,
    )
    mode_series, average_series_by_mode, line_series_by_mode = _build_mode_series(
        sections=normalized_sections,
        submissions=active_submissions,
        assignments=assignments,
    )
    keywords_by_instructor = _build_keywords_by_instructor(
        chunks=deduped_chunks,
        sections=normalized_sections,
    )
    rose_series_by_instructor = _build_rose_series(summaries)
    insights, insight_generation_mode, insight_warnings = _build_insights(
        course_name=course_name,
        sections=normalized_sections,
        summaries=summaries,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        settings=settings,
    )
    warnings.extend(insight_warnings)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisRun(
        sections=normalized_sections,
        instructors=summaries,
        warnings=warnings,
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
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        rose_series_by_instructor=rose_series_by_instructor,
        line_series_by_mode=line_series_by_mode,
        insights=insights,
        insight_generation_mode=insight_generation_mode,
        external_trends_status="planned",
    )


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


def _assign_chunks(chunks, sections, settings: Settings):
    if settings.openai_api_key and OpenAI is not None:
        try:
            return _assign_with_openai(chunks, sections, settings), "openai-embeddings", []
        except Exception as exc:  # noqa: BLE001
            warning = f"OpenAI 임베딩 호출에 실패해 lexical similarity로 fallback 했습니다. ({exc})"
            assignments = _assign_with_lexical(chunks, sections)
            return assignments, "lexical-fallback", [warning]

    return _assign_with_lexical(chunks, sections), "lexical", []


def _assign_with_lexical(chunks, sections):
    section_counters = {section.id: Counter(tokenize(section.search_text)) for section in sections}
    section_titles = {section.id: set(tokenize(section.title)) for section in sections}
    assignments = []

    for chunk in chunks:
        chunk_counter = Counter(tokenize(chunk.text))
        chunk_tokens = set(chunk_counter)
        scored = []

        for section in sections:
            cosine = cosine_similarity(chunk_counter, section_counters[section.id])
            title_tokens = section_titles[section.id]
            title_overlap = len(chunk_tokens & title_tokens) / max(1, len(title_tokens))
            score = (cosine * 0.75) + (title_overlap * 0.25)
            scored.append((section, score))

        assignments.append(_best_assignment(chunk, scored, min_score=0.07, min_margin=0.01))

    return assignments


def _assign_with_openai(chunks, sections, settings: Settings):
    client = OpenAI(api_key=settings.openai_api_key)
    section_inputs = [section.search_text for section in sections]
    chunk_inputs = [chunk.text for chunk in chunks]
    section_vectors = _embed_texts(client, section_inputs, settings.openai_embedding_model)
    chunk_vectors = _embed_texts(client, chunk_inputs, settings.openai_embedding_model)
    assignments = []

    for chunk, chunk_vector in zip(chunks, chunk_vectors, strict=True):
        scored = []
        for section, section_vector in zip(sections, section_vectors, strict=True):
            score = _vector_cosine(chunk_vector, section_vector)
            scored.append((section, max(0.0, score)))
        assignments.append(_best_assignment(chunk, scored, min_score=0.23, min_margin=0.025))

    return assignments


def _embed_texts(client, texts: list[str], model: str):  # noqa: ANN001
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


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

        coverages: list[SectionCoverage] = []
        for section in sections:
            token_count_value = section_tokens[section.id]
            share = (token_count_value / total_tokens) if total_tokens else 0.0
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
) -> tuple[dict, dict, dict]:
    mode_map = {
        "combined": None,
        "material": MATERIAL_SOURCE_TYPES,
        "speech": SPEECH_SOURCE_TYPES,
    }
    mode_series: dict[str, dict] = {}
    average_series_by_mode: dict[str, list[dict]] = {}
    line_series_by_mode: dict[str, dict] = {}

    for mode, allowed_types in mode_map.items():
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

    return mode_series, average_series_by_mode, line_series_by_mode


def _build_keywords_by_instructor(chunks, sections: list[CurriculumSection]) -> dict[str, list[dict]]:
    curriculum_tokens = set()
    for section in sections:
        curriculum_tokens.update(tokenize(section.search_text))

    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    grouped_off_curriculum: dict[str, Counter[str]] = defaultdict(Counter)
    for chunk in chunks:
        tokens = tokenize(chunk.text)
        grouped[chunk.instructor_name].update(tokens)
        grouped_off_curriculum[chunk.instructor_name].update(
            token for token in tokens if token not in curriculum_tokens
        )

    keywords: dict[str, list[dict]] = {}
    for instructor_name, counts in grouped.items():
        top_keywords = counts.most_common(25)
        top_off_curriculum = grouped_off_curriculum[instructor_name].most_common(15)
        keywords[instructor_name] = [
            {"text": token, "value": int(value)}
            for token, value in top_keywords
        ]
        keywords[f"{instructor_name}__off_curriculum"] = [
            {"text": token, "value": int(value)}
            for token, value in top_off_curriculum
        ]

    return keywords


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


def _build_insights(
    *,
    course_name: str,
    sections: list[CurriculumSection],
    summaries: list[InstructorSummary],
    average_series_by_mode: dict[str, list[dict]],
    keywords_by_instructor: dict[str, list[dict]],
    settings: Settings,
) -> tuple[list[dict], str, list[str]]:
    metrics = _compute_insight_metrics(
        course_name=course_name,
        sections=sections,
        summaries=summaries,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
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
        off_curriculum = keywords_by_instructor.get(f"{summary.name}__off_curriculum", [])
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
