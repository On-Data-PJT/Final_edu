from __future__ import annotations

import json
import mimetypes
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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
    load_job_payload,
    load_job_result,
    new_job_id,
)
from final_edu.models import (
    AnalysisJobPayload,
    AnalysisPreparation,
    CourseRecord,
    JobInstructorInput,
    StoredUploadRef,
)
from final_edu.storage import create_object_storage
from final_edu.utils import build_safe_storage_name
from final_edu.youtube import estimate_openai_cost_usd, recommend_analysis_mode, summarize_youtube_inputs

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
            temp_path = Path(temp_dir) / build_safe_storage_name(
                curriculum_pdf.filename or "curriculum.pdf",
                default_stem="curriculum-preview",
                default_ext=".pdf",
                max_basename_chars=72,
            )
            await _write_upload_to_path(curriculum_pdf, temp_path, settings.max_upload_bytes)
            preview = preview_course_pdf(temp_path, settings.max_sections, settings)
        return JSONResponse(preview.to_dict())

    @app.post("/courses", response_class=JSONResponse)
    async def create_course(
        course_name: str = Form(...),
        sections_json: str = Form(...),
        instructor_names_json: str = Form("[]"),
        raw_curriculum_text: str = Form(""),
        curriculum_pdf: UploadFile = File(...),
    ) -> JSONResponse:
        _ensure_pdf_upload(curriculum_pdf)
        try:
            sections_payload = json.loads(sections_json)
            if not isinstance(sections_payload, list):
                raise ValueError("sections_json must be a list")
            instructor_names_payload = json.loads(instructor_names_json)
            if not isinstance(instructor_names_payload, list):
                raise ValueError("instructor_names_json must be a list")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"과정 섹션 정보를 해석하지 못했습니다. ({exc})") from exc

        normalized_instructor_names: list[str] = []
        for item in instructor_names_payload:
            name = str(item or "").strip()
            if name and name not in normalized_instructor_names:
                normalized_instructor_names.append(name)
        if not normalized_instructor_names:
            raise HTTPException(status_code=400, detail="과정에는 최소 1명의 강사를 등록해 주세요.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / build_safe_storage_name(
                curriculum_pdf.filename or "curriculum.pdf",
                default_stem="curriculum-upload",
                default_ext=".pdf",
                max_basename_chars=72,
            )
            await _write_upload_to_path(curriculum_pdf, temp_path, settings.max_upload_bytes)
            try:
                record = create_course_record(
                    name=course_name,
                    curriculum_pdf_path=temp_path,
                    curriculum_pdf_name=curriculum_pdf.filename or "curriculum.pdf",
                    sections_payload=sections_payload,
                    instructor_names=normalized_instructor_names,
                    raw_curriculum_text=raw_curriculum_text,
                    storage=storage,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    @app.post("/analyze/prepare", response_class=JSONResponse)
    async def analyze_prepare(request: Request) -> JSONResponse:
        form = await request.form()
        try:
            preparation = await _prepare_analysis_request(
                form=form,
                request_id=new_job_id(),
                course_repository=course_repository,
                storage=storage,
                settings=settings,
            )
            _save_preparation(storage, preparation)
            return JSONResponse(_serialize_preparation(preparation))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/analyze/prepare/{request_id}/confirm", response_class=JSONResponse)
    async def analyze_prepare_confirm(request: Request, request_id: str) -> JSONResponse:
        preparation = _load_preparation(storage, request_id)
        if preparation is None:
            raise HTTPException(status_code=404, detail="분석 준비 정보를 찾지 못했습니다.")
        record = enqueue_analysis_job(
            preparation.payload,
            len(preparation.payload.course_sections),
            settings,
            selected_analysis_mode=preparation.recommended_analysis_mode,
            estimated_cost_usd=preparation.estimated_cost_usd,
            expanded_video_count=preparation.expanded_video_count,
        )
        return JSONResponse(
            {
                "job_id": record.id,
                "redirect_url": str(request.url_for("job_detail", job_id=record.id)),
            }
        )

    @app.post("/analyze", response_class=HTMLResponse)
    async def analyze(request: Request) -> HTMLResponse:
        form = await request.form()
        try:
            preparation = await _prepare_analysis_request(
                form=form,
                request_id=new_job_id(),
                course_repository=course_repository,
                storage=storage,
                settings=settings,
            )
            job = enqueue_analysis_job(
                preparation.payload,
                len(preparation.payload.course_sections),
                settings,
                selected_analysis_mode=preparation.recommended_analysis_mode,
                estimated_cost_usd=preparation.estimated_cost_usd,
                expanded_video_count=preparation.expanded_video_count,
            )
            return RedirectResponse(url=request.url_for("job_detail", job_id=job.id), status_code=303)
        except ValueError as exc:
            course_id = str(form.get("course_id", "") or "").strip()
            course = course_repository.get(course_id) if course_id else None
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

    @app.get("/jobs/{job_id}/assets/{instructor_index}/{asset_index}", response_class=Response, name="job_asset_download")
    async def job_asset_download(job_id: str, instructor_index: int, asset_index: int) -> Response:
        job = get_job(job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾지 못했습니다.")

        payload = load_job_payload(job, settings)
        if payload is None:
            raise HTTPException(status_code=404, detail="작업 입력을 찾지 못했습니다.")

        try:
            instructor = payload.instructors[instructor_index - 1]
            asset_ref = instructor.files[asset_index - 1]
        except IndexError as exc:
            raise HTTPException(status_code=404, detail="업로드 자료를 찾지 못했습니다.") from exc

        original_name = Path(asset_ref.original_name or f"upload-{instructor_index}-{asset_index}").name
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / build_safe_storage_name(
                original_name,
                default_stem=f"job-asset-{instructor_index}-{asset_index}",
                max_basename_chars=72,
            )
            storage.download_to_path(asset_ref.storage_key, temp_path)
            payload_bytes = temp_path.read_bytes()

        media_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        ascii_name = Path(build_safe_storage_name(original_name, default_stem="download", max_basename_chars=48)).name
        content_disposition = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(original_name)}'
        )
        return Response(
            content=payload_bytes,
            media_type=media_type,
            headers={"Content-Disposition": content_disposition},
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
        payload["phase_label"] = _phase_label(job.phase)
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
    recent_job_records = list_recent_jobs(limit=settings.max_saved_jobs, settings=settings)
    return {
        "request": request,
        "settings": settings,
        "error": error,
        "courses": serialized_courses,
        "courses_json": json.dumps(serialized_courses, ensure_ascii=False),
        "course_restore_drafts_json": json.dumps(
            _serialize_course_restore_drafts(request, settings, recent_job_records),
            ensure_ascii=False,
        ),
        "selected_course_id": selected_course.id if selected_course else "",
        "selected_course_name": selected_course.name if selected_course else "",
        "recent_jobs": [_job_card(job, request) for job in recent_job_records],
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
            "phase_label": _phase_label(job.get("phase")),
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
            "phase_label": _phase_label(job.get("phase")),
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

    for asset_index, upload in enumerate(uploads, start=1):
        original_name = Path(upload.filename or f"upload-{index}").name
        safe_temp_name = build_safe_storage_name(
            original_name,
            default_stem=f"upload-{index}",
            max_basename_chars=72,
        )
        temp_path = temp_dir / f"instructor-{index}-{asset_index}-{safe_temp_name}"
        total_size = await _write_upload_to_path(upload, temp_path, max_upload_bytes)
        if total_size == 0:
            continue
        storage_key = build_upload_key(job_id, index, original_name)
        storage.put_file(storage_key, temp_path, content_type=upload.content_type)
        stored_uploads.append(StoredUploadRef(storage_key=storage_key, original_name=original_name))

    urls = [line.strip() for line in youtube_urls.splitlines() if line.strip()]
    return JobInstructorInput(
        name=normalized_name,
        files=stored_uploads,
        youtube_inputs=urls,
        youtube_urls=[],
    )


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
        "instructor_names": list(course.instructor_names),
        "raw_curriculum_text": course.raw_curriculum_text,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        "section_count": len(course.sections),
    }


async def _prepare_analysis_request(
    *,
    form,
    request_id: str,
    course_repository,
    storage,
    settings,
) -> AnalysisPreparation:
    course_id = str(form.get("course_id", "") or "").strip()
    course = course_repository.get(course_id) if course_id else None
    if course is None:
        raise ValueError("분석할 과정을 먼저 선택해 주세요.")

    manifest = _parse_instructor_manifest(str(form.get("instructor_manifest", "[]") or "[]"))
    if len(manifest) < 1:
        raise ValueError("최소 1명의 강사 자료가 필요합니다.")

    instructors: list[JobInstructorInput] = []
    playlist_summaries: list[dict] = []
    warnings: list[str] = []
    expanded_video_count = 0
    estimated_transcript_tokens = 0
    estimated_chunk_count = 0
    estimated_processing_seconds = 0
    total_video_duration_seconds = 0
    caption_probe_sample_count = 0
    caption_probe_success_count = 0
    has_playlist = False

    with tempfile.TemporaryDirectory() as temp_dir:
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
                job_id=request_id,
                temp_dir=Path(temp_dir),
                name=name,
                youtube_urls=youtube_urls,
                uploads=uploads,
                max_upload_bytes=settings.max_upload_bytes,
                storage=storage,
            )
            if instructor.youtube_inputs:
                youtube_summary = summarize_youtube_inputs(
                    instructor.youtube_inputs,
                    settings=settings,
                    instructor_count=max(1, len(manifest)),
                    section_count=len(course.sections),
                )
                instructor.youtube_urls = list(youtube_summary["expanded_urls"])
                has_playlist = has_playlist or bool(youtube_summary["has_playlist"])
                expanded_video_count += int(youtube_summary["expanded_video_count"])
                estimated_transcript_tokens += int(youtube_summary["estimated_transcript_tokens"])
                estimated_chunk_count += int(youtube_summary["estimated_chunk_count"])
                estimated_processing_seconds += int(youtube_summary["estimated_processing_seconds"])
                total_video_duration_seconds += int(youtube_summary["total_duration_seconds"])
                caption_probe_sample_count += int(youtube_summary["caption_probe_sample_count"])
                caption_probe_success_count += int(youtube_summary["caption_probe_success_count"])
                warnings.extend(youtube_summary["warnings"])
                playlist_summaries.extend(
                    {
                        **summary,
                        "instructor_name": instructor.name,
                    }
                    for summary in youtube_summary["playlist_summaries"]
                )
            if instructor.files or instructor.youtube_urls:
                instructors.append(instructor)

    if len(instructors) < 1:
        raise ValueError("강사명과 자료가 있는 강사 1명 이상이 필요합니다.")

    recommended_analysis_mode = (
        recommend_analysis_mode(
            settings=settings,
            expanded_video_count=expanded_video_count,
            estimated_chunk_count=estimated_chunk_count,
            estimated_transcript_tokens=estimated_transcript_tokens,
        )
        if expanded_video_count > 0
        else ("openai" if settings.openai_api_key else "lexical")
    )
    estimated_cost_usd = estimate_openai_cost_usd(
        settings=settings,
        analysis_mode=recommended_analysis_mode,
        transcript_tokens=estimated_transcript_tokens,
        instructor_count=len(instructors),
        section_count=len(course.sections),
    )
    requires_confirmation = bool(has_playlist or expanded_video_count > settings.small_youtube_video_threshold or warnings)
    payload = AnalysisJobPayload(
        job_id=request_id,
        course_id=course.id,
        course_name=course.name,
        course_sections=course.sections,
        curriculum_text=_sections_to_curriculum_text(course.sections),
        instructors=instructors,
        submitted_at=_now_iso(),
        analysis_mode=recommended_analysis_mode,
    )
    return AnalysisPreparation(
        request_id=request_id,
        payload=payload,
        created_at=_now_iso(),
        requires_confirmation=requires_confirmation,
        recommended_analysis_mode=recommended_analysis_mode,
        estimated_cost_usd=estimated_cost_usd,
        estimated_transcript_tokens=estimated_transcript_tokens,
        estimated_chunk_count=estimated_chunk_count,
        estimated_processing_seconds=estimated_processing_seconds,
        expanded_video_count=expanded_video_count,
        total_video_duration_seconds=total_video_duration_seconds,
        caption_probe_sample_count=caption_probe_sample_count,
        caption_probe_success_count=caption_probe_success_count,
        has_playlist=has_playlist,
        playlist_summaries=playlist_summaries,
        warnings=warnings,
    )


