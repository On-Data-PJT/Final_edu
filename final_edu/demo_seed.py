from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from final_edu.jobs import create_job_services
from final_edu.models import (
    AnalysisJobPayload,
    AnalysisJobRecord,
    CourseRecord,
    CurriculumSection,
    JobInstructorInput,
    StoredUploadRef,
)
from final_edu.solution_content import build_solution_payload, fallback_solution_content

DEMO_COURSE_ID = "demo-ai-bootcamp-course"
DEMO_JOB_ID = "job-demo-judge-ready"
DEMO_COURSE_NAME = "2026 AI 데이터 분석 실무 집중과정"
DEMO_HINT_TEXT = "준비된 샘플로 결과 보기(데모)"
DEMO_TIMESTAMP = "2026-04-13T09:00:00+09:00"
DEMO_INSTRUCTOR_NAMES = ["오강사", "이강사", "박강사"]
DEMO_CURRICULUM_KEY = f"courses/{DEMO_COURSE_ID}/curriculum/demo-ai-curriculum.pdf"


@dataclass(frozen=True, slots=True)
class DemoSeedBundle:
    course: CourseRecord
    payload: AnalysisJobPayload
    job: AnalysisJobRecord
    result: dict
    file_objects: dict[str, tuple[bytes, str]]


def is_demo_seeded_course(course_id: str) -> bool:
    return str(course_id or "").strip() == DEMO_COURSE_ID


def demo_course_url(job_id: str = DEMO_JOB_ID) -> str:
    return f"/jobs/{job_id}"


def build_demo_seed_bundle() -> DemoSeedBundle:
    sections = _demo_sections()
    payload = AnalysisJobPayload(
        job_id=DEMO_JOB_ID,
        course_id=DEMO_COURSE_ID,
        course_name=DEMO_COURSE_NAME,
        course_sections=sections,
        curriculum_text=_sections_to_curriculum_text(sections),
        submitted_at=DEMO_TIMESTAMP,
        analysis_mode="demo-seeded",
        page1_submission_version=2,
        instructors=[
            JobInstructorInput(
                name=name,
                mode="files",
                files=[
                    StoredUploadRef(
                        storage_key=f"jobs/{DEMO_JOB_ID}/uploads/instructor-{index}/files/demo-study-material.pdf",
                        original_name=f"{name}_강의자료.pdf",
                    )
                ],
                youtube_inputs=[f"https://www.youtube.com/watch?v=demo-{index:02d}abc"],
                youtube_urls=[f"https://www.youtube.com/watch?v=demo-{index:02d}abc"],
                voc_files=[
                    StoredUploadRef(
                        storage_key=f"jobs/{DEMO_JOB_ID}/uploads/instructor-{index}/voc/demo-review.csv",
                        original_name=f"{name}_VOC.csv",
                    )
                ],
            )
            for index, name in enumerate(DEMO_INSTRUCTOR_NAMES, start=1)
        ],
    )
    result = _build_demo_result(sections)
    timestamp = _timestamp_from_iso(DEMO_TIMESTAMP)
    job = AnalysisJobRecord(
        id=DEMO_JOB_ID,
        course_id=DEMO_COURSE_ID,
        course_name=DEMO_COURSE_NAME,
        status="completed",
        created_at=DEMO_TIMESTAMP,
        updated_at=DEMO_TIMESTAMP,
        created_at_ts=timestamp,
        updated_at_ts=timestamp,
        payload_key=f"jobs/{DEMO_JOB_ID}/payload.json",
        result_key=f"jobs/{DEMO_JOB_ID}/result.json",
        scorer_mode="demo-seeded",
        duration_ms=1840,
        instructor_names=list(DEMO_INSTRUCTOR_NAMES),
        instructor_count=len(DEMO_INSTRUCTOR_NAMES),
        asset_count=len(DEMO_INSTRUCTOR_NAMES) * 2,
        youtube_url_count=len(DEMO_INSTRUCTOR_NAMES),
        section_count=len(sections),
        warning_count=0,
        selected_analysis_mode="demo-seeded",
        estimated_cost_usd=0.0,
    )
    course = CourseRecord(
        id=DEMO_COURSE_ID,
        name=DEMO_COURSE_NAME,
        curriculum_pdf_key=DEMO_CURRICULUM_KEY,
        sections=sections,
        instructor_names=list(DEMO_INSTRUCTOR_NAMES),
        raw_curriculum_text=_sections_to_curriculum_text(sections),
        created_at=DEMO_TIMESTAMP,
        updated_at=DEMO_TIMESTAMP,
    )
    return DemoSeedBundle(
        course=course,
        payload=payload,
        job=job,
        result=result,
        file_objects=_build_demo_file_objects(),
    )


