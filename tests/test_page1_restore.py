from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()
