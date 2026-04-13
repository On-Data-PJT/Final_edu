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
    _build_chunks_for_source_segments,
    _build_keyword_payloads_by_mode,
    _build_section_assignment_texts,
    _material_candidate_section_ids,
    _material_anchor_counts_by_section,
    _restrict_scored_sections_to_candidates,
    _resolve_speech_title_rescue,
    _score_speech_title_sections,
    _section_material_anchor_terms,
    _section_speech_anchor_terms,
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
from final_edu.utils import build_preserved_segment_chunks, tokenize_keywords


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


def _sample_chaptered_ml_sections() -> list[CurriculumSection]:
    return [
        CurriculumSection(
            id="chapter-1-motivations-and-basics",
            title="Chapter 1: Motivations and Basics",
            description="확률·통계 기초 · 총 4강",
            target_weight=10,
        ),
        CurriculumSection(
            id="chapter-2-rule-based-decision-tree",
            title="Chapter 2: Rule Based & Decision Tree",
            description="규칙 기반 / 의사결정트리 · 총 5강",
            target_weight=20,
        ),
        CurriculumSection(
            id="chapter-3-optimal-classification-naive-bayes",
            title="Chapter 3: Optimal Classification & Naive Bayes",
            description="나이브 베이즈 · 총 4강",
            target_weight=20,
        ),
        CurriculumSection(
            id="chapter-4-logistic-regression",
            title="Chapter 4: Logistic Regression",
            description="로지스틱 회귀 · 총 8강",
            target_weight=20,
        ),
        CurriculumSection(
            id="chapter-5-support-vector-machine-svm",
            title="Chapter 5: Support Vector Machine SVM",
            description="Support Vector Machine SVM · 총 9강",
            target_weight=15,
        ),
        CurriculumSection(
            id="chapter-6-overfitting-regularization-model-selection",
            title="Chapter 6: Overfitting, Regularization & Model Selection",
            description="모델 선택 / 정규화 · 총 7강",
            target_weight=15,
        ),
    ]


def _sample_biology_sections() -> list[CurriculumSection]:
    return [
        CurriculumSection(id="photosynthesis", title="광합성", description="광합성의 명반응과 암반응", target_weight=25),
        CurriculumSection(id="cell-respiration", title="세포 호흡", description="세포 호흡과 ATP 생성", target_weight=25),
        CurriculumSection(id="genetics", title="유전", description="유전 법칙과 유전자 발현", target_weight=25),
        CurriculumSection(id="evolution", title="진화", description="진화와 자연선택", target_weight=25),
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


def _fake_extract_biology_youtube_asset(url: str, instructor_name: str, settings=None, storage=None):
    source_id = f"{instructor_name}-biology-speech"
    segments = [
        ("00:00", "[음악]"),
        ("15:37", "광합성의 명반응에서 빛에너지가 전자 전달계로 넘어가는 과정을 먼저 정리하겠습니다."),
        ("16:02", "광합성의 암반응과 캘빈 회로에서 포도당이 합성되는 흐름을 이어서 보겠습니다."),
        ("16:31", "광합성은 엽록체와 엽록소의 역할까지 함께 묶어서 복습합니다."),
        ("18:02", "세포 호흡의 해당 과정과 피루브산 생성 단계를 같이 기억해 두세요."),
        ("18:36", "세포 호흡은 미토콘드리아에서 ATP가 합성되는 경로가 핵심입니다."),
        ("19:08", "세포 호흡의 전자 전달계와 산화적 인산화도 시험 포인트로 같이 정리합니다."),
        ("20:11", "유전의 분리 법칙과 우열 관계는 반드시 문제 풀이 순서로 잡아야 합니다."),
        ("20:44", "유전 단원에서는 독립의 법칙과 유전자형 표현형 구분도 같이 연결해서 봅니다."),
        ("21:18", "유전 확률 계산과 가계도 해석까지 한 번에 비교해 보겠습니다."),
        ("22:47", "진화의 자연선택과 적응 과정을 문제에서 자주 묻습니다."),
        ("23:15", "진화 단원에서는 종분화와 공통 조상 개념을 함께 묶어서 암기하세요."),
        ("23:49", "진화의 증거와 생물 다양성 변화까지 연결해서 보겠습니다."),
    ]
    return (
        SourceAsset(
            id=source_id,
            instructor_name=instructor_name,
            asset_type="youtube",
            label="생명과학 라이브 특강",
            origin=url,
        ),
        [
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label="생명과학 라이브 특강",
                source_type="youtube",
                locator=locator,
                text=text,
            )
            for locator, text in segments
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


def _fake_extract_material_partial_coverage_asset(upload: UploadedAsset, instructor_name: str):
    source_id = f"{instructor_name}-partial-material"
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
                text="SQL 데이터 분석 전처리 시각화 pandas SQL 데이터 분석",
            ),
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.2",
                text="이번 페이지는 학생 활동 안내와 수업 운영 메모만 포함합니다.",
            ),
        ],
        [],
    )