def ensure_demo_seeded(settings, course_repository) -> DemoSeedBundle:  # noqa: ANN001
    bundle = build_demo_seed_bundle()
    job_services = create_job_services(settings)
    course_repository.save(bundle.course)
    _put_bytes(job_services.storage, bundle.course.curriculum_pdf_key, bundle.file_objects[bundle.course.curriculum_pdf_key])
    for key, file_object in bundle.file_objects.items():
        if key == bundle.course.curriculum_pdf_key:
            continue
        _put_bytes(job_services.storage, key, file_object)
    job_services.storage.put_json(bundle.job.payload_key, bundle.payload.to_dict())
    job_services.storage.put_json(bundle.job.result_key or f"jobs/{bundle.job.id}/result.json", bundle.result)
    job_services.repository.save(bundle.job)
    return bundle


def _demo_sections() -> list[CurriculumSection]:
    return [
        CurriculumSection(
            id="python-core",
            title="Python 핵심 문법",
            description="데이터 타입, 조건문, 반복문, 함수 작성",
            target_weight=20.0,
        ),
        CurriculumSection(
            id="data-analysis",
            title="데이터 분석",
            description="Pandas 기반 전처리와 EDA 리포트 작성",
            target_weight=16.0,
        ),
        CurriculumSection(
            id="ml-basics",
            title="머신러닝 기초",
            description="지도학습, 회귀/분류, 검증 지표 이해",
            target_weight=24.0,
        ),
        CurriculumSection(
            id="deep-learning",
            title="딥러닝 응용",
            description="신경망, 실습 모델링, 프로젝트 적용",
            target_weight=16.0,
        ),
        CurriculumSection(
            id="nlp-practice",
            title="자연어 처리 실습",
            description="텍스트 전처리, 임베딩, 간단한 분류 실습",
            target_weight=14.0,
        ),
        CurriculumSection(
            id="deployment",
            title="모델 배포와 운영",
            description="FastAPI, Docker, 배포 후 운영 체크포인트",
            target_weight=10.0,
        ),
    ]


