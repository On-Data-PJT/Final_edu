# STATUS

Last Updated: 2026-04-10

## Current Snapshot

- 저장소 목적: 강의 자료와 YouTube/VOC 입력을 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차와 개선 포인트를 비교하는 공모전용 MVP
- 현재 기준 브랜치: `dev`
- 현재 앱 스택: `FastAPI + Jinja + CSS + Vanilla JS + uv + RQ`
- 현재 실행 명령:
  - Web: `uv run python -m final_edu --reload`
  - Worker: `uv run python -m final_edu.worker`
- 현재 입력 포맷:
  - 과정 등록: `커리큘럼 PDF`
  - 강의 자료: `PDF`, `PPTX`, `TXT/MD`
  - VOC 자료: `PDF`, `CSV`, `TXT`
  - 링크 입력: `YouTube URL`, `YouTube Playlist URL`

## Current Product State

- `Page 1`
  - `dev`의 composer lane UI를 유지한다.
  - lane mode 는 `files`, `youtube`, `voc` 3종을 지원한다.
  - persisted draft restore 는 `files`, `vocFiles`, `youtubeUrls`, `mode`, `instructorName`를 복원한다.
  - 분석 제출은 `과정 선택 + 유효 lane 1개 이상`일 때만 활성화된다.
- `Page 2`
  - `dev`의 `sidebar + 4 panel` dashboard 구조를 유지한다.
  - 첫 패널의 `combined | material | speech` toggle 이 Page 2 전체 데이터셋 source of truth 다.
  - 결과 렌더는 저장된 `course`와 실제 업로드/YouTube 분석 결과만 사용한다.
- `Page 3 / Review`
  - `GET /review`는 강사별 실제 VOC 결과 페이지다.
  - 강사별 `voc_analysis`를 사용해 파일 메타, 감성 키워드, 반복 불만 패턴, 개선 포인트를 렌더한다.
- `Page 4 / Solution`
  - `GET /solution`은 기존 `분석 결과 기반 인사이트`, `최신 업계 동향 분석` 2섹션을 유지한다.
  - 하단에 별도 `VOC 기반 인사이트` 패널이 추가되어 공통 `voc_summary`를 렌더한다.

## Backend Contract

- `dev` UI/레이아웃/라우트는 유지하고, `lexical`의 백엔드를 이식한 상태다.
- YouTube 처리 계약:
  - 명시적 `playlist?list=...`만 playlist 로 확장한다.
  - `watch?v=...&list=...`는 단일 영상으로 유지한다.
  - `prepare`와 worker 는 object-storage 기반 shared cache 를 재사용한다.
  - process-local throttle + distributed throttle + cooldown 을 함께 사용한다.
  - ScraperAPI trial 이 켜져 있으면 metadata/watch/transcript 해석은 ScraperAPI proxy port 를 사용한다.
  - 공개 자막이 없으면 selective STT fallback 이 동작할 수 있다.
  - probe 정책은 `30개 이하 full / 31~200 partial / 200+ skip`이다.
- lexical 분석 계약:
  - `kiwipiepy` 기반 tokenization 을 사용한다.
  - section title 사용자 사전을 미리 등록한다.
  - curriculum-first keyword ranking 을 유지한다.
- VOC 분석 계약:
  - Page 1 업로드된 `voc_files`는 payload -> worker -> result 로 실제 전달된다.
  - 강사별 `voc_analysis`, 공통 `voc_summary`를 result JSON에 저장한다.
  - 커버리지 자료가 없어도 VOC만 있으면 VOC-only 결과를 반환한다.
- 모델 계약:
  - 솔루션 인사이트와 VOC LLM 분석은 `OPENAI_INSIGHT_MODEL`을 사용한다.
  - embedding 경로 실패 시 lexical fallback 으로 내려간다.

## What Changed This Round

