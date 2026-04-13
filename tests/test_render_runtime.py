from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.jobs import create_job_record
from final_edu.models import AnalysisJobPayload, AnalysisJobRecord, CurriculumSection, JobInstructorInput
from final_edu import worker as worker_module


def _iso_from_ts(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


class RenderRuntimeTests(unittest.TestCase):
    def test_web_app_startup_does_not_force_kiwi_ready(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
            clear=False,
        ), patch("final_edu.app.ensure_kiwi_ready", side_effect=AssertionError("web startup should not preload kiwi")):
            get_settings.cache_clear()
            with TestClient(create_app()) as client:
                response = client.get("/health")
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_worker_main_still_checks_kiwi_ready(self) -> None:
        fake_connection = object()
        fake_redis = MagicMock()
        fake_redis.from_url.return_value = fake_connection
        fake_worker_instance = MagicMock()
        fake_worker_class = MagicMock(return_value=fake_worker_instance)

        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {
                "FINAL_EDU_RUNTIME_DIR": runtime_dir,
                "REDIS_URL": "redis://localhost:6379/0",
            },
            clear=False,
        ), patch("final_edu.worker.ensure_kiwi_ready") as mock_ready, patch.dict(
            sys.modules,
            {
                "redis": SimpleNamespace(Redis=fake_redis),
                "rq": SimpleNamespace(Worker=fake_worker_class),
            },
            clear=False,
        ):
            get_settings.cache_clear()
            worker_module.main()
            get_settings.cache_clear()

        mock_ready.assert_called_once()
        fake_redis.from_url.assert_called_once_with("redis://localhost:6379/0")
        fake_worker_class.assert_called_once()
        fake_worker_instance.work.assert_called_once()

    def test_job_status_marks_stalled_queued_job(self) -> None:
        now_ts = datetime.now(UTC).timestamp()
        job = AnalysisJobRecord(
            id="job-stalled-queued",
            course_id="course-1",
            course_name="대기 테스트",
            status="queued",
            created_at=_iso_from_ts(now_ts - 120),
            updated_at=_iso_from_ts(now_ts - 120),
            created_at_ts=now_ts - 120,
            updated_at_ts=now_ts - 120,
            payload_key="jobs/job-stalled-queued/payload.json",
            instructor_names=["강사 1"],
            instructor_count=1,
            asset_count=1,
            youtube_url_count=0,
            section_count=1,
        )

        with tempfile.TemporaryDirectory() as runtime_dir:
            jobs_root = Path(runtime_dir) / "jobs"
            jobs_root.mkdir(parents=True, exist_ok=True)
            (jobs_root / f"{job.id}.json").write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"FINAL_EDU_RUNTIME_DIR": runtime_dir}, clear=False):
                get_settings.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.get(f"/jobs/{job.id}/status")
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_stalled"])
        self.assertGreaterEqual(payload["queue_wait_seconds"], 120)
        self.assertIn("Render worker 상태", payload["stalled_message"])

    def test_job_status_marks_stalled_running_job(self) -> None:
        now_ts = datetime.now(UTC).timestamp()
        job = AnalysisJobRecord(
            id="job-stalled-running",
            course_id="course-1",
            course_name="실행 테스트",
            status="running",
            created_at=_iso_from_ts(now_ts - 240),
            updated_at=_iso_from_ts(now_ts - 240),
            created_at_ts=now_ts - 240,
            updated_at_ts=now_ts - 240,
            payload_key="jobs/job-stalled-running/payload.json",
            instructor_names=["강사 1"],
            instructor_count=1,
            asset_count=1,
            youtube_url_count=1,
            section_count=1,
            phase="transcript_fetching",
            expanded_video_count=1,
            processed_video_count=0,
        )

        with tempfile.TemporaryDirectory() as runtime_dir:
            jobs_root = Path(runtime_dir) / "jobs"
            jobs_root.mkdir(parents=True, exist_ok=True)
            (jobs_root / f"{job.id}.json").write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"FINAL_EDU_RUNTIME_DIR": runtime_dir}, clear=False):
                get_settings.cache_clear()
                with TestClient(create_app()) as client:
                    response = client.get(f"/jobs/{job.id}/status")
                get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_stalled"])
        self.assertGreaterEqual(payload["last_update_seconds"], 180)
        self.assertIn("작업 진행 로그", payload["stalled_message"])

    def test_render_blueprint_uses_venv_start_commands(self) -> None:
        render_yaml = Path("render.yaml").read_text(encoding="utf-8")
        self.assertIn("startCommand: .venv/bin/python -m final_edu --host 0.0.0.0 --port $PORT", render_yaml)
        self.assertIn("startCommand: .venv/bin/python -m final_edu.worker", render_yaml)

    def test_queued_job_record_starts_without_placeholder_phase(self) -> None:
        payload = AnalysisJobPayload(
            job_id="job-phase-none",
            course_id="course-1",
            course_name="상태 점검 과정",
            course_sections=[CurriculumSection(id="section-1", title="대주제", description="설명", target_weight=100.0)],
            curriculum_text="대주제 | 설명",
            instructors=[JobInstructorInput(name="강사 1", youtube_urls=["https://www.youtube.com/watch?v=test"])],
            submitted_at=_iso_from_ts(datetime.now(UTC).timestamp()),
        )

        record = create_job_record(payload, "jobs/job-phase-none/payload.json", 1, SimpleNamespace())

        self.assertEqual(record.status, "queued")
        self.assertIsNone(record.phase)

    def test_page1_requests_use_render_timeout_messages(self) -> None:
        app_js = Path("final_edu/static/app.js").read_text(encoding="utf-8")
        self.assertIn("timeoutMs: 120000", app_js)
        self.assertIn("timeoutMs: 30000", app_js)
        self.assertIn("Render 인스턴스가 재시작되었습니다", app_js)
        self.assertIn("waitForPreparedJobTerminalState", app_js)
        self.assertIn("buildPage1JobStatusUrl", app_js)
        self.assertIn("worker가 작업을 시작할 때까지 잠시 기다려 주세요.", app_js)
        self.assertIn("window.location.href = targetUrl", app_js)


if __name__ == "__main__":
    unittest.main()
