from __future__ import annotations

import json
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime when dependency is missing.
    OpenAI = None


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def group_question_scores(question_scores: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in question_scores:
        group = str(_read(item, "group") or "기타").strip() or "기타"
        grouped.setdefault(group, []).append(
            {
                "question_id": str(_read(item, "question_id") or "").strip(),
                "label": str(_read(item, "label") or "").strip(),
                "average": float(_read(item, "average") or 0.0),
                "response_count": int(_read(item, "response_count") or 0),
                "scale_max": int(_read(item, "scale_max") or 5),
            }
        )
    return [{"group": group, "entries": items} for group, items in grouped.items()]


def generate_solution_content(payload: dict, settings) -> tuple[dict, str, str | None]:  # noqa: ANN001
    if not settings.openai_api_key or OpenAI is None:
        return fallback_solution_content(payload), "fallback", "OPENAI_API_KEY가 없어 규칙 기반 솔루션을 표시합니다."

    client = OpenAI(api_key=settings.openai_api_key)
    prompt_data = {
        "topics": payload.get("topics", []),
        "target": payload.get("target", []),
        "instructors": [
            {
                "name": inst["name"],
                "rawValues": inst.get("rawValues", []),
                "totalGapScore": inst["totalGapScore"],
                "topGaps": inst["chartRows"][:3],
            }
            for inst in payload["instructors"]
        ],
    }

    try:
        response = client.chat.completions.create(
            model=settings.openai_insight_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 교육 커리큘럼 분석 전문가입니다. "
                        "강사별 커버리지 데이터와 목표 커리큘럼을 비교해 "
                        "실행 가능한 인사이트와 업계 동향 분석을 JSON으로 반환하세요. "
                        "모든 문구는 자연스러운 한국어로 작성하고, 과장 없이 데이터 기반으로만 분석하세요. "
                        "trendAnalysis는 topics의 섹션명을 보고 과목 도메인을 먼저 파악한 뒤, "
                        "그 도메인과 직접 관련된 교육기관·자격시험·교육 정책 또는 학습 제도만 구체적으로 언급하세요. "
                        "특정 연도(예: 2024, 2025)를 언급하지 말고 '최근' 또는 '현재' 등의 표현을 사용하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "아래 커리큘럼 데이터를 분석해 JSON을 생성하세요.\n"
                        "반환 형식:\n"
                        "{\n"
                        '  "insights": [\n'
                        '    {"text": "인사이트 문장 (구체적 수치% 포함 필수)", '
                        '"numbers": [{"label": "레이블", "value": 숫자, "benchmark": 숫자, "topic": "섹션명"}]},\n'
                        "    ...5개 이상 반드시 포함\n"
                        "  ],\n"
                        '  "trendAnalysis": [\n'
                        '    {"title": "동향 제목", "detail": "상세 설명 (타 기관 비교 포함)", '
                        '"badge": "갭|일치|신규", "comparison": "타 기관 대비 요약"},\n'
                        "    ...3개 이상\n"
                        "  ]\n"
                        "}\n\n"
                        "요구사항:\n"
                        "- insights: 전체 강사 평균과 목표 커리큘럼 비교 인사이트 5개 이상. 각각 구체적 수치(%p, %) 포함\n"
                        "- trendAnalysis: topics 섹션명을 읽어 과목 도메인을 파악하고, "
                        "그 도메인에 맞는 최신 교육 트렌드 3개를 작성하세요. "
                        "topics에 드러난 과목 도메인과 직접 관련된 교육기관·자격시험·정책 또는 학습 제도만 언급하고, "
                        "다른 과목의 기관이나 시험을 끌어오지 마세요. "
                        "특정 연도 수치(2024, 2025 등)는 사용하지 말고 '최근' 표현을 쓰세요.\n"
                        "- badge는 반드시 갭/일치/신규 중 하나\n\n"
                        f"데이터:\n{json.dumps(prompt_data, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        return _normalize_new_content(raw, payload), "gpt", None
    except Exception as exc:  # noqa: BLE001
        return fallback_solution_content(payload), "fallback", f"GPT 생성 실패: {exc}"


def _normalize_new_content(raw: dict, payload: dict) -> dict:
    fallback = fallback_solution_content(payload)
    allowed_badges = {"갭", "일치", "신규"}

    insights = []
    for item in raw.get("insights", [])[:10]:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        numbers = [
            {
                "label": str(n.get("label", "")),
                "value": float(n.get("value", 0)),
                "benchmark": float(n.get("benchmark", 0)),
                "topic": str(n.get("topic", "")),
            }
            for n in item.get("numbers", [])
            if isinstance(n, dict)
        ]
        insights.append({"text": str(item["text"]), "numbers": numbers})

    if len(insights) < 5:
        insights = fallback["insights"]

    trend_analysis = []
    for item in raw.get("trendAnalysis", [])[:6]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        badge = item.get("badge", "갭")
        trend_analysis.append(
            {
                "title": str(item.get("title", "")),
                "detail": str(item.get("detail", "")),
                "badge": badge if badge in allowed_badges else "갭",
                "comparison": str(item.get("comparison", "")),
            }
        )

    if len(trend_analysis) < 2:
        trend_analysis = fallback["trendAnalysis"]

    return {"insights": insights, "trendAnalysis": trend_analysis}


def fallback_solution_content(payload: dict) -> dict:
    topics = payload.get("topics", [])
    target_vals = payload.get("target", [])
    instructors = payload.get("instructors", [])

    avg_actual: list[float] = []
    for i in range(len(topics)):
        vals = []
        for inst in instructors:
            raw = inst.get("rawValues", [])
            all_rows = inst.get("allRows", [])
            if raw and i < len(raw):
                vals.append(float(raw[i]))
            elif all_rows and i < len(all_rows):
                vals.append(float(all_rows[i]["actualShare"]))
        avg_actual.append(round(sum(vals) / len(vals) if vals else 0.0, 1))

    topic_gaps = sorted(
        [
            (topics[i], avg_actual[i], target_vals[i], round(abs(avg_actual[i] - target_vals[i]), 1))
            for i in range(min(len(topics), len(target_vals), len(avg_actual)))
        ],
        key=lambda item: item[3],
        reverse=True,
    )

    insights: list[dict] = []
    for topic, actual, bench, gap in topic_gaps:
        if gap > 0:
            direction = "낮아" if actual < bench else "높아"
            action = "보강" if actual < bench else "축소 조정"
            insights.append(
                {
                    "text": (
                        f"{topic} 섹션의 전체 강사 평균 커버리지({actual}%)가 "
                        f"목표({bench}%)보다 {gap}%p {direction} {action}이 필요합니다."
                    ),
                    "numbers": [{"label": "평균 실제", "value": actual, "benchmark": bench, "topic": topic}],
                }
            )

    for inst in instructors:
        biggest = inst["chartRows"][0] if inst.get("chartRows") else None
        if biggest and biggest["gapScore"] >= 5:
            insights.append(
                {
                    "text": (
                        f"{inst['name']}의 {biggest['section']} 섹션({biggest['actualShare']}%)이 "
                        f"목표({biggest['benchmarkShare']}%)보다 {biggest['gapScore']}%p 차이 납니다."
                    ),
                    "numbers": [
                        {
                            "label": inst["name"],
                            "value": biggest["actualShare"],
                            "benchmark": biggest["benchmarkShare"],
                            "topic": biggest["section"],
                        }
                    ],
                }
            )

    if len(insights) < 5:
        total_avg_gap = round(sum(item["totalGapScore"] for item in instructors) / len(instructors), 1) if instructors else 0
        insights.append(
            {
                "text": f"전체 강사 평균 누적 갭 점수는 {total_avg_gap}%p로, 커리큘럼 목표 대비 전반적인 재조정이 필요합니다.",
                "numbers": [],
            }
        )

    top_topic = topic_gaps[0][0] if topic_gaps else "핵심 섹션"
    bottom_topic = topic_gaps[-1][0] if topic_gaps else "기초 섹션"
    return {
        "insights": insights[:8],
        "trendAnalysis": [
            {
                "title": "실습·사례 중심 학습 비중 확대 추세",
                "detail": (
                    "최근 국내외 주요 교육기관들은 이론 강의 비중을 줄이고 "
                    "실습·사례 분석 중심으로 커리큘럼을 재편하는 추세입니다. "
                    "현재 커리큘럼의 이론-실습 비율 검토가 필요합니다."
                ),
                "badge": "갭",
                "comparison": "타 기관 평균 대비 실습 비중 검토 필요",
            },
            {
                "title": f"{top_topic} 관련 교육 수요 증가",
                "detail": (
                    f"최근 교육 시장에서 {top_topic} 관련 강좌 수요가 지속적으로 증가하고 있습니다. "
                    "해당 섹션의 심화 내용 편성 및 비중 강화를 권장합니다."
                ),
                "badge": "일치",
                "comparison": "교육 시장 수요와 방향 일치 — 비중 강화 권장",
            },
            {
                "title": f"{bottom_topic} 기초 역량 강화 필요",
                "detail": (
                    f"학습자 기초 역량 격차를 줄이기 위해 {bottom_topic} 섹션의 "
                    "단계별 학습 콘텐츠 구성이 중요해지고 있습니다. "
                    "입문자와 심화 학습자를 위한 난이도 구분이 필요합니다."
                ),
                "badge": "신규",
                "comparison": "기초-심화 연계 콘텐츠 구성 강화 권장",
            },
        ],
    }


def demo_solution_payload() -> dict:
    topics = ["SQL", "데이터 분석", "머신러닝", "딥러닝", "전처리"]
    target = [15.0, 25.0, 25.0, 20.0, 15.0]
    inst_colors = ["#6366f1", "#ef4444", "#10b981"]

    raw_data = [
        {"name": "오정훈 강사", "values": [15.0, 30.0, 25.0, 20.0, 10.0], "unmapped": 12.4, "unmappedTopics": ["ChatGPT 활용", "데이터 시각화 도구"]},
        {"name": "김데이터 강사", "values": [20.0, 25.0, 30.0, 10.0, 15.0], "unmapped": 7.1, "unmappedTopics": ["클라우드 배포"]},
        {"name": "이파이썬 강사", "values": [10.0, 20.0, 30.0, 25.0, 15.0], "unmapped": 18.3, "unmappedTopics": ["LLM 파인튜닝", "벡터 DB", "MLOps 기초"]},
    ]

    instructors = []
    for idx, raw in enumerate(raw_data):
        all_rows = []
        for i, topic in enumerate(topics):
            actual = raw["values"][i]
            bench = target[i]
            gap = round(abs(actual - bench), 1)
            all_rows.append(
                {
                    "section": topic,
                    "actualShare": actual,
                    "benchmarkShare": bench,
                    "gapScore": gap,
                    "direction": "강화" if actual < bench else "정리",
                }
            )

        sorted_rows = sorted(all_rows, key=lambda row: row["gapScore"], reverse=True)
        top_rows = [row for row in sorted_rows if row["gapScore"] > 0][:4] or sorted_rows[:1]
        total_gap = min(round(sum(row["gapScore"] for row in top_rows), 1), 100.0)

        instructors.append(
            {
                "name": raw["name"],
                "color": inst_colors[idx % len(inst_colors)],
                "assetCount": 4,
                "warningCount": 0,
                "unmappedShare": raw.get("unmapped", 0.0),
                "unmappedTopics": raw.get("unmappedTopics", []),
                "totalGapScore": total_gap,
                "chartRows": top_rows,
                "allRows": all_rows,
                "rawValues": raw["values"],
            }
        )

    return {
        "title": "강사별 솔루션 분석",
        "source": "demo-fallback",
        "topics": topics,
        "target": target,
        "sections": [{"id": topic.replace(" ", "-"), "title": topic} for topic in topics],
        "instructors": instructors,
        "voc_summary": {
            "question_scores": [],
            "question_score_groups": [],
            "positive": ["실습 중심", "친절한 설명"],
            "negative": ["강의 속도", "자료 부족"],
            "repeated_complaints": [
                {"pattern": "강의 속도 조절 필요", "count": 2, "week": "3~4주차"},
            ],
            "next_suggestions": [
                {"priority": "high", "label": "강의 속도 조절", "body": "핵심 개념 뒤 체크포인트와 질의 시간을 추가해 보세요."},
            ],
        },
    }


def build_solution_payload(result: dict | None) -> dict:
    if not result:
        return demo_solution_payload()

    inst_colors = ["#6366f1", "#ef4444", "#10b981", "#f59e0b"]
    sections = _read(result, "sections") or []
    instructors = _read(result, "instructors") or []
    average_share_by_section: dict[str, float] = {}

    for section in sections:
        section_id = _read(section, "id")
        average_share_by_section[section_id] = round(float(_read(section, "target_weight") or 0.0), 1)

    topics = [_read(section, "title") for section in sections]
    target = [
        round(float(_read(section, "target_weight") or average_share_by_section.get(_read(section, "id"), 0.0)), 1)
        for section in sections
    ]

    instructor_payloads = []
    for idx, instructor in enumerate(instructors):
        all_rows = []
        coverages = _read(instructor, "section_coverages") or []
        for coverage in coverages:
            section_id = _read(coverage, "section_id")
            actual_share = round(float(_read(coverage, "token_share") or 0.0) * 100, 1)
            benchmark_share = round(average_share_by_section.get(section_id, 0.0), 1)
            gap_score = round(abs(actual_share - benchmark_share), 1)
            all_rows.append(
                {
                    "section": _read(coverage, "section_title"),
                    "actualShare": actual_share,
                    "benchmarkShare": benchmark_share,
                    "gapScore": gap_score,
                    "direction": "강화" if actual_share < benchmark_share else "정리",
                }
            )

        sorted_rows = sorted(all_rows, key=lambda item: item["gapScore"], reverse=True)
        top_rows = [row for row in sorted_rows if row["gapScore"] > 0][:4] or sorted_rows[:1]
        total_gap = min(round(sum(row["gapScore"] for row in top_rows), 1), 100.0)
        raw_values = [row["actualShare"] for row in all_rows]

        instructor_payloads.append(
            {
                "name": _read(instructor, "name"),
                "color": inst_colors[idx % len(inst_colors)],
                "assetCount": int(_read(instructor, "asset_count") or 0),
                "warningCount": len(_read(instructor, "warnings") or []),
                "unmappedShare": round(float(_read(instructor, "unmapped_share") or 0.0) * 100, 1),
                "unmappedTopics": [],
                "totalGapScore": total_gap,
                "chartRows": top_rows,
                "allRows": all_rows,
                "rawValues": raw_values,
            }
        )

    return {
        "title": "강사별 솔루션 분석",
        "source": "analysis-result",
        "topics": topics,
        "target": target,
        "sections": [{"id": _read(section, "id"), "title": _read(section, "title")} for section in sections],
        "instructors": instructor_payloads,
        "voc_summary": {
            **(_read(result, "voc_summary") or {}),
            "question_score_groups": group_question_scores(
                _read(_read(result, "voc_summary") or {}, "question_scores") or []
            ),
        },
    }
