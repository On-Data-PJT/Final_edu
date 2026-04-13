from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class CurriculumSection:
    id: str
    title: str
    description: str
    target_weight: float = 0.0

    @property
    def search_text(self) -> str:
        return f"{self.title}\n{self.description}".strip()


@dataclass(slots=True)
class CurriculumPreviewEvidence:
    page: int | None = None
    snippet: str = ""
    reason: str = ""


@dataclass(slots=True)
class CurriculumPreviewSection:
    id: str
    title: str
    description: str
    target_weight: float | None = None
    weight_source: str = "none"
    raw_weight_value: float | None = None
    confidence: float = 0.0
    source_pages: list[int] = field(default_factory=list)
    source_snippets: list[str] = field(default_factory=list)
    needs_weight_input: bool = False


@dataclass(slots=True)
class CurriculumPreviewResult:
    decision: str
    document_kind: str
    document_confidence: float
    weight_status: str
    raw_curriculum_text: str
    sections: list[CurriculumPreviewSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    evidence: list[CurriculumPreviewEvidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class UploadedAsset:
    path: Path
    original_name: str


@dataclass(slots=True)
class InstructorSubmission:
    name: str
    files: list[UploadedAsset] = field(default_factory=list)
    youtube_urls: list[str] = field(default_factory=list)
    voc_files: list[UploadedAsset] = field(default_factory=list)


@dataclass(slots=True)
class SourceAsset:
    id: str
    instructor_name: str
    asset_type: str
    label: str
    origin: str
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RawTextSegment:
    source_id: str
    instructor_name: str
    source_label: str
    source_type: str
    locator: str
    text: str


@dataclass(slots=True)
class ExtractedChunk:
    id: str
    source_id: str
    instructor_name: str
    source_label: str
    source_type: str
    locator: str
    text: str
    token_count: int
    fingerprint: str


@dataclass(slots=True)
class ChunkAssignment:
    chunk: ExtractedChunk
    section_id: str | None
    section_title: str
    score: float
    runner_up_score: float
    rationale_short: str

    @property
    def is_unmapped(self) -> bool:
        return self.section_id is None


@dataclass(slots=True)
class EvidenceSnippet:
    source_label: str
    locator: str
    text: str
    score: float


@dataclass(slots=True)
class SectionCoverage:
    section_id: str
    section_title: str
    token_count: int
    token_share: float
    deviation_from_average: float = 0.0
    evidence_snippets: list[EvidenceSnippet] = field(default_factory=list)


@dataclass(slots=True)
class InstructorSummary:
    name: str
    total_tokens: int
    asset_count: int
    section_coverages: list[SectionCoverage] = field(default_factory=list)
    unmapped_tokens: int = 0
    unmapped_share: float = 0.0
    warnings: list[str] = field(default_factory=list)
    voc_file_count: int = 0
    voc_analysis: dict = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisRun:
    sections: list[CurriculumSection]
    instructors: list[InstructorSummary]
    warnings: list[str]
    scorer_mode: str
    duration_ms: int
    course: dict = field(default_factory=dict)
    available_source_modes: list[str] = field(default_factory=list)
    source_mode_stats: dict = field(default_factory=dict)
    mode_unmapped_series: dict = field(default_factory=dict)
    mode_series: dict = field(default_factory=dict)
    average_series_by_mode: dict = field(default_factory=dict)
    average_keywords_by_mode: dict = field(default_factory=dict)
    keywords_by_instructor: dict = field(default_factory=dict)
    keywords_by_mode: dict = field(default_factory=dict)
    rose_series_by_instructor: dict = field(default_factory=dict)
    rose_series_by_mode: dict = field(default_factory=dict)
    line_series_by_mode: dict = field(default_factory=dict)
    insights: list[dict] = field(default_factory=list)
    voc_summary: dict = field(default_factory=dict)
    insight_generation_mode: str = "deterministic-fallback"
    solution_content: dict = field(default_factory=dict)
    solution_generation_mode: str = "fallback"
    solution_generation_warning: str | None = None
    external_trends_status: str = "planned"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class CourseRecord:
    id: str
    name: str
    curriculum_pdf_key: str
    sections: list[CurriculumSection]
    instructor_names: list[str]
    raw_curriculum_text: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "CourseRecord":
        return cls(
            id=payload["id"],
            name=payload["name"],
            curriculum_pdf_key=payload["curriculum_pdf_key"],
            sections=[CurriculumSection(**item) for item in payload.get("sections", [])],
            instructor_names=list(payload.get("instructor_names", [])),
            raw_curriculum_text=payload.get("raw_curriculum_text", ""),
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
        )


@dataclass(slots=True)
class StoredUploadRef:
    storage_key: str
    original_name: str

    def to_dict(self) -> dict:
        return {
            "storage_key": self.storage_key,
            "original_name": self.original_name,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "StoredUploadRef":
        return cls(
            storage_key=payload["storage_key"],
            original_name=payload["original_name"],
        )


def _normalize_lane_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "youtube":
        return "youtube"
    if normalized == "voc":
        return "voc"
    return "files"


@dataclass(slots=True)
class JobInstructorInput:
    name: str
    mode: str = "files"
    files: list[StoredUploadRef] = field(default_factory=list)
    youtube_inputs: list[str] = field(default_factory=list)
    youtube_urls: list[str] = field(default_factory=list)
    voc_files: list[StoredUploadRef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mode": _normalize_lane_mode(self.mode),
            "files": [file_ref.to_dict() for file_ref in self.files],
            "youtube_inputs": list(self.youtube_inputs),
            "youtube_urls": list(self.youtube_urls),
            "voc_files": [file_ref.to_dict() for file_ref in self.voc_files],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "JobInstructorInput":
        if "mode" in payload:
            mode = _normalize_lane_mode(payload.get("mode"))
        else:
            mode = "files"
            if payload.get("files"):
                mode = "files"
            elif payload.get("youtube_inputs") or payload.get("youtube_urls"):
                mode = "youtube"
            elif payload.get("voc_files"):
                mode = "voc"
        return cls(
            name=payload["name"],
            mode=mode,
            files=[StoredUploadRef.from_dict(item) for item in payload.get("files", [])],
            youtube_inputs=list(payload.get("youtube_inputs", payload.get("youtube_urls", []))),
            youtube_urls=list(payload.get("youtube_urls", [])),
            voc_files=[StoredUploadRef.from_dict(item) for item in payload.get("voc_files", [])],
        )


@dataclass(slots=True)
class AnalysisJobPayload:
    job_id: str
    course_id: str
    course_name: str
    course_sections: list[CurriculumSection]
    curriculum_text: str
    instructors: list[JobInstructorInput]
    submitted_at: str
    analysis_mode: str = "auto"
    page1_submission_version: int = 1

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "course_sections": [asdict(section) for section in self.course_sections],
            "curriculum_text": self.curriculum_text,
            "submitted_at": self.submitted_at,
            "analysis_mode": self.analysis_mode,
            "page1_submission_version": int(self.page1_submission_version or 1),
            "instructors": [instructor.to_dict() for instructor in self.instructors],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "AnalysisJobPayload":
        return cls(
            job_id=payload["job_id"],
            course_id=payload.get("course_id", "legacy-course"),
            course_name=payload.get("course_name", "Legacy Course"),
            course_sections=[CurriculumSection(**item) for item in payload.get("course_sections", [])],
            curriculum_text=payload["curriculum_text"],
            submitted_at=payload["submitted_at"],
            analysis_mode=payload.get("analysis_mode", "auto"),
            page1_submission_version=int(payload.get("page1_submission_version", 1) or 1),
            instructors=[JobInstructorInput.from_dict(item) for item in payload.get("instructors", [])],
        )


@dataclass(slots=True)
class AnalysisPreparation:
    request_id: str
    payload: AnalysisJobPayload
    created_at: str
    requires_confirmation: bool
    recommended_analysis_mode: str
    estimated_cost_usd: float | None = None
    estimated_transcript_tokens: int = 0
    estimated_chunk_count: int = 0
    estimated_processing_seconds: int = 0
    expanded_video_count: int = 0
    total_video_duration_seconds: int = 0
    caption_probe_sample_count: int = 0
    caption_probe_success_count: int = 0
    has_playlist: bool = False
    playlist_summaries: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "payload": self.payload.to_dict(),
            "created_at": self.created_at,
            "requires_confirmation": self.requires_confirmation,
            "recommended_analysis_mode": self.recommended_analysis_mode,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_transcript_tokens": self.estimated_transcript_tokens,
            "estimated_chunk_count": self.estimated_chunk_count,
            "estimated_processing_seconds": self.estimated_processing_seconds,
            "expanded_video_count": self.expanded_video_count,
            "total_video_duration_seconds": self.total_video_duration_seconds,
            "caption_probe_sample_count": self.caption_probe_sample_count,
            "caption_probe_success_count": self.caption_probe_success_count,
            "has_playlist": self.has_playlist,
            "playlist_summaries": list(self.playlist_summaries),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "AnalysisPreparation":
        return cls(
            request_id=payload["request_id"],
            payload=AnalysisJobPayload.from_dict(payload["payload"]),
            created_at=payload["created_at"],
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
            recommended_analysis_mode=payload.get("recommended_analysis_mode", "lexical"),
            estimated_cost_usd=payload.get("estimated_cost_usd"),
            estimated_transcript_tokens=int(payload.get("estimated_transcript_tokens", 0)),
            estimated_chunk_count=int(payload.get("estimated_chunk_count", 0)),
            estimated_processing_seconds=int(payload.get("estimated_processing_seconds", 0)),
            expanded_video_count=int(payload.get("expanded_video_count", 0)),
            total_video_duration_seconds=int(payload.get("total_video_duration_seconds", 0)),
            caption_probe_sample_count=int(payload.get("caption_probe_sample_count", 0)),
            caption_probe_success_count=int(payload.get("caption_probe_success_count", 0)),
            has_playlist=bool(payload.get("has_playlist", False)),
            playlist_summaries=list(payload.get("playlist_summaries", [])),
            warnings=list(payload.get("warnings", [])),
        )


@dataclass(slots=True)
class AnalysisJobRecord:
    id: str
    course_id: str
    course_name: str
    status: str
    created_at: str
    updated_at: str
    created_at_ts: float
    updated_at_ts: float
    payload_key: str
    result_key: str | None = None
    error: str | None = None
    scorer_mode: str | None = None
    duration_ms: int | None = None
    instructor_names: list[str] = field(default_factory=list)
    instructor_count: int = 0
    asset_count: int = 0
    youtube_url_count: int = 0
    section_count: int = 0
    warning_count: int = 0
    phase: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    expanded_video_count: int = 0
    processed_video_count: int = 0
    caption_success_count: int = 0
    caption_failure_count: int = 0
    selected_analysis_mode: str | None = None
    estimated_cost_usd: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"completed", "failed"}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "AnalysisJobRecord":
        return cls(
            id=payload["id"],
            course_id=payload.get("course_id", "legacy-course"),
            course_name=payload.get("course_name", "Legacy Course"),
            status=payload["status"],
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            created_at_ts=float(payload["created_at_ts"]),
            updated_at_ts=float(payload["updated_at_ts"]),
            payload_key=payload["payload_key"],
            result_key=payload.get("result_key"),
            error=payload.get("error"),
            scorer_mode=payload.get("scorer_mode"),
            duration_ms=payload.get("duration_ms"),
            instructor_names=list(payload.get("instructor_names", [])),
            instructor_count=int(payload.get("instructor_count", 0)),
            asset_count=int(payload.get("asset_count", 0)),
            youtube_url_count=int(payload.get("youtube_url_count", 0)),
            section_count=int(payload.get("section_count", 0)),
            warning_count=int(payload.get("warning_count", 0)),
            phase=payload.get("phase"),
            progress_current=int(payload.get("progress_current", 0)),
            progress_total=int(payload.get("progress_total", 0)),
            expanded_video_count=int(payload.get("expanded_video_count", 0)),
            processed_video_count=int(payload.get("processed_video_count", 0)),
            caption_success_count=int(payload.get("caption_success_count", 0)),
            caption_failure_count=int(payload.get("caption_failure_count", 0)),
            selected_analysis_mode=payload.get("selected_analysis_mode"),
            estimated_cost_usd=payload.get("estimated_cost_usd"),
        )