def _build_demo_result(sections: list[CurriculumSection]) -> dict:
    material_shares = {
        "오강사": [26.0, 36.0, 14.0, 8.0, 5.0, 11.0],
        "이강사": [10.0, 12.0, 40.0, 18.0, 4.0, 16.0],
        "박강사": [8.0, 12.0, 14.0, 46.0, 7.0, 13.0],
    }
    speech_shares = {
        "오강사": [17.1, 22.7, 18.4, 16.9, 11.7, 13.2],
        "이강사": [5.6, 18.7, 26.7, 22.4, 6.2, 20.4],
        "박강사": [10.2, 18.7, 18.4, 32.7, 9.2, 10.8],
    }
    combined_unmapped = {
        "오강사": 18.4,
        "이강사": 11.2,
        "박강사": 23.6,
    }
    material_unmapped = {
        "오강사": 15.2,
        "이강사": 9.3,
        "박강사": 19.4,
    }
    speech_unmapped = {
        "오강사": 22.1,
        "이강사": 13.8,
        "박강사": 27.4,
    }
    unmapped_topics = {
        "오강사": ["LangChain", "데이터 스토리텔링", "대시보드 자동화"],
        "이강사": ["클라우드 비용 최적화", "모델 정책 운영"],
        "박강사": ["MLOps", "벡터 데이터베이스", "RAG 서빙"],
    }
    combined_shares = {
        name: _normalize_percentages(
            [
                material_shares[name][index] * 0.55 + speech_shares[name][index] * 0.45
                for index in range(len(sections))
            ]
        )
        for name in DEMO_INSTRUCTOR_NAMES
    }
    keywords_by_mode = {
        "combined": {
            "오강사": _keyword_list(
                ("python", 24),
                ("pandas", 20),
                ("sql", 18),
                ("전처리", 17),
                ("시각화", 16),
                ("seaborn", 15),
                ("notebook", 13),
                ("eda", 12),
                ("데이터클리닝", 11),
                ("feature store", 10),
                ("대시보드", 10),
                ("리포트", 9),
                ("결측치", 9),
                ("실습", 8),
                ("프로젝트", 8),
                ("automation", 7),
            ),
            "이강사": _keyword_list(
                ("회귀", 22),
                ("분류", 21),
                ("검증", 19),
                ("교차검증", 18),
                ("confusion matrix", 16),
                ("roc-auc", 15),
                ("feature engineering", 14),
                ("기준선", 13),
                ("재현성", 12),
                ("오차분석", 12),
                ("하이퍼파라미터", 11),
                ("ensemble", 10),
                ("calibration", 10),
                ("지표", 9),
                ("threshold", 9),
                ("fastapi", 8),
            ),
            "박강사": _keyword_list(
                ("딥러닝", 25),
                ("cnn", 21),
                ("임베딩", 20),
                ("transformer", 18),
                ("attention", 17),
                ("docker", 16),
                ("배포", 15),
                ("서빙", 14),
                ("모니터링", 13),
                ("mlops", 12),
                ("inference", 11),
                ("latency", 10),
                ("vector db", 9),
                ("rag", 9),
                ("api gateway", 8),
                ("tracing", 8),
            ),
        },
        "material": {
            "오강사": _keyword_list(
                ("python", 25),
                ("pandas", 21),
                ("sql", 19),
                ("전처리", 18),
                ("데이터프레임", 16),
                ("시각화", 15),
                ("seaborn", 13),
                ("notebook", 12),
                ("변수", 11),
                ("리포트", 10),
                ("결측치", 10),
                ("정규화", 9),
                ("eda", 9),
                ("feature store", 8),
                ("실습", 8),
                ("dashboard", 7),
            ),
            "이강사": _keyword_list(
                ("회귀", 23),
                ("분류", 21),
                ("검증", 19),
                ("지표", 17),
                ("confusion matrix", 16),
                ("roc-auc", 15),
                ("feature engineering", 14),
                ("모델선정", 13),
                ("baseline", 12),
                ("grid search", 11),
                ("calibration", 10),
                ("precision", 10),
                ("recall", 9),
                ("하이퍼파라미터", 9),
                ("ensemble", 8),
                ("threshold", 8),
            ),
            "박강사": _keyword_list(
                ("딥러닝", 24),
                ("cnn", 20),
                ("임베딩", 18),
                ("transformer", 17),
                ("attention", 15),
                ("docker", 14),
                ("배포", 13),
                ("서빙", 12),
                ("mlops", 11),
                ("monitoring", 11),
                ("inference", 10),
                ("vector db", 9),
                ("rag", 9),
                ("api", 8),
                ("tracing", 8),
                ("latency", 7),
            ),
        },
        "speech": {
            "오강사": _keyword_list(
                ("실습", 18),
                ("질문응답", 16),
                ("예제풀이", 15),
                ("파이썬", 14),
                ("판다스", 13),
                ("시각화", 12),
                ("프로젝트", 12),
                ("notebook", 11),
                ("데이터정리", 10),
                ("workflow", 9),
                ("자동화", 9),
                ("대시보드", 8),
                ("복습", 8),
                ("실전", 7),
                ("리포트", 7),
                ("질의", 6),
            ),
            "이강사": _keyword_list(
                ("검증", 18),
                ("기준선", 16),
                ("오차분석", 15),
                ("confusion matrix", 14),
                ("roc-auc", 13),
                ("feature engineering", 13),
                ("fastapi", 11),
                ("실전", 11),
                ("재현성", 10),
                ("threshold", 10),
                ("calibration", 9),
                ("ensemble", 9),
                ("하이퍼파라미터", 8),
                ("모델비교", 8),
                ("precision", 7),
                ("recall", 7),
            ),
            "박강사": _keyword_list(
                ("임베딩", 19),
                ("추론속도", 17),
                ("배포", 16),
                ("운영", 15),
                ("모니터링", 14),
                ("docker", 13),
                ("transformer", 12),
                ("서빙", 12),
                ("api", 11),
                ("latency", 10),
                ("tracing", 9),
                ("rag", 9),
                ("vector db", 8),
                ("observability", 8),
                ("rollout", 7),
                ("incident", 7),
            ),
        },
    }
    average_keywords_by_mode = {
        mode: _average_keyword_list(keyword_map)
        for mode, keyword_map in keywords_by_mode.items()
    }
    result = {
        "course_id": DEMO_COURSE_ID,
        "course_name": DEMO_COURSE_NAME,
        "course": {
            "id": DEMO_COURSE_ID,
            "name": DEMO_COURSE_NAME,
            "instructor_names": list(DEMO_INSTRUCTOR_NAMES),
            "section_count": len(sections),
        },
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "description": section.description,
                "target_weight": section.target_weight,
            }
            for section in sections
        ],
        "instructors": [],
        "warnings": [],
        "scorer_mode": "demo-seeded",
        "duration_ms": 1840,
        "available_source_modes": ["combined", "material", "speech"],
        "source_mode_stats": {
            "combined": {"asset_count": 6, "total_tokens": 9200, "mapped_tokens": 6830},
            "material": {"asset_count": 3, "total_tokens": 4100, "mapped_tokens": 3320},
            "speech": {"asset_count": 3, "total_tokens": 5100, "mapped_tokens": 3510},
        },
        "mode_unmapped_series": {
            "combined": {
                "average": round(sum(combined_unmapped.values()) / len(combined_unmapped), 1),
                "instructors": dict(combined_unmapped),
            },
            "material": {
                "average": round(sum(material_unmapped.values()) / len(material_unmapped), 1),
                "instructors": dict(material_unmapped),
            },
            "speech": {
                "average": round(sum(speech_unmapped.values()) / len(speech_unmapped), 1),
                "instructors": dict(speech_unmapped),
            },
        },
        "mode_series": {},
        "average_series_by_mode": {},
        "keywords_by_instructor": keywords_by_mode["combined"],
        "keywords_by_mode": keywords_by_mode,
        "average_keywords_by_mode": average_keywords_by_mode,
        "rose_series_by_instructor": {},
        "rose_series_by_mode": {},
        "line_series_by_mode": {},
        "insights": [
            {
                "title": "강사별 커리큘럼 해석 차이가 뚜렷함",
                "category": "편차",
                "issue": "오강사는 데이터 분석, 이강사는 머신러닝 기초, 박강사는 딥러닝 응용에 강하게 쏠려 있습니다.",
                "evidence": "강사별 combined 최고 비중 섹션이 각각 30.0%, 33.9%, 39.9%로 분산됩니다.",
                "recommendation": "표준안 기준 필수 비중 구간을 먼저 고정하고, 강사별 특화 파트는 후반 심화 영역으로 분리하는 편이 안정적입니다.",
                "icon": "spark",
            },
            {
                "title": "NLP 실습은 목표 대비 일관되게 얇음",
                "category": "보완",
                "issue": "세 강사 모두 자연어 처리 실습을 최소 비중으로만 다뤄 목표 대비 체감 존재감이 낮습니다.",
                "evidence": "combined 평균은 7.0%로 목표 14.0%보다 7.0%p 낮습니다.",
                "recommendation": "임베딩-분류-응용 예제를 묶은 짧은 실습 블록을 별도 확보해 목표 비중에 가깝게 회복하는 편이 좋습니다.",
                "icon": "alert",
            },
        ],
        "voc_summary": _demo_voc_summary(),
        "insight_generation_mode": "demo-seeded",
        "selected_instructor": DEMO_INSTRUCTOR_NAMES[0],
    }
    result["instructors"] = [
        {
            "name": name,
            "total_tokens": 2000 + index * 180,
            "asset_count": 2,
            "voc_file_count": 1,
            "section_coverages": _section_coverages(sections, combined_shares[name], 1800 + index * 120),
            "unmapped_tokens": int(round((1800 + index * 120) * (combined_unmapped[name] / 100))),
            "unmapped_share": round(combined_unmapped[name] / 100, 4),
            "warnings": [],
            "voc_analysis": _demo_voc_analysis(name, index),
        }
        for index, name in enumerate(DEMO_INSTRUCTOR_NAMES, start=1)
    ]
    for mode, shares_by_instructor in {
        "combined": combined_shares,
        "material": material_shares,
        "speech": speech_shares,
    }.items():
        result["mode_series"][mode] = {
            "average": _average_series(sections, shares_by_instructor),
            "instructors": {
                name: _mode_series_entries(sections, shares)
                for name, shares in shares_by_instructor.items()
            },
        }
        result["average_series_by_mode"][mode] = result["mode_series"][mode]["average"]
        result["rose_series_by_mode"][mode] = {
            name: _rose_entries(sections, shares)
            for name, shares in shares_by_instructor.items()
        }
        result["line_series_by_mode"][mode] = {
            "target": [{"section_id": section.id, "share": round(section.target_weight / 100, 6)} for section in sections],
            "instructors": {
                name: [{"section_id": section.id, "share": round(share / 100, 6)} for section, share in zip(sections, shares, strict=True)]
                for name, shares in shares_by_instructor.items()
            },
    }
    result["rose_series_by_instructor"] = result["rose_series_by_mode"]["combined"]
    solution_payload = build_solution_payload(result)
    result["solution_content"] = fallback_solution_content(solution_payload)
    result["solution_generation_mode"] = "demo-seeded"
    result["solution_generation_warning"] = None
    result["external_trends_status"] = "reflected"
    return result