def _fake_extract_chaptered_material_drift_asset(upload: UploadedAsset, instructor_name: str):
    source_id = f"{instructor_name}-chaptered-material"
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
                text="2주차 서포트 벡터 머신 Support Vector Machine SVM 최대 마진 초평면 커널",
            ),
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.2",
                text="신경망 모델 역전파 활성화 함수 은닉층 가중치 업데이트",
            ),
            RawTextSegment(
                source_id=source_id,
                instructor_name=instructor_name,
                source_label=upload.original_name,
                source_type="pdf",
                locator="p.3",
                text="정규화 Regularization 과적합 방지 L1 L2 Dropout 모델 선택",
            ),
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

    def test_keyword_tokenizer_filters_low_signal_terms_but_keeps_english_terms(self) -> None:
        tokens = tokenize_keywords("다음 생각 모양 SQL SVM 데이터 2026 강의 자료")

        self.assertIn("sql", tokens)
        self.assertIn("svm", tokens)
        self.assertIn("데이터", tokens)
        self.assertNotIn("다음", tokens)
        self.assertNotIn("생각", tokens)
        self.assertNotIn("모양", tokens)
        self.assertNotIn("2026", tokens)

    def test_keyword_payloads_use_current_run_tfidf_without_needing_history(self) -> None:
        sections = [
            CurriculumSection(
                id="ml",
                title="머신러닝",
                description="sql 신경망 데이터",
                target_weight=100,
            )
        ]
        chunks = [
            ExtractedChunk(
                id="chunk-a-1",
                source_id="material-a",
                instructor_name="강사 A",
                source_label="study-a.pdf",
                source_type="pdf",
                locator="p.1",
                text="다음 생각 데이터 데이터 데이터 sql sql sql",
                token_count=6,
                fingerprint="chunk-a-1",
            ),
            ExtractedChunk(
                id="chunk-a-2",
                source_id="material-a",
                instructor_name="강사 A",
                source_label="study-a.pdf",
                source_type="pdf",
                locator="p.2",
                text="데이터 데이터 데이터 sql sql sql",
                token_count=6,
                fingerprint="chunk-a-2",
            ),
            ExtractedChunk(
                id="chunk-b-1",
                source_id="material-b",
                instructor_name="강사 B",
                source_label="study-b.pdf",
                source_type="pdf",
                locator="p.1",
                text="데이터 데이터 데이터 신경망 신경망 신경망",
                token_count=6,
                fingerprint="chunk-b-1",
            ),
        ]

        keywords_by_mode, _off_curriculum, average_keywords_by_mode = _build_keyword_payloads_by_mode(
            chunks,
            sections,
        )

        combined_a_keywords = [item["text"] for item in keywords_by_mode["combined"]["강사 A"][:3]]
        combined_b_keywords = [item["text"] for item in keywords_by_mode["combined"]["강사 B"][:3]]

        self.assertEqual(combined_a_keywords[0], "sql")
        self.assertEqual(combined_b_keywords[0], "신경망")
        self.assertNotIn("다음", combined_a_keywords)
        self.assertNotIn("생각", combined_a_keywords)
        self.assertEqual(
            [item["text"] for item in average_keywords_by_mode["combined"][:3]],
            ["데이터", "sql", "신경망"],
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

    def test_material_mode_uses_mapped_only_denominator_in_streaming_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            material_path = Path(temp_dir) / "partial-study.pdf"
            material_path.write_text("placeholder", encoding="utf-8")
            submissions = [
                InstructorSubmission(
                    name="강사 A",
                    files=[UploadedAsset(path=material_path, original_name="partial-study.pdf")],
                )
            ]
            settings = replace(
                get_settings(),
                openai_api_key=None,
                chunk_target_tokens=64,
                chunk_overlap_segments=0,
                max_evidence_per_section=1,
            )

            with patch(
                "final_edu.analysis.extract_file_asset",
                side_effect=_fake_extract_material_partial_coverage_asset,
            ):
                result = analyze_submissions(
                    course_id="course-1",
                    course_name="AI 데이터 과정",
                    sections=_sample_sections(),
                    submissions=submissions,
                    settings=settings,
                    analysis_mode="lexical",
                ).to_dict()

        material_stat = result["source_mode_stats"]["material"]
        self.assertGreater(material_stat["total_tokens"], material_stat["mapped_tokens"])
        material_rose = result["rose_series_by_mode"]["material"]["강사 A"]
        self.assertAlmostEqual(sum(item["value"] for item in material_rose), 100.0, places=2)

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

    def test_generic_material_anchor_terms_include_title_and_description_fragments(self) -> None:
        chapter_two, chapter_three, *_rest = _sample_chaptered_ml_sections()[1:]
        chapter_six = _sample_chaptered_ml_sections()[5]

        chapter_two_anchors = _section_material_anchor_terms(chapter_two)
        chapter_three_anchors = _section_material_anchor_terms(chapter_three)
        chapter_six_anchors = _section_material_anchor_terms(chapter_six)

        self.assertIn("rule based", chapter_two_anchors)
        self.assertIn("decision tree", chapter_two_anchors)
        self.assertIn("규칙 기반", chapter_two_anchors)
        self.assertIn("의사결정트리", chapter_two_anchors)
        self.assertIn("naive bayes", chapter_three_anchors)
        self.assertIn("나이브 베이즈", chapter_three_anchors)
        self.assertIn("정규화", chapter_six_anchors)
        self.assertIn("모델 선택", chapter_six_anchors)

    def test_material_candidate_gate_keeps_neural_network_chunk_unmapped_for_chaptered_course(self) -> None:
        sections = _sample_chaptered_ml_sections()
        chunk = ExtractedChunk(
            id="chunk-material-1",
            source_id="material-1",
            instructor_name="강사 A",
            source_label="study.pdf",
            source_type="pdf",
            locator="p.6 (2/5)",
            text="인공 뉴런 다층 뉴럴 네트워크 손실 함수 역전파 활성화 함수",
            token_count=20,
            fingerprint="chunk-material-1",
        )

        candidate_ids = _material_candidate_section_ids(
            material_anchor_counts=_material_anchor_counts_by_section(
                chunk=chunk,
                sections=sections,
            )
        )

        self.assertEqual(candidate_ids, set())

    def test_chaptered_material_analysis_does_not_collapse_into_single_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            material_path = Path(temp_dir) / "chaptered-study.pdf"
            material_path.write_text("placeholder", encoding="utf-8")
            submissions = [
                InstructorSubmission(
                    name="점매",
                    files=[UploadedAsset(path=material_path, original_name="chaptered-study.pdf")],
                )
            ]
            settings = replace(
                get_settings(),
                openai_api_key=None,
                chunk_target_tokens=64,
                chunk_overlap_segments=0,
                max_evidence_per_section=1,
            )

            with patch(
                "final_edu.analysis.extract_file_asset",
                side_effect=_fake_extract_chaptered_material_drift_asset,
            ):
                result = analyze_submissions(
                    course_id="course-1",
                    course_name="AI chapter 과정",
                    sections=_sample_chaptered_ml_sections(),
                    submissions=submissions,
                    settings=settings,
                    analysis_mode="lexical",
                ).to_dict()

        material_stat = result["source_mode_stats"]["material"]
        self.assertGreater(material_stat["total_tokens"], material_stat["mapped_tokens"])
        material_rose = {
            item["section_id"]: item["value"]
            for item in result["rose_series_by_mode"]["material"]["점매"]
        }
        self.assertGreater(material_rose["chapter-5-support-vector-machine-svm"], 0.0)
        self.assertGreater(material_rose["chapter-6-overfitting-regularization-model-selection"], 0.0)
        self.assertLess(material_rose["chapter-6-overfitting-regularization-model-selection"], 100.0)
        self.assertAlmostEqual(sum(material_rose.values()), 100.0, places=2)

    def test_generic_speech_anchor_terms_include_title_and_description_fragments(self) -> None:
        chapter_two = _sample_chaptered_ml_sections()[1]

        anchors = _section_speech_anchor_terms(chapter_two)

        self.assertIn("rule based", anchors)
        self.assertIn("decision tree", anchors)
        self.assertIn("decision trees", anchors)
        self.assertIn("규칙 기반", anchors)
        self.assertIn("의사결정트리", anchors)

    def test_generic_speech_title_scoring_matches_chaptered_playlist_titles(self) -> None:
        sections = _sample_chaptered_ml_sections()
        expected_matches = {
            "인공지능 및 기계학습 개론1 [2-3] Introduction to Decision Trees": "chapter-2-rule-based-decision-tree",
            "인공지능 및 기계학습 개론1 [3-3] Naive Bayes Classifier": "chapter-3-optimal-classification-naive-bayes",
            "인공지능 및 기계학습 개론1 [4-2] Introduction to Logistic Regression": "chapter-4-logistic-regression",
            "인공지능 및 기계학습 개론1 [6-2] Regularization": "chapter-6-overfitting-regularization-model-selection",
        }

        for source_label, expected_section_id in expected_matches.items():
            with self.subTest(source_label=source_label):
                title_scored = _score_speech_title_sections(
                    sections=sections,
                    source_label=source_label,
                )

                self.assertTrue(title_scored)
                self.assertEqual(
                    sorted(title_scored, key=lambda item: item[1], reverse=True)[0][0].id,
                    expected_section_id,
                )

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
            title_scored=_score_speech_title_sections(
                sections=[decision_tree, regression],
                source_label=chunk.source_label,
            ),
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
            sections=[decision_tree, svm],
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
            sections=[decision_tree],
        )

        self.assertEqual(candidate_ids, {"decision-tree"})

    def test_speech_candidate_gate_accepts_single_exact_title_hit(self) -> None:
        photosynthesis = CurriculumSection(id="photosynthesis", title="광합성", description="광합성의 단계")
        respiration = CurriculumSection(id="cell-respiration", title="세포 호흡", description="세포 호흡의 단계")
        chunk = ExtractedChunk(
            id="chunk-bio-1",
            source_id="video-bio-1",
            instructor_name="강사 A",
            source_label="생명과학 라이브",
            source_type="youtube",
            locator="15:37",
            text="광합성의 명반응과 엽록체 역할을 먼저 정리하겠습니다.",
            token_count=12,
            fingerprint="chunk-bio-1",
        )

        candidate_ids = _speech_transcript_candidate_section_ids(
            transcript_anchor_counts=_speech_transcript_anchor_counts_by_section(
                chunk=chunk,
                sections=[photosynthesis, respiration],
            ),
            sections=[photosynthesis, respiration],
        )

        self.assertEqual(candidate_ids, {"photosynthesis"})

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

    def test_speech_chunk_builder_drops_music_cues_and_uses_smaller_budget(self) -> None:
        segments = [
            RawTextSegment(
                source_id="youtube-1",
                instructor_name="강사 A",
                source_label="생명과학 라이브",
                source_type="youtube",
                locator=f"{index:02d}:00",
                text="[음악]" if index % 9 == 0 else "광합성 세포 호흡 유전 진화 흐름을 계속 정리합니다.",
            )
            for index in range(80)
        ]
        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=550,
            chunk_overlap_segments=1,
        )

        chunks = _build_chunks_for_source_segments(segments, settings)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(all("[음악]" not in chunk.text for chunk in chunks))

    def test_biology_speech_analysis_maps_multiple_sections(self) -> None:
        submissions = [
            InstructorSubmission(
                name="생명 강사",
                youtube_urls=["https://www.youtube.com/watch?v=tf97j0aG7YE"],
            )
        ]
        settings = replace(
            get_settings(),
            openai_api_key=None,
            chunk_target_tokens=550,
            chunk_overlap_segments=1,
            max_evidence_per_section=1,
        )

        with patch(
            "final_edu.analysis.extract_youtube_asset",
            side_effect=_fake_extract_biology_youtube_asset,
        ):
            result = analyze_submissions(
                course_id="biology-course-1",
                course_name="생명과학 특강",
                sections=_sample_biology_sections(),
                submissions=submissions,
                settings=settings,
                analysis_mode="lexical",
            ).to_dict()

        speech_rose = {
            item["section_id"]: item["value"]
            for item in result["rose_series_by_mode"]["speech"]["생명 강사"]
        }
        self.assertGreater(speech_rose["photosynthesis"], 0.0)
        self.assertGreater(speech_rose["cell-respiration"], 0.0)
        self.assertGreater(speech_rose["genetics"], 0.0)
        self.assertGreater(speech_rose["evolution"], 0.0)

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
        self.assertIn('id="comparisonLegend"', response.text)
        self.assertIn('id="coverageNote"', response.text)
        self.assertIn('data-source-mode-label="material"', response.text)
        self.assertIn('id="donutEmptyState"', response.text)
        self.assertIn("mode_unmapped_series", response.text)
        self.assertIn("mapped_tokens", response.text)
        self.assertIn("average_keywords_by_mode", response.text)
        self.assertIn("강사별 커리큘럼 구성 비중", response.text)
        self.assertIn("직접 연결된", response.text)
        self.assertIn("전체 주요 수업 키워드", response.text)
        self.assertIn("Study Labs Dashboard", response.text)
        self.assertIn("VOC Analysis", response.text)
        self.assertIn("강사 A", response.text)
        self.assertNotIn("오정훈 강사", response.text)
        self.assertNotIn("name: '미분류'", response.text)


if __name__ == "__main__":
    unittest.main()
