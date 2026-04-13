from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.models import (
    AnalysisJobPayload,
    AnalysisJobRecord,
    CourseRecord,
    CurriculumSection,
    JobInstructorInput,
    StoredUploadRef,
)


def _extract_script_payload(html: str, script_id: str) -> dict:
    match = re.search(rf'<script id="{script_id}"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise AssertionError(f"{script_id} script payload not found")
    return json.loads(match.group(1))


def _build_xlsx_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    default_sheet = workbook.active
    for index, (title, rows) in enumerate(sheets.items()):
        worksheet = default_sheet if index == 0 else workbook.create_sheet(title=title)
        worksheet.title = title
        for row in rows:
            worksheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


class Page1RestoreTests(unittest.TestCase):
    def test_index_restore_payload_keeps_explicit_lane_mode_and_separate_voc_assets(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-restore",
                name="기계공학테스트",
                curriculum_pdf_key="courses/course-restore/curriculum/test.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="기초",
                        description="기계공학 기초",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["기계군"],
                raw_curriculum_text="기계공학 커리큘럼",
                created_at="2026-04-12T10:00:00+09:00",
                updated_at="2026-04-12T10:00:00+09:00",
            )
            payload = AnalysisJobPayload(
                job_id="job-restore",
                course_id=course.id,
                course_name=course.name,
                course_sections=course.sections,
                curriculum_text="기계공학 커리큘럼",
                submitted_at="2026-04-12T10:30:00+09:00",
                analysis_mode="openai",
                page1_submission_version=2,
                instructors=[
                    JobInstructorInput(
                        name="기계군",
                        mode="youtube",
                        files=[],
                        youtube_inputs=["https://www.youtube.com/watch?v=abc123&list=playlist123"],
                        youtube_urls=["https://www.youtube.com/watch?v=abc123"],
                        voc_files=[
                            StoredUploadRef(
                                storage_key="jobs/job-restore/uploads/instructor-1/voc/review.pdf",
                                original_name="review.pdf",
                            )
                        ],
                    )
                ],
            )
            job = AnalysisJobRecord(
                id="job-restore",
                course_id=course.id,
                course_name=course.name,
                status="completed",
                created_at="2026-04-12T01:30:00+00:00",
                updated_at="2026-04-12T01:31:00+00:00",
                created_at_ts=1775957400.0,
                updated_at_ts=1775957460.0,
                payload_key="jobs/job-restore/payload.json",
                result_key="jobs/job-restore/result.json",
                instructor_names=["기계군"],
                instructor_count=1,
                asset_count=1,
                youtube_url_count=1,
                section_count=1,
                warning_count=0,
                selected_analysis_mode="openai",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            job_path = runtime_root / "jobs" / f"{job.id}.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            payload_path = runtime_root / "object_store" / job.payload_key
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            voc_path = runtime_root / "object_store" / "jobs" / "job-restore" / "uploads" / "instructor-1" / "voc" / "review.pdf"
            voc_path.parent.mkdir(parents=True, exist_ok=True)
            with voc_path.open("wb") as handle:
                handle.write(b"%PDF-1.4\n%%EOF\n")

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.get("/")
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="page1-loading-overlay"', response.text)
        self.assertIn("분석 범위를 확인하는 중입니다", response.text)
        self.assertIn('data-action="toggle-mode-menu"', response.text)
        self.assertIn('data-action="switch-mode"', response.text)
        self.assertIn('data-action="open-file-picker"', response.text)
        self.assertIn('data-role="asset-rail"', response.text)
        self.assertIn('data-course-delete="course-restore"', response.text)
        self.assertNotIn("선택 가능", response.text)
        self.assertRegex(response.text, r'/static/styles\.css\?v=\d+')
        self.assertRegex(response.text, r'/static/app\.js\?v=\d+')
        drafts = _extract_script_payload(response.text, "page1-course-drafts-data")
        block = drafts["course-restore"]["blocks"][0]

        self.assertEqual(block["mode"], "youtube")
        self.assertEqual(block["youtube_urls"], ["https://www.youtube.com/watch?v=abc123&list=playlist123"])
        self.assertEqual(block["files"], [])
        self.assertEqual(len(block["voc_files"]), 1)
        self.assertEqual(block["voc_files"][0]["original_name"], "review.pdf")
        self.assertTrue(block["voc_files"][0]["download_url"].endswith("/jobs/job-restore/voc-assets/1/1"))

    def test_index_restore_payload_keeps_files_and_voc_assets_separate_in_same_lane(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-mixed-restore",
                name="윤강의",
                curriculum_pdf_key="courses/course-mixed-restore/curriculum/test.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개론",
                        description="강의 개론",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["윤강사"],
                raw_curriculum_text="윤강의 커리큘럼",
                created_at="2026-04-12T18:00:00+09:00",
                updated_at="2026-04-12T18:00:00+09:00",
            )
            payload = AnalysisJobPayload(
                job_id="job-mixed-restore",
                course_id=course.id,
                course_name=course.name,
                course_sections=course.sections,
                curriculum_text="윤강의 커리큘럼",
                submitted_at="2026-04-12T18:10:00+09:00",
                analysis_mode="openai",
                page1_submission_version=2,
                instructors=[
                    JobInstructorInput(
                        name="윤강사",
                        mode="voc",
                        files=[
                            StoredUploadRef(
                                storage_key="jobs/job-mixed-restore/uploads/instructor-1/files/study-material.pdf",
                                original_name="study-material.pdf",
                            )
                        ],
                        youtube_inputs=["https://www.youtube.com/watch?v=abc123"],
                        youtube_urls=["https://www.youtube.com/watch?v=abc123"],
                        voc_files=[
                            StoredUploadRef(
                                storage_key="jobs/job-mixed-restore/uploads/instructor-1/voc/review.pdf",
                                original_name="review.pdf",
                            )
                        ],
                    )
                ],
            )
            job = AnalysisJobRecord(
                id="job-mixed-restore",
                course_id=course.id,
                course_name=course.name,
                status="completed",
                created_at="2026-04-12T09:10:00+00:00",
                updated_at="2026-04-12T09:11:00+00:00",
                created_at_ts=1775985000.0,
                updated_at_ts=1775985060.0,
                payload_key="jobs/job-mixed-restore/payload.json",
                result_key="jobs/job-mixed-restore/result.json",
                instructor_names=["윤강사"],
                instructor_count=1,
                asset_count=2,
                youtube_url_count=1,
                section_count=1,
                warning_count=0,
                selected_analysis_mode="openai",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            job_path = runtime_root / "jobs" / f"{job.id}.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            payload_path = runtime_root / "object_store" / job.payload_key
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            file_path = runtime_root / "object_store" / "jobs" / "job-mixed-restore" / "uploads" / "instructor-1" / "files" / "study-material.pdf"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

            voc_path = runtime_root / "object_store" / "jobs" / "job-mixed-restore" / "uploads" / "instructor-1" / "voc" / "review.pdf"
            voc_path.parent.mkdir(parents=True, exist_ok=True)
            voc_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.get("/")
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        drafts = _extract_script_payload(response.text, "page1-course-drafts-data")
        block = drafts["course-mixed-restore"]["blocks"][0]

        self.assertEqual(block["mode"], "voc")
        self.assertEqual(block["youtube_urls"], ["https://www.youtube.com/watch?v=abc123"])
        self.assertEqual(len(block["files"]), 1)
        self.assertEqual(block["files"][0]["original_name"], "study-material.pdf")
        self.assertTrue(block["files"][0]["download_url"].endswith("/jobs/job-mixed-restore/assets/1/1"))
        self.assertEqual(len(block["voc_files"]), 1)
        self.assertEqual(block["voc_files"][0]["original_name"], "review.pdf")
        self.assertTrue(block["voc_files"][0]["download_url"].endswith("/jobs/job-mixed-restore/voc-assets/1/1"))

    def test_index_restore_payload_flags_legacy_draft_for_reset(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-legacy-reset",
                name="레거시 과정",
                curriculum_pdf_key="courses/course-legacy-reset/curriculum/test.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개론",
                        description="레거시 개론",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["레거시강사"],
                raw_curriculum_text="레거시 커리큘럼",
                created_at="2026-04-12T18:00:00+09:00",
                updated_at="2026-04-12T18:00:00+09:00",
            )
            payload = AnalysisJobPayload(
                job_id="job-legacy-reset",
                course_id=course.id,
                course_name=course.name,
                course_sections=course.sections,
                curriculum_text="레거시 커리큘럼",
                submitted_at="2026-04-12T18:10:00+09:00",
                analysis_mode="openai",
                instructors=[
                    JobInstructorInput(
                        name="레거시강사",
                        mode="voc",
                        files=[],
                        youtube_inputs=["https://www.youtube.com/watch?v=abc123"],
                        youtube_urls=["https://www.youtube.com/watch?v=abc123"],
                        voc_files=[
                            StoredUploadRef(
                                storage_key="jobs/job-legacy-reset/uploads/instructor-1/voc/study-material.pdf",
                                original_name="study-material.pdf",
                            )
                        ],
                    )
                ],
            )
            job = AnalysisJobRecord(
                id="job-legacy-reset",
                course_id=course.id,
                course_name=course.name,
                status="completed",
                created_at="2026-04-12T09:10:00+00:00",
                updated_at="2026-04-12T09:11:00+00:00",
                created_at_ts=1775985000.0,
                updated_at_ts=1775985060.0,
                payload_key="jobs/job-legacy-reset/payload.json",
                result_key="jobs/job-legacy-reset/result.json",
                instructor_names=["레거시강사"],
                instructor_count=1,
                asset_count=1,
                youtube_url_count=1,
                section_count=1,
                warning_count=0,
                selected_analysis_mode="openai",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            job_path = runtime_root / "jobs" / f"{job.id}.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            payload_path = runtime_root / "object_store" / job.payload_key
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.get("/")
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="page1-restore-notice"', response.text)
        drafts = _extract_script_payload(response.text, "page1-course-drafts-data")
        draft = drafts["course-legacy-reset"]
        self.assertEqual(draft["page1_submission_version"], 1)
        self.assertTrue(draft["requires_reset"])
        self.assertEqual(draft["blocks"], [])
        self.assertIn("구버전", draft["reset_message"])

    def test_prepare_submission_keeps_files_and_voc_buckets_separate(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-submit-check",
                name="제출체크",
                curriculum_pdf_key="courses/course-submit-check/curriculum/test.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개요",
                        description="제출 경로 확인",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["윤머신"],
                raw_curriculum_text="제출체크 커리큘럼",
                created_at="2026-04-12T18:00:00+09:00",
                updated_at="2026-04-12T18:00:00+09:00",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.post(
                    "/analyze/prepare",
                    data={
                        "course_id": course.id,
                        "course_name": course.name,
                        "instructor_manifest": json.dumps([{"id": "primary", "mode": "voc"}]),
                        "instructor_name__primary": "윤머신",
                        "page1_submission_version": "2",
                    },
                    files=[
                        ("instructor_files__primary", ("study.pdf", b"%PDF-1.4 study", "application/pdf")),
                        ("instructor_voc__primary", ("review.pdf", b"%PDF-1.4 review", "application/pdf")),
                    ],
                )
                self.assertEqual(response.status_code, 200)
                request_id = response.json()["request_id"]
                preparation_path = runtime_root / "object_store" / "analysis-preparations" / f"{request_id}.json"
                preparation_payload = json.loads(preparation_path.read_text(encoding="utf-8"))
                get_settings.cache_clear()

            payload = preparation_payload["payload"]

        self.assertEqual(payload["page1_submission_version"], 2)
        self.assertEqual(len(payload["instructors"]), 1)
        instructor = payload["instructors"][0]
        self.assertEqual(instructor["mode"], "voc")
        self.assertEqual([item["original_name"] for item in instructor["files"]], ["study.pdf"])
        self.assertEqual([item["original_name"] for item in instructor["voc_files"]], ["review.pdf"])
        self.assertEqual(instructor["youtube_inputs"], [])

    def test_prepare_submission_accepts_xlsx_voc_upload(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-voc-xlsx",
                name="VOC엑셀",
                curriculum_pdf_key="courses/course-voc-xlsx/curriculum/test.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개요",
                        description="VOC 엑셀 테스트",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["윤머신"],
                raw_curriculum_text="VOC엑셀 커리큘럼",
                created_at="2026-04-12T19:00:00+09:00",
                updated_at="2026-04-12T19:00:00+09:00",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            workbook_bytes = _build_xlsx_bytes(
                {
                    "rawdata": [
                        ["Section A. 참여자 정보", "", "Section B. 교육 전반 만족도", "", "", "Section C. 강사 만족도", "", "Section D. 서술형"],
                        ["AQ1. 응답자 기본 정보", "", "BQ1. 교육 전반 만족도", "", "", "BQ2. 강사 만족도", "", "DQ1. 기타 의견"],
                        [
                            "AQ1-1. 소속",
                            "AQ1-2. 직무",
                            "BQ1-1. 교육 신청 및 안내 절차가 수월하였다.",
                            "BQ1-2. 교육 목표가 명확하였다.",
                            "BQ1-3. 교육 운영이 전반적으로 만족스러웠다.",
                            "BQ2-1. 강사의 설명이 이해하기 쉬웠다.",
                            "BQ2-2. 질의응답이 도움이 되었다.",
                            "기타 의견",
                        ],
                        ["제조", "신규", 5, 4, 5, 5, 4, "설명은 친절했고 예시는 좋았어요"],
                        ["서비스", "재직", 2, 3, 3, 4, 3, "실습 환경 오류가 자주 났어요"],
                    ]
                }
            )

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.post(
                    "/analyze/prepare",
                    data={
                        "course_id": course.id,
                        "course_name": course.name,
                        "instructor_manifest": json.dumps([{"id": "primary", "mode": "voc"}]),
                        "instructor_name__primary": "윤머신",
                        "page1_submission_version": "2",
                    },
                    files=[
                        (
                            "instructor_voc__primary",
                            (
                                "review.xlsx",
                                workbook_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            ),
                        ),
                    ],
                )
                self.assertEqual(response.status_code, 200)
                request_id = response.json()["request_id"]
                preparation_path = runtime_root / "object_store" / "analysis-preparations" / f"{request_id}.json"
                preparation_payload = json.loads(preparation_path.read_text(encoding="utf-8"))
                get_settings.cache_clear()

        instructor = preparation_payload["payload"]["instructors"][0]
        self.assertEqual([item["original_name"] for item in instructor["voc_files"]], ["review.xlsx"])

    def test_prepare_submission_rejects_ambiguous_xlsx_voc_upload(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-voc-xlsx-ambiguous",
                name="VOC엑셀모호",
                curriculum_pdf_key="courses/course-voc-xlsx-ambiguous/curriculum/test.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개요",
                        description="VOC 엑셀 모호성 테스트",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["윤머신"],
                raw_curriculum_text="VOC엑셀모호 커리큘럼",
                created_at="2026-04-12T19:10:00+09:00",
                updated_at="2026-04-12T19:10:00+09:00",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            workbook_bytes = _build_xlsx_bytes(
                {
                    "응답A": [
                        ["week", "comment"],
                        ["1주차", "설명은 친절했어요"],
                        ["2주차", "실습 환경이 불안정했어요"],
                    ],
                    "응답B": [
                        ["week", "comment"],
                        ["1주차", "자료가 부족했어요"],
                        ["2주차", "질문 시간이 더 필요해요"],
                    ],
                }
            )

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.post(
                    "/analyze/prepare",
                    data={
                        "course_id": course.id,
                        "course_name": course.name,
                        "instructor_manifest": json.dumps([{"id": "primary", "mode": "voc"}]),
                        "instructor_name__primary": "윤머신",
                        "page1_submission_version": "2",
                    },
                    files=[
                        (
                            "instructor_voc__primary",
                            (
                                "review.xlsx",
                                workbook_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            ),
                        ),
                    ],
                )
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 400)
        self.assertIn("응답이 담긴 단일 시트만 남기거나 CSV로 저장해 다시 업로드", response.json()["detail"])

    def test_delete_course_removes_course_jobs_and_preparations(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-delete",
                name="삭제대상과정",
                curriculum_pdf_key="courses/course-delete/curriculum/source.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개요",
                        description="삭제 테스트",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["삭제강사"],
                raw_curriculum_text="삭제 테스트 커리큘럼",
                created_at="2026-04-12T20:00:00+09:00",
                updated_at="2026-04-12T20:00:00+09:00",
            )
            job = AnalysisJobRecord(
                id="job-delete",
                course_id=course.id,
                course_name=course.name,
                status="completed",
                created_at="2026-04-12T11:00:00+00:00",
                updated_at="2026-04-12T11:01:00+00:00",
                created_at_ts=1775991600.0,
                updated_at_ts=1775991660.0,
                payload_key="jobs/job-delete/payload.json",
                result_key="jobs/job-delete/result.json",
                instructor_names=["삭제강사"],
                instructor_count=1,
                asset_count=1,
                youtube_url_count=0,
                section_count=1,
                warning_count=0,
                selected_analysis_mode="openai",
            )
            payload = AnalysisJobPayload(
                job_id=job.id,
                course_id=course.id,
                course_name=course.name,
                course_sections=course.sections,
                curriculum_text="삭제 테스트 커리큘럼",
                submitted_at="2026-04-12T20:01:00+09:00",
                analysis_mode="openai",
                page1_submission_version=2,
                instructors=[
                    JobInstructorInput(
                        name="삭제강사",
                        files=[StoredUploadRef(storage_key="jobs/job-delete/uploads/instructor-1/material.pdf", original_name="material.pdf")],
                    )
                ],
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            curriculum_path = runtime_root / "object_store" / course.curriculum_pdf_key
            curriculum_path.parent.mkdir(parents=True, exist_ok=True)
            curriculum_path.write_bytes(b"%PDF-1.4 curriculum\n%%EOF\n")

            job_path = runtime_root / "jobs" / f"{job.id}.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            payload_path = runtime_root / "object_store" / job.payload_key
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            result_path = runtime_root / "object_store" / "jobs" / job.id / "result.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps({"status": "ok"}, ensure_ascii=False), encoding="utf-8")

            upload_path = runtime_root / "object_store" / "jobs" / job.id / "uploads" / "instructor-1" / "material.pdf"
            upload_path.parent.mkdir(parents=True, exist_ok=True)
            upload_path.write_bytes(b"%PDF-1.4 upload\n%%EOF\n")

            preparation_path = runtime_root / "object_store" / "analysis-preparations" / "prep-delete.json"
            preparation_path.parent.mkdir(parents=True, exist_ok=True)
            preparation_path.write_text(
                json.dumps(
                    {
                        "request_id": "prep-delete",
                        "payload": payload.to_dict(),
                        "created_at": "2026-04-12T20:02:00+09:00",
                        "requires_confirmation": True,
                        "recommended_analysis_mode": "openai",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.delete(f"/courses/{course.id}")
                job_response = client.get(f"/jobs/{job.id}")
                course_response = client.get(f"/courses/{course.id}")
                course_exists_after = course_path.exists()
                curriculum_exists_after = curriculum_path.exists()
                job_exists_after = job_path.exists()
                job_prefix_exists_after = (runtime_root / "object_store" / "jobs" / job.id).exists()
                preparation_exists_after = preparation_path.exists()
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "course_id": course.id,
                "deleted_job_count": 1,
                "deleted_preparation_count": 1,
            },
        )
        self.assertEqual(job_response.status_code, 404)
        self.assertEqual(course_response.status_code, 404)
        self.assertFalse(course_exists_after)
        self.assertFalse(curriculum_exists_after)
        self.assertFalse(job_exists_after)
        self.assertFalse(job_prefix_exists_after)
        self.assertFalse(preparation_exists_after)

    def test_delete_course_rejects_active_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-delete-busy",
                name="삭제불가과정",
                curriculum_pdf_key="courses/course-delete-busy/curriculum/source.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개요",
                        description="삭제 차단 테스트",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["삭제강사"],
                raw_curriculum_text="삭제 차단 커리큘럼",
                created_at="2026-04-12T20:10:00+09:00",
                updated_at="2026-04-12T20:10:00+09:00",
            )
            job = AnalysisJobRecord(
                id="job-delete-busy",
                course_id=course.id,
                course_name=course.name,
                status="running",
                created_at="2026-04-12T11:10:00+00:00",
                updated_at="2026-04-12T11:11:00+00:00",
                created_at_ts=1775992200.0,
                updated_at_ts=1775992260.0,
                payload_key="jobs/job-delete-busy/payload.json",
                instructor_names=["삭제강사"],
                instructor_count=1,
                asset_count=1,
                youtube_url_count=0,
                section_count=1,
                warning_count=0,
                selected_analysis_mode="openai",
            )

            course_path = runtime_root / "courses" / f"{course.id}.json"
            course_path.parent.mkdir(parents=True, exist_ok=True)
            course_path.write_text(json.dumps(course.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            curriculum_path = runtime_root / "object_store" / course.curriculum_pdf_key
            curriculum_path.parent.mkdir(parents=True, exist_ok=True)
            curriculum_path.write_bytes(b"%PDF-1.4 curriculum\n%%EOF\n")

            job_path = runtime_root / "jobs" / f"{job.id}.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            job_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.delete(f"/courses/{course.id}")
                course_exists_after = course_path.exists()
                curriculum_exists_after = curriculum_path.exists()
                job_exists_after = job_path.exists()
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 409)
        self.assertIn("진행 중", response.json()["detail"])
        self.assertTrue(course_exists_after)
        self.assertTrue(curriculum_exists_after)
        self.assertTrue(job_exists_after)

    def test_prepare_confirm_rejects_deleted_course(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            course = CourseRecord(
                id="course-missing-confirm",
                name="삭제된과정",
                curriculum_pdf_key="courses/course-missing-confirm/curriculum/source.pdf",
                sections=[
                    CurriculumSection(
                        id="section-1",
                        title="개요",
                        description="confirm 차단",
                        target_weight=100.0,
                    )
                ],
                instructor_names=["삭제강사"],
                raw_curriculum_text="confirm 차단",
                created_at="2026-04-12T20:20:00+09:00",
                updated_at="2026-04-12T20:20:00+09:00",
            )
            payload = AnalysisJobPayload(
                job_id="job-missing-confirm",
                course_id=course.id,
                course_name=course.name,
                course_sections=course.sections,
                curriculum_text="confirm 차단",
                submitted_at="2026-04-12T20:21:00+09:00",
                analysis_mode="openai",
                page1_submission_version=2,
                instructors=[JobInstructorInput(name="삭제강사")],
            )
            preparation_path = runtime_root / "object_store" / "analysis-preparations" / "prep-missing-course.json"
            preparation_path.parent.mkdir(parents=True, exist_ok=True)
            preparation_path.write_text(
                json.dumps(
                    {
                        "request_id": "prep-missing-course",
                        "payload": payload.to_dict(),
                        "created_at": "2026-04-12T20:22:00+09:00",
                        "requires_confirmation": True,
                        "recommended_analysis_mode": "openai",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
                clear=False,
            ):
                get_settings.cache_clear()
                client = TestClient(create_app())
                response = client.post("/analyze/prepare/prep-missing-course/confirm")
                preparation_exists_after = preparation_path.exists()
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 404)
        self.assertIn("과정이 삭제되어", response.json()["detail"])
        self.assertFalse(preparation_exists_after)


if __name__ == "__main__":
    unittest.main()
