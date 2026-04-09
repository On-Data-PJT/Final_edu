from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from final_edu.analysis import analyze_submissions
from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.models import (
    AnalysisJobRecord,
    CurriculumSection,
    InstructorSubmission,
    RawTextSegment,
    SourceAsset,
    UploadedAsset,
)


def _sample_sections() -> list[CurriculumSection]:
    return [
        CurriculumSection(
            id="data-analysis",
            title="데이터 분석",
            description="sql pandas 전처리 시각화",
            target_weight=50,
        ),
        CurriculumSection(
            id="deep-learning",
            title="딥러닝",
            description="신경망 모델 학습 추론",
            target_weight=50,
        ),
    ]


def _fake_extract_file_asset(upload: UploadedAsset, instructor_name: str):
    source_id = f"{instructor_name}-material"
    return (
        SourceAsset(
            id=source_id,
            instructor_name=instructor_name,
            asset_type="file",
            label=upload.original_name,
            origin="upload",
        ),
        [
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="text",
                locator="material-1",
                text="SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석",
            )
        ],
        [],
    )


def _fake_extract_youtube_asset(url: str, instructor_name: str, settings=None, storage=None):
    source_id = f"{instructor_name}-speech"
    return (
        SourceAsset(
            id=source_id,
            instructor_name=instructor_name,
            asset_type="youtube",
            label=url,
            origin=url,
        ),
        [
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=url,
                source_type="youtube",
                locator="00:00",
                text="딥러닝 신경망 모델 학습 발화 신경망 딥러닝 실습",
            )
        ],
        [],
    )


def _build_result_payload() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        material_path_a = Path(temp_dir) / "instructor-a.txt"
        material_path_b = Path(temp_dir) / "instructor-b.txt"
        material_path_a.write_text("placeholder", encoding="utf-8")
        material_path_b.write_text("placeholder", encoding="utf-8")

        submissions = [
            InstructorSubmission(
                name="강사 A",
                files=[UploadedAsset(path=material_path_a, original_name="a.txt")],
                youtube_urls=["https://example.com/a"],
            ),
            InstructorSubmission(
                name="강사 B",
                files=[UploadedAsset(path=material_path_b, original_name="b.txt")],
                youtube_urls=["https://example.com/b"],
            ),
        ]

        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=32,
            chunk_overlap_segments=0,
            max_evidence_per_section=1,
        )

        with patch("final_edu.analysis.extract_file_asset", side_effect=_fake_extract_file_asset), patch(
            "final_edu.analysis.extract_youtube_asset",
            side_effect=_fake_extract_youtube_asset,
        ):
            result = analyze_submissions(
                course_id="course-1",
                course_name="AI 데이터 과정",
                sections=_sample_sections(),
                submissions=submissions,
                settings=settings,
                analysis_mode="lexical",
            )

    return result.to_dict()


class Page2DashboardTests(unittest.TestCase):
    def test_analysis_builds_mode_specific_payloads_for_page2(self) -> None:
        result = _build_result_payload()

        self.assertIn("rose_series_by_mode", result)
        self.assertIn("keywords_by_mode", result)
        self.assertEqual(sorted(result["rose_series_by_mode"].keys()), ["combined", "material", "speech"])
        self.assertEqual(sorted(result["keywords_by_mode"].keys()), ["combined", "material", "speech"])

        material_rose = {
            item["section_id"]: item["value"]
            for item in result["rose_series_by_mode"]["material"]["강사 A"]
        }
        speech_rose = {
            item["section_id"]: item["value"]
            for item in result["rose_series_by_mode"]["speech"]["강사 A"]
        }

        self.assertGreater(material_rose["data-analysis"], speech_rose["data-analysis"])
        self.assertGreater(speech_rose["deep-learning"], material_rose["deep-learning"])

        material_keywords = {
            item["text"] for item in result["keywords_by_mode"]["material"]["강사 A"][:6]
        }
        speech_keywords = {
            item["text"] for item in result["keywords_by_mode"]["speech"]["강사 A"][:6]
        }

        self.assertIn("sql", material_keywords)
        self.assertIn("신경망", speech_keywords)
        self.assertEqual(
            result["rose_series_by_instructor"],
            result["rose_series_by_mode"]["combined"],
        )
        self.assertEqual(
            result["keywords_by_instructor"],
            result["keywords_by_mode"]["combined"],
        )

    def test_job_detail_renders_real_dashboard_shell_without_demo_seed_data(self) -> None:
        result = _build_result_payload()
        record = AnalysisJobRecord(
            id="job123",
            course_id="course-1",
            course_name="AI 데이터 과정",
            status="completed",
            created_at="2026-04-09T10:00:00",
            updated_at="2026-04-09T10:05:00",
            created_at_ts=1.0,
            updated_at_ts=2.0,
            payload_key="payload.json",
            result_key="result.json",
            instructor_names=["강사 A", "강사 B"],
            instructor_count=2,
            asset_count=4,
            youtube_url_count=2,
            section_count=2,
            warning_count=0,
            selected_analysis_mode="lexical",
        )

        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
            clear=False,
        ):
            get_settings.cache_clear()
            app = create_app()
            client = TestClient(app)
            with patch("final_edu.app.get_job", return_value=record), patch(
                "final_edu.app.load_job_result",
                return_value=result,
            ):
                response = client.get("/jobs/job123")
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="dashboard-sidebar"', response.text)
        self.assertIn('id="section-donut"', response.text)
        self.assertIn('data-view-mode="speech"', response.text)
        self.assertIn("강사별 커리큘럼 구성 비중", response.text)
        self.assertIn("강사 A", response.text)
        self.assertNotIn("Study Labs", response.text)
        self.assertNotIn("오정훈 강사", response.text)


if __name__ == "__main__":
    unittest.main()
