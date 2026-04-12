from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from final_edu.analysis import analyze_submissions
from final_edu.analysis import (
    _apply_speech_title_prior,
    _build_section_assignment_texts,
    _restrict_scored_sections_to_candidates,
    _resolve_speech_title_rescue,
    _score_speech_title_sections,
    _speech_anchor_counts,
    _speech_transcript_anchor_counts_by_section,
    _speech_transcript_candidate_section_ids,
)
from final_edu.app import create_app
from final_edu.config import get_settings
from final_edu.models import (
    AnalysisJobRecord,
    CurriculumSection,
    ExtractedChunk,
    InstructorSubmission,
    RawTextSegment,
    SourceAsset,
    UploadedAsset,
)
from final_edu.utils import build_preserved_segment_chunks


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


def _sample_material_ml_sections() -> list[CurriculumSection]:
    return [
        CurriculumSection(
            id="deep-learning-and-boltzmann-machine",
            title="Deep Learning and Boltzmann Machine",
            description="restricted boltzmann machine deep learning",
            target_weight=50,
        ),
        CurriculumSection(
            id="random-forest-autoencoder",
            title="랜덤 포레스트 / 오토인코더",
            description="random forest autoencoder",
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


def _fake_extract_pdf_asset(upload: UploadedAsset, instructor_name: str):
    source_id = f"{instructor_name}-pdf"
    return (
        SourceAsset(
            id=source_id,
            instructor_name=instructor_name,
            asset_type="pdf",
            label=upload.original_name,
            origin="upload",
        ),
        [
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.1",
                text="SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석 전처리",
            ),
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.2",
                text="딥러닝 신경망 모델 학습 추론 딥러닝 신경망 모델 실습",
            ),
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.3",
                text="SQL 데이터 분석 리포트 시각화 pandas 데이터 분석 SQL",
            ),
        ],
        [],
    )


def _fake_extract_off_curriculum_file_asset(upload: UploadedAsset, instructor_name: str):
    source_id = f"{instructor_name}-off-curriculum"
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
                text="그럼 다음 그리고 자 이제 실제 예시로 넘어가 보겠습니다 반복 설명 연결 멘트",
            )
        ],
        [],
    )


def _fake_extract_material_mixed_topic_asset(upload: UploadedAsset, instructor_name: str):
    source_id = f"{instructor_name}-mixed-material"
    return (
        SourceAsset(
            id=source_id,
            instructor_name=instructor_name,
            asset_type="pdf",
            label=upload.original_name,
            origin="upload",
        ),
        [
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.8",
                text=(
                    "■ 딥 러닝 딥 러닝 제한적 볼츠만 기계 볼츠만 RBM 딥러닝 표현학습 "
                    "▷ 오토인코더 오토인코더 autoencoder 잠재표현 재구성 "
                    "Q1. 확인 문제 답: _____"
                ),
            )
        ],
        [],
    )


