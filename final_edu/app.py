from __future__ import annotations

import json
import logging
import mimetypes
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from final_edu.analysis import analyze_voc_assets
from final_edu.config import get_settings
from final_edu.courses import (
    LocalCourseRepository,
    create_course_record,
    preview_course_pdf,
    section_to_dict,
)
from final_edu.jobs import (
    build_upload_key,
    delete_job,
    enqueue_analysis_job,
    get_job,
    list_course_jobs,
    list_recent_jobs,
    load_job_payload,
    load_job_result,
    new_job_id,
)
from final_edu.extractors import extract_voc_asset
from final_edu.models import (
    AnalysisJobPayload,
    AnalysisPreparation,
    CourseRecord,
    JobInstructorInput,
    StoredUploadRef,
    UploadedAsset,
)
from final_edu.storage import create_object_storage
from final_edu.utils import build_safe_storage_name, ensure_kiwi_ready

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
from final_edu.youtube import estimate_openai_cost_usd, recommend_analysis_mode, summarize_youtube_inputs

PACKAGE_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
STATIC_ROOT = (PACKAGE_ROOT / "static").resolve()
QUEUED_JOB_STALLED_SECONDS = 90
RUNNING_JOB_STALLED_SECONDS = 180
logger = logging.getLogger(__name__)


def _normalize_lane_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "youtube":
        return "youtube"
    if normalized == "voc":
        return "voc"
    return "files"


def _normalize_submitted_instructor_name(raw_name: str, index: int, roster: list[str]) -> str:
    normalized_name = str(raw_name or "").strip()
    normalized_roster = [str(item or "").strip() for item in roster if str(item or "").strip()]
    if normalized_name and normalized_name in normalized_roster:
        return normalized_name

    generic_index = None
    if normalized_name.startswith("강사 "):
        try:
            generic_index = int(normalized_name.split(" ", maxsplit=1)[1]) - 1
        except (TypeError, ValueError):
            generic_index = None

    if generic_index is not None and 0 <= generic_index < len(normalized_roster):
        return normalized_roster[generic_index]
    if len(normalized_roster) == 1:
        return normalized_roster[0]
    if normalized_name:
        return normalized_name
    return f"강사 {index}"


def _normalize_page1_submission_version(value: Any) -> int:
    try:
        normalized = int(str(value or "").strip() or "1")
    except (TypeError, ValueError):
        return 1
    return normalized if normalized >= 1 else 1


