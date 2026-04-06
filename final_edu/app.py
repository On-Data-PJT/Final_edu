from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from final_edu.analysis import analyze_submissions
from final_edu.config import get_settings
from final_edu.models import InstructorSubmission, UploadedAsset

PACKAGE_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
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
            _base_context(request=request, settings=settings),
        )

    @app.get("/health", response_class=JSONResponse)
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "app": settings.app_name})

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
            with tempfile.TemporaryDirectory() as temp_dir:
                submissions = [
                    await _build_submission(
                        index=1,
                        temp_dir=Path(temp_dir),
                        name=instructor_1_name,
                        youtube_urls=instructor_1_youtube_urls,
                        uploads=instructor_1_files,
                        max_upload_bytes=settings.max_upload_bytes,
                    ),
                    await _build_submission(
                        index=2,
                        temp_dir=Path(temp_dir),
                        name=instructor_2_name,
                        youtube_urls=instructor_2_youtube_urls,
                        uploads=instructor_2_files,
                        max_upload_bytes=settings.max_upload_bytes,
                    ),
                    await _build_submission(
                        index=3,
                        temp_dir=Path(temp_dir),
                        name=instructor_3_name,
                        youtube_urls=instructor_3_youtube_urls,
                        uploads=instructor_3_files,
                        max_upload_bytes=settings.max_upload_bytes,
                    ),
                ]

                result = analyze_submissions(curriculum_text, submissions, settings)

            context = _base_context(
                request=request,
                settings=settings,
                form_values=form_values,
                result=result,
                comparison_rows=_comparison_rows(result),
            )
            return templates.TemplateResponse(request, "index.html", context)
        except ValueError as exc:
            context = _base_context(
                request=request,
                settings=settings,
                form_values=form_values,
                error=str(exc),
            )
            return templates.TemplateResponse(request, "index.html", context, status_code=400)

    return app


async def _build_submission(
    index: int,
    temp_dir: Path,
    name: str,
    youtube_urls: str,
    uploads: list[UploadFile] | None,
    max_upload_bytes: int,
) -> InstructorSubmission:
    normalized_name = name.strip() or f"강사 {index}"
    saved_uploads: list[UploadedAsset] = []

    for upload in uploads or []:
        if not upload.filename:
            continue
        payload = await upload.read()
        await upload.close()
        if len(payload) > max_upload_bytes:
            raise ValueError(
                f"{upload.filename}: 업로드 가능 크기를 초과했습니다. 현재 제한은 {max_upload_bytes // (1024 * 1024)}MB입니다."
            )
        destination = temp_dir / f"instructor-{index}-{upload.filename}"
        destination.write_bytes(payload)
        saved_uploads.append(UploadedAsset(path=destination, original_name=upload.filename))

    urls = [line.strip() for line in youtube_urls.splitlines() if line.strip()]
    return InstructorSubmission(name=normalized_name, files=saved_uploads, youtube_urls=urls)


def _base_context(
    request: Request,
    settings,
    form_values: dict | None = None,
    error: str | None = None,
    result=None,  # noqa: ANN001
    comparison_rows=None,  # noqa: ANN001
) -> dict:
    return {
        "request": request,
        "settings": settings,
        "error": error,
        "result": result,
        "comparison_rows": comparison_rows or [],
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
            "텍스트 청크 기반 분석",
            "대단원 수준 분류",
            "근거 스니펫 제공",
            "OpenAI 임베딩 optional",
        ],
    }


def _comparison_rows(result) -> list[dict]:  # noqa: ANN001
    rows = []
    for section in result.sections:
        items = []
        for instructor in result.instructors:
            coverage = next(
                coverage
                for coverage in instructor.section_coverages
                if coverage.section_id == section.id
            )
            items.append(
                {
                    "name": instructor.name,
                    "share": coverage.token_share,
                    "deviation": coverage.deviation_from_average,
                }
            )
        rows.append({"title": section.title, "entries": items})

    rows.append(
        {
            "title": "Other / Unmapped",
            "entries": [
                {
                    "name": instructor.name,
                    "share": instructor.unmapped_share,
                    "deviation": 0.0,
                }
                for instructor in result.instructors
            ],
        }
    )
    return rows
