from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class CurriculumSection:
    id: str
    title: str
    description: str

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
