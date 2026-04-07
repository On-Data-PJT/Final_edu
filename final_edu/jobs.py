from __future__ import annotations

import json
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from final_edu.analysis import analyze_submissions
from final_edu.config import Settings, get_settings
from final_edu.models import (
    AnalysisJobPayload,
    AnalysisJobRecord,
    InstructorSubmission,
    UploadedAsset,
)
from final_edu.storage import ObjectStorage, create_object_storage

RECENT_JOBS_LIMIT = 10
SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z가-힣._-]+")


class JobRepository:
    def save(self, record: AnalysisJobRecord) -> None:
        raise NotImplementedError

    def get(self, job_id: str) -> AnalysisJobRecord | None:
        raise NotImplementedError

    def list_recent(self, limit: int) -> list[AnalysisJobRecord]:
        raise NotImplementedError


class LocalJobRepository(JobRepository):
    def __init__(self, settings: Settings) -> None:
        self.root = settings.runtime_dir / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = settings.job_ttl_days * 86400
        self.max_saved_jobs = settings.max_saved_jobs

    def save(self, record: AnalysisJobRecord) -> None:
        self._write(record)
        self._prune()

    def get(self, job_id: str) -> AnalysisJobRecord | None:
        path = self.root / f"{job_id}.json"
        if not path.exists():
            return None
        record = AnalysisJobRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if self._is_expired(record):
            path.unlink(missing_ok=True)
            return None
        return record

    def list_recent(self, limit: int) -> list[AnalysisJobRecord]:
        self._prune()
        records: list[AnalysisJobRecord] = []
        for path in self.root.glob("*.json"):
            record = AnalysisJobRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            records.append(record)
        records.sort(key=lambda item: item.updated_at_ts, reverse=True)
        return records[:limit]

    def _write(self, record: AnalysisJobRecord) -> None:
        path = self.root / f"{record.id}.json"
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _prune(self) -> None:
        records = []
        for path in self.root.glob("*.json"):
            record = AnalysisJobRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            if self._is_expired(record):
                path.unlink(missing_ok=True)
                continue
            records.append((path, record))

        records.sort(key=lambda item: item[1].updated_at_ts, reverse=True)
        for path, _record in records[self.max_saved_jobs :]:
            path.unlink(missing_ok=True)

    def _is_expired(self, record: AnalysisJobRecord) -> bool:
        return (datetime.now(UTC).timestamp() - record.updated_at_ts) > self.ttl_seconds


class RedisJobRepository(JobRepository):
    def __init__(self, settings: Settings) -> None:
        Redis = _import_redis()
        self.redis = Redis.from_url(settings.redis_url or "", decode_responses=True)
        self.ttl_seconds = settings.job_ttl_days * 86400
        self.max_saved_jobs = settings.max_saved_jobs
        self.key_prefix = "final-edu:job"
        self.recent_key = "final-edu:jobs:recent"

    def save(self, record: AnalysisJobRecord) -> None:
        payload = json.dumps(record.to_dict(), ensure_ascii=False)
        metadata_key = self._metadata_key(record.id)
        pipeline = self.redis.pipeline()
        pipeline.setex(metadata_key, self.ttl_seconds, payload)
        pipeline.zadd(self.recent_key, {record.id: record.updated_at_ts})
        pipeline.execute()
        self._prune()

    def get(self, job_id: str) -> AnalysisJobRecord | None:
        payload = self.redis.get(self._metadata_key(job_id))
        if not payload:
            return None
        return AnalysisJobRecord.from_dict(json.loads(payload))

    def list_recent(self, limit: int) -> list[AnalysisJobRecord]:
        self._prune()
        job_ids = self.redis.zrevrange(self.recent_key, 0, max(0, limit - 1))
        if not job_ids:
            return []
        pipeline = self.redis.pipeline()
        for job_id in job_ids:
            pipeline.get(self._metadata_key(job_id))
        payloads = pipeline.execute()
        records = [AnalysisJobRecord.from_dict(json.loads(item)) for item in payloads if item]
        records.sort(key=lambda item: item.updated_at_ts, reverse=True)
        return records

    def _metadata_key(self, job_id: str) -> str:
        return f"{self.key_prefix}:{job_id}"

    def _prune(self) -> None:
        expiry_cutoff = datetime.now(UTC).timestamp() - self.ttl_seconds
        expired_ids = self.redis.zrangebyscore(self.recent_key, 0, expiry_cutoff)
        if expired_ids:
            pipeline = self.redis.pipeline()
            for job_id in expired_ids:
                pipeline.delete(self._metadata_key(job_id))
            pipeline.zrem(self.recent_key, *expired_ids)
            pipeline.execute()

        size = self.redis.zcard(self.recent_key)
        if size <= self.max_saved_jobs:
            return

        overflow = size - self.max_saved_jobs
        removable_ids = self.redis.zrange(self.recent_key, 0, overflow - 1)
        if not removable_ids:
            return
        pipeline = self.redis.pipeline()
        for job_id in removable_ids:
            pipeline.delete(self._metadata_key(job_id))
        pipeline.zrem(self.recent_key, *removable_ids)
        pipeline.execute()