def _build_result_payload(
    *,
    include_material: bool = True,
    include_speech: bool = True,
    instructor_names: tuple[str, ...] = ("강사 A", "강사 B"),
) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        submissions = []
        for index, instructor_name in enumerate(instructor_names):
            material_path = Path(temp_dir) / f"instructor-{index + 1}.txt"
            material_path.write_text("placeholder", encoding="utf-8")
            submissions.append(
                InstructorSubmission(
                    name=instructor_name,
                    files=[UploadedAsset(path=material_path, original_name=f"{instructor_name}.txt")] if include_material else [],
                    youtube_urls=[f"https://example.com/{index + 1}"] if include_speech else [],
                )
            )

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

        self.assertIn("available_source_modes", result)
        self.assertIn("source_mode_stats", result)
        self.assertIn("mode_unmapped_series", result)
        self.assertIn("rose_series_by_mode", result)
        self.assertIn("keywords_by_mode", result)
        self.assertIn("average_keywords_by_mode", result)
        self.assertEqual(sorted(result["rose_series_by_mode"].keys()), ["combined", "material", "speech"])
        self.assertEqual(sorted(result["keywords_by_mode"].keys()), ["combined", "material", "speech"])
        self.assertEqual(sorted(result["available_source_modes"]), ["combined", "material", "speech"])
        self.assertEqual(result["source_mode_stats"]["material"]["asset_count"], 2)
        self.assertGreater(result["source_mode_stats"]["material"]["total_tokens"], 0)
        self.assertGreater(result["source_mode_stats"]["material"]["mapped_tokens"], 0)
        self.assertEqual(result["source_mode_stats"]["speech"]["asset_count"], 2)
        self.assertGreater(result["source_mode_stats"]["speech"]["total_tokens"], 0)
        self.assertGreater(result["source_mode_stats"]["speech"]["mapped_tokens"], 0)

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
        self.assertAlmostEqual(sum(material_rose.values()), 100.0, places=2)
        self.assertAlmostEqual(sum(speech_rose.values()), 100.0, places=2)

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
        self.assertEqual(
            sorted(result["keywords_by_mode"]["combined"].keys()),
            ["강사 A", "강사 B"],
        )
        self.assertTrue(all("__off_curriculum" not in key for key in result["keywords_by_mode"]["combined"]))
        self.assertTrue(all("__off_curriculum" not in key for key in result["keywords_by_instructor"]))
        self.assertEqual(
            [item["text"] for item in result["average_keywords_by_mode"]["combined"][:4]],
            ["sql", "데이터", "딥러닝", "분석"],
        )
        self.assertIn("material", result["mode_unmapped_series"])
        self.assertIn("강사 A", result["mode_unmapped_series"]["material"]["instructors"])

    def test_average_keywords_match_single_instructor_keywords(self) -> None:
        result = _build_result_payload(instructor_names=("강사 A",))

        for mode in ("combined", "material", "speech"):
            self.assertEqual(
                result["average_keywords_by_mode"][mode],
                result["keywords_by_mode"][mode]["강사 A"],
            )

    def test_analysis_marks_material_mode_unavailable_when_no_material_assets_exist(self) -> None:
        result = _build_result_payload(include_material=False, include_speech=True)

        self.assertNotIn("material", result["available_source_modes"])
        self.assertIn("combined", result["available_source_modes"])
        self.assertIn("speech", result["available_source_modes"])
        self.assertEqual(result["source_mode_stats"]["material"]["asset_count"], 0)
        self.assertEqual(result["source_mode_stats"]["material"]["total_tokens"], 0)
        self.assertEqual(result["source_mode_stats"]["material"]["mapped_tokens"], 0)
        self.assertEqual(result["mode_unmapped_series"]["material"]["average"], 0.0)
        self.assertEqual(result["source_mode_stats"]["speech"]["asset_count"], 2)
        self.assertGreater(result["source_mode_stats"]["speech"]["total_tokens"], 0)
        self.assertGreater(result["source_mode_stats"]["speech"]["mapped_tokens"], 0)

    def test_material_pdf_chunks_preserve_page_boundaries(self) -> None:
        segments = [
            RawTextSegment(
                source_id="material-1",
                instructor_name="강사 A",
                source_label="study.pdf",
                source_type="pdf",
                locator="p.1",
                text="SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석 전처리",
            ),
            RawTextSegment(
                source_id="material-1",
                instructor_name="강사 A",
                source_label="study.pdf",
                source_type="pdf",
                locator="p.2",
                text="딥러닝 신경망 모델 학습 추론 딥러닝 신경망 모델 실습",
            ),
            RawTextSegment(
                source_id="material-1",
                instructor_name="강사 A",
                source_label="study.pdf",
                source_type="pdf",
                locator="p.3",
                text="SQL 데이터 분석 리포트 시각화 pandas 데이터 분석 SQL",
            ),
        ]

        chunks = build_preserved_segment_chunks(segments, target_tokens=1000)

        self.assertEqual([chunk.locator for chunk in chunks], ["p.1", "p.2", "p.3"])

    def test_material_pdf_semantic_subchunks_drop_question_blocks(self) -> None:
        segments = [
            RawTextSegment(
                source_id="material-1",
                instructor_name="강사 A",
                source_label="study.pdf",
                source_type="pdf",
                locator="p.8",
                text=(
                    "■ 딥 러닝 딥 러닝 제한적 볼츠만 기계 볼츠만 RBM 딥러닝 표현학습 "
                    "▷ 오토인코더 오토인코더 autoencoder 잠재표현 재구성 "
                    "Q1. 확인 문제 답: _____"
                ),
            )
        ]

        chunks = build_preserved_segment_chunks(segments, target_tokens=1000)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.locator.startswith("p.8") for chunk in chunks))
        self.assertTrue(all("Q1." not in chunk.text for chunk in chunks))
        self.assertTrue(all("확인 문제" not in chunk.text for chunk in chunks))
        self.assertTrue(all("답:" not in chunk.text for chunk in chunks))

    def test_analysis_spreads_material_pdf_across_multiple_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            material_path = Path(temp_dir) / "study.pdf"
            material_path.write_text("placeholder", encoding="utf-8")
            submissions = [
                InstructorSubmission(
                    name="강사 A",
                    files=[UploadedAsset(path=material_path, original_name="study.pdf")],
                )
            ]
            settings = replace(
                get_settings(),
                openai_api_key=None,
                chunk_target_tokens=1000,
                chunk_overlap_segments=1,
                max_evidence_per_section=1,
            )

            with patch("final_edu.analysis.extract_file_asset", side_effect=_fake_extract_pdf_asset):
                result = analyze_submissions(
                    course_id="course-1",
                    course_name="AI 데이터 과정",
                    sections=_sample_sections(),
                    submissions=submissions,
                    settings=settings,
                    analysis_mode="lexical",
                ).to_dict()

        material_rose = {
            item["section_id"]: item["value"]
            for item in result["rose_series_by_mode"]["material"]["강사 A"]
        }
        self.assertGreater(material_rose["data-analysis"], 0.0)
        self.assertGreater(material_rose["deep-learning"], 0.0)
        self.assertAlmostEqual(sum(material_rose.values()), 100.0, places=2)
        self.assertEqual(result["mode_unmapped_series"]["material"]["instructors"]["강사 A"], 0.0)

    def test_analysis_assigns_deep_learning_and_autoencoder_when_material_page_is_split(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            material_path = Path(temp_dir) / "study.pdf"
            material_path.write_text("placeholder", encoding="utf-8")
            submissions = [
                InstructorSubmission(
                    name="강사 A",
                    files=[UploadedAsset(path=material_path, original_name="study.pdf")],
                )
            ]
            settings = replace(
                get_settings(),
                openai_api_key=None,
                chunk_target_tokens=1000,
                chunk_overlap_segments=1,
                max_evidence_per_section=1,
            )

            with patch(
                "final_edu.analysis.extract_file_asset",
                side_effect=_fake_extract_material_mixed_topic_asset,
            ):
                result = analyze_submissions(
                    course_id="course-1",
                    course_name="AI 데이터 과정",
                    sections=_sample_material_ml_sections(),
                    submissions=submissions,
                    settings=settings,
                    analysis_mode="lexical",
                ).to_dict()

        material_rose = {
            item["section_id"]: item["value"]
            for item in result["rose_series_by_mode"]["material"]["강사 A"]
        }
        self.assertGreater(material_rose["deep-learning-and-boltzmann-machine"], 0.0)
        self.assertGreater(material_rose["random-forest-autoencoder"], 0.0)
        self.assertAlmostEqual(sum(material_rose.values()), 100.0, places=2)

    def test_analysis_keeps_mode_available_when_source_exists_but_mapped_tokens_are_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            material_path = Path(temp_dir) / "off-curriculum.txt"
            material_path.write_text("placeholder", encoding="utf-8")
            submissions = [
                InstructorSubmission(
                    name="강사 A",
                    files=[UploadedAsset(path=material_path, original_name="off-curriculum.txt")],
                )
            ]
            settings = replace(
                get_settings(),
                openai_api_key=None,
                chunk_target_tokens=64,
                chunk_overlap_segments=0,
                max_evidence_per_section=1,
            )

            with patch("final_edu.analysis.extract_file_asset", side_effect=_fake_extract_off_curriculum_file_asset):
                result = analyze_submissions(
                    course_id="course-1",
                    course_name="AI 데이터 과정",
                    sections=_sample_sections(),
                    submissions=submissions,
                    settings=settings,
                    analysis_mode="lexical",
                ).to_dict()

        self.assertIn("material", result["available_source_modes"])
        self.assertEqual(result["source_mode_stats"]["material"]["asset_count"], 1)
        self.assertGreater(result["source_mode_stats"]["material"]["total_tokens"], 0)
        self.assertEqual(result["source_mode_stats"]["material"]["mapped_tokens"], 0)
        material_rose = result["rose_series_by_mode"]["material"]["강사 A"]
        self.assertTrue(all(item["value"] == 0.0 for item in material_rose))

    def test_decision_tree_assignment_text_includes_entropy_aliases(self) -> None:
        sections = [
            CurriculumSection(
                id="decision-tree",
                title="결정 트리",
                description="Decision Trees and related topic content.",
            )
        ]

        assignment_text = _build_section_assignment_texts(sections)["decision-tree"]

        self.assertIn("entropy", assignment_text.lower())
        self.assertIn("information gain", assignment_text.lower())
        self.assertIn("지니", assignment_text)
        self.assertIn("가지치기", assignment_text)

    def test_speech_title_prior_rescues_near_tie_decision_tree_chunk(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        deep_learning = CurriculumSection(
            id="deep-learning",
            title="Deep Learning and Boltzmann Machine",
            description="Deep learning topic.",
        )
        chunk = ExtractedChunk(
            id="chunk-1",
            source_id="video-1",
            instructor_name="강사 A",
            source_label="Introduction to Decision Trees",
            source_type="youtube",
            locator="00:00 -> 09:11",
            text="decision tree entropy information gain",
            token_count=8,
            fingerprint="chunk-1",
        )

        adjusted, warning = _apply_speech_title_prior(
            chunk=chunk,
            transcript_scored=[
                (decision_tree, 0.2597),
                (deep_learning, 0.2496),
            ],
            title_scored=[
                (decision_tree, 0.66),
                (deep_learning, 0.22),
            ],
            transcript_anchor_counts={"decision-tree": {"decision tree": 1}},
            min_score=0.23,
            min_margin=0.025,
        )

        ranked = sorted(adjusted, key=lambda item: item[1], reverse=True)
        self.assertEqual(ranked[0][0].id, "decision-tree")
        self.assertGreater(ranked[0][1] - ranked[1][1], 0.025)
        self.assertIsNone(warning)

    def test_speech_title_prior_warns_but_does_not_override_mismatched_transcript(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        regression = CurriculumSection(id="regression", title="회귀분석", description="Regression topic.")
        chunk = ExtractedChunk(
            id="chunk-2",
            source_id="video-2",
            instructor_name="강사 A",
            source_label="How to create a decision tree given a training dataset",
            source_type="youtube",
            locator="00:01 -> 14:12",
            text="linear regression statistics loss function",
            token_count=8,
            fingerprint="chunk-2",
        )

        adjusted, warning = _apply_speech_title_prior(
            chunk=chunk,
            transcript_scored=[
                (regression, 0.2924),
                (decision_tree, 0.2461),
            ],
            title_scored=[
                (decision_tree, 0.72),
                (regression, 0.18),
            ],
            transcript_anchor_counts={},
            min_score=0.23,
            min_margin=0.025,
        )

        ranked = sorted(adjusted, key=lambda item: item[1], reverse=True)
        self.assertEqual(ranked[0][0].id, "regression")
        self.assertIsNotNone(warning)
        self.assertIn("영상 제목은 '결정 트리'에 가깝지만", warning)

    def test_speech_title_exact_anchor_does_not_match_decision_boundary_video(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        svm = CurriculumSection(
            id="support-vector-machine",
            title="Support Vector Machine",
            description="SVM topic.",
        )

        title_scored = _score_speech_title_sections(
            sections=[decision_tree, svm],
            source_label="Introduction to Artificial Intelligence and Machine Learning 1 [4-1] Decision Boundary",
        )

        self.assertEqual(title_scored, [])

    def test_speech_transcript_anchor_gate_rejects_rule_based_intro_chunk(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        svm = CurriculumSection(
            id="support-vector-machine",
            title="Support Vector Machine",
            description="SVM topic.",
        )
        chunk = ExtractedChunk(
            id="chunk-3",
            source_id="video-3",
            instructor_name="강사 A",
            source_label="Rule-Based Machine Learning",
            source_type="youtube",
            locator="00:00 -> 14:34",
            text=(
                "이번 주차에서는 룰 베이스 러닝과 리니어 리그레션을 보고 "
                "디시전트리도 잠깐 소개하겠습니다."
            ),
            token_count=18,
            fingerprint="chunk-3",
        )

        candidate_ids = _speech_transcript_candidate_section_ids(
            transcript_anchor_counts=_speech_transcript_anchor_counts_by_section(
                chunk=chunk,
                sections=[decision_tree, svm],
            ),
        )

        self.assertEqual(candidate_ids, set())

    def test_speech_transcript_anchor_gate_accepts_decision_tree_chunk(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        chunk = ExtractedChunk(
            id="chunk-4",
            source_id="video-4",
            instructor_name="강사 A",
            source_label="Entropy and Information Gain",
            source_type="youtube",
            locator="00:00 -> 14:41",
            text="decision tree entropy information gain leaf node root node",
            token_count=12,
            fingerprint="chunk-4",
        )

        candidate_ids = _speech_transcript_candidate_section_ids(
            transcript_anchor_counts=_speech_transcript_anchor_counts_by_section(
                chunk=chunk,
                sections=[decision_tree],
            ),
        )

        self.assertEqual(candidate_ids, {"decision-tree"})

    def test_speech_candidate_gate_zeroes_scores_without_anchor_evidence(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        svm = CurriculumSection(
            id="support-vector-machine",
            title="Support Vector Machine",
            description="SVM topic.",
        )

        restricted = _restrict_scored_sections_to_candidates(
            scored=[(decision_tree, 0.3145), (svm, 0.2447)],
            candidate_ids=set(),
        )

        self.assertEqual(restricted, [(decision_tree, 0.0), (svm, 0.0)])

    def test_speech_anchor_counts_respect_token_boundaries(self) -> None:
        counts = _speech_anchor_counts(
            text="슬랙베리어블의 값을 지니고 있다는 겁니다.",
            anchors=["지니"],
        )

        self.assertEqual(counts, {})

    def test_speech_title_exact_match_rescues_svm_chunk_with_single_transcript_anchor(self) -> None:
        decision_tree = CurriculumSection(id="decision-tree", title="결정 트리", description="Decision Trees topic.")
        svm = CurriculumSection(
            id="support-vector-machine",
            title="Support Vector Machine",
            description="SVM topic.",
        )
        chunk = ExtractedChunk(
            id="chunk-5",
            source_id="video-5",
            instructor_name="강사 A",
            source_label="Soft Margin with SVM",
            source_type="youtube",
            locator="00:00 -> 12:27",
            text="소프트 마진 svm 과 슬랙 베리어블을 설명합니다.",
            token_count=10,
            fingerprint="chunk-5",
        )

        rescue_section_id, warning = _resolve_speech_title_rescue(
            chunk=chunk,
            transcript_scored=[
                (decision_tree, 0.2559),
                (svm, 0.19),
            ],
            title_scored=_score_speech_title_sections(
                sections=[decision_tree, svm],
                source_label=chunk.source_label,
            ),
            transcript_anchor_counts=_speech_transcript_anchor_counts_by_section(
                chunk=chunk,
                sections=[decision_tree, svm],
            ),
            min_score=0.23,
            min_margin=0.025,
        )

        self.assertEqual(rescue_section_id, "support-vector-machine")
        self.assertIsNone(warning)

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
        self.assertIn('id="section-donut"', response.text)
        self.assertIn('id="donutLegend"', response.text)
        self.assertIn('data-source-mode-label="material"', response.text)
        self.assertIn('id="donutEmptyState"', response.text)
        self.assertIn("mode_unmapped_series", response.text)
        self.assertIn("mapped_tokens", response.text)
        self.assertIn("average_keywords_by_mode", response.text)
        self.assertIn("강사별 커리큘럼 구성 비중", response.text)
        self.assertIn("전체 주요 수업 키워드", response.text)
        self.assertIn("Final Edu Dashboard", response.text)
        self.assertIn("VOC Analysis", response.text)
        self.assertIn("강사 A", response.text)
        self.assertNotIn("오정훈 강사", response.text)
        self.assertNotIn("name: '미분류'", response.text)


if __name__ == "__main__":
    unittest.main()
