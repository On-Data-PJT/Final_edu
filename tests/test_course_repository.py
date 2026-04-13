from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.courses import ObjectStorageCourseRepository
from final_edu.models import CourseRecord, CurriculumSection
from final_edu.storage import LocalObjectStorage


def _course_record(
    course_id: str,
    *,
    updated_at: str,
    name: str | None = None,
) -> CourseRecord:
    return CourseRecord(
        id=course_id,
        name=name or course_id,
        curriculum_pdf_key=f"courses/{course_id}/curriculum/source.pdf",
        sections=[
            CurriculumSection(
                id="section-1",
                title="개요",
                description="테스트 섹션",
                target_weight=100.0,
            )
        ],
        instructor_names=["강사 A"],
        raw_curriculum_text="테스트 커리큘럼",
        created_at="2026-04-13T10:00:00+09:00",
        updated_at=updated_at,
    )


class ObjectStorageCourseRepositoryTests(unittest.TestCase):
    def test_object_storage_course_repository_round_trip_and_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            storage = LocalObjectStorage(Path(runtime_dir) / "object_store")
            repository = ObjectStorageCourseRepository(storage)
            older = _course_record("course-older", updated_at="2026-04-13T10:00:00+09:00")
            newer = _course_record("course-newer", updated_at="2026-04-13T11:00:00+09:00")

            repository.save(older)
            repository.save(newer)

            self.assertIsNone(repository.get("missing-course"))
            self.assertEqual(repository.get("course-newer").name, "course-newer")
            self.assertEqual(
                [record.id for record in repository.list_all()],
                ["course-newer", "course-older"],
            )

            deleted = repository.delete("course-older")
            self.assertIsNotNone(deleted)
            self.assertEqual(deleted.id, "course-older")
            self.assertIsNone(repository.get("course-older"))
            self.assertEqual([record.id for record in repository.list_all()], ["course-newer"])
            self.assertIsNone(repository.delete("course-older"))

    def test_r2_mode_courses_persist_across_app_instances(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            object_root = runtime_root / "persisted-object-store"

            def _local_object_storage(_settings):
                return LocalObjectStorage(object_root)

            with patch.dict(
                os.environ,
                {
                    "FINAL_EDU_RUNTIME_DIR": runtime_dir,
                    "R2_ENDPOINT_URL": "https://example.invalid",
                    "R2_ACCESS_KEY_ID": "test-access-key",
                    "R2_SECRET_ACCESS_KEY": "test-secret-key",
                    "R2_BUCKET": "test-bucket",
                    "R2_REGION": "auto",
                },
                clear=False,
            ), patch("final_edu.app.create_object_storage", side_effect=_local_object_storage):
                get_settings.cache_clear()
                client = TestClient(create_app())
                create_response = client.post(
                    "/courses",
                    data={
                        "course_name": "Render 과정 유지 테스트",
                        "sections_json": json.dumps(
                            [
                                {
                                    "title": "개요",
                                    "description": "R2-backed course repository",
                                    "target_weight": 100,
                                }
                            ],
                            ensure_ascii=False,
                        ),
                        "instructor_names_json": json.dumps(["윤강사"], ensure_ascii=False),
                        "raw_curriculum_text": "Render sync 이후에도 남아야 하는 과정",
                    },
                    files=[("curriculum_pdf", ("curriculum.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf"))],
                )
                self.assertEqual(create_response.status_code, 200)
                course_id = create_response.json()["course"]["id"]
                record_path = object_root / "course-records" / f"{course_id}.json"
                self.assertTrue(record_path.exists())

                first_list_response = client.get("/courses")
                self.assertEqual(first_list_response.status_code, 200)
                self.assertEqual([item["id"] for item in first_list_response.json()["courses"]], [course_id])

                second_client = TestClient(create_app())
                second_list_response = second_client.get("/courses")
                self.assertEqual(second_list_response.status_code, 200)
                self.assertEqual([item["id"] for item in second_list_response.json()["courses"]], [course_id])

                delete_response = second_client.delete(f"/courses/{course_id}")
                self.assertEqual(delete_response.status_code, 200)
                self.assertFalse(record_path.exists())
                self.assertEqual(second_client.get("/courses").json()["courses"], [])
                get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
