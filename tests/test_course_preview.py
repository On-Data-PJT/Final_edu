from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf.errors import FileNotDecryptedError, PdfReadError

from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.courses import preview_course_pdf, _preview_with_openai, _preview_without_openai
from final_edu.models import CurriculumPreviewResult


class CoursePreviewTests(unittest.TestCase):
    @staticmethod
    def _chapter_roadmap_pages() -> list[dict]:
        return [
            {
                "page": 1,
                "text": (
                    "■ 강의 구성 로드맵\n"
                    "챕터 주제 분류 주차 강수\n"
                    "Chapter 1 Motivations and Basics 확률·통계 기초 1~2주차 4강\n"
                    "Chapter 2 Rule Based & Decision Tree 규칙 기반 / 의사결정트리 3~4주차 5강\n"
                    "Chapter 3 Optimal Classification & Naive Bayes 나이브 베이즈 5~6주차 4강\n"
                    "Chapter 4 Logistic Regression 로지스틱 회귀 7~9주차 8강\n"
                    "Chapter 5 Support Vector Machine SVM 10~12주차 9강\n"
                    "Chapter 6 Overfitting, Regularization & Model Selection 모델 선택 / 정규화 13~15주차 7강\n"
                    "챕터별 강의 세부 계획\n"
                ),
                "flat_text": (
                    "강의 구성 로드맵 Chapter 1 Motivations and Basics 확률·통계 기초 1~2주차 4강 "
                    "Chapter 2 Rule Based & Decision Tree 규칙 기반 / 의사결정트리 3~4주차 5강 "
                    "Chapter 3 Optimal Classification & Naive Bayes 나이브 베이즈 5~6주차 4강 "
                    "Chapter 4 Logistic Regression 로지스틱 회귀 7~9주차 8강 "
                    "Chapter 5 Support Vector Machine SVM 10~12주차 9강 "
                    "Chapter 6 Overfitting, Regularization & Model Selection 모델 선택 / 정규화 13~15주차 7강"
                ),
                "raw_layout_text": (
                    "■ 강의 구성 로드맵\n"
                    "챕터 주제 분류 주차 강수\n"
                    "Chapter 1 Motivations and Basics 확률·통계 기초 1~2주차 4강\n"
                    "Chapter 2 Rule Based & Decision Tree 규칙 기반 / 의사결정트리 3~4주차 5강\n"
                    "Chapter 3 Optimal Classification & Naive Bayes 나이브 베이즈 5~6주차 4강\n"
                    "Chapter 4 Logistic Regression 로지스틱 회귀 7~9주차 8강\n"
                    "Chapter 5 Support Vector Machine SVM 10~12주차 9강\n"
                    "Chapter 6 Overfitting, Regularization & Model Selection 모델 선택 / 정규화 13~15주차 7강\n"
                    "챕터별 강의 세부 계획\n"
                ),
            }
        ]

    def test_preview_endpoint_returns_result_payload(self) -> None:
        preview = CurriculumPreviewResult(
            decision="review_required",
            document_kind="curriculum_like",
            document_confidence=0.66,
            weight_status="missing",
            raw_curriculum_text="샘플 커리큘럼",
            sections=[],
            warnings=[],
            blocking_reasons=["검토 필요"],
        )

        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
            clear=False,
        ):
            get_settings.cache_clear()
            app = create_app()
            client = TestClient(app)
            with patch("final_edu.app.preview_course_pdf", return_value=preview):
                response = client.post(
                    "/courses/preview",
                    files={"curriculum_pdf": ("curriculum.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
                )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "review_required")
        self.assertEqual(response.json()["blocking_reasons"], ["검토 필요"])

    def test_preview_with_openai_uses_bounded_timeout(self) -> None:
        settings = replace(
            get_settings(),
            openai_api_key="test-key",
            curriculum_preview_timeout_seconds=7.5,
        )

        with patch("final_edu.courses.OpenAI") as mock_openai, patch(
            "final_edu.courses._build_preview_candidate_excerpt",
            return_value="",
        ):
            result = _preview_with_openai(
                page_records=[{"page": 1, "text": "커리큘럼", "flat_text": "커리큘럼", "raw_layout_text": "커리큘럼"}],
                raw_text="커리큘럼",
                warnings=[],
                max_sections=8,
                settings=settings,
            )

        self.assertEqual(result.decision, "rejected")
        mock_openai.assert_called_once_with(
            api_key="test-key",
            timeout=7.5,
            max_retries=0,
        )

    def test_preview_course_pdf_rejects_encrypted_pdf_without_raising(self) -> None:
        with patch("final_edu.courses._extract_pdf_pages", side_effect=FileNotDecryptedError("File has not been decrypted")):
            preview = preview_course_pdf(Path("encrypted.pdf"), 8, get_settings())

        self.assertEqual(preview.decision, "rejected")
        self.assertEqual(preview.document_kind, "unreadable")
        self.assertTrue(any("암호화/보호된 PDF" in reason for reason in preview.blocking_reasons))
        self.assertTrue(any("암호화/보호" in warning for warning in preview.warnings))

    def test_preview_course_pdf_rejects_broken_pdf_without_raising(self) -> None:
        with patch("final_edu.courses._extract_pdf_pages", side_effect=PdfReadError("broken xref table")):
            preview = preview_course_pdf(Path("broken.pdf"), 8, get_settings())

        self.assertEqual(preview.decision, "rejected")
        self.assertEqual(preview.document_kind, "unreadable")
        self.assertTrue(any("PDF 구조를 읽지 못해" in reason for reason in preview.blocking_reasons))
        self.assertTrue(any("broken xref table" in warning for warning in preview.warnings))

    def test_create_course_accepts_manual_sections_without_preview_decision_gate(self) -> None:
        with tempfile.TemporaryDirectory() as runtime_dir, patch.dict(
            os.environ,
            {"FINAL_EDU_RUNTIME_DIR": runtime_dir},
            clear=False,
        ):
            get_settings.cache_clear()
            app = create_app()
            client = TestClient(app)
            response = client.post(
                "/courses",
                data={
                    "course_name": "직접 정리 과정",
                    "sections_json": json.dumps(
                        [
                            {
                                "title": "대주제 1",
                                "description": "사용자가 직접 입력한 설명",
                                "target_weight": 60,
                            },
                            {
                                "title": "대주제 2",
                                "description": "두 번째 대주제",
                                "target_weight": 40,
                            },
                        ],
                        ensure_ascii=False,
                    ),
                    "instructor_names_json": json.dumps(["윤막강"], ensure_ascii=False),
                    "raw_curriculum_text": "자동 판정 실패 후 사용자가 직접 정리한 과정",
                },
                files={"curriculum_pdf": ("curriculum.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")},
            )
            get_settings.cache_clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["course"]["name"], "직접 정리 과정")
        self.assertEqual(len(payload["course"]["sections"]), 2)
        self.assertEqual(payload["course"]["sections"][0]["title"], "대주제 1")
        self.assertAlmostEqual(payload["course"]["sections"][0]["target_weight"], 60.0)

    def test_preview_without_openai_prefers_deterministic_lecture_counts(self) -> None:
        page_records = self._chapter_roadmap_pages()
        result = _preview_without_openai(
            page_records=page_records,
            raw_text=page_records[0]["text"],
            warnings=[],
            max_sections=8,
        )

        self.assertEqual(result.weight_status, "derivable")
        self.assertEqual([section.weight_source for section in result.sections], ["lecture_count"] * 6)
        weights = [section.target_weight for section in result.sections]
        self.assertEqual(weights, [10.81, 13.51, 10.81, 21.62, 24.32, 18.93])

    def test_preview_with_openai_keeps_deterministic_chapter_weights(self) -> None:
        settings = replace(
            get_settings(),
            openai_api_key="test-key",
            curriculum_preview_timeout_seconds=7.5,
            curriculum_accept_confidence=0.7,
            curriculum_review_confidence=0.5,
        )
        page_records = self._chapter_roadmap_pages()
        classification = SimpleNamespace(
            output_parsed=SimpleNamespace(
                document_kind="curriculum",
                confidence=0.93,
                has_section_structure=True,
                has_explicit_weight_signals=False,
                has_derivable_weight_signals=True,
                warnings=[],
                blocking_reasons=[],
                evidence=[],
            )
        )

        with patch("final_edu.courses.OpenAI") as mock_openai, patch(
            "final_edu.courses._build_preview_candidate_excerpt",
            return_value=page_records[0]["text"],
        ):
            mock_client = mock_openai.return_value
            mock_client.responses.parse.side_effect = [classification]
            result = _preview_with_openai(
                page_records=page_records,
                raw_text=page_records[0]["text"],
                warnings=[],
                max_sections=8,
                settings=settings,
            )

        self.assertEqual(mock_client.responses.parse.call_count, 1)
        self.assertEqual([section.weight_source for section in result.sections], ["lecture_count"] * 6)
        self.assertEqual([section.target_weight for section in result.sections], [10.81, 13.51, 10.81, 21.62, 24.32, 18.93])

    def test_preview_weight_input_allows_hundredth_step(self) -> None:
        app_js = Path("final_edu/static/app.js").read_text(encoding="utf-8")
        self.assertIn('step="0.01"', app_js)


if __name__ == "__main__":
    unittest.main()
