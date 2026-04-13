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
            target_weight=15.0,
        ),
        CurriculumSection(
            id="data-analysis",
            title="데이터 분석",
            description="Pandas 기반 전처리와 EDA 리포트 작성",
            target_weight=20.0,
        ),
        CurriculumSection(
            id="ml-basics",
            title="머신러닝 기초",
            description="지도학습, 회귀/분류, 검증 지표 이해",
            target_weight=20.0,
        ),
        CurriculumSection(
            id="deep-learning",
            title="딥러닝 응용",
            description="신경망, 실습 모델링, 프로젝트 적용",
            target_weight=25.0,
        ),
        CurriculumSection(
            id="nlp-practice",
            title="자연어 처리 실습",
            description="텍스트 전처리, 임베딩, 간단한 분류 실습",
            target_weight=10.0,
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
        "오강사": [18.0, 24.0, 18.0, 20.0, 10.0, 10.0],
        "이강사": [12.0, 18.0, 24.0, 26.0, 10.0, 10.0],
        "박강사": [15.0, 16.0, 18.0, 31.0, 10.0, 10.0],
    }
    speech_shares = {
        "오강사": [12.0, 19.0, 21.0, 26.0, 12.0, 10.0],
        "이강사": [10.0, 14.0, 25.0, 28.0, 11.0, 12.0],
        "박강사": [14.0, 20.0, 18.0, 24.0, 14.0, 10.0],
    }
    combined_unmapped = {
        "오강사": 14.8,
        "이강사": 11.5,
        "박강사": 17.2,
    }
    material_unmapped = {
        "오강사": 12.1,
        "이강사": 10.4,
        "박강사": 15.8,
    }
    speech_unmapped = {
        "오강사": 17.5,
        "이강사": 12.6,
        "박강사": 18.7,
    }
    unmapped_topics = {
        "오강사": ["LangChain", "데이터 스토리텔링"],
        "이강사": ["클라우드 비용 최적화"],
        "박강사": ["MLOps", "벡터 데이터베이스"],
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
            "오강사": _keyword_list(("python", 18), ("pandas", 15), ("sql", 13), ("신경망", 11), ("프로젝트", 10)),
            "이강사": _keyword_list(("회귀", 16), ("분류", 15), ("검증", 13), ("fastapi", 10), ("지표", 9)),
            "박강사": _keyword_list(("딥러닝", 18), ("cnn", 13), ("임베딩", 12), ("docker", 10), ("배포", 9)),
        },
        "material": {
            "오강사": _keyword_list(("python", 19), ("pandas", 16), ("sql", 14), ("eda", 10)),
            "이강사": _keyword_list(("회귀", 16), ("분류", 15), ("검증", 13), ("지표", 10)),
            "박강사": _keyword_list(("딥러닝", 18), ("cnn", 14), ("프로젝트", 12), ("배포", 9)),
        },
        "speech": {
            "오강사": _keyword_list(("프로젝트", 15), ("실습", 14), ("신경망", 12), ("피드백", 9)),
            "이강사": _keyword_list(("검증", 13), ("fastapi", 12), ("오류해결", 10), ("실전", 9)),
            "박강사": _keyword_list(("임베딩", 14), ("docker", 13), ("운영", 11), ("배포", 10)),
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
            "combined": {"asset_count": 6, "total_tokens": 8200, "mapped_tokens": 6740},
            "material": {"asset_count": 3, "total_tokens": 3600, "mapped_tokens": 3010},
            "speech": {"asset_count": 3, "total_tokens": 4600, "mapped_tokens": 3730},
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
                "title": "딥러닝 비중은 전반적으로 높음",
                "category": "강점",
                "issue": "세 강사 모두 딥러닝 응용 비중이 높아, 심화 실습 중심 과정이라는 인상이 명확합니다.",
                "evidence": "딥러닝 응용 섹션이 강사별 combined 기준 22% 이상을 차지합니다.",
                "recommendation": "입문자를 위한 머신러닝 기초와 연결 설명을 조금 더 보강하면 난이도 균형이 좋아집니다.",
                "icon": "spark",
            },
            {
                "title": "배포/운영 단원은 비교적 얇음",
                "category": "보완",
                "issue": "배포와 운영 단원은 목표 비중 대비 설명 밀도가 낮습니다.",
                "evidence": "배포/운영 실제 커버리지는 강사별 10~11% 수준으로 고정되어 있습니다.",
                "recommendation": "실전 배포 체크리스트나 운영 장애 사례를 추가하면 과정 마무리 완성도가 높아집니다.",
                "icon": "alert",
            },
        ],
        "voc_summary": _demo_voc_summary(),
        "insight_generation_mode": "demo-seeded",
        "external_trends_status": "reflected",
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
    return {
        "file_name": f"{name}_VOC.csv",
        "analyzed_at": "2026-04-12",
        "response_count": 18 + index * 3,
        "question_scores": [
            {
                "group": "강의 운영",
                "question_id": "BQ1",
                "label": "교육 신청 및 안내 절차가 수월하였다",
                "average": round(4.2 + (index * 0.1), 1),
                "response_count": 18 + index * 3,
                "scale_max": 5,
            },
            {
                "group": "강의 운영",
                "question_id": "BQ2",
                "label": "강사의 설명이 이해하기 쉬웠다",
                "average": round(4.3 + (index * 0.1), 1),
                "response_count": 18 + index * 3,
                "scale_max": 5,
            },
        ],
        "sentiment": {
            "positive": [f"{name} 강사님의 설명이 친절함", "실습 예제가 풍부함"],
            "negative": ["강의 속도가 조금 빠름"],
        },
        "repeated_complaints": [
            {
                "pattern": "실습 속도 조절 요청",
                "count": 3 + index,
                "week": "3주차",
            }
        ],
        "next_suggestions": [
            {
                "priority": "high",
                "label": "실습 체크포인트 추가",
                "body": f"{name} 강사님의 실습 파트마다 중간 확인 문제를 넣어 이해도를 점검해 보세요.",
            }
        ],
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
        ],
        "positive": ["실습 중심 커리큘럼", "설명이 친절함", "프로젝트 예제가 좋음"],
        "negative": ["강의 속도 조절 필요", "배포 단원 사례 추가 필요"],
        "repeated_complaints": [
            {
                "pattern": "딥러닝 실습 속도가 빠르다는 피드백",
                "count": 9,
                "week": "4주차",
            }
        ],
        "next_suggestions": [
            {
                "priority": "high",
                "label": "딥러닝 실습 체크포인트 보강",
                "body": "중간 저장본과 예제 코드를 함께 제공해 심사위원이 결과 흐름을 쉽게 따라갈 수 있게 합니다.",
            }
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
        for text, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:12]
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
