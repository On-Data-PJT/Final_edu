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
class UploadedAsset:
    path: Path
    original_name: str


@dataclass(slots=True)
class InstructorSubmission:
    name: str
    files: list[UploadedAsset] = field(default_factory=list)
    youtube_urls: list[str] = field(default_factory=list)


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


@dataclass(slots=True)
class AnalysisRun:
    sections: list[CurriculumSection]
    instructors: list[InstructorSummary]
    warnings: list[str]
    scorer_mode: str
    duration_ms: int
    course: dict = field(default_factory=dict)
    mode_series: dict = field(default_factory=dict)
    average_series_by_mode: dict = field(default_factory=dict)
    keywords_by_instructor: dict = field(default_factory=dict)
    rose_series_by_instructor: dict = field(default_factory=dict)
    line_series_by_mode: dict = field(default_factory=dict)
    insights: list[dict] = field(default_factory=list)
    insight_generation_mode: str = "deterministic-fallback"
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


@dataclass(slots=True)
class JobInstructorInput:
    name: str
    files: list[StoredUploadRef] = field(default_factory=list)
    youtube_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "files": [file_ref.to_dict() for file_ref in self.files],
            "youtube_urls": list(self.youtube_urls),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "JobInstructorInput":
        return cls(
            name=payload["name"],
            files=[StoredUploadRef.from_dict(item) for item in payload.get("files", [])],
            youtube_urls=list(payload.get("youtube_urls", [])),
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

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "course_sections": [asdict(section) for section in self.course_sections],
            "curriculum_text": self.curriculum_text,
            "submitted_at": self.submitted_at,
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
            instructors=[JobInstructorInput.from_dict(item) for item in payload.get("instructors", [])],
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
        )
