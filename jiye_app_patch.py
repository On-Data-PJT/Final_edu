# ============================================================
# jiye 브랜치 app.py 패치 가이드
# ============================================================
# 아래 내용을 dev 브랜치의 app.py에 추가하면 됩니다.
#
# [추가 위치 1] create_app() 함수 안, 기존 라우트들 사이에 추가
# [추가 위치 2] 파일 맨 아래에 함수들 추가
# ============================================================


# ──────────────────────────────────────────────────────────
# [추가 위치 1] create_app() 안에 추가할 라우트
# 기존 @app.get("/solution", ...) 라우트 바로 아래에 붙여넣기
# ──────────────────────────────────────────────────────────

"""
    @app.get("/jiye", response_class=HTMLResponse, name="jiye_page")
    async def jiye_page(request: Request, job_id: str | None = None) -> HTMLResponse:
        job = None
        result = None
        if job_id:
            job = get_job(job_id, settings)
            if job and job.result_key:
                result = load_job_result(job, settings)
        else:
            for recent_job in list_recent_jobs(settings=settings):
                if recent_job.result_key:
                    job = recent_job
                    result = load_job_result(recent_job, settings)
                    break

        solution_input = _build_solution_payload(result)
        solution_content, generation_mode, generation_warning = _generate_solution_content(solution_input, settings)
        review_payload = _build_review_payload(result)
        return templates.TemplateResponse(
            request,
            "jiye.html",
            {
                "request": request,
                "solution_payload": {
                    **solution_input,
                    "content": solution_content,
                    "generation_mode": generation_mode,
                    "generation_warning": generation_warning,
                },
                "review_payload": review_payload,
            },
        )
"""


# ──────────────────────────────────────────────────────────
# [추가 위치 2] 파일 맨 아래에 추가할 함수들
# ──────────────────────────────────────────────────────────

def _build_solution_payload(result):
    if not result:
        return _demo_solution_payload()

    inst_colors = ["#6366f1", "#ef4444", "#10b981", "#f59e0b"]
    sections = _read(result, "sections")
    instructors = _read(result, "instructors")
    average_share_by_section = {}

    for section in sections:
        section_id = _read(section, "id")
        shares = []
        for instructor in instructors:
            coverage = next(
                (c for c in _read(instructor, "section_coverages")
                 if _read(c, "section_id") == section_id),
                None,
            )
            if coverage is None:
                continue
            shares.append(float(_read(coverage, "token_share")) * 100)
        average_share_by_section[section_id] = sum(shares) / len(shares) if shares else 0.0

    topics = [_read(s, "title") for s in sections]
    target = [round(average_share_by_section.get(_read(s, "id"), 0.0), 1) for s in sections]

    instructor_payloads = []
    for idx, instructor in enumerate(instructors):
        all_rows = []
        for coverage in _read(instructor, "section_coverages"):
            section_id = _read(coverage, "section_id")
            actual_share = round(float(_read(coverage, "token_share")) * 100, 1)
            benchmark_share = round(average_share_by_section.get(section_id, 0.0), 1)
            gap_score = round(abs(actual_share - benchmark_share), 1)
            all_rows.append({
                "section": _read(coverage, "section_title"),
                "actualShare": actual_share,
                "benchmarkShare": benchmark_share,
                "gapScore": gap_score,
                "direction": "강화" if actual_share < benchmark_share else "정리",
            })

        sorted_rows = sorted(all_rows, key=lambda item: item["gapScore"], reverse=True)
        top_rows = [r for r in sorted_rows if r["gapScore"] > 0][:4] or sorted_rows[:1]
        total_gap = round(sum(item["gapScore"] for item in top_rows), 1)
        raw_values = [r["actualShare"] for r in all_rows]

        instructor_payloads.append({
            "name": _read(instructor, "name"),
            "color": inst_colors[idx % len(inst_colors)],
            "assetCount": int(_read(instructor, "asset_count")),
            "warningCount": len(_read(instructor, "warnings")),
            "unmappedShare": round(float(_read(instructor, "unmapped_share")) * 100, 1),
            "unmappedTopics": [],
            "totalGapScore": total_gap,
            "chartRows": top_rows,
            "allRows": all_rows,
            "rawValues": raw_values,
        })

    return {
        "title": "강사별 솔루션 분석",
        "source": "analysis-result",
        "topics": topics,
        "target": target,
        "sections": [{"id": _read(s, "id"), "title": _read(s, "title")} for s in sections],
        "instructors": instructor_payloads,
    }


