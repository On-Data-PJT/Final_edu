from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_name: str
    host: str
    port: int
    openai_api_key: str | None
    openai_embedding_model: str
    max_sections: int
    max_instructors: int
    max_upload_bytes: int
    chunk_target_tokens: int
    chunk_overlap_segments: int
    max_evidence_per_section: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    max_upload_mb = int(os.getenv("FINAL_EDU_MAX_UPLOAD_MB", "20"))
    return Settings(
        app_name="Final Edu",
        host=os.getenv("FINAL_EDU_HOST", "127.0.0.1"),
        port=int(os.getenv("FINAL_EDU_PORT", "8000")),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_embedding_model=os.getenv(
            "OPENAI_EMBEDDING_MODEL",
            "text-embedding-3-small",
        ),
        max_sections=8,
        max_instructors=3,
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        chunk_target_tokens=550,
        chunk_overlap_segments=1,
        max_evidence_per_section=3,
    )
