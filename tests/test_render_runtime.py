from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from final_edu.analysis import (
    _assign_with_lexical,
    _assign_with_openai,
    _build_lexical_index,
    _init_mode_aggregates,
    _stream_segments_into_aggregates,
)
from final_edu.app import _phase_label, create_app
from final_edu.config import get_settings
from final_edu.jobs import create_job_record, run_analysis_job
from final_edu.models import (
    AnalysisJobPayload,
    AnalysisJobRecord,
    CurriculumSection,
    ExtractedChunk,
    InstructorSubmission,
    JobInstructorInput,
    RawTextSegment,
)
from final_edu import worker as worker_module


def _iso_from_ts(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


class RenderRuntimeTests(unittest.TestCase):
    def test_web_app_startup_does_not_force_kiwi_ready(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
            clear=False,
        ), patch(
            "final_edu.app.ensure_kiwi_ready",
            side_effect=AssertionError("web startup should not preload kiwi"),
            create=True,
        ):
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

    def test_phase_label_includes_embedding(self) -> None:
        self.assertEqual(_phase_label("embedding"), "임베딩 계산 중")

    def test_assign_with_lexical_emits_chunk_progress(self) -> None:
        sections = [
            CurriculumSection(id="alpha", title="Alpha", description="alpha topic", target_weight=50.0),
            CurriculumSection(id="beta", title="Beta", description="beta topic", target_weight=50.0),
        ]
        chunks = [
            ExtractedChunk(
                id="chunk-1",
                source_id="source-1",
                instructor_name="강사 1",
                source_label="Manual 1",
                source_type="manual",
                locator="1",
                text="alpha alpha fundamentals",
                token_count=3,
                fingerprint="alpha",
            ),
            ExtractedChunk(
                id="chunk-2",
                source_id="source-2",
                instructor_name="강사 1",
                source_label="Manual 2",
                source_type="manual",
                locator="2",
                text="beta beta practice",
                token_count=3,
                fingerprint="beta",
            ),
        ]
        snapshots: list[tuple[str, int, int]] = []

        assignments, warnings = _assign_with_lexical(
            chunks,
            sections,
            SimpleNamespace(),
            progress_callback=lambda **snapshot: snapshots.append(
                (snapshot.get("phase"), snapshot.get("progress_current"), snapshot.get("progress_total"))
            ),
        )

        self.assertEqual(len(assignments), 2)
        self.assertEqual(warnings, [])
        self.assertEqual(
            [snapshot for snapshot in snapshots if snapshot[0] == "assigning"],
            [("assigning", 0, 2), ("assigning", 1, 2), ("assigning", 2, 2)],
        )

    def test_assign_with_openai_emits_embedding_then_assignment_progress(self) -> None:
        class FakeEmbeddings:
            @staticmethod
            def create(*, model, input):  # noqa: ANN001
                data = []
                for text in input:
                    normalized = str(text).lower()
                    if "alpha" in normalized:
                        embedding = [1.0, 0.0]
                    elif "beta" in normalized:
                        embedding = [0.0, 1.0]
                    else:
                        embedding = [0.5, 0.5]
                    data.append(SimpleNamespace(embedding=embedding))
                return SimpleNamespace(data=data)

        fake_client = SimpleNamespace(embeddings=FakeEmbeddings())
        sections = [
            CurriculumSection(id="alpha", title="Alpha", description="alpha topic", target_weight=50.0),
            CurriculumSection(id="beta", title="Beta", description="beta topic", target_weight=50.0),
        ]
        chunks = [
            ExtractedChunk(
                id="chunk-1",
                source_id="source-1",
                instructor_name="강사 1",
                source_label="Manual 1",
                source_type="manual",
                locator="1",
                text="alpha alpha fundamentals",
                token_count=3,
                fingerprint="alpha",
            ),
            ExtractedChunk(
                id="chunk-2",
                source_id="source-2",
                instructor_name="강사 1",
                source_label="Manual 2",
                source_type="manual",
                locator="2",
                text="beta beta practice",
                token_count=3,
                fingerprint="beta",
            ),
        ]
        snapshots: list[tuple[str, int, int]] = []

        with patch("final_edu.analysis.OpenAI", return_value=fake_client):
            assignments, warnings = _assign_with_openai(
                chunks,
                sections,
                SimpleNamespace(openai_api_key="test-key", openai_embedding_model="test-embedding"),
                progress_callback=lambda **snapshot: snapshots.append(
                    (snapshot.get("phase"), snapshot.get("progress_current"), snapshot.get("progress_total"))
                ),
            )

        self.assertEqual(len(assignments), 2)
        self.assertEqual(warnings, [])
        self.assertEqual(
            [snapshot for snapshot in snapshots if snapshot[0] == "embedding"],
            [("embedding", 0, 2), ("embedding", 1, 2), ("embedding", 2, 2)],
        )
        self.assertEqual(
            [snapshot for snapshot in snapshots if snapshot[0] == "assigning"],
            [("assigning", 0, 2), ("assigning", 1, 2), ("assigning", 2, 2)],
        )

    def test_streaming_assignment_progress_moves_per_chunk(self) -> None:
        sections = [
            CurriculumSection(id="photosynthesis", title="광합성", description="엽록체와 광반응", target_weight=50.0),
            CurriculumSection(id="respiration", title="세포 호흡", description="ATP 생성", target_weight=50.0),
        ]
        submissions = [InstructorSubmission(name="강사 1")]
        segments = [
            RawTextSegment(
                source_id="youtube-1",
                instructor_name="강사 1",
                source_label="생명과학 라이브",
                source_type="youtube",
                locator="00:00",
                text="광합성은 엽록체에서 일어납니다.",
            ),
            RawTextSegment(
                source_id="youtube-1",
                instructor_name="강사 1",
                source_label="생명과학 라이브",
                source_type="youtube",
                locator="00:20",
                text="세포 호흡은 ATP를 생성합니다.",
            ),
        ]
        snapshots: list[tuple[str, int, int]] = []
        progress_state = {"current": 0, "total": 0}
        removed_duplicates, warnings = _stream_segments_into_aggregates(
            segments=segments,
            instructor_name="강사 1",
            settings=SimpleNamespace(chunk_target_tokens=24, openai_api_key=None),
            sections=sections,
            lexical_index=_build_lexical_index(sections),
            dedupe_seen=set(),
            mode_aggregates=_init_mode_aggregates(sections, submissions),
            evidence_map=defaultdict(lambda: defaultdict(list)),
            keyword_counters_by_mode={mode: defaultdict(Counter) for mode in ("combined", "material", "speech")},
            off_curriculum_counters_by_mode={mode: defaultdict(Counter) for mode in ("combined", "material", "speech")},
            keyword_documents_by_mode={mode: [] for mode in ("combined", "material", "speech")},
            off_curriculum_keyword_documents_by_mode={mode: [] for mode in ("combined", "material", "speech")},
            curriculum_tokens={"광합성", "세포", "호흡"},
            max_evidence=2,
            progress_callback=lambda **snapshot: snapshots.append(
                (snapshot.get("phase"), snapshot.get("progress_current"), snapshot.get("progress_total"))
            ),
            progress_state=progress_state,
            progress_context={"expanded_video_count": 1, "processed_video_count": 1, "caption_success_count": 1, "caption_failure_count": 0},
        )

        self.assertEqual(removed_duplicates, 0)
        self.assertEqual(warnings, [])
        self.assertTrue(any(snapshot[0] == "assigning" and snapshot[1] == 0 for snapshot in snapshots))
        self.assertTrue(any(snapshot[0] == "assigning" and snapshot[1] == snapshot[2] for snapshot in snapshots))

    def test_run_analysis_job_persists_small_progress_increments(self) -> None:
        payload = AnalysisJobPayload(
            job_id="job-small-progress",
            course_id="course-1",
            course_name="진행률 테스트",
            course_sections=[CurriculumSection(id="section-1", title="대주제", description="설명", target_weight=100.0)],
            curriculum_text="대주제 | 설명",
            instructors=[JobInstructorInput(name="강사 1", youtube_urls=["https://www.youtube.com/watch?v=test"])],
            submitted_at=_iso_from_ts(datetime.now(UTC).timestamp()),
        )
        initial_record = create_job_record(payload, "jobs/job-small-progress/payload.json", 1, SimpleNamespace())
        saved_records: list[AnalysisJobRecord] = []

        class FakeRepository:
            def __init__(self, record: AnalysisJobRecord) -> None:
                self.record = record

            def get(self, job_id: str) -> AnalysisJobRecord | None:
                return self.record if job_id == self.record.id else None

            def save(self, record: AnalysisJobRecord) -> None:
                self.record = record
                saved_records.append(record)

        fake_repository = FakeRepository(initial_record)
        fake_storage = SimpleNamespace(
            get_json=lambda _key: payload.to_dict(),
            put_json=lambda _key, _value: None,
        )
        fake_services = SimpleNamespace(
            repository=fake_repository,
            storage=fake_storage,
            settings=SimpleNamespace(),
        )

        def fake_execute_analysis(_payload, _storage, _settings, *, progress_callback=None):
            if progress_callback is not None:
                progress_callback(phase="embedding", progress_current=1, progress_total=3)
                progress_callback(phase="embedding", progress_current=2, progress_total=3)
                progress_callback(phase="embedding", progress_current=3, progress_total=3)
            return {"scorer_mode": "lexical", "duration_ms": 10, "warnings": []}

        with patch("final_edu.jobs.create_job_services", return_value=fake_services), patch(
            "final_edu.jobs._execute_analysis",
            side_effect=fake_execute_analysis,
        ):
            run_analysis_job(payload.job_id)

        embedding_progresses = [
            (record.phase, record.progress_current, record.progress_total)
            for record in saved_records
            if record.phase == "embedding"
        ]
        self.assertIn(("embedding", 1, 3), embedding_progresses)
        self.assertIn(("embedding", 2, 3), embedding_progresses)
        self.assertIn(("embedding", 3, 3), embedding_progresses)

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
