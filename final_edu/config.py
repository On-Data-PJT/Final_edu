from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"


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
    redis_url: str | None
    queue_name: str
    job_timeout_seconds: int
    job_ttl_days: int
    max_saved_jobs: int
    runtime_dir: Path
    r2_endpoint_url: str | None
    r2_access_key_id: str | None
    r2_secret_access_key: str | None
    r2_bucket: str | None
    r2_region: str

    @property
    def queue_mode(self) -> str:
        return "rq" if self.redis_url else "inline"

    @property
    def storage_mode(self) -> str:
        required = [
            self.r2_endpoint_url,
            self.r2_access_key_id,
            self.r2_secret_access_key,
            self.r2_bucket,
        ]
        return "r2" if all(required) else "local"


def _load_dotenv(dotenv_path: Path = DOTENV_PATH) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", maxsplit=1)
        normalized_key = key.strip()
        if not normalized_key or normalized_key in os.environ:
            continue

        normalized_value = value.strip()
        if normalized_value and normalized_value[0] == normalized_value[-1] and normalized_value[0] in {'"', "'"}:
            normalized_value = normalized_value[1:-1]

        os.environ[normalized_key] = normalized_value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
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
        redis_url=os.getenv("REDIS_URL"),
        queue_name=os.getenv("FINAL_EDU_QUEUE_NAME", "final-edu-analysis"),
        job_timeout_seconds=int(os.getenv("FINAL_EDU_JOB_TIMEOUT_SECONDS", "7200")),
        job_ttl_days=int(os.getenv("FINAL_EDU_JOB_TTL_DAYS", "7")),
        max_saved_jobs=int(os.getenv("FINAL_EDU_MAX_SAVED_JOBS", "20")),
        runtime_dir=Path(os.getenv("FINAL_EDU_RUNTIME_DIR", ".final_edu_runtime")).resolve(),
        r2_endpoint_url=os.getenv("R2_ENDPOINT_URL"),
        r2_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        r2_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
        r2_bucket=os.getenv("R2_BUCKET"),
        r2_region=os.getenv("R2_REGION", "auto"),
    )
