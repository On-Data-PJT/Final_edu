from __future__ import annotations

import csv
import os
import tempfile
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from final_edu.analysis import analyze_submissions
from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.extractors import TabularSheet, extract_file_asset
from final_edu.models import AnalysisJobRecord, CurriculumSection, InstructorSubmission, UploadedAsset


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


def _build_result_with_voc() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        material_path = Path(temp_dir) / "material.txt"
        material_path.write_text(
            "SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석",
            encoding="utf-8",
        )

        voc_path = Path(temp_dir) / "review.csv"
        with voc_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["week", "comment"])
            writer.writerow(["3주차", "강의 속도가 너무 빨라요"])
            writer.writerow(["4주차", "실습 환경 오류가 자주 났어요"])
            writer.writerow(["5주차", "자료가 부족해서 복습이 어려웠어요"])
            writer.writerow(["1주차", "설명은 친절했고 예시는 좋았어요"])

        submissions = [
            InstructorSubmission(
                name="오정훈 강사",
                files=[UploadedAsset(path=material_path, original_name="material.txt")],
                voc_files=[UploadedAsset(path=voc_path, original_name="review.csv")],
            )
        ]

        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=32,
            chunk_overlap_segments=0,
            max_evidence_per_section=1,
        )
        result = analyze_submissions(
            course_id="course-1",
            course_name="AI 데이터 과정",
            sections=_sample_sections(),
            submissions=submissions,
            settings=settings,
            analysis_mode="lexical",
        )
        return result.to_dict()


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


def _build_result_with_xlsx_voc() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        material_path = Path(temp_dir) / "material.txt"
        material_path.write_text(
            "SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석",
            encoding="utf-8",
        )

        voc_path = Path(temp_dir) / "review.xlsx"
        voc_path.write_bytes(
            _build_xlsx_bytes(
                {
                    "응답": [
                        ["week", "rating", "comment"],
                        ["3주차", 2, "강의 속도가 너무 빨라요"],
                        ["4주차", 2, "실습 환경 오류가 자주 났어요"],
                        ["5주차", 3, "자료가 부족해서 복습이 어려웠어요"],
                        ["1주차", 5, "설명은 친절했고 예시는 좋았어요"],
                    ]
                }
            )
        )

        submissions = [
            InstructorSubmission(
                name="오정훈 강사",
                files=[UploadedAsset(path=material_path, original_name="material.txt")],
                voc_files=[UploadedAsset(path=voc_path, original_name="review.xlsx")],
            )
        ]

        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=32,
            chunk_overlap_segments=0,
            max_evidence_per_section=1,
        )
        result = analyze_submissions(
            course_id="course-1",
            course_name="AI 데이터 과정",
            sections=_sample_sections(),
            submissions=submissions,
            settings=settings,
            analysis_mode="lexical",
        )
        return result.to_dict()


class VocAnalysisTests(unittest.TestCase):
    def test_analysis_includes_voc_by_instructor_and_summary(self) -> None:
        result = _build_result_with_voc()

        instructor = result["instructors"][0]
        self.assertEqual(instructor["voc_analysis"]["file_name"], "review.csv")
        self.assertGreaterEqual(instructor["voc_analysis"]["response_count"], 4)
        self.assertTrue(instructor["voc_analysis"]["sentiment"]["positive"])
        self.assertTrue(instructor["voc_analysis"]["repeated_complaints"])
        self.assertTrue(result["voc_summary"]["negative"])
        self.assertTrue(result["voc_summary"]["next_suggestions"])

    def test_review_and_solution_pages_render_real_voc_results(self) -> None:
        result = _build_result_with_voc()
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
            instructor_names=["오정훈 강사"],
            instructor_count=1,
            asset_count=2,
            youtube_url_count=0,
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
                review_response = client.get("/review?job_id=job123")
                solution_response = client.get("/solution?job_id=job123")
            get_settings.cache_clear()

        self.assertEqual(review_response.status_code, 200)
        self.assertIn("review.csv", review_response.text)
        self.assertIn("강의 속도 조절", review_response.text)
        self.assertIn("친절한 설명", review_response.text)
        self.assertIn('href="/jobs/job123"', review_response.text)
        self.assertIn('href="/review?job_id=job123"', review_response.text)
        self.assertIn('href="/solution?job_id=job123"', review_response.text)

        self.assertEqual(solution_response.status_code, 200)
        self.assertIn("VOC 기반 인사이트", solution_response.text)
        self.assertIn("강의 속도", solution_response.text)
        self.assertIn("실제 VOC 결과", solution_response.text)
        self.assertIn('href="/jobs/job123"', solution_response.text)
        self.assertIn('href="/review?job_id=job123"', solution_response.text)
        self.assertIn('href="/solution?job_id=job123"', solution_response.text)

    def test_analysis_includes_xlsx_voc_by_instructor_and_summary(self) -> None:
        result = _build_result_with_xlsx_voc()

        instructor = result["instructors"][0]
        self.assertEqual(instructor["voc_analysis"]["file_name"], "review.xlsx")
        self.assertGreaterEqual(instructor["voc_analysis"]["response_count"], 4)
        self.assertTrue(instructor["voc_analysis"]["sentiment"]["negative"])
        self.assertTrue(result["voc_summary"]["next_suggestions"])

    def test_extract_file_asset_supports_xls_voc_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "final_edu.extractors._read_xls_sheets",
            return_value=[
                TabularSheet(
                    name="응답",
                    rows=[
                        ["week", "comment"],
                        ["1주차", "설명은 친절했어요"],
                        ["2주차", "실습 환경이 불안정했어요"],
                    ],
                )
            ],
        ):
            voc_path = Path(temp_dir) / "review.xls"
            voc_path.write_bytes(b"placeholder")
            source, segments, warnings = extract_file_asset(
                UploadedAsset(path=voc_path, original_name="review.xls"),
                "오정훈 강사",
            )

        self.assertEqual(source.asset_type, "xls")
        self.assertFalse(warnings)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].locator, "응답.row.1")
        self.assertIn("comment: 설명은 친절했어요", segments[0].text)


if __name__ == "__main__":
    unittest.main()