def _build_demo_file_objects() -> dict[str, tuple[bytes, str]]:
    file_objects: dict[str, tuple[bytes, str]] = {
        DEMO_CURRICULUM_KEY: (
            _pseudo_pdf_bytes(
                DEMO_COURSE_NAME,
                [
                    "Python 핵심 문법",
                    "데이터 분석",
                    "머신러닝 기초",
                    "딥러닝 응용",
                    "자연어 처리 실습",
                    "모델 배포와 운영",
                ],
            ),
            "application/pdf",
        )
    }
    for index, name in enumerate(DEMO_INSTRUCTOR_NAMES, start=1):
        material_key = f"jobs/{DEMO_JOB_ID}/uploads/instructor-{index}/files/demo-study-material.pdf"
        voc_key = f"jobs/{DEMO_JOB_ID}/uploads/instructor-{index}/voc/demo-review.csv"
        file_objects[material_key] = (
            _pseudo_pdf_bytes(
                f"{name} 강의자료",
                [
                    f"{name} 강의자료",
                    "Python 핵심 문법 복습",
                    "데이터 분석 실습",
                    "머신러닝/딥러닝 프로젝트",
                ],
            ),
            "application/pdf",
        )
        file_objects[voc_key] = (
            (
                "week,comment\n"
                f"1주차,{name} 강사님의 설명이 명확했어요\n"
                f"2주차,{name} 강사님의 실습 예제가 좋았습니다\n"
                f"3주차,{name} 강사님의 강의 속도는 약간 빨랐어요\n"
            ).encode("utf-8"),
            "text/csv; charset=utf-8",
        )
    return file_objects