def _demo_solution_payload():
    topics = ["SQL", "데이터 분석", "머신러닝", "딥러닝", "전처리"]
    target = [15.0, 25.0, 25.0, 20.0, 15.0]
    inst_colors = ["#6366f1", "#ef4444", "#10b981"]

    raw_data = [
        {"name": "오정훈 강사", "values": [15.0, 30.0, 25.0, 20.0, 10.0], "unmapped": 12.4,
         "unmappedTopics": ["ChatGPT 활용", "데이터 시각화 도구"]},
        {"name": "김데이터 강사", "values": [20.0, 25.0, 30.0, 10.0, 15.0], "unmapped": 7.1,
         "unmappedTopics": ["클라우드 배포"]},
        {"name": "이파이썬 강사", "values": [10.0, 20.0, 30.0, 25.0, 15.0], "unmapped": 18.3,
         "unmappedTopics": ["LLM 파인튜닝", "벡터 DB", "MLOps 기초"]},
    ]

    instructors = []
    for idx, raw in enumerate(raw_data):
        all_rows = []
        for i, topic in enumerate(topics):
            actual = raw["values"][i]
            bench = target[i]
            gap = round(abs(actual - bench), 1)
            all_rows.append({
                "section": topic,
                "actualShare": actual,
                "benchmarkShare": bench,
                "gapScore": gap,
                "direction": "강화" if actual < bench else "정리",
            })

        sorted_rows = sorted(all_rows, key=lambda r: r["gapScore"], reverse=True)
        top_rows = [r for r in sorted_rows if r["gapScore"] > 0][:4] or sorted_rows[:1]
        total_gap = round(sum(r["gapScore"] for r in top_rows), 1)

        instructors.append({
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
        })

    return {
        "title": "강사별 솔루션 분석",
        "source": "demo-fallback",
        "topics": topics,
        "target": target,
        "sections": [{"id": t.replace(" ", "-"), "title": t} for t in topics],
        "instructors": instructors,
    }


def _generate_solution_content(payload, settings):
    try:
        from openai import OpenAI as _OpenAI
    except ImportError:
        _OpenAI = None

    import json

    if not getattr(settings, "openai_api_key", None) or _OpenAI is None:
        return _fallback_solution_content(payload), "fallback", "OPENAI_API_KEY가 없어 규칙 기반 솔루션을 표시합니다."

    client = _OpenAI(api_key=settings.openai_api_key)
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
        model = getattr(settings, "openai_solution_model", "gpt-5.4-mini")
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 교육 커리큘럼 분석 전문가입니다. "
                        "강사별 커버리지 데이터와 목표 커리큘럼을 비교해 "
                        "실행 가능한 인사이트와 업계 동향 분석을 JSON으로 반환하세요. "
                        "모든 문구는 자연스러운 한국어로 작성하고, 과장 없이 데이터 기반으로만 분석하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "아래 커리큘럼 데이터를 분석해 JSON을 생성하세요.\n"
                        "반환 형식:\n"
                        '{"insights": [{"text": "인사이트 문장", "numbers": []}], '
                        '"trendAnalysis": [{"title": "동향", "detail": "설명", "badge": "갭|일치|신규", "comparison": "비교"}]}\n\n'
                        f"데이터:\n{json.dumps(prompt_data, ensure_ascii=False)}"
                    ),
                },
            ],
        )
        raw = json.loads(response.choices[0].message.content or "{}")
        return raw, "gpt", None
    except Exception as exc:
        return _fallback_solution_content(payload), "fallback", f"GPT 생성 실패: {exc}"


def _fallback_solution_content(payload):
    topics = payload.get("topics", [])
    target_vals = payload.get("target", [])
    instructors = payload.get("instructors", [])

    avg_actual = []
    for i in range(len(topics)):
        vals = []
        for inst in instructors:
            raw = inst.get("rawValues", [])
            if raw and i < len(raw):
                vals.append(float(raw[i]))
        avg_actual.append(round(sum(vals) / len(vals) if vals else 0.0, 1))

    topic_gaps = sorted(
        [(topics[i], avg_actual[i], target_vals[i], round(abs(avg_actual[i] - target_vals[i]), 1))
         for i in range(min(len(topics), len(target_vals), len(avg_actual)))],
        key=lambda x: x[3], reverse=True,
    )

    insights = []
    for topic, actual, bench, gap in topic_gaps:
        if gap > 0:
            direction = "낮아" if actual < bench else "높아"
            action = "보강" if actual < bench else "축소 조정"
            insights.append({"text": f"{topic} 섹션의 전체 강사 평균({actual}%)이 목표({bench}%)보다 {gap}%p {direction} {action}이 필요합니다.", "numbers": []})

    top_topic = topic_gaps[0][0] if topic_gaps else "핵심 섹션"
    return {
        "insights": insights[:8],
        "trendAnalysis": [
            {"title": "실무 프로젝트 기반 학습 확대 추세", "detail": "주요 IT 교육기관은 프로젝트 실습을 40% 이상 배정하는 추세입니다.", "badge": "갭", "comparison": "타 기관 대비 프로젝트 비중 낮음"},
            {"title": "LLM·생성 AI 활용 실습 급증", "detail": "생성 AI 도구 활용 커리큘럼이 2024년 대비 2.3배 증가했습니다.", "badge": "신규", "comparison": "AI 도구 활용 섹션 부재"},
            {"title": f"{top_topic} 심화 콘텐츠 수요 증가", "detail": f"{top_topic} 관련 직무 요구사항이 전년 대비 35% 증가했습니다.", "badge": "일치", "comparison": "업계 수요와 방향 일치"},
        ],
    }


