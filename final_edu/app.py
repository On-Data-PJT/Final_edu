from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from final_edu.analysis import parse_curriculum_sections
from final_edu.config import get_settings
from final_edu.jobs import (
    build_upload_key,
    enqueue_analysis_job,
    get_job,
    list_recent_jobs,
    load_job_result,
    new_job_id,
)
from final_edu.models import AnalysisJobPayload, JobInstructorInput, StoredUploadRef
from final_edu.storage import create_object_storage

PACKAGE_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    storage = create_object_storage(settings)
    app = FastAPI(
        title=settings.app_name,
        description="강의 자료 기반 커리큘럼 커버리지 분석 MVP",
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            _index_context(request=request, settings=settings),
        )

    @app.get("/health", response_class=JSONResponse)
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "app": settings.app_name,
                "queue_mode": settings.queue_mode,
                "storage_mode": settings.storage_mode,
            }
        )

    @app.post("/analyze", response_class=HTMLResponse)
    async def analyze(
        request: Request,
        curriculum_text: Annotated[str, Form()],
        instructor_1_name: Annotated[str, Form()] = "",
        instructor_1_youtube_urls: Annotated[str, Form()] = "",
        instructor_1_files: Annotated[list[UploadFile] | None, File()] = None,
        instructor_2_name: Annotated[str, Form()] = "",
        instructor_2_youtube_urls: Annotated[str, Form()] = "",
        instructor_2_files: Annotated[list[UploadFile] | None, File()] = None,
        instructor_3_name: Annotated[str, Form()] = "",
        instructor_3_youtube_urls: Annotated[str, Form()] = "",
        instructor_3_files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> HTMLResponse:
        form_values = {
            "curriculum_text": curriculum_text,
            "instructors": [
                {"name": instructor_1_name, "youtube_urls": instructor_1_youtube_urls},
                {"name": instructor_2_name, "youtube_urls": instructor_2_youtube_urls},
                {"name": instructor_3_name, "youtube_urls": instructor_3_youtube_urls},
            ],
        }

        try:
            sections = parse_curriculum_sections(curriculum_text, settings.max_sections)
            job_id = new_job_id()
            with tempfile.TemporaryDirectory() as temp_dir:
                instructors = [
                    await _build_job_instructor(
                        index=1,
                        job_id=job_id,
                        temp_dir=Path(temp_dir),
                        name=instructor_1_name,
                        youtube_urls=instructor_1_youtube_urls,
                        uploads=instructor_1_files,
                        max_upload_bytes=settings.max_upload_bytes,
                        storage=storage,
                    ),
                    await _build_job_instructor(
                        index=2,
                        job_id=job_id,
                        temp_dir=Path(temp_dir),
                        name=instructor_2_name,
                        youtube_urls=instructor_2_youtube_urls,
                        uploads=instructor_2_files,
                        max_upload_bytes=settings.max_upload_bytes,
                        storage=storage,
                    ),
                    await _build_job_instructor(
                        index=3,
                        job_id=job_id,
                        temp_dir=Path(temp_dir),
                        name=instructor_3_name,
                        youtube_urls=instructor_3_youtube_urls,
                        uploads=instructor_3_files,
                        max_upload_bytes=settings.max_upload_bytes,
                        storage=storage,
                    ),
                ]

            active_instructors = [instructor for instructor in instructors if instructor.files or instructor.youtube_urls]
            if len(active_instructors) < 2:
                raise ValueError("최소 2명의 강사 자료가 필요합니다.")

            payload = AnalysisJobPayload(
                job_id=job_id,
                curriculum_text=curriculum_text,
                instructors=active_instructors,
                submitted_at=datetime.now().isoformat(timespec="seconds"),
            )
            job = enqueue_analysis_job(payload, len(sections), settings)
            return RedirectResponse(url=request.url_for("job_detail", job_id=job.id), status_code=303)
        except ValueError as exc:
            context = _index_context(
                request=request,
                settings=settings,
                form_values=form_values,
                error=str(exc),
            )
            return templates.TemplateResponse(request, "index.html", context, status_code=400)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse, name="job_detail")
    async def job_detail(request: Request, job_id: str) -> HTMLResponse:
        job = get_job(job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾지 못했습니다.")

        result = load_job_result(job, settings) if job.result_key else None
        context = _job_context(
            request=request,
            settings=settings,
            job=job.to_dict(),
            result=result,
        )
        return templates.TemplateResponse(request, "job.html", context)

    @app.get("/jobs/{job_id}/status", response_class=JSONResponse, name="job_status")
    async def job_status(job_id: str) -> JSONResponse:
        job = get_job(job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾지 못했습니다.")
        payload = job.to_dict()
        payload["status_label"] = _status_label(job.status)
        payload["updated_at_label"] = _format_timestamp(job.updated_at)
        payload["has_result"] = bool(job.result_key)
        return JSONResponse(payload)

    return app


async def _build_job_instructor(
    index: int,
    job_id: str,
    temp_dir: Path,
    name: str,
    youtube_urls: str,
    uploads: list[UploadFile] | None,
    max_upload_bytes: int,
    storage,
) -> JobInstructorInput:
    normalized_name = name.strip() or f"강사 {index}"
    stored_uploads: list[StoredUploadRef] = []

    for upload in uploads or []:
        if not upload.filename:
            continue

        safe_filename = Path(upload.filename).name or f"upload-{index}"
        temp_path = temp_dir / f"instructor-{index}-{safe_filename}"
        total_size = 0

        with temp_path.open("wb") as file_handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_upload_bytes:
                    await upload.close()
                    raise ValueError(
                        f"{safe_filename}: 업로드 가능 크기를 초과했습니다. 현재 제한은 {max_upload_bytes // (1024 * 1024)}MB입니다."
                    )
                file_handle.write(chunk)

        await upload.close()
        if total_size == 0:
            continue

        storage_key = build_upload_key(job_id, index, safe_filename)
        storage.put_file(storage_key, temp_path, content_type=upload.content_type)
        stored_uploads.append(StoredUploadRef(storage_key=storage_key, original_name=safe_filename))

    urls = [line.strip() for line in youtube_urls.splitlines() if line.strip()]
    return JobInstructorInput(name=normalized_name, files=stored_uploads, youtube_urls=urls)


def _index_context(
    request: Request,
    settings,
    form_values: dict | None = None,
    error: str | None = None,
) -> dict:
    recent_jobs = [_job_card(job, request) for job in list_recent_jobs(settings=settings)]
    return {
        "request": request,
        "settings": settings,
        "error": error,
        "recent_jobs": recent_jobs,
        "supported_formats": ["PDF", "PPTX", "TXT", "MD", "YouTube URL"],
        "form_values": form_values
        or {
            "curriculum_text": "",
            "instructors": [
                {"name": "강사 A", "youtube_urls": ""},
                {"name": "강사 B", "youtube_urls": ""},
                {"name": "강사 C", "youtube_urls": ""},
            ],
        },
        "method_badges": [
            "배치 분석 작업 생성",
            "대단원 수준 분류",
            "근거 스니펫 제공",
            "OpenAI 임베딩 optional",
        ],
    }


def _job_context(request: Request, settings, job: dict, result: dict | None) -> dict:
    return {
        "request": request,
        "settings": settings,
        "job": {
            **job,
            "status_label": _status_label(str(job["status"])),
            "created_at_label": _format_timestamp(str(job["created_at"])),
            "updated_at_label": _format_timestamp(str(job["updated_at"])),
            "is_active": str(job["status"]) in {"queued", "running"},
            "is_failed": str(job["status"]) == "failed",
            "is_completed": str(job["status"]) == "completed",
        },
        "result": result,
        "comparison_rows": _comparison_rows(result) if result else [],
    }


def _job_card(job, request: Request) -> dict:  # noqa: ANN001
    return {
        "id": job.id,
        "status": job.status,
        "status_label": _status_label(job.status),
        "updated_at_label": _format_timestamp(job.updated_at),
        "created_at_label": _format_timestamp(job.created_at),
        "instructor_names": list(job.instructor_names),
        "instructor_count": job.instructor_count,
        "asset_count": job.asset_count,
        "youtube_url_count": job.youtube_url_count,
        "section_count": job.section_count,
        "url": request.url_for("job_detail", job_id=job.id),
    }


def _comparison_rows(result: dict | None) -> list[dict]:
    if not result:
        return []

    rows = []
    sections = _read(result, "sections")
    instructors = _read(result, "instructors")

    for section in sections:
        items = []
        section_id = _read(section, "id")
        section_title = _read(section, "title")

        for instructor in instructors:
            coverage = next(
                coverage
                for coverage in _read(instructor, "section_coverages")
                if _read(coverage, "section_id") == section_id
            )
            items.append(
                {
                    "name": _read(instructor, "name"),
                    "share": float(_read(coverage, "token_share")),
                    "deviation": float(_read(coverage, "deviation_from_average")),
                }
            )

        rows.append({"title": section_title, "entries": items})

    rows.append(
        {
            "title": "Other / Unmapped",
            "entries": [
                {
                    "name": _read(instructor, "name"),
                    "share": float(_read(instructor, "unmapped_share")),
                    "deviation": 0.0,
                }
                for instructor in instructors
            ],
        }
    )
    return rows


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _status_label(status: str) -> str:
    labels = {
        "queued": "대기중",
        "running": "분석중",
        "completed": "완료",
        "failed": "실패",
    }
    return labels.get(status, status)


def _format_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")