def _put_bytes(storage, key: str, file_object: tuple[bytes, str]) -> None:  # noqa: ANN001
    payload, content_type = file_object
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "seeded-demo-asset"
        temp_path.write_bytes(payload)
        storage.put_file(key, temp_path, content_type=content_type)


def _mode_series_entries(sections: list[CurriculumSection], shares: list[float]) -> list[dict]:
    return [
        {
            "section_id": section.id,
            "section_title": section.title,
            "share": round(share / 100, 6),
        }
        for section, share in zip(sections, shares, strict=True)
    ]


def _rose_entries(sections: list[CurriculumSection], shares: list[float]) -> list[dict]:
    return [
        {
            "section_id": section.id,
            "section_title": section.title,
            "name": section.title,
            "value": round(share, 1),
        }
        for section, share in zip(sections, shares, strict=True)
    ]


def _average_series(sections: list[CurriculumSection], shares_by_instructor: dict[str, list[float]]) -> list[dict]:
    averages = []
    instructor_values = list(shares_by_instructor.values())
    for section_index, section in enumerate(sections):
        average = sum(values[section_index] for values in instructor_values) / len(instructor_values)
        averages.append(
            {
                "section_id": section.id,
                "section_title": section.title,
                "share": round(average / 100, 6),
            }
        )
    return averages