def _static_asset_url(request: Request, path: str) -> str:
    normalized_path = str(path or "").lstrip("/")
    url = request.url_for("static", path=normalized_path)
    asset_path = (STATIC_ROOT / normalized_path).resolve()
    try:
        asset_path.relative_to(STATIC_ROOT)
    except ValueError:
        return str(url)
    if not asset_path.is_file():
        return str(url)
    return str(url.include_query_params(v=asset_path.stat().st_mtime_ns))


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    storage = create_object_storage(settings)
    course_repository = LocalCourseRepository(settings)
    app = FastAPI(
        title=settings.app_name,
        description="강의 자료 기반 커리큘럼 커버리지 분석 MVP",
        lifespan=_app_lifespan,
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")
    templates.env.globals["static_asset_url"] = _static_asset_url

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

    @app.get("/demo", response_class=HTMLResponse)
    async def demo(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "demo.html",
            _demo_context(request=request, settings=settings),
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
            preview = await run_in_threadpool(preview_course_pdf, temp_path, settings.max_sections, settings)
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

    @app.delete("/courses/{course_id}", response_class=JSONResponse)
    async def delete_course(course_id: str) -> JSONResponse:
        course = course_repository.get(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="과정을 찾지 못했습니다.")

        related_jobs = list_course_jobs(course_id, settings)
        active_jobs = [job for job in related_jobs if str(job.status) in {"queued", "running"}]
        if active_jobs:
            raise HTTPException(status_code=409, detail="분석이 진행 중인 과정은 삭제할 수 없습니다.")

        deleted_job_count = 0
        for job in related_jobs:
            storage.delete_prefix(f"jobs/{job.id}/")
            if delete_job(job.id, settings):
                deleted_job_count += 1

        deleted_preparation_count = _delete_preparations_for_course(storage, course_id)
        storage.delete_key(course.curriculum_pdf_key)
        course_repository.delete(course_id)
        return JSONResponse(
            {
                "course_id": course_id,
                "deleted_job_count": deleted_job_count,
                "deleted_preparation_count": deleted_preparation_count,
            }
        )

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
        if course_repository.get(preparation.payload.course_id) is None:
            storage.delete_key(_preparation_key(request_id))
            raise HTTPException(status_code=404, detail="과정이 삭제되어 분석을 시작할 수 없습니다.")
        asset_count = sum(len(instructor.files) + len(instructor.voc_files) for instructor in preparation.payload.instructors)
        youtube_url_count = sum(len(instructor.youtube_urls or instructor.youtube_inputs) for instructor in preparation.payload.instructors)
        logger.info(
            "Confirming prepared analysis %s (job_id=%s, course_id=%s, instructors=%s, assets=%s, youtube_urls=%s, queue_mode=%s)",
            request_id,
            preparation.payload.job_id,
            preparation.payload.course_id,
            len(preparation.payload.instructors),
            asset_count,
            youtube_url_count,
            settings.queue_mode,
        )
        record = enqueue_analysis_job(
            preparation.payload,
            len(preparation.payload.course_sections),
            settings,
            selected_analysis_mode=preparation.recommended_analysis_mode,
            estimated_cost_usd=preparation.estimated_cost_usd,
            expanded_video_count=preparation.expanded_video_count,
        )
        if record.status == "failed":
            logger.warning("Prepared analysis %s failed to enqueue job %s (%s)", request_id, record.id, record.error)
        else:
            logger.info("Prepared analysis %s enqueued job %s", request_id, record.id)
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

    @app.get(
        "/jobs/{job_id}/voc-assets/{instructor_index}/{asset_index}",
        response_class=Response,
        name="job_voc_asset_download",
    )
    async def job_voc_asset_download(job_id: str, instructor_index: int, asset_index: int) -> Response:
        job = get_job(job_id, settings)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾지 못했습니다.")

        payload = load_job_payload(job, settings)
        if payload is None:
            raise HTTPException(status_code=404, detail="작업 입력을 찾지 못했습니다.")

        try:
            instructor = payload.instructors[instructor_index - 1]
            asset_ref = instructor.voc_files[asset_index - 1]
        except IndexError as exc:
            raise HTTPException(status_code=404, detail="업로드 VOC 파일을 찾지 못했습니다.") from exc

        original_name = Path(asset_ref.original_name or f"voc-{instructor_index}-{asset_index}").name
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / build_safe_storage_name(
                original_name,
                default_stem=f"job-voc-{instructor_index}-{asset_index}",
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

    @app.get("/solution", response_class=HTMLResponse, name="solution_page")
    async def solution_page(request: Request, job_id: str | None = None) -> HTMLResponse:
        job = None
        result = None

        if job_id:
            job = get_job(job_id, settings)
            if job is None:
                raise HTTPException(status_code=404, detail="해당 작업을 찾을 수 없습니다.")
            if job.result_key:
                result = load_job_result(job, settings)
        else:
            for recent_job in list_recent_jobs(settings=settings):
                if recent_job.result_key:
                    job = recent_job
                    result = load_job_result(recent_job, settings)
                    break

        solution_input = _build_solution_payload(result)
        solution_content, generation_mode, generation_warning = _generate_solution_content(solution_input, settings)
        dashboard_links = _job_dashboard_links(request, job)

        return templates.TemplateResponse(
            request,
            "solution.html",
            {
                "request": request,
                "settings": settings,
                "job": job.to_dict() if job else None,
                "dashboard_links": dashboard_links,
                "solution_payload": {
                    **solution_input,
                    "content": solution_content,
                    "generation_mode": generation_mode,
                    "generation_warning": generation_warning,
                },
            },
        )

    @app.get("/review", response_class=HTMLResponse, name="review_page")
    async def review_page(request: Request, job_id: str | None = None) -> HTMLResponse:
        job = None
        result = None
        if job_id:
            job = get_job(job_id, settings)
            if job and job.result_key:
                result = load_job_result(job, settings)
        else:
            for recent_job in list_recent_jobs(settings=settings):
                if recent_job.result_key:
                    job = recent_job
                    result = load_job_result(recent_job, settings)
                    break

        payload = _build_review_payload(result)
        dashboard_links = _job_dashboard_links(request, job)
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "request": request,
                "settings": settings,
                "job": job.to_dict() if job else None,
                "dashboard_links": dashboard_links,
                "review_payload": payload,
            },
        )

    @app.post("/api/evaluate", response_class=JSONResponse)
    async def api_evaluate(
        request: Request,
        review_file: UploadFile = File(...),
        instructor_name: str = Form(""),
    ) -> JSONResponse:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                safe_name = build_safe_storage_name(
                    review_file.filename or "review.txt",
                    default_stem="review-upload",
                    max_basename_chars=72,
                )
                temp_path = Path(temp_dir) / safe_name
                size = await _write_upload_to_path(review_file, temp_path, settings.max_upload_bytes)
                if size == 0:
                    return JSONResponse({"error": "비어 있는 파일은 분석할 수 없어요."}, status_code=400)

                analysis, warnings = analyze_voc_assets(
                    instructor_name=instructor_name.strip() or "강사",
                    uploads=[UploadedAsset(path=temp_path, original_name=review_file.filename or safe_name)],
                    settings=settings,
                )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"VOC 분석 실패: {exc}"}, status_code=500)

        if warnings:
            analysis["warnings"] = warnings
        return JSONResponse(analysis)

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
        payload.update(_job_runtime_status(job))
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