class JobQueue:
    def enqueue(self, job_id: str) -> None:
        raise NotImplementedError


class InlineJobQueue(JobQueue):
    def enqueue(self, job_id: str) -> None:
        run_analysis_job(job_id)


class RQJobQueue(JobQueue):
    def __init__(self, settings: Settings) -> None:
        Redis = _import_redis()
        Queue = _import_rq_queue()
        connection = Redis.from_url(settings.redis_url or "")
        self.queue = Queue(
            settings.queue_name,
            connection=connection,
            default_timeout=settings.job_timeout_seconds,
        )
        self.job_timeout_seconds = settings.job_timeout_seconds

    def enqueue(self, job_id: str) -> None:
        self.queue.enqueue(
            run_analysis_job,
            job_id,
            job_timeout=self.job_timeout_seconds,
            result_ttl=0,
        )


@dataclass(slots=True)
class JobServices:
    settings: Settings
    storage: ObjectStorage
    repository: JobRepository
    queue: JobQueue


def create_job_services(settings: Settings | None = None) -> JobServices:
    active_settings = settings or get_settings()
    storage = create_object_storage(active_settings)
    repository: JobRepository
    queue: JobQueue

    if active_settings.queue_mode == "rq":
        repository = RedisJobRepository(active_settings)
        queue = RQJobQueue(active_settings)
    else:
        repository = LocalJobRepository(active_settings)
        queue = InlineJobQueue()

    return JobServices(
        settings=active_settings,
        storage=storage,
        repository=repository,
        queue=queue,
    )


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def build_upload_key(job_id: str, instructor_index: int, original_name: str) -> str:
    safe_name = SAFE_NAME_RE.sub("-", original_name.strip()).strip("-") or "upload"
    return f"jobs/{job_id}/uploads/instructor-{instructor_index}/{uuid.uuid4().hex[:8]}-{safe_name}"


def create_job_record(
    payload: AnalysisJobPayload,
    payload_key: str,
    section_count: int,
    settings: Settings,
) -> AnalysisJobRecord:
    created_at, created_at_ts = _now()
    instructor_names = [item.name for item in payload.instructors]
    asset_count = sum(len(item.files) for item in payload.instructors)
    youtube_url_count = sum(len(item.youtube_urls) for item in payload.instructors)
    return AnalysisJobRecord(
        id=payload.job_id,
        status="queued",
        created_at=created_at,
        updated_at=created_at,
        created_at_ts=created_at_ts,
        updated_at_ts=created_at_ts,
        payload_key=payload_key,
        instructor_names=instructor_names,
        instructor_count=len(payload.instructors),
        asset_count=asset_count,
        youtube_url_count=youtube_url_count,
        section_count=section_count,
    )


def enqueue_analysis_job(
    payload: AnalysisJobPayload,
    section_count: int,
    settings: Settings | None = None,
) -> AnalysisJobRecord:
    services = create_job_services(settings)
    payload_key = f"jobs/{payload.job_id}/payload.json"
    services.storage.put_json(payload_key, payload.to_dict())
    record = create_job_record(payload, payload_key, section_count, services.settings)
    services.repository.save(record)

    try:
        services.queue.enqueue(payload.job_id)
    except Exception as exc:  # noqa: BLE001
        failed = _updated_record(record, status="failed", error=f"작업을 큐에 등록하지 못했습니다. ({exc})")
        services.repository.save(failed)
        return failed

    return record