def _section_coverages(
    sections: list[CurriculumSection],
    shares: list[float],
    token_budget: int,
) -> list[dict]:
    coverages: list[dict] = []
    for section, share in zip(sections, shares, strict=True):
        token_count = max(1, int(round(token_budget * (share / 100))))
        coverages.append(
            {
                "section_id": section.id,
                "section_title": section.title,
                "token_count": token_count,
                "token_share": round(share / 100, 6),
                "deviation_from_average": 0.0,
                "evidence_snippets": [
                    {
                        "source_label": f"{section.title} 실습 자료",
                        "locator": "핵심 예제",
                        "text": f"{section.title} 단원의 핵심 개념과 실습 예제를 실제 프로젝트 맥락으로 설명합니다.",
                        "score": round(0.82 + (share / 1000), 3),
                    }
                ],
            }
        )
    return coverages


def _demo_voc_analysis(name: str, index: int) -> dict:
    profiles = {
        "오강사": {
            "scores": (4.6, 4.8, 4.7),
            "positive": ["설명이 친절함", "실습 예제가 풍부함", "질문 응답이 세심함"],
            "negative": ["강의 속도가 조금 빠름", "중간 점검 문제가 더 필요함"],
            "repeated_complaints": [
                {"pattern": "실습 속도 조절 요청", "count": 4, "week": "3주차"},
                {"pattern": "중간 체크포인트 부족", "count": 3, "week": "4주차"},
            ],
            "next_suggestions": [
                {
                    "priority": "high",
                    "label": "실습 체크포인트 추가",
                    "body": "핵심 실습 파트마다 중간 확인 문제와 예상 출력 예시를 함께 넣어 이해도를 점검하세요.",
                },
                {
                    "priority": "medium",
                    "label": "속도 조절용 복습 슬라이드 보강",
                    "body": "주차 말미에 빠르게 정리할 수 있는 한 장짜리 복습 슬라이드를 추가해 속도 부담을 줄여 보세요.",
                },
            ],
        },
        "이강사": {
            "scores": (4.4, 4.6, 4.3),
            "positive": ["지표 해석이 쉬움", "모델 비교가 체계적임", "검증 흐름이 명확함"],
            "negative": ["전처리 연결 설명이 짧음", "실습 전환이 조금 빠름"],
            "repeated_complaints": [
                {"pattern": "전처리에서 모델링으로 넘어가는 연결 보강 요청", "count": 5, "week": "2주차"},
                {"pattern": "지표 선택 기준 복습 요청", "count": 4, "week": "5주차"},
            ],
            "next_suggestions": [
                {
                    "priority": "high",
                    "label": "전처리-모델링 연결 브리지 슬라이드 추가",
                    "body": "EDA 결과가 어떤 기준으로 feature engineering과 모델 선택으로 이어지는지 한 흐름으로 다시 묶어 주세요.",
                },
                {
                    "priority": "medium",
                    "label": "검증 지표 선택 가이드 배포",
                    "body": "회귀와 분류에서 어떤 지표를 우선 써야 하는지 한눈에 볼 수 있는 가이드를 함께 제공하세요.",
                },
            ],
        },
        "박강사": {
            "scores": (4.3, 4.4, 4.5),
            "positive": ["심화 개념 설명이 밀도 높음", "배포 시나리오가 인상적임", "최신 사례가 풍부함"],
            "negative": ["배포 단원 난이도가 높음", "운영 장애 예시가 더 필요함"],
            "repeated_complaints": [
                {"pattern": "딥러닝 심화 파트 속도 조절 요청", "count": 6, "week": "4주차"},
                {"pattern": "배포 운영 사례 보강 요청", "count": 4, "week": "6주차"},
            ],
            "next_suggestions": [
                {
                    "priority": "high",
                    "label": "배포 운영 장애 사례 카드 추가",
                    "body": "모델 서빙 이후 발생할 수 있는 오류 패턴과 모니터링 포인트를 짧은 사례 카드로 정리해 보세요.",
                },
                {
                    "priority": "medium",
                    "label": "딥러닝 심화 예제 난이도 이중화",
                    "body": "기본 예제와 심화 예제를 분리해 초반 이탈 없이 심화 파트까지 따라오게 만드는 구성이 필요합니다.",
                },
            ],
        },
    }
    profile = profiles.get(name, profiles["오강사"])
    bq1, bq2, bq3 = profile["scores"]
    return {
        "file_name": f"{name}_VOC.csv",
        "analyzed_at": "2026-04-12",
        "response_count": 18 + index * 3,
        "question_scores": [
            {
                "group": "강의 운영",
                "question_id": "BQ1",
                "label": "교육 신청 및 안내 절차가 수월하였다",
                "average": bq1,
                "response_count": 18 + index * 3,
                "scale_max": 5,
            },
            {
                "group": "강사 설명",
                "question_id": "BQ2",
                "label": "강사의 설명이 이해하기 쉬웠다",
                "average": bq2,
                "response_count": 18 + index * 3,
                "scale_max": 5,
            },
            {
                "group": "실습 구성",
                "question_id": "BQ3",
                "label": "실습 예제가 이해에 도움이 되었다",
                "average": bq3,
                "response_count": 18 + index * 3,
                "scale_max": 5,
            },
        ],
        "sentiment": {
            "positive": list(profile["positive"]),
            "negative": list(profile["negative"]),
        },
        "repeated_complaints": list(profile["repeated_complaints"]),
        "next_suggestions": list(profile["next_suggestions"]),
    }