def _demo_context(*, request: Request, settings) -> dict:
    # Simplified sample data focusing on the Overview
    sections = [
        {"id": "python-core", "title": "Python 핵심 문법", "description": "기초 데이터 타입 및 제어 흐름", "target_weight": 15.0},
        {"id": "data-viz", "title": "데이터 시각화", "description": "Matplotlib 및 Seaborn 실습", "target_weight": 20.0},
        {"id": "ml-theory", "title": "머신러닝 이론", "description": "지도 학습과 비지도 학습 알고리즘", "target_weight": 20.0},
        {"id": "deep-learning", "title": "딥러닝 응용", "description": "CNN, RNN 기반 실무 적용", "target_weight": 25.0},
        {"id": "nlp-basics", "title": "자연어 처리 기초", "description": "텍스트 전처리 및 임베딩 모델", "target_weight": 10.0},
        {"id": "deployment", "title": "모델 배포/운영", "description": "FastAPI 및 Docker 기반 서빙", "target_weight": 10.0},
    ]
    
    instructor_names = ["전체 평균", "오정훈 강사", "김데이터 강사", "이파이썬 강사"]
    
    inst_data = []
    for i, name in enumerate(instructor_names):
        # Base values with some variance
        results = {
            "python-core": 12 + i * 2,
            "data-viz": 18 + (i % 3) * 3,
            "ml-theory": 22 - i * 2,
            "deep-learning": 20 + (i % 2) * 8,
            "nlp-basics": 8 + i,
            "deployment": 15 - i * 3
        }
        total = sum(results.values())
        normalized = {k: round(v * 100 / total, 1) for k, v in results.items()}
        
        keywords = [
            {"text": "Python", "value": 25 - i},
            {"text": "Pandas", "value": 20 + i},
            {"text": "TensorFlow", "value": 15 + i*2},
            {"text": "실무 예제", "value": 30 - i*3},
            {"text": "수학 원리", "value": 10 + i*4}
        ]
        inst_data.append({"name": name, "results": normalized, "keywords": keywords})

    result = {
        "course_id": "demo-curriculum-2026",
        "course_name": "2026 실무 인공지능 마스터 클래스",
        "sections": sections,
        "instructors": [
            {
                "name": inst["name"],
                "results": [{"section_id": sid, "value": val} for sid, val in inst["results"].items()],
                "keywords": inst["keywords"]
            }
            for inst in inst_data
        ],
        "rose_series_by_instructor": {
            inst["name"]: [{"section_id": sid, "value": val} for sid, val in inst["results"].items()]
            for inst in inst_data
        },
        "rose_series_by_mode": {
            "combined": {
                inst["name"]: [{"section_id": sid, "value": val} for sid, val in inst["results"].items()]
                for inst in inst_data
            },
            "material": {
                inst["name"]: [{"section_id": sid, "value": round(val * 0.75, 1)} for sid, val in inst["results"].items()]
                for inst in inst_data
            },
            "speech": {
                inst["name"]: [{"section_id": sid, "value": round(val * 0.25, 1)} for sid, val in inst["results"].items()]
                for inst in inst_data
            }
        },
        "keywords_by_instructor": {
            inst["name"]: inst["keywords"]
            for inst in inst_data
        },
        "keywords_by_mode": {
            "combined": {inst["name"]: inst["keywords"] for inst in inst_data},
            "material": {inst["name"]: inst["keywords"][:3] for inst in inst_data},
            "speech": {inst["name"]: inst["keywords"][2:] for inst in inst_data}
        },
        "average_keywords_by_mode": {
            "combined": inst_data[0]["keywords"][:5],
            "material": inst_data[0]["keywords"][:3],
            "speech": inst_data[0]["keywords"][2:6],
        },
        # Necessary for average and comparison visuals even if simplified
        "mode_series": {
            "combined": {
                "average": [
                    {"section_id": s["id"], "section_title": s["title"], "share": sum(inst["results"][s["id"]] for inst in inst_data) / (len(inst_data) * 100)}
                    for s in sections
                ],
                "instructors": {
                    inst["name"]: [{"section_id": sid, "share": val / 100} for sid, val in inst["results"].items()]
                    for inst in inst_data
                }
            }
        },
        "line_series_by_mode": {
            "combined": {
                "target": [{"section_id": s["id"], "share": s["target_weight"] / 100} for s in sections],
                "instructors": {
                    inst["name"]: [{"section_id": sid, "share": val / 100} for sid, val in inst["results"].items()]
                    for inst in inst_data
                }
            }
        },
        "selected_instructor": "전체 평균",
        "external_trends_status": "reflected",
        "insights": [
            {
                "title": "딥러닝 강조 수준",
                "category": "강점",
                "issue": f"{inst_data[0]['name']}는 딥러닝 응용 부문에서 매우 상세한 커버리지를 보입니다.",
                "evidence": f"전체 강의의 {inst_data[0]['results']['deep-learning']}%를 딥러닝 실무에 할당함.",
                "recommendation": "기초 문법 대비 심화 학습 비율이 우수하여 고급 과정으로 적합합니다.",
                "icon": "spark"
            }
        ]
    }

    return {
        "request": request,
        "settings": settings,
        "job": {
            "id": "job-demo-full",
            "course_name": "2026 실무 인공지능 마스터 클래스",
            "status": "completed",
            "status_label": "완료",
            "section_count": len(sections),
            "updated_at_label": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": False,
            "is_failed": False,
            "is_completed": True,
        },
        "result": result,
        "result_json": json.dumps(result, ensure_ascii=False),
        "selected_instructor": inst_data[0]["name"],
    }