def _preparation_key(request_id: str) -> str:
    return f"analysis-preparations/{request_id}.json"


def _save_preparation(storage, preparation: AnalysisPreparation) -> None:
    storage.put_json(_preparation_key(preparation.request_id), preparation.to_dict())


def _load_preparation(storage, request_id: str) -> AnalysisPreparation | None:
    try:
        payload = storage.get_json(_preparation_key(request_id))
    except Exception:  # noqa: BLE001
        return None
    if not payload:
        return None
    return AnalysisPreparation.from_dict(payload)


def _job_card(job, request: Request) -> dict:  # noqa: ANN001
    return {
        "id": job.id,
        "course_name": job.course_name,
        "status": job.status,
        "status_label": _status_label(job.status),
        "phase": job.phase,
        "phase_label": _phase_label(job.phase),
        "updated_at_label": _format_timestamp(job.updated_at),
        "created_at_label": _format_timestamp(job.created_at),
        "instructor_names": list(job.instructor_names),
        "instructor_count": job.instructor_count,
        "asset_count": job.asset_count,
        "youtube_url_count": job.youtube_url_count,
        "expanded_video_count": job.expanded_video_count,
        "section_count": job.section_count,
        "url": request.url_for("job_detail", job_id=job.id),
    }


def _serialize_course_restore_drafts(request: Request, settings, jobs) -> dict:  # noqa: ANN001
    drafts: dict[str, dict] = {}
    for job in jobs:
        course_id = str(getattr(job, "course_id", "") or "").strip()
        if not course_id or course_id in drafts:
            continue
        try:
            payload = load_job_payload(job, settings)
        except Exception:
            continue
        if payload is None or not payload.instructors:
            continue
        drafts[course_id] = {
            "course_id": course_id,
            "job_id": job.id,
            "updated_at": job.updated_at,
            "updated_at_label": _format_timestamp(job.updated_at),
            "blocks": [
                {
                    "instructor_name": instructor.name,
                    "mode": "files" if instructor.files else "youtube",
                    "youtube_urls": list(instructor.youtube_inputs or instructor.youtube_urls),
                    "files": [
                        {
                            "original_name": asset_ref.original_name,
                            "download_url": str(
                                request.url_for(
                                    "job_asset_download",
                                    job_id=job.id,
                                    instructor_index=str(instructor_index),
                                    asset_index=str(asset_index),
                                )
                            ),
                        }
                        for asset_index, asset_ref in enumerate(instructor.files, start=1)
                    ],
                }
                for instructor_index, instructor in enumerate(payload.instructors, start=1)
            ],
        }
    return drafts


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