- `dev`의 디자인/레이아웃/라우트를 유지한 채 `lexical` 백엔드를 이식했다.
- ScraperAPI, distributed throttle, cooldown, selective STT, playlist probe threshold, Kiwi tokenization 을 `dev` 브랜치에 반영했다.
- Page 1 VOC 업로드를 실제 분석 파이프라인에 연결했다.
  - `JobInstructorInput.voc_files`
  - worker download
  - `InstructorSubmission(voc_files=...)`
  - 강사별 `voc_analysis`
  - 공통 `voc_summary`
- `/review`가 더 이상 placeholder 고정값만 쓰지 않고 실제 결과 JSON 기반으로 렌더되도록 수정했다.
- `/solution`에 기존 2섹션을 유지한 채 별도 `VOC 기반 인사이트` 패널을 추가했다.
- `/api/evaluate`는 ad-hoc PDF 파싱 대신 공통 VOC 분석 helper 를 재사용하도록 정리했다.
- `job_voc_asset_download`를 추가해 persisted draft 에서 VOC 파일 download URL 을 복원할 수 있게 했다.
- `pyproject.toml`과 `uv.lock`에 `kiwipiepy` 의존성을 반영했다.
- `render.yaml`을 현재 ScraperAPI/STT/probe/distributed throttle env 계약과 맞췄다.

## Verification

- 정적/문법 검증
  - `python3 -m py_compile final_edu/*.py tests/test_page2_dashboard.py tests/test_course_preview.py tests/test_youtube_inputs.py tests/test_youtube_cache.py tests/test_utils.py tests/test_voc_analysis.py`
  - `node --check final_edu/static/app.js`
- 의존성 동기화
  - `uv sync`
- 테스트
  - `python3 -m unittest tests.test_page2_dashboard tests.test_course_preview tests.test_youtube_inputs tests.test_youtube_cache tests.test_utils tests.test_voc_analysis`
- 검증 내용
  - Page 2 dashboard shell 과 dataset mode payload 회귀
  - curriculum preview 회귀
  - watch URL / playlist URL 분기
  - metadata cache hit, transcript cache reuse, stale fallback, throttle
  - Kiwi tokenization
  - 강사별 VOC 분석 및 공통 VOC 요약
  - `/review`, `/solution`의 실제 VOC 결과 렌더
- 독립 검토
  - backend reviewer subagent: `Pass`
  - UI reviewer subagent: `Pass`

## Known Gaps / Next Priorities

- `POST /analyze/prepare`부터 저장 결과까지 가는 VOC-only HTTP end-to-end 테스트는 아직 없다.
- `job_voc_asset_download`와 persisted draft restore용 VOC download URL 전용 테스트는 아직 없다.
- OCR 기반 스캔 PDF 지원은 아직 없다.
- 외부 동향 인사이트는 deterministic fallback 중심이며 실검색 기반 고도화는 아직 없다.
- Render 실배포 smoke test 는 아직 별도로 수행하지 않았다.

## Working Tree Notes

- 문서 기준 source branch 는 `dev`다.
- 현재 구현은 `dev` UI 유지 + `lexical` 백엔드 이식 + 실제 VOC 분석 연결 상태를 기준으로 한다.
- `.codex/config.toml`은 로컬 Codex 실행 설정으로 취급하며 저장소 커밋 대상이 아니다.

## Consulted DEBUG IDs

- `DBG-005`
- `DBG-012`
- `DBG-014`
- `DBG-015`
- `DBG-016`
- `DBG-023`

## Recent Updates

### 2026-04-10

- `dev` 기준으로 `lexical`의 ScraperAPI/STT/Kiwi/YouTube 완화 백엔드를 통합했다.
- VOC 업로드를 실제 분석 파이프라인과 `/review`, `/solution` 렌더에 연결했다.
- `/solution`에 별도 `VOC 기반 인사이트` 패널을 추가했다.
- 운영문서와 Render/env 계약을 현재 구현 기준으로 정리했다.
