from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.courses import _preview_with_openai
from final_edu.models import CurriculumPreviewResult


class CoursePreviewTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