def _demo_voc_summary() -> dict:
    return {
        "question_scores": [
            {
                "group": "강의 운영",
                "question_id": "BQ1",
                "label": "교육 신청 및 안내 절차가 수월하였다",
                "average": 4.4,
                "response_count": 66,
                "scale_max": 5,
            },
            {
                "group": "강의 운영",
                "question_id": "BQ2",
                "label": "강사의 설명이 이해하기 쉬웠다",
                "average": 4.5,
                "response_count": 66,
                "scale_max": 5,
            },
            {
                "group": "실습 구성",
                "question_id": "BQ3",
                "label": "실습 예제가 이해에 도움이 되었다",
                "average": 4.4,
                "response_count": 66,
                "scale_max": 5,
            },
        ],
        "positive": ["실습 중심 커리큘럼", "설명이 친절함", "프로젝트 예제가 좋음", "모델 비교가 체계적임"],
        "negative": ["강의 속도 조절 필요", "배포 단원 사례 추가 필요", "검증 지표 복습 자료 요청"],
        "repeated_complaints": [
            {
                "pattern": "딥러닝 실습 속도가 빠르다는 피드백",
                "count": 9,
                "week": "4주차",
            },
            {
                "pattern": "배포 운영 사례를 더 보고 싶다는 요청",
                "count": 7,
                "week": "6주차",
            },
            {
                "pattern": "검증 지표 해석 복습 자료 요청",
                "count": 5,
                "week": "5주차",
            },
        ],
        "next_suggestions": [
            {
                "priority": "high",
                "label": "딥러닝 실습 체크포인트 보강",
                "body": "중간 저장본과 예제 코드를 함께 제공해 심사위원이 결과 흐름을 쉽게 따라갈 수 있게 합니다.",
            },
            {
                "priority": "medium",
                "label": "배포 운영 사례 카드 추가",
                "body": "배포/모니터링 단계에서 실제로 어떤 장애와 체크리스트가 나오는지 요약 카드로 묶어 이해도를 높입니다.",
            },
        ],
    }


def _keyword_list(*entries: tuple[str, int]) -> list[dict]:
    return [{"text": text, "value": value} for text, value in entries]


def _average_keyword_list(keyword_map: dict[str, list[dict]]) -> list[dict]:
    totals: dict[str, float] = {}
    for items in keyword_map.values():
        for item in items:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            totals[text] = totals.get(text, 0.0) + float(item.get("value") or 0.0)
    return [
        {"text": text, "value": round(value, 1)}
        for text, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:28]
    ]


def _normalize_percentages(values: list[float]) -> list[float]:
    rounded = [round(float(value), 1) for value in values]
    delta = round(100.0 - sum(rounded), 1)
    if rounded:
        rounded[-1] = round(rounded[-1] + delta, 1)
    return rounded


def _pseudo_pdf_bytes(title: str, lines: list[str]) -> bytes:
    body = "\n".join(lines)
    return (
        "%PDF-1.4\n"
        "% Seeded demo asset\n"
        f"% {title}\n"
        f"% {body}\n"
        "1 0 obj << /Type /Catalog >> endobj\n"
        "%%EOF\n"
    ).encode("utf-8")


def _sections_to_curriculum_text(sections: list[CurriculumSection]) -> str:
    return "\n".join(f"{section.title} | {section.description}" for section in sections)


def _timestamp_from_iso(value: str) -> float:
    return datetime.fromisoformat(value).astimezone(UTC).timestamp()