def _phase_label(phase: str | None) -> str:
    labels = {
        "playlist_expanding": "재생목록 확장 중",
        "transcript_fetching": "자막 수집 중",
        "chunking": "텍스트 정리 중",
        "assigning": "커리큘럼 매핑 중",
        "insight_generating": "인사이트 생성 중",
    }
    return labels.get(str(phase or "").strip(), "")


def _serialize_preparation(preparation: AnalysisPreparation) -> dict:
    return {
        "request_id": preparation.request_id,
        "requires_confirmation": preparation.requires_confirmation,
        "recommended_analysis_mode": preparation.recommended_analysis_mode,
        "estimated_cost_usd": preparation.estimated_cost_usd,
        "estimated_transcript_tokens": preparation.estimated_transcript_tokens,
        "estimated_chunk_count": preparation.estimated_chunk_count,
        "estimated_processing_seconds": preparation.estimated_processing_seconds,
        "expanded_video_count": preparation.expanded_video_count,
        "total_video_duration_seconds": preparation.total_video_duration_seconds,
        "caption_probe_sample_count": preparation.caption_probe_sample_count,
        "caption_probe_success_count": preparation.caption_probe_success_count,
        "has_playlist": preparation.has_playlist,
        "playlist_summaries": list(preparation.playlist_summaries),
        "warnings": list(preparation.warnings),
    }


def _format_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
