from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from statistics import mean

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing.
    OpenAI = None

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
    count_tokens,
    normalize_text,
    safe_snippet,
    slugify,
    tokenize,
)

SECTION_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+[\.\)]?)\s*")


def analyze_submissions(
    curriculum_text: str,
    submissions: list[InstructorSubmission],
    settings: Settings,
) -> AnalysisRun:
    started = time.perf_counter()
    sections = parse_curriculum_sections(curriculum_text, settings.max_sections)
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

    assignments, scorer_mode, scorer_warnings = _assign_chunks(deduped_chunks, sections, settings)
    warnings.extend(scorer_warnings)
    summaries = _build_instructor_summaries(
        sections=sections,
        submissions=active_submissions,
        assignments=assignments,
        instructor_assets=instructor_assets,
        instructor_warnings=instructor_warnings,
        max_evidence=settings.max_evidence_per_section,
    )

    duration_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisRun(
        sections=sections,
        instructors=summaries,
        warnings=warnings,
        scorer_mode=scorer_mode,
        duration_ms=duration_ms,
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

    return sections


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
) -> list[InstructorSummary]:
    grouped_assignments: dict[str, list[ChunkAssignment]] = defaultdict(list)
    for assignment in assignments:
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
