from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from final_edu.config import get_settings
from final_edu.courses import (
    LocalCourseRepository,
    create_course_record,
    preview_course_pdf,
    section_to_dict,
)
from final_edu.jobs import (
    build_upload_key,
    enqueue_analysis_job,
    get_job,
    list_recent_jobs,
    load_job_result,
    new_job_id,
)
from final_edu.models import AnalysisJobPayload, CourseRecord, JobInstructorInput, StoredUploadRef
from final_edu.storage import create_object_storage

PACKAGE_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    storage = create_object_storage(settings)
    course_repository = LocalCourseRepository(settings)
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
            _index_context(
                request=request,
                settings=settings,
                courses=course_repository.list_all(),
            ),
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

    @app.post("/courses/preview", response_class=JSONResponse)
    async def course_preview(
        curriculum_pdf: UploadFile = File(...),
    ) -> JSONResponse:
        _ensure_pdf_upload(curriculum_pdf)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / (Path(curriculum_pdf.filename or "curriculum.pdf").name)
            await _write_upload_to_path(curriculum_pdf, temp_path, settings.max_upload_bytes)
            preview = preview_course_pdf(temp_path, settings.max_sections)
        return JSONResponse(preview)

    @app.post("/courses", response_class=JSONResponse)
    async def create_course(
        course_name: str = Form(...),
        sections_json: str = Form(...),
        raw_curriculum_text: str = Form(""),
        curriculum_pdf: UploadFile = File(...),
    ) -> JSONResponse:
        _ensure_pdf_upload(curriculum_pdf)
        try:
            sections_payload = json.loads(sections_json)
            if not isinstance(sections_payload, list):
                raise ValueError("sections_json must be a list")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"과정 섹션 정보를 해석하지 못했습니다. ({exc})") from exc

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / (Path(curriculum_pdf.filename or "curriculum.pdf").name)
            await _write_upload_to_path(curriculum_pdf, temp_path, settings.max_upload_bytes)
            record = create_course_record(
                name=course_name,
                curriculum_pdf_path=temp_path,
                curriculum_pdf_name=curriculum_pdf.filename or "curriculum.pdf",
                sections_payload=sections_payload,
                raw_curriculum_text=raw_curriculum_text,
                storage=storage,
            )

        course_repository.save(record)
        return JSONResponse(
            {
                "course": _serialize_course(record),
                "courses": [_serialize_course(item) for item in course_repository.list_all()],
            }
        )

    @app.get("/courses", response_class=JSONResponse)
    async def list_courses() -> JSONResponse:
        return JSONResponse({"courses": [_serialize_course(course) for course in course_repository.list_all()]})

    @app.get("/courses/{course_id}", response_class=JSONResponse)
    async def get_course_detail(course_id: str) -> JSONResponse:
        course = course_repository.get(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="과정을 찾지 못했습니다.")
        return JSONResponse({"course": _serialize_course(course)})

    @app.post("/analyze", response_class=HTMLResponse)
    async def analyze(request: Request) -> HTMLResponse:
        form = await request.form()
        course_id = str(form.get("course_id", "") or "").strip()
        course = course_repository.get(course_id) if course_id else None

        try:
            if course is None:
                raise ValueError("분석할 과정을 먼저 선택해 주세요.")

            manifest = _parse_instructor_manifest(str(form.get("instructor_manifest", "[]") or "[]"))
            if len(manifest) < 2:
                raise ValueError("최소 2명의 강사 블록이 필요합니다.")

            job_id = new_job_id()
            with tempfile.TemporaryDirectory() as temp_dir:
                instructors = []
                for block_index, item in enumerate(manifest, start=1):
                    block_id = item["id"]
                    name = str(form.get(f"instructor_name__{block_id}", "") or "")
                    youtube_urls = str(form.get(f"instructor_youtube_urls__{block_id}", "") or "")
                    uploads = [
                        upload
                        for upload in form.getlist(f"instructor_files__{block_id}")
                        if getattr(upload, "filename", None)
                    ]
                    instructor = await _build_job_instructor(
                        index=block_index,
                        job_id=job_id,
                        temp_dir=Path(temp_dir),
                        name=name,
                        youtube_urls=youtube_urls,
                        uploads=uploads,
                        max_upload_bytes=settings.max_upload_bytes,
                        storage=storage,
                    )
                    if instructor.files or instructor.youtube_urls:
                        instructors.append(instructor)

            if len(instructors) < 2:
                raise ValueError("강사명과 자료가 있는 강사 2명 이상이 필요합니다.")

            payload = AnalysisJobPayload(
                job_id=job_id,
                course_id=course.id,
                course_name=course.name,
                course_sections=course.sections,
                curriculum_text=_sections_to_curriculum_text(course.sections),
                instructors=instructors,
                submitted_at=_now_iso(),
            )
            job = enqueue_analysis_job(payload, len(course.sections), settings)
            return RedirectResponse(url=request.url_for("job_detail", job_id=job.id), status_code=303)
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "index.html",
                _index_context(
                    request=request,
                    settings=settings,
                    courses=course_repository.list_all(),
                    error=str(exc),
                    selected_course=course,
                ),
                status_code=400,
            )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse, name="job_detail")
    async def job_detail(request: Request, job_id: str) -> HTMLResponse:
        job = get_job(job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾지 못했습니다.")

        result = load_job_result(job, settings) if job.result_key else None
        return templates.TemplateResponse(
            request,
            "job.html",
            _job_context(request=request, settings=settings, job=job.to_dict(), result=result),
        )

    @app.get("/jobs/{job_id}/solutions", response_class=HTMLResponse, name="job_solutions")
    async def job_solutions(request: Request, job_id: str) -> HTMLResponse:
        job = get_job(job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾지 못했습니다.")

        result = load_job_result(job, settings) if job.result_key else None
        if result is None or str(job.status) != "completed":
            return RedirectResponse(url=request.url_for("job_detail", job_id=job_id), status_code=303)

        return templates.TemplateResponse(
            request,
            "solutions.html",
            _solutions_context(request=request, settings=settings, job=job.to_dict(), result=result),
        )

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


def _index_context(
    *,
    request: Request,
    settings,
    courses: list[CourseRecord],
    error: str | None = None,
    selected_course: CourseRecord | None = None,
) -> dict:
    serialized_courses = [_serialize_course(course) for course in courses]
    return {
        "request": request,
        "settings": settings,
        "error": error,
        "courses": serialized_courses,
        "courses_json": json.dumps(serialized_courses, ensure_ascii=False),
        "selected_course_id": selected_course.id if selected_course else "",
        "selected_course_name": selected_course.name if selected_course else "",
        "recent_jobs": [_job_card(job, request) for job in list_recent_jobs(settings=settings)],
    }


def _job_context(*, request: Request, settings, job: dict, result: dict | None) -> dict:
    selected_instructor = ""
    if result and result.get("instructors"):
        selected_instructor = result["instructors"][0]["name"]

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
        "result_json": json.dumps(result or {}, ensure_ascii=False),
        "selected_instructor": selected_instructor,
    }


def _solutions_context(*, request: Request, settings, job: dict, result: dict) -> dict:
    return {
        "request": request,
        "settings": settings,
        "job": {
            **job,
            "status_label": _status_label(str(job["status"])),
            "created_at_label": _format_timestamp(str(job["created_at"])),
            "updated_at_label": _format_timestamp(str(job["updated_at"])),
        },
        "result": result,
        "result_json": json.dumps(result, ensure_ascii=False),
    }


async def _build_job_instructor(
    *,
    index: int,
    job_id: str,
    temp_dir: Path,
    name: str,
    youtube_urls: str,
    uploads: list[UploadFile],
    max_upload_bytes: int,
    storage,
) -> JobInstructorInput:
    normalized_name = name.strip()
    if not normalized_name:
        normalized_name = f"강사 {index}"
    stored_uploads: list[StoredUploadRef] = []

    for upload in uploads:
        safe_filename = Path(upload.filename or f"upload-{index}").name
        temp_path = temp_dir / f"instructor-{index}-{safe_filename}"
        total_size = await _write_upload_to_path(upload, temp_path, max_upload_bytes)
        if total_size == 0:
            continue
        storage_key = build_upload_key(job_id, index, safe_filename)
        storage.put_file(storage_key, temp_path, content_type=upload.content_type)
        stored_uploads.append(StoredUploadRef(storage_key=storage_key, original_name=safe_filename))

    urls = [line.strip() for line in youtube_urls.splitlines() if line.strip()]
    return JobInstructorInput(name=normalized_name, files=stored_uploads, youtube_urls=urls)


async def _write_upload_to_path(upload: UploadFile, path: Path, max_upload_bytes: int) -> int:
    total_size = 0
    with path.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_upload_bytes:
                await upload.close()
                raise ValueError(
                    f"{Path(upload.filename or 'upload').name}: 업로드 가능 크기를 초과했습니다. 현재 제한은 {max_upload_bytes // (1024 * 1024)}MB입니다."
                )
            handle.write(chunk)
    await upload.close()
    return total_size


def _ensure_pdf_upload(upload: UploadFile) -> None:
    filename = (upload.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="커리큘럼 업로드는 PDF만 지원합니다.")


def _parse_instructor_manifest(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"강사 입력 블록 정보를 해석하지 못했습니다. ({exc})") from exc

    if not isinstance(payload, list):
        raise ValueError("강사 입력 블록 정보가 올바르지 않습니다.")

    manifest = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        block_id = str(item.get("id", "")).strip()
        if not block_id:
            continue
        manifest.append({"id": block_id})

    return manifest


def _serialize_course(course: CourseRecord) -> dict:
    return {
        "id": course.id,
        "name": course.name,
        "sections": [section_to_dict(section) for section in course.sections],
        "raw_curriculum_text": course.raw_curriculum_text,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "section_count": len(course.sections),
    }


def _job_card(job, request: Request) -> dict:  # noqa: ANN001
    return {
        "id": job.id,
        "course_name": job.course_name,
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


def _sections_to_curriculum_text(sections) -> str:  # noqa: ANN001
    return "\n".join(f"{section.title} | {section.description}" for section in sections)


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
    return parsed.astimezone(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