def _build_review_payload(result):
    """강사별 평가서 분석 결과 payload. 실제 결과 없으면 데모 데이터 반환."""
    if result:
        instructors = _read(result, "instructors")
        return {
            "common_summary": {"positive": [], "negative": []},
            "instructors": [
                {
                    "name": _read(inst, "name"),
                    "file_name": None,
                    "analyzed_at": None,
                    "response_count": None,
                    "sentiment": {"positive": [], "negative": []},
                    "repeated_complaints": [],
                    "next_suggestions": [],
                }
                for inst in instructors
            ],
        }

    # 데모 데이터
    return {
        "common_summary": {
            "positive": ["실습 중심 강의 구성", "친절하고 명확한 설명"],
            "negative": ["강의 속도 및 실습 시간 부족", "실습 환경·자료 지원 미흡"],
        },
        "instructors": [
            {
                "name": "오정훈 강사",
                "file_name": "evaluation_ojh_2026q1.pdf",
                "analyzed_at": "2026-04-10",
                "response_count": 28,
                "sentiment": {
                    "positive": ["실습 위주", "친절한 설명", "예시 풍부", "이해하기 쉬움"],
                    "negative": ["속도 빠름", "과제 부담", "PDF 자료 부족"],
                },
                "repeated_complaints": [
                    {"pattern": "강의 속도가 너무 빠르다는 의견", "count": 9, "week": "3~4주차"},
                    {"pattern": "실습 시간이 충분하지 않다는 피드백", "count": 6, "week": "5주차"},
                ],
                "next_suggestions": [
                    {"priority": "high",   "label": "강의 속도 조절",    "body": "3~4주차 ML 파트에서 Q&A 시간을 추가로 확보하면 좋을 것 같아요."},
                    {"priority": "medium", "label": "실습 자료 보강",    "body": "PDF 외 코드 파일을 함께 제공하면 복습에 도움이 될 것 같아요."},
                    {"priority": "low",    "label": "과제 난이도 단계화", "body": "기초·심화 과제를 분리해 수강생 수준별로 선택할 수 있도록 제안해요."},
                ],
            },
            {
                "name": "김데이터 강사",
                "file_name": "evaluation_kdm_2026q1.pdf",
                "analyzed_at": "2026-04-09",
                "response_count": 21,
                "sentiment": {
                    "positive": ["체계적인 구성", "실무 연결", "명확한 설명"],
                    "negative": ["실습 환경 불안정", "질문 시간 부족"],
                },
                "repeated_complaints": [
                    {"pattern": "실습 환경(Colab) 오류로 수업이 자주 끊겼다는 피드백", "count": 7, "week": "2주차"},
                ],
                "next_suggestions": [
                    {"priority": "high",   "label": "실습 환경 사전 점검", "body": "Colab 환경 및 패키지 버전을 사전에 공유해두면 오류를 줄일 수 있을 것 같아요."},
                    {"priority": "medium", "label": "질문 채널 운영",      "body": "실시간 질문 채널(슬랙 등)을 병행하면 질문 기회가 늘어날 것 같아요."},
                ],
            },
            {
                "name": "이파이썬 강사",
                "file_name": None,
                "analyzed_at": None,
                "response_count": None,
                "sentiment": {"positive": [], "negative": []},
                "repeated_complaints": [],
                "next_suggestions": [],
            },
        ],
    }


# ──────────────────────────────────────────────────────────
# [참고] _read() 함수가 dev app.py에 없다면 아래도 추가
# ──────────────────────────────────────────────────────────

def _read(value, key):
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)