async def _build_job_instructor(
    *,
    index: int,
    job_id: str,
    temp_dir: Path,
    name: str,
    mode: str,
    youtube_urls: str,
    uploads: list[UploadFile],
    voc_uploads: list[UploadFile],
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

    stored_voc_uploads: list[StoredUploadRef] = []
    for asset_index, upload in enumerate(voc_uploads, start=1):
        original_name = Path(upload.filename or f"voc-{index}").name
        safe_temp_name = build_safe_storage_name(
            original_name,
            default_stem=f"voc-{index}",
            max_basename_chars=72,
        )
        temp_path = temp_dir / f"instructor-{index}-voc-{asset_index}-{safe_temp_name}"
        total_size = await _write_upload_to_path(upload, temp_path, max_upload_bytes)
        if total_size == 0:
            continue
        await _validate_voc_upload(temp_path, original_name, normalized_name)
        storage_key = f"jobs/{job_id}/uploads/instructor-{index}/voc/{uuid.uuid4().hex[:8]}-{safe_temp_name}"
        storage.put_file(storage_key, temp_path, content_type=upload.content_type)
        stored_voc_uploads.append(StoredUploadRef(storage_key=storage_key, original_name=original_name))

    urls = [line.strip() for line in youtube_urls.splitlines() if line.strip()]
    return JobInstructorInput(
        name=normalized_name,
        mode=_normalize_lane_mode(mode),
        files=stored_uploads,
        youtube_inputs=urls,
        youtube_urls=[],
        voc_files=stored_voc_uploads,
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


async def _validate_voc_upload(path: Path, original_name: str, instructor_name: str) -> None:
    suffix = path.suffix.lower()
    if suffix not in {".pdf", ".csv", ".txt", ".xlsx", ".xls"}:
        raise ValueError(f"{original_name}: VOC 업로드는 PDF, CSV, TXT, XLSX, XLS 파일만 지원합니다.")
    if suffix not in {".xlsx", ".xls"}:
        return
    upload = UploadedAsset(path=path, original_name=original_name)
    await run_in_threadpool(extract_voc_asset, upload, instructor_name)


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
        manifest.append(
            {
                "id": block_id,
                "mode": _normalize_lane_mode(item.get("mode")),
            }
        )

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
    page1_submission_version = _normalize_page1_submission_version(form.get("page1_submission_version"))
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
            block_mode = _normalize_lane_mode(item.get("mode"))
            raw_name = str(form.get(f"instructor_name__{block_id}", "") or "")
            name = _normalize_submitted_instructor_name(raw_name, block_index, course.instructor_names)
            youtube_urls = str(form.get(f"instructor_youtube_urls__{block_id}", "") or "")
            uploads = [
                upload
                for upload in form.getlist(f"instructor_files__{block_id}")
                if getattr(upload, "filename", None)
            ]
            voc_uploads = [
                upload
                for upload in form.getlist(f"instructor_voc__{block_id}")
                if getattr(upload, "filename", None)
            ]
            instructor = await _build_job_instructor(
                index=block_index,
                job_id=request_id,
                temp_dir=Path(temp_dir),
                name=name,
                mode=block_mode,
                youtube_urls=youtube_urls,
                uploads=uploads,
                voc_uploads=voc_uploads,
                max_upload_bytes=settings.max_upload_bytes,
                storage=storage,
            )
            if instructor.youtube_inputs:
                youtube_summary = summarize_youtube_inputs(
                    instructor.youtube_inputs,
                    settings=settings,
                    instructor_count=max(1, len(manifest)),
                    section_count=len(course.sections),
                    storage=storage,
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
            if instructor.files or instructor.youtube_urls or instructor.voc_files:
                instructors.append(instructor)

    if len(instructors) < 1:
        raise ValueError("강사명과 자료 또는 VOC가 있는 강사 1명 이상이 필요합니다.")

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
        page1_submission_version=page1_submission_version,
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


def _delete_preparations_for_course(storage, course_id: str) -> int:
    normalized_course_id = str(course_id or "").strip()
    if not normalized_course_id:
        return 0
    deleted_count = 0
    for key in storage.list_keys("analysis-preparations/"):
        try:
            payload = storage.get_json(key)
            preparation = AnalysisPreparation.from_dict(payload)
        except Exception:  # noqa: BLE001
            continue
        if str(preparation.payload.course_id or "").strip() != normalized_course_id:
            continue
        if storage.delete_key(key):
            deleted_count += 1
    return deleted_count


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


def _job_dashboard_links(request: Request, job) -> dict[str, str]:  # noqa: ANN001
    review_url = str(request.app.url_path_for("review_page"))
    solution_url = str(request.app.url_path_for("solution_page"))
    if job is None:
        return {
            "overview": "/demo",
            "review": review_url,
            "solution": solution_url,
        }

    job_id = str(getattr(job, "id", "") or "").strip()
    if not job_id:
        return {
            "overview": "/demo",
            "review": review_url,
            "solution": solution_url,
        }

    encoded_job_id = quote(job_id, safe="")
    return {
        "overview": str(request.app.url_path_for("job_detail", job_id=job_id)),
        "review": f"{review_url}?job_id={encoded_job_id}",
        "solution": f"{solution_url}?job_id={encoded_job_id}",
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
        submission_version = _normalize_page1_submission_version(
            getattr(payload, "page1_submission_version", 1)
        )
        drafts[course_id] = {
            "course_id": course_id,
            "job_id": job.id,
            "updated_at": job.updated_at,
            "updated_at_label": _format_timestamp(job.updated_at),
            "page1_submission_version": submission_version,
            "requires_reset": submission_version < 2,
            "reset_message": (
                "이전 저장 상태는 구버전이라 초기화되었습니다. 자료를 다시 연결해 주세요."
                if submission_version < 2
                else ""
            ),
            "blocks": (
                []
                if submission_version < 2
                else [
                    {
                        "instructor_name": instructor.name,
                        "mode": _normalize_lane_mode(getattr(instructor, "mode", "")),
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
                        "voc_files": [
                            {
                                "original_name": asset_ref.original_name,
                                "download_url": str(
                                    request.url_for(
                                        "job_voc_asset_download",
                                        job_id=job.id,
                                        instructor_index=str(instructor_index),
                                        asset_index=str(asset_index),
                                    )
                                ),
                            }
                            for asset_index, asset_ref in enumerate(instructor.voc_files, start=1)
                        ],
                    }
                    for instructor_index, instructor in enumerate(payload.instructors, start=1)
                ]
            ),
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


def _job_runtime_status(job) -> dict:  # noqa: ANN001
    now_ts = datetime.now(UTC).timestamp()
    queue_wait_seconds = max(0, int(now_ts - float(getattr(job, "created_at_ts", 0.0) or 0.0)))
    last_update_seconds = max(0, int(now_ts - float(getattr(job, "updated_at_ts", 0.0) or 0.0)))
    status = str(getattr(job, "status", "") or "").strip()
    is_stalled = False
    stalled_message = ""
    if status == "queued" and last_update_seconds >= QUEUED_JOB_STALLED_SECONDS:
        is_stalled = True
        stalled_message = "작업이 오래 대기 중입니다. Render worker 상태와 로그를 확인해 주세요."
    elif status == "running" and last_update_seconds >= RUNNING_JOB_STALLED_SECONDS:
        is_stalled = True
        stalled_message = "작업 진행 로그가 오래 갱신되지 않았습니다. Render worker 상태와 로그를 확인해 주세요."
    return {
        "queue_wait_seconds": queue_wait_seconds,
        "last_update_seconds": last_update_seconds,
        "is_stalled": is_stalled,
        "stalled_message": stalled_message,
    }


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _generate_solution_content(payload: dict, settings) -> tuple[dict, str, str | None]:
    if not settings.openai_api_key or OpenAI is None:
        return _fallback_solution_content(payload), "fallback", "OPENAI_API_KEY가 없어 규칙 기반 솔루션을 표시합니다."

    client = OpenAI(api_key=settings.openai_api_key)
    prompt_data = {
        "topics": payload.get("topics", []),
        "target": payload.get("target", []),
        "instructors": [
            {
                "name": inst["name"],
                "rawValues": inst.get("rawValues", []),
                "totalGapScore": inst["totalGapScore"],
                "topGaps": inst["chartRows"][:3],
            }
            for inst in payload["instructors"]
        ],
    }

    try:
        response = client.chat.completions.create(
            model=settings.openai_insight_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 교육 커리큘럼 분석 전문가입니다. "
                        "강사별 커버리지 데이터와 목표 커리큘럼을 비교해 "
                        "실행 가능한 인사이트와 업계 동향 분석을 JSON으로 반환하세요. "
                        "모든 문구는 자연스러운 한국어로 작성하고, 과장 없이 데이터 기반으로만 분석하세요. "
                        "trendAnalysis는 topics의 섹션명을 보고 과목 도메인을 먼저 파악한 뒤, "
                        "그 도메인에 실제로 존재하는 교육기관·자격시험·교육 정책을 구체적으로 언급하세요. "
                        "특정 연도(예: 2024, 2025)를 언급하지 말고 '최근' 또는 '현재' 등의 표현을 사용하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "아래 커리큘럼 데이터를 분석해 JSON을 생성하세요.\n"
                        "반환 형식:\n"
                        "{\n"
                        '  "insights": [\n'
                        '    {"text": "인사이트 문장 (구체적 수치% 포함 필수)", '
                        '"numbers": [{"label": "레이블", "value": 숫자, "benchmark": 숫자, "topic": "섹션명"}]},\n'
                        "    ...5개 이상 반드시 포함\n"
                        "  ],\n"
                        '  "trendAnalysis": [\n'
                        '    {"title": "동향 제목", "detail": "상세 설명 (타 기관 비교 포함)", '
                        '"badge": "갭|일치|신규", "comparison": "타 기관 대비 요약"},\n'
                        "    ...3개 이상\n"
                        "  ]\n"
                        "}\n\n"
                        "요구사항:\n"
                        "- insights: 전체 강사 평균과 목표 커리큘럼 비교 인사이트 5개 이상. 각각 구체적 수치(%p, %) 포함\n"
                        "- trendAnalysis: topics 섹션명을 읽어 과목 도메인을 파악하고, "
                        "그 도메인에 맞는 최신 교육 트렌드 3개를 작성하세요. "
                        "예를 들어 한국사·역사 관련 과목이라면 한국사능력검정시험·EBS 한국사·교육부 역사교육 지침 등을 언급하고, "
                        "수학이라면 수능·경시대회·교육과정, 과학이라면 과학탐구·KSF 등을 언급하세요. "
                        "도메인에 실제로 존재하는 교육기관·자격시험·정책만 언급하고, "
                        "특정 연도 수치(2024, 2025 등)는 사용하지 말고 '최근' 표현을 쓰세요.\n"
                        "- badge는 반드시 갭/일치/신규 중 하나\n\n"
                        f"데이터:\n{json.dumps(prompt_data, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        return _normalize_new_content(raw, payload), "gpt", None
    except Exception as exc:  # noqa: BLE001
        return _fallback_solution_content(payload), "fallback", f"GPT 생성 실패: {exc}"


def _normalize_new_content(raw: dict, payload: dict) -> dict:
    fallback = _fallback_solution_content(payload)
    allowed_badges = {"갭", "일치", "신규"}

    insights = []
    for item in raw.get("insights", [])[:10]:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        numbers = [
            {
                "label": str(n.get("label", "")),
                "value": float(n.get("value", 0)),
                "benchmark": float(n.get("benchmark", 0)),
                "topic": str(n.get("topic", "")),
            }
            for n in item.get("numbers", [])
            if isinstance(n, dict)
        ]
        insights.append({"text": str(item["text"]), "numbers": numbers})

    if len(insights) < 5:
        insights = fallback["insights"]

    trend_analysis = []
    for item in raw.get("trendAnalysis", [])[:6]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        badge = item.get("badge", "갭")
        trend_analysis.append(
            {
                "title": str(item.get("title", "")),
                "detail": str(item.get("detail", "")),
                "badge": badge if badge in allowed_badges else "갭",
                "comparison": str(item.get("comparison", "")),
            }
        )

    if len(trend_analysis) < 2:
        trend_analysis = fallback["trendAnalysis"]

    return {"insights": insights, "trendAnalysis": trend_analysis}


def _fallback_solution_content(payload: dict) -> dict:
    topics = payload.get("topics", [])
    target_vals = payload.get("target", [])
    instructors = payload.get("instructors", [])

    avg_actual: list[float] = []
    for i in range(len(topics)):
        vals = []
        for inst in instructors:
            raw = inst.get("rawValues", [])
            all_rows = inst.get("allRows", [])
            if raw and i < len(raw):
                vals.append(float(raw[i]))
            elif all_rows and i < len(all_rows):
                vals.append(float(all_rows[i]["actualShare"]))
        avg_actual.append(round(sum(vals) / len(vals) if vals else 0.0, 1))

    topic_gaps = sorted(
        [
            (topics[i], avg_actual[i], target_vals[i], round(abs(avg_actual[i] - target_vals[i]), 1))
            for i in range(min(len(topics), len(target_vals), len(avg_actual)))
        ],
        key=lambda x: x[3],
        reverse=True,
    )

    insights: list[dict] = []
    for topic, actual, bench, gap in topic_gaps:
        if gap > 0:
            direction = "낮아" if actual < bench else "높아"
            action = "보강" if actual < bench else "축소 조정"
            insights.append(
                {
                    "text": (
                        f"{topic} 섹션의 전체 강사 평균 커버리지({actual}%)가 "
                        f"목표({bench}%)보다 {gap}%p {direction} {action}이 필요합니다."
                    ),
                    "numbers": [{"label": "평균 실제", "value": actual, "benchmark": bench, "topic": topic}],
                }
            )

    for inst in instructors:
        biggest = inst["chartRows"][0] if inst.get("chartRows") else None
        if biggest and biggest["gapScore"] >= 5:
            insights.append(
                {
                    "text": (
                        f"{inst['name']}의 {biggest['section']} 섹션({biggest['actualShare']}%)이 "
                        f"목표({biggest['benchmarkShare']}%)보다 {biggest['gapScore']}%p 차이 납니다."
                    ),
                    "numbers": [
                        {
                            "label": inst["name"],
                            "value": biggest["actualShare"],
                            "benchmark": biggest["benchmarkShare"],
                            "topic": biggest["section"],
                        }
                    ],
                }
            )

    if len(insights) < 5:
        total_avg_gap = round(sum(i["totalGapScore"] for i in instructors) / len(instructors), 1) if instructors else 0
        insights.append(
            {
                "text": f"전체 강사 평균 누적 갭 점수는 {total_avg_gap}%p로, 커리큘럼 목표 대비 전반적인 재조정이 필요합니다.",
                "numbers": [],
            }
        )

    top_topic = topic_gaps[0][0] if topic_gaps else "핵심 섹션"
    bottom_topic = topic_gaps[-1][0] if topic_gaps else "기초 섹션"
    return {
        "insights": insights[:8],
        "trendAnalysis": [
            {
                "title": "실습·사례 중심 학습 비중 확대 추세",
                "detail": (
                    "최근 국내외 주요 교육기관들은 이론 강의 비중을 줄이고 "
                    "실습·사례 분석 중심으로 커리큘럼을 재편하는 추세입니다. "
                    "현재 커리큘럼의 이론-실습 비율 검토가 필요합니다."
                ),
                "badge": "갭",
                "comparison": "타 기관 평균 대비 실습 비중 검토 필요",
            },
            {
                "title": f"{top_topic} 관련 교육 수요 증가",
                "detail": (
                    f"최근 교육 시장에서 {top_topic} 관련 강좌 수요가 지속적으로 증가하고 있습니다. "
                    "해당 섹션의 심화 내용 편성 및 비중 강화를 권장합니다."
                ),
                "badge": "일치",
                "comparison": "교육 시장 수요와 방향 일치 — 비중 강화 권장",
            },
            {
                "title": f"{bottom_topic} 기초 역량 강화 필요",
                "detail": (
                    f"학습자 기초 역량 격차를 줄이기 위해 {bottom_topic} 섹션의 "
                    "단계별 학습 콘텐츠 구성이 중요해지고 있습니다. "
                    "입문자와 심화 학습자를 위한 난이도 구분이 필요합니다."
                ),
                "badge": "신규",
                "comparison": "기초-심화 연계 콘텐츠 구성 강화 권장",
            },
        ],
    }


def _fallback_risk_zones(text: str) -> list[dict]:
    low_kw = ["어렵", "이해 안", "모르겠", "힘들", "어려웠", "너무 빠름", "이해못"]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    neg = sum(1 for line in lines if any(kw in line for kw in low_kw))
    total = len(lines) or 1

    zones: list[dict] = []
    if neg / total > 0.3:
        zones.append(
            {
                "title": "전반적 이해도 저하 신호",
                "detail": f"전체 피드백 중 약 {round(neg / total * 100)}%에서 이해 어려움이 언급됩니다.",
                "level": "위험",
                "score": 30,
            }
        )
    zones.append(
        {
            "title": "규칙 기반 분석 (API 키 없음)",
            "detail": "OpenAI API 키 설정 시 GPT 기반 정밀 분석이 제공됩니다.",
            "level": "주의",
            "score": 50,
        }
    )
    return zones


def _build_solution_payload(result: dict | None) -> dict:
    if not result:
        return _demo_solution_payload()

    inst_colors = ["#6366f1", "#ef4444", "#10b981", "#f59e0b"]
    sections = _read(result, "sections") or []
    instructors = _read(result, "instructors") or []
    average_share_by_section: dict[str, float] = {}

    for section in sections:
        section_id = _read(section, "id")
        average_share_by_section[section_id] = round(float(_read(section, "target_weight") or 0.0), 1)

    topics = [_read(s, "title") for s in sections]
    target = [round(float(_read(s, "target_weight") or average_share_by_section.get(_read(s, "id"), 0.0)), 1) for s in sections]

    instructor_payloads = []
    for idx, instructor in enumerate(instructors):
        all_rows = []
        coverages = _read(instructor, "section_coverages") or []
        for coverage in coverages:
            section_id = _read(coverage, "section_id")
            actual_share = round(float(_read(coverage, "token_share") or 0.0) * 100, 1)
            benchmark_share = round(average_share_by_section.get(section_id, 0.0), 1)
            gap_score = round(abs(actual_share - benchmark_share), 1)
            all_rows.append(
                {
                    "section": _read(coverage, "section_title"),
                    "actualShare": actual_share,
                    "benchmarkShare": benchmark_share,
                    "gapScore": gap_score,
                    "direction": "강화" if actual_share < benchmark_share else "정리",
                }
            )

        sorted_rows = sorted(all_rows, key=lambda item: item["gapScore"], reverse=True)
        top_rows = [r for r in sorted_rows if r["gapScore"] > 0][:4] or sorted_rows[:1]
        total_gap = min(round(sum(item["gapScore"] for item in top_rows), 1), 100.0)
        raw_values = [r["actualShare"] for r in all_rows]

        instructor_payloads.append(
            {
                "name": _read(instructor, "name"),
                "color": inst_colors[idx % len(inst_colors)],
                "assetCount": int(_read(instructor, "asset_count") or 0),
                "warningCount": len(_read(instructor, "warnings") or []),
                "unmappedShare": round(float(_read(instructor, "unmapped_share") or 0.0) * 100, 1),
                "unmappedTopics": [],
                "totalGapScore": total_gap,
                "chartRows": top_rows,
                "allRows": all_rows,
                "rawValues": raw_values,
            }
        )

    return {
        "title": "강사별 솔루션 분석",
        "source": "analysis-result",
        "topics": topics,
        "target": target,
        "sections": [{"id": _read(section, "id"), "title": _read(section, "title")} for section in sections],
        "instructors": instructor_payloads,
        "voc_summary": {
            **(_read(result, "voc_summary") or {}),
            "question_score_groups": _group_question_scores(
                _read(_read(result, "voc_summary") or {}, "question_scores") or []
            ),
        },
    }


def _demo_solution_payload() -> dict:
    topics = ["SQL", "데이터 분석", "머신러닝", "딥러닝", "전처리"]
    target = [15.0, 25.0, 25.0, 20.0, 15.0]
    inst_colors = ["#6366f1", "#ef4444", "#10b981"]

    raw_data = [
        {"name": "오정훈 강사", "values": [15.0, 30.0, 25.0, 20.0, 10.0], "unmapped": 12.4,
         "unmappedTopics": ["ChatGPT 활용", "데이터 시각화 도구"]},
        {"name": "김데이터 강사", "values": [20.0, 25.0, 30.0, 10.0, 15.0], "unmapped": 7.1,
         "unmappedTopics": ["클라우드 배포"]},
        {"name": "이파이썬 강사", "values": [10.0, 20.0, 30.0, 25.0, 15.0], "unmapped": 18.3,
         "unmappedTopics": ["LLM 파인튜닝", "벡터 DB", "MLOps 기초"]},
    ]

    instructors = []
    for idx, raw in enumerate(raw_data):
        all_rows = []
        for i, topic in enumerate(topics):
            actual = raw["values"][i]
            bench = target[i]
            gap = round(abs(actual - bench), 1)
            all_rows.append({
                "section": topic,
                "actualShare": actual,
                "benchmarkShare": bench,
                "gapScore": gap,
                "direction": "강화" if actual < bench else "정리",
            })

        sorted_rows = sorted(all_rows, key=lambda r: r["gapScore"], reverse=True)
        top_rows = [r for r in sorted_rows if r["gapScore"] > 0][:4] or sorted_rows[:1]
        total_gap = min(round(sum(r["gapScore"] for r in top_rows), 1), 100.0)

        instructors.append({
            "name": raw["name"],
            "color": inst_colors[idx % len(inst_colors)],
            "assetCount": 4,
            "warningCount": 0,
            "unmappedShare": raw.get("unmapped", 0.0),
            "unmappedTopics": raw.get("unmappedTopics", []),
            "totalGapScore": total_gap,
            "chartRows": top_rows,
            "allRows": all_rows,
            "rawValues": raw["values"],
        })

    return {
        "title": "강사별 솔루션 분석",
        "source": "demo-fallback",
        "topics": topics,
        "target": target,
        "sections": [{"id": t.replace(" ", "-"), "title": t} for t in topics],
        "instructors": instructors,
        "voc_summary": {
            "question_scores": [],
            "question_score_groups": [],
            "positive": ["실습 중심", "친절한 설명"],
            "negative": ["강의 속도", "자료 부족"],
            "repeated_complaints": [
                {"pattern": "강의 속도 조절 필요", "count": 2, "week": "3~4주차"},
            ],
            "next_suggestions": [
                {"priority": "high", "label": "강의 속도 조절", "body": "핵심 개념 뒤 체크포인트와 질의 시간을 추가해 보세요."},
            ],
        },
    }


def _build_review_payload(result: dict | None) -> dict:
    if result:
        instructors = _read(result, "instructors") or []
        return {
            "common_summary": {
                **(_read(result, "voc_summary") or {"positive": [], "negative": []}),
                "question_score_groups": _group_question_scores(
                    _read(_read(result, "voc_summary") or {}, "question_scores") or []
                ),
            },
            "instructors": [
                {
                    "name": _read(inst, "name"),
                    "file_name": _read(_read(inst, "voc_analysis") or {}, "file_name"),
                    "analyzed_at": _read(_read(inst, "voc_analysis") or {}, "analyzed_at"),
                    "response_count": _read(_read(inst, "voc_analysis") or {}, "response_count"),
                    "question_scores": list(
                        _read(_read(inst, "voc_analysis") or {}, "question_scores") or []
                    ),
                    "question_score_groups": _group_question_scores(
                        _read(_read(inst, "voc_analysis") or {}, "question_scores") or []
                    ),
                    "sentiment": _read(_read(inst, "voc_analysis") or {}, "sentiment")
                    or {"positive": [], "negative": []},
                    "repeated_complaints": list(
                        _read(_read(inst, "voc_analysis") or {}, "repeated_complaints") or []
                    ),
                    "next_suggestions": list(
                        _read(_read(inst, "voc_analysis") or {}, "next_suggestions") or []
                    ),
                }
                for inst in instructors
            ]
        }

    return {
        "common_summary": {
            "question_scores": [],
            "question_score_groups": [],
            "positive": ["실습 중심 강의 구성", "친절하고 명확한 설명"],
            "negative": ["강의 속도 및 실습 시간 부족", "실습 환경·자료 지원 미흡"],
        },
        "instructors": [
            {
                "name": "오정훈 강사",
                "file_name": "evaluation_ojh_2026q1.pdf",
                "analyzed_at": "2026-04-10",
                "response_count": 28,
                "question_scores": [],
                "question_score_groups": [],
                "sentiment": {
                    "positive": ["실습 위주", "친절한 설명", "예시 풍부", "이해하기 쉬움"],
                    "negative": ["속도 빠름", "과제 부담", "PDF 자료 부족"],
                },
                "repeated_complaints": [
                    {"pattern": "강의 속도가 너무 빠르다는 의견", "count": 9, "week": "3~4주차"},
                    {"pattern": "실습 시간이 충분하지 않다는 피드백", "count": 6, "week": "5주차"},
                ],
                "next_suggestions": [
                    {"priority": "high",   "label": "강의 속도 조절",    "body": "3~4주차 ML 파트에서 개념 설명 후 Q&A 시간을 추가로 확보하면 좋을 것 같아요."},
                    {"priority": "medium", "label": "실습 자료 보강",    "body": "PDF 외 코드 파일을 강의 자료와 함께 제공하면 복습에 도움이 될 것 같아요."},
                    {"priority": "low",    "label": "과제 난이도 단계화", "body": "기초·심화 과제를 분리해 수강생 수준별로 선택할 수 있도록 제안해요."},
                ],
            },
            {
                "name": "김데이터 강사",
                "file_name": "evaluation_kdm_2026q1.pdf",
                "analyzed_at": "2026-04-09",
                "response_count": 21,
                "sentiment": {
                    "positive": ["체계적인 구성", "실무 연결", "명확한 설명"],
                    "negative": ["실습 환경 불안정", "질문 시간 부족"],
                },
                "repeated_complaints": [
                    {"pattern": "실습 환경(Colab) 오류로 수업이 자주 끊겼다는 피드백", "count": 7, "week": "2주차"},
                ],
                "next_suggestions": [
                    {"priority": "high",   "label": "실습 환경 사전 점검", "body": "강의 전 Colab 환경 및 패키지 버전을 사전에 공유해두면 오류를 줄일 수 있을 것 같아요."},
                    {"priority": "medium", "label": "질문 채널 운영",      "body": "강의 중 실시간 질문 채널(슬랙 등)을 병행하면 질문 기회가 늘어날 것 같아요."},
                ],
            },
        ]
    }


def _group_question_scores(question_scores: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in question_scores:
        group = str(_read(item, "group") or "기타").strip() or "기타"
        grouped.setdefault(group, []).append(
            {
                "question_id": str(_read(item, "question_id") or "").strip(),
                "label": str(_read(item, "label") or "").strip(),
                "average": float(_read(item, "average") or 0.0),
                "response_count": int(_read(item, "response_count") or 0),
                "scale_max": int(_read(item, "scale_max") or 5),
            }
        )
    return [{"group": group, "entries": items} for group, items in grouped.items()]

if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8080)