def get_job(job_id: str, settings: Settings | None = None) -> AnalysisJobRecord | None:
    services = create_job_services(settings)
    return services.repository.get(job_id)


def list_recent_jobs(limit: int = RECENT_JOBS_LIMIT, settings: Settings | None = None) -> list[AnalysisJobRecord]:
    services = create_job_services(settings)
    return services.repository.list_recent(limit)


def load_job_result(job: AnalysisJobRecord, settings: Settings | None = None) -> dict | None:
    if not job.result_key:
        return None
    services = create_job_services(settings)
    return services.storage.get_json(job.result_key)


def run_analysis_job(job_id: str) -> None:
    services = create_job_services()
    record = services.repository.get(job_id)
    if record is None:
        return

    services.repository.save(_updated_record(record, status="running", error=None))

    try:
        payload = AnalysisJobPayload.from_dict(services.storage.get_json(record.payload_key))
        result = _execute_analysis(payload, services.storage, services.settings)
        result_key = f"jobs/{job_id}/result.json"
        services.storage.put_json(result_key, result)
        completed = _updated_record(
            record,
            status="completed",
            result_key=result_key,
            error=None,
            scorer_mode=str(result.get("scorer_mode", "")),
            duration_ms=int(result.get("duration_ms", 0)),
            warning_count=len(result.get("warnings", [])),
        )
        services.repository.save(completed)
    except Exception as exc:  # noqa: BLE001
        services.repository.save(_updated_record(record, status="failed", error=str(exc)))


def _execute_analysis(payload: AnalysisJobPayload, storage: ObjectStorage, settings: Settings) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        submissions: list[InstructorSubmission] = []

        for instructor_index, instructor in enumerate(payload.instructors, start=1):
            uploads: list[UploadedAsset] = []
            for asset_index, asset_ref in enumerate(instructor.files, start=1):
                destination = root / f"instructor-{instructor_index}-{asset_index}-{_safe_name(asset_ref.original_name)}"
                storage.download_to_path(asset_ref.storage_key, destination)
                uploads.append(UploadedAsset(path=destination, original_name=asset_ref.original_name))

            submissions.append(
                InstructorSubmission(
                    name=instructor.name,
                    files=uploads,
                    youtube_urls=list(instructor.youtube_urls),
                )
            )

        result = analyze_submissions(payload.curriculum_text, submissions, settings)
        return result.to_dict()


def _updated_record(record: AnalysisJobRecord, **changes) -> AnalysisJobRecord:
    updated_at, updated_at_ts = _now()
    payload = record.to_dict()
    payload.update(changes)
    payload["updated_at"] = updated_at
    payload["updated_at_ts"] = updated_at_ts
    return AnalysisJobRecord.from_dict(payload)


def _safe_name(original_name: str) -> str:
    return SAFE_NAME_RE.sub("-", original_name).strip("-") or "upload"


def _now() -> tuple[str, float]:
    current = datetime.now(UTC)
    return current.isoformat(), current.timestamp()


def _import_redis():
    try:
        from redis import Redis
    except ImportError as exc:  # pragma: no cover - dependency is installed in the app environment.
        raise RuntimeError("redis 패키지가 없어 Redis 기반 저장소를 초기화할 수 없습니다.") from exc
    return Redis


def _import_rq_queue():
    try:
        # Avoid importing `rq` top-level here because it eagerly loads worker/scheduler modules.
        from rq.queue import Queue
    except ImportError as exc:  # pragma: no cover - dependency is installed in the app environment.
        raise RuntimeError("rq 패키지가 없어 RQ Queue를 초기화할 수 없습니다.") from exc
    except Exception as exc:  # pragma: no cover - platform-specific import failures.
        raise RuntimeError(
            "RQ Queue 초기화에 실패했습니다. Redis 기반 큐를 쓰는 경우 현재 OS/패키지 조합을 확인해 주세요."
        ) from exc
    return Queue
