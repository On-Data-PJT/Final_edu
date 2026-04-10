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
from final_edu.storage import ObjectStorage
from final_edu.youtube_cache import (
    YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE,
    has_youtube_request_limit_warning,
)
from final_edu.utils import (
    build_chunks,
    build_custom_dictionary,
    count_tokens,
    cosine_similarity,
    normalize_text,
    safe_snippet,
    slugify,
    tokenize,
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


class InsightCardSchema(BaseModel):
    category: str
    title: str
    issue: str
    evidence: str
    recommendation: str
    icon: str = "lightbulb"


class InsightBundleSchema(BaseModel):
    cards: list[InsightCardSchema] = Field(min_length=5, max_length=5)


def _analysis_no_text_error(warnings: list[str]) -> str:
    if has_youtube_request_limit_warning(warnings):
        return YOUTUBE_REQUEST_LIMIT_ERROR_MESSAGE
    return NO_ANALYZABLE_TEXT_ERROR_MESSAGE


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
    build_custom_dictionary([section.title for section in normalized_sections])
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
                all_chunks.extend(
                    build_chunks(
                        segments,
                        target_tokens=settings.chunk_target_tokens,
                        overlap_segments=settings.chunk_overlap_segments,
                    )
                )

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
                all_chunks.extend(
                    build_chunks(
                        segments,
                        target_tokens=settings.chunk_target_tokens,
                        overlap_segments=settings.chunk_overlap_segments,
                    )
                )
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

    _emit_progress(
        progress_callback,
        phase="assigning",
        progress_current=0,
        progress_total=len(deduped_chunks),
        expanded_video_count=total_youtube_videos,
        processed_video_count=processed_youtube_videos,
        caption_success_count=caption_success_count,
        caption_failure_count=caption_failure_count,
    )
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
    rose_series_by_mode = _build_rose_series_by_mode(
        mode_series=mode_series,
        sections=normalized_sections,
    )
    keywords_by_mode = _build_keywords_by_mode(
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
        settings=settings,
    )
    warnings.extend(insight_warnings)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisRun(
        sections=normalized_sections,
        instructors=_attach_voc_to_summaries(
            summaries=summaries,
            submissions=active_submissions,
            voc_analyses_by_instructor=voc_analyses_by_instructor,
        ),
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
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        keywords_by_mode=keywords_by_mode,
        rose_series_by_instructor=rose_series_by_instructor,
        rose_series_by_mode=rose_series_by_mode,
        line_series_by_mode=line_series_by_mode,
        insights=insights,
        voc_summary=voc_summary,
        insight_generation_mode=insight_generation_mode,
        external_trends_status="planned",
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
    curriculum_tokens = set()
    for section in sections:
        curriculum_tokens.update(tokenize(section.search_text))
    lexical_index = _build_lexical_index(sections)
    dedupe_seen: set[tuple[str, str]] = set()
    removed_duplicates = 0
    mode_aggregates = _init_mode_aggregates(sections, submissions)
    evidence_map: dict[str, dict[str, list[ChunkAssignment]]] = defaultdict(lambda: defaultdict(list))

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
            removed_duplicates += _stream_segments_into_aggregates(
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
                curriculum_tokens=curriculum_tokens,
                max_evidence=settings.max_evidence_per_section,
            )

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
                removed_duplicates += _stream_segments_into_aggregates(
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
                    curriculum_tokens=curriculum_tokens,
                    max_evidence=settings.max_evidence_per_section,
                )
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

    _emit_progress(
        progress_callback,
        phase="assigning",
        progress_current=1,
        progress_total=1,
        expanded_video_count=total_youtube_videos,
        processed_video_count=processed_youtube_videos,
        caption_success_count=caption_success_count,
        caption_failure_count=caption_failure_count,
    )

    summaries = _build_summaries_from_aggregates(
        sections=sections,
        submissions=submissions,
        combined_aggregates=combined_aggregates,
        evidence_map=evidence_map,
        instructor_assets=instructor_assets,
        instructor_warnings=instructor_warnings,
    )
    mode_series, average_series_by_mode, line_series_by_mode = _build_mode_series_from_aggregates(
        sections=sections,
        submissions=submissions,
        mode_aggregates=mode_aggregates,
    )
    rose_series_by_mode = _build_rose_series_by_mode(
        mode_series=mode_series,
        sections=sections,
    )
    keywords_by_mode = _build_keywords_by_mode_from_counters(
        grouped_by_mode=keyword_counters_by_mode,
        grouped_off_curriculum_by_mode=off_curriculum_counters_by_mode,
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
        settings=replace(settings, openai_api_key=None),
    )
    warnings.extend(insight_warnings)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return AnalysisRun(
        sections=sections,
        instructors=_attach_voc_to_summaries(
            summaries=summaries,
            submissions=submissions,
            voc_analyses_by_instructor=voc_analyses_by_instructor or {},
        ),
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
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_instructor,
        keywords_by_mode=keywords_by_mode,
        rose_series_by_instructor=rose_series_by_instructor,
        rose_series_by_mode=rose_series_by_mode,
        line_series_by_mode=line_series_by_mode,
        insights=insights,
        voc_summary=voc_summary or {},
        insight_generation_mode=insight_generation_mode,
        external_trends_status="planned",
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

    for upload in uploads:
        source, segments, source_warnings = extract_file_asset(upload, instructor_name)
        warnings.extend(source_warnings)
        if not segments:
            continue
        analyzed_files.append(upload.original_name)
        collected_segments.extend(segments)
        response_count += _estimate_voc_response_count(source.asset_type, segments)

    if not collected_segments:
        raise ValueError("VOC 파일에서 분석 가능한 텍스트를 추출하지 못했습니다.")

    structured, generation_warning = _generate_voc_analysis(
        instructor_name=instructor_name,
        segments=collected_segments,
        settings=settings,
    )
    if generation_warning:
        warnings.append(generation_warning)

    file_name = ""
    if len(analyzed_files) == 1:
        file_name = analyzed_files[0]
    elif analyzed_files:
        file_name = f"{analyzed_files[0]} 외 {len(analyzed_files) - 1}개"

    analysis = {
        "file_name": file_name,
        "analyzed_at": datetime.now(UTC).astimezone().strftime("%Y-%m-%d"),
        "response_count": max(response_count, len(collected_segments)),
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
    mode_series, average_series_by_mode, line_series_by_mode = _build_mode_series(
        sections=sections,
        submissions=submissions,
        assignments=[],
    )
    rose_series_by_mode = _build_rose_series_by_mode(
        mode_series=mode_series,
        sections=sections,
    )
    keywords_by_mode = _empty_keywords_by_mode(submissions)
    duration_ms = int((time.perf_counter() - started) * 1000)
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
        mode_series=mode_series,
        average_series_by_mode=average_series_by_mode,
        keywords_by_instructor=keywords_by_mode.get("combined", {}),
        keywords_by_mode=keywords_by_mode,
        rose_series_by_instructor=rose_series_by_mode.get("combined", {}),
        rose_series_by_mode=rose_series_by_mode,
        line_series_by_mode=line_series_by_mode,
        insights=[],
        voc_summary=voc_summary,
        insight_generation_mode="deterministic-fallback",
        external_trends_status="planned",
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
            payload[mode][f"{submission.name}__off_curriculum"] = []
    return payload


def _estimate_voc_response_count(source_type: str, segments: list) -> int:
    if source_type == "csv":
        return len(segments)
    if source_type == "text":
        return sum(max(1, len([line for line in segment.text.split("|") if line.strip()])) for segment in segments)
    return len(segments)


def _generate_voc_analysis(
    *,
    instructor_name: str,
    segments: list,
    settings: Settings,
) -> tuple[dict, str | None]:
    lines = [normalize_text(segment.text) for segment in segments if normalize_text(segment.text)]
    fallback = _fallback_voc_analysis(lines)
    if not settings.openai_api_key or OpenAI is None:
        return fallback, None

    client = OpenAI(api_key=settings.openai_api_key)
    compact_text = "\n".join(lines[:120])
    try:
        response = client.chat.completions.create(
            model=settings.openai_insight_model,
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

    for analysis in analyses.values():
        sentiment = analysis.get("sentiment", {})
        positive_counts.update(sentiment.get("positive", []))
        negative_counts.update(sentiment.get("negative", []))
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


def _build_lexical_index(sections: list[CurriculumSection]) -> dict:
    return {
        "section_counters": {section.id: Counter(tokenize(section.search_text)) for section in sections},
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
    curriculum_tokens: set[str],
    max_evidence: int,
) -> int:
    removed_duplicates = 0
    chunks = build_chunks(
        segments,
        target_tokens=settings.chunk_target_tokens,
        overlap_segments=settings.chunk_overlap_segments,
    )
    for chunk in chunks:
        dedupe_key = (chunk.instructor_name, chunk.fingerprint)
        if dedupe_key in dedupe_seen:
            removed_duplicates += 1
            continue
        dedupe_seen.add(dedupe_key)

        assignment = _assign_chunk_lexical(chunk, sections, lexical_index)
        tokens = tokenize(chunk.text)
        for mode in _modes_for_source_type(chunk.source_type):
            keyword_counters_by_mode[mode][instructor_name].update(tokens)
            off_curriculum_counters_by_mode[mode][instructor_name].update(
                token for token in tokens if token not in curriculum_tokens
            )
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
    return removed_duplicates


def _modes_for_source_type(source_type: str) -> list[str]:
    if source_type in MATERIAL_SOURCE_TYPES:
        return ["combined", "material"]
    if source_type in SPEECH_SOURCE_TYPES:
        return ["combined", "speech"]
    return ["combined"]


def _assign_chunk_lexical(chunk, sections, lexical_index: dict) -> ChunkAssignment:
    section_counters = lexical_index["section_counters"]
    section_titles = lexical_index["section_titles"]
    chunk_counter = Counter(tokenize(chunk.text))
    chunk_tokens = set(chunk_counter)
    scored = []

    for section in sections:
        cosine = cosine_similarity(chunk_counter, section_counters[section.id])
        title_tokens = section_titles[section.id]
        title_overlap = len(chunk_tokens & title_tokens) / max(1, len(title_tokens))
        score = (cosine * 0.75) + (title_overlap * 0.25)
        scored.append((section, score))

    return _best_assignment(chunk, scored, min_score=0.07, min_margin=0.01)


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
        section_tokens = aggregate.get("section_tokens", {})
        coverages: list[SectionCoverage] = []

        for section in sections:
            token_count_value = int(section_tokens.get(section.id, 0))
            share = (token_count_value / total_tokens) if total_tokens else 0.0
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
                unmapped_tokens=int(aggregate.get("unmapped_tokens", 0)),
                unmapped_share=(aggregate.get("unmapped_tokens", 0) / total_tokens) if total_tokens else 0.0,
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
) -> tuple[dict, dict, dict]:
    mode_series: dict[str, dict] = {}
    average_series_by_mode: dict[str, list[dict]] = {}
    line_series_by_mode: dict[str, dict] = {}

    for mode in RESULT_MODES:
        aggregates = mode_aggregates.get(mode, {})
        average_values: list[dict] = []
        instructor_values: dict[str, list[dict]] = {}

        for submission in submissions:
            aggregate = aggregates.get(
                submission.name,
                {"total_tokens": 0, "section_tokens": {section.id: 0 for section in sections}},
            )
            total_tokens = int(aggregate.get("total_tokens", 0))
            section_tokens = aggregate.get("section_tokens", {})
            instructor_values[submission.name] = [
                {
                    "section_id": section.id,
                    "section_title": section.title,
                    "share": round((int(section_tokens.get(section.id, 0)) / total_tokens), 6) if total_tokens else 0.0,
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


def _build_keywords_from_counters(grouped: dict[str, Counter[str]], grouped_off_curriculum: dict[str, Counter[str]]) -> dict[str, list[dict]]:
    keywords: dict[str, list[dict]] = {}
    for instructor_name, counts in grouped.items():
        off_counts = grouped_off_curriculum.get(instructor_name, Counter())
        
        # 커리큘럼 기반 단어에 가중치 크게 부여
        boosted = Counter()
        for token, count in counts.items():
            if token not in off_counts:
                boosted[token] = count * 50
            else:
                boosted[token] = count
                
        best_tokens = [token for token, _ in boosted.most_common(25)]
        
        keywords[instructor_name] = [
            {"text": token, "value": int(counts[token])}
            for token in best_tokens
        ]
        
        top_off_curriculum = off_counts.most_common(15)
        keywords[f"{instructor_name}__off_curriculum"] = [
            {"text": token, "value": int(value)}
            for token, value in top_off_curriculum
        ]
    return keywords


def _build_keywords_by_mode_from_counters(
    *,
    grouped_by_mode: dict[str, dict[str, Counter[str]]],
    grouped_off_curriculum_by_mode: dict[str, dict[str, Counter[str]]],
) -> dict[str, dict[str, list[dict]]]:
    return {
        mode: _build_keywords_from_counters(
            grouped_by_mode.get(mode, {}),
            grouped_off_curriculum_by_mode.get(mode, {}),
        )
        for mode in RESULT_MODES
    }


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

    vectors: list[list[float]] = []
    for batch in batches:
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend(item.embedding for item in response.data)
    return vectors


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
    mode_series: dict[str, dict] = {}
    average_series_by_mode: dict[str, list[dict]] = {}
    line_series_by_mode: dict[str, dict] = {}

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
    return _build_keywords_by_mode(chunks, sections).get("combined", {})


def _build_keywords_by_mode(chunks, sections: list[CurriculumSection]) -> dict[str, dict[str, list[dict]]]:
    curriculum_tokens = set()
    for section in sections:
        curriculum_tokens.update(tokenize(section.search_text))

    grouped_by_mode: dict[str, dict[str, Counter[str]]] = {
        mode: defaultdict(Counter) for mode in RESULT_MODES
    }
    grouped_off_curriculum_by_mode: dict[str, dict[str, Counter[str]]] = {
        mode: defaultdict(Counter) for mode in RESULT_MODES
    }
    for chunk in chunks:
        tokens = tokenize(chunk.text)
        for mode in _modes_for_source_type(chunk.source_type):
            grouped_by_mode[mode][chunk.instructor_name].update(tokens)
            grouped_off_curriculum_by_mode[mode][chunk.instructor_name].update(
                token for token in tokens if token not in curriculum_tokens
            )

    return _build_keywords_by_mode_from_counters(
        grouped_by_mode=grouped_by_mode,
        grouped_off_curriculum_by_mode=grouped_off_curriculum_by_mode,
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
