from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from final_edu.analysis import _generate_voc_analysis, analyze_submissions
from final_edu.app import _build_solution_payload, _fallback_solution_content, _generate_solution_content, create_app
from final_edu.config import get_settings
from final_edu.extractors import TabularSheet, extract_file_asset
from final_edu import utils as edu_utils
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


def _survey_workbook_rows() -> list[list[object]]:
    return [
        [
            "Section A. 참여자 정보",
            "",
            "Section B. 교육 전반 만족도",
            "",
            "",
            "Section C. 강사 만족도",
            "",
            "Section D. 서술형",
        ],
        [
            "AQ1. 응답자 기본 정보",
            "",
            "BQ1. 교육 전반 만족도",
            "",
            "",
            "BQ2. 강사 만족도",
            "",
            "DQ1. 기타 의견",
        ],
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
        ["제조", "신규", 5, 4, 5, 5, 4, "설명이 친절했고 진행이 매끄러웠습니다."],
        ["서비스", "재직", 4, 4, 4, 5, 5, "실습 예시는 좋았지만 환경 안내가 더 필요합니다."],
        ["공공", "관리", 3, 4, 4, 4, 4, ""],
    ]


def _build_result_with_survey_xlsx_voc() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        material_path = Path(temp_dir) / "material.txt"
        material_path.write_text(
            "SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석",
            encoding="utf-8",
        )

        voc_path = Path(temp_dir) / "survey-review.xlsx"
        voc_path.write_bytes(_build_xlsx_bytes({"rawdata": _survey_workbook_rows()}))

        submissions = [
            InstructorSubmission(
                name="윤막강",
                files=[UploadedAsset(path=material_path, original_name="material.txt")],
                voc_files=[UploadedAsset(path=voc_path, original_name="survey-review.xlsx")],
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
            course_id="course-survey",
            course_name="설문형 VOC 과정",
            sections=_sample_sections(),
            submissions=submissions,
            settings=settings,
            analysis_mode="lexical",
        )
        return result.to_dict()


class VocAnalysisTests(unittest.TestCase):
    def test_legacy_jiye_and_job_solutions_routes_are_not_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
            clear=False,
        ):
            get_settings.cache_clear()
            client = TestClient(create_app())
            jiye_response = client.get("/jiye")
            solutions_response = client.get("/jobs/job123/solutions")
            get_settings.cache_clear()

        self.assertEqual(jiye_response.status_code, 404)
        self.assertEqual(solutions_response.status_code, 404)

    def test_voc_llm_analysis_uses_zero_temperature(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"sentiment":{"positive":["친절"],"negative":["속도"]},"repeated_complaints":[],"next_suggestions":[]}'))]

        with patch("final_edu.analysis.OpenAI") as openai_class:
            openai_class.return_value.chat.completions.create.return_value = mock_response
            settings = replace(get_settings(), openai_api_key="test-key")
            _generate_voc_analysis(
                instructor_name="윤막강",
                segments=[MagicMock(text="설명이 친절했지만 속도가 빨랐어요.")],
                settings=settings,
            )

        openai_class.return_value.chat.completions.create.assert_called_once()
        self.assertEqual(
            openai_class.return_value.chat.completions.create.call_args.kwargs["temperature"],
            0,
        )

    def test_solution_payload_uses_target_weight_as_gap_benchmark(self) -> None:
        payload = _build_solution_payload(
            {
                "sections": [
                    {"id": "sec-a", "title": "섹션 A", "target_weight": 60.0},
                    {"id": "sec-b", "title": "섹션 B", "target_weight": 40.0},
                ],
                "instructors": [
                    {
                        "name": "윤막강",
                        "asset_count": 1,
                        "warnings": [],
                        "unmapped_share": 0.1,
                        "section_coverages": [
                            {"section_id": "sec-a", "section_title": "섹션 A", "token_share": 0.2},
                            {"section_id": "sec-b", "section_title": "섹션 B", "token_share": 0.8},
                        ],
                    }
                ],
                "voc_summary": {"positive": ["친절"], "negative": []},
            }
        )

        self.assertEqual(payload["target"], [60.0, 40.0])
        self.assertEqual(payload["instructors"][0]["allRows"][0]["benchmarkShare"], 60.0)
        self.assertEqual(payload["instructors"][0]["allRows"][1]["benchmarkShare"], 40.0)

    def test_solution_payload_caps_total_gap_score_at_hundred(self) -> None:
        payload = _build_solution_payload(
            {
                "sections": [
                    {"id": "sec-a", "title": "섹션 A", "target_weight": 10.0},
                    {"id": "sec-b", "title": "섹션 B", "target_weight": 10.0},
                ],
                "instructors": [
                    {
                        "name": "윤막강",
                        "asset_count": 1,
                        "warnings": [],
                        "unmapped_share": 0.0,
                        "section_coverages": [
                            {"section_id": "sec-a", "section_title": "섹션 A", "token_share": 1.0},
                            {"section_id": "sec-b", "section_title": "섹션 B", "token_share": 1.0},
                        ],
                    }
                ],
                "voc_summary": {"positive": [], "negative": []},
            }
        )

        self.assertEqual(payload["instructors"][0]["totalGapScore"], 100.0)

    def test_generate_solution_content_uses_domain_specific_trend_guidance(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "insights": [
                                {"text": "인사이트 1", "numbers": []},
                                {"text": "인사이트 2", "numbers": []},
                                {"text": "인사이트 3", "numbers": []},
                                {"text": "인사이트 4", "numbers": []},
                                {"text": "인사이트 5", "numbers": []},
                            ],
                            "trendAnalysis": [
                                {"title": "동향 1", "detail": "상세 1", "badge": "갭", "comparison": "비교 1"},
                                {"title": "동향 2", "detail": "상세 2", "badge": "일치", "comparison": "비교 2"},
                                {"title": "동향 3", "detail": "상세 3", "badge": "신규", "comparison": "비교 3"},
                            ],
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]

        with patch("final_edu.app.OpenAI") as openai_class:
            openai_class.return_value.chat.completions.create.return_value = mock_response
            settings = replace(get_settings(), openai_api_key="test-key")
            _generate_solution_content(
                {
                    "topics": ["한국사 개론", "조선사"],
                    "target": [50.0, 50.0],
                    "instructors": [{"name": "윤막강", "rawValues": [45.0, 55.0], "totalGapScore": 10.0, "chartRows": []}],
                },
                settings,
            )

        messages = openai_class.return_value.chat.completions.create.call_args.kwargs["messages"]
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        self.assertIn("topics의 섹션명을 보고 과목 도메인", system_prompt)
        self.assertIn("특정 연도(예: 2024, 2025)를 언급하지 말고", system_prompt)
        self.assertIn("한국사능력검정시험", user_prompt)
        self.assertNotIn("2024-2025년 IT 교육 시장 동향", user_prompt)

    def test_fallback_solution_content_removes_it_specific_trend_copy(self) -> None:
        content = _fallback_solution_content(
            {
                "topics": ["한국사 개론", "조선사"],
                "target": [60.0, 40.0],
                "instructors": [
                    {
                        "name": "윤막강",
                        "rawValues": [45.0, 55.0],
                        "totalGapScore": 15.0,
                        "chartRows": [
                            {
                                "section": "한국사 개론",
                                "actualShare": 45.0,
                                "benchmarkShare": 60.0,
                                "gapScore": 15.0,
                            }
                        ],
                    }
                ],
            }
        )

        trend_blob = json.dumps(content["trendAnalysis"], ensure_ascii=False)
        self.assertNotIn("패스트캠퍼스", trend_blob)
        self.assertNotIn("Coursera", trend_blob)
        self.assertNotIn("LLM", trend_blob)
        self.assertNotIn("2024", trend_blob)
        self.assertNotIn("2025", trend_blob)

    def test_kiwi_uses_configured_model_path_when_present(self) -> None:
        with patch.dict(
            os.environ,
            {"FINAL_EDU_KIWI_MODEL_PATH": "C:/kiwi_model"},
            clear=False,
        ):
            get_settings.cache_clear()
            with patch("kiwipiepy.Kiwi") as kiwi_class, patch("final_edu.utils._KIWI", None):
                edu_utils.ensure_kiwi_ready()

            get_settings.cache_clear()

        kiwi_class.assert_called_once_with(num_workers=1, model_path="C:/kiwi_model")

    def test_kiwi_model_path_error_is_surfaced_clearly(self) -> None:
        with patch.dict(
            os.environ,
            {"FINAL_EDU_KIWI_MODEL_PATH": "C:/kiwi_model"},
            clear=False,
        ):
            get_settings.cache_clear()
            with patch("kiwipiepy.Kiwi", side_effect=RuntimeError("cannot open model")), patch(
                "final_edu.utils._KIWI",
                None,
            ):
                with self.assertRaises(RuntimeError) as context:
                    edu_utils.ensure_kiwi_ready()
            get_settings.cache_clear()

        self.assertIn("FINAL_EDU_KIWI_MODEL_PATH", str(context.exception))
        self.assertIn("C:/kiwi_model", str(context.exception))

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
        self.assertIn("현재 커리큘럼과 최신 교육 시장 트렌드 비교", solution_response.text)
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

    def test_analysis_includes_question_scores_for_survey_xlsx_voc(self) -> None:
        result = _build_result_with_survey_xlsx_voc()

        instructor = result["instructors"][0]
        question_scores = instructor["voc_analysis"]["question_scores"]
        summary_scores = result["voc_summary"]["question_scores"]

        self.assertTrue(question_scores)
        self.assertEqual([item["question_id"] for item in question_scores], [
            "BQ1-1",
            "BQ1-2",
            "BQ1-3",
            "BQ2-1",
            "BQ2-2",
        ])
        self.assertEqual([item["question_id"] for item in summary_scores], [
            "BQ1-1",
            "BQ1-2",
            "BQ1-3",
            "BQ2-1",
            "BQ2-2",
        ])
        self.assertNotIn("AQ1-1", {item["question_id"] for item in question_scores})
        self.assertGreaterEqual(instructor["voc_analysis"]["response_count"], 3)
        self.assertTrue(instructor["voc_analysis"]["sentiment"]["positive"])
        self.assertTrue(result["voc_summary"]["negative"])

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

    def test_review_and_solution_pages_render_voc_question_scores(self) -> None:
        result = _build_result_with_survey_xlsx_voc()
        record = AnalysisJobRecord(
            id="job-survey",
            course_id="course-survey",
            course_name="설문형 VOC 과정",
            status="completed",
            created_at="2026-04-13T10:00:00",
            updated_at="2026-04-13T10:05:00",
            created_at_ts=1.0,
            updated_at_ts=2.0,
            payload_key="payload.json",
            result_key="result.json",
            instructor_names=["윤막강"],
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
            client = TestClient(create_app())
            with patch("final_edu.app.get_job", return_value=record), patch(
                "final_edu.app.load_job_result",
                return_value=result,
            ):
                review_response = client.get("/review?job_id=job-survey")
                solution_response = client.get("/solution?job_id=job-survey")
            get_settings.cache_clear()

        self.assertEqual(review_response.status_code, 200)
        self.assertIn("문항별 평균 점수", review_response.text)
        self.assertIn("BQ1", review_response.text)
        self.assertIn("교육 신청 및 안내 절차가 수월하였다", review_response.text)

        self.assertEqual(solution_response.status_code, 200)
        self.assertIn("BQ1 평균 점수", solution_response.text)
        self.assertIn("강사의 설명이 이해하기 쉬웠다", solution_response.text)
        self.assertIn("현재 커리큘럼과 최신 교육 시장 트렌드 비교", solution_response.text)
        self.assertIn("강사별 표준커리큘럼 준수도", solution_response.text)
        self.assertIn("최근 주요 IT 교육기관은 프로젝트 실습을 전체 과정의 40% 이상 배정하는 추세입니다.", solution_response.text)
        self.assertNotIn("2024-2025년 주요 IT 교육기관은 프로젝트 실습을 전체 과정의 40% 이상 배정하는 추세입니다.", solution_response.text)


if __name__ == "__main__":
    unittest.main()
