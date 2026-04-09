# STATUS

Last Updated: 2026-04-09

## Current Snapshot

- 저장소 목적: 강의 자료를 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차를 시각화하는 공모전용 MVP
- 현재 앱 스택: `FastAPI + Jinja + CSS + Vanilla JS + uv + RQ`
- 현재 실행 명령: `uv run python -m final_edu --reload`
- 현재 worker 실행 명령: `uv run python -m final_edu.worker`
- 현재 입력 포맷: `PDF`, `PPTX`, `TXT/MD`, `YouTube URL`, `YouTube Playlist URL`
  - 현재 YouTube 입력은 개별 영상 URL과 playlist URL 모두 지원하고, playlist 는 내부 영상을 확장한 뒤 분석한다
- 현재 과정 기준:
  - `Page 1`에서 과정명, 커리큘럼 PDF, 담당 강사 roster 를 등록
  - `POST /courses/preview`는 커리큘럼 PDF를 `accepted | review_required | rejected`로 판정하고, 자동 저장 가능 여부를 함께 반환함
  - 주차별 시간표형 커리큘럼은 `layout` 텍스트를 기준으로 로컬 시간표 파서가 과목별 slot 수를 집계해 목표 비중을 자동 산출할 수 있음
  - 비관련 PDF나 unreadable PDF는 기본 대주제를 억지로 만들지 않고 저장 차단 대상으로 처리함
- `review_required` 상태에서만 대주제/설명/비중 편집 표를 다시 노출해 사용자가 직접 수정 후 저장할 수 있음
- 과정 등록 modal 의 preview 피드백은 상세 근거/경고 목록 대신 저장 가능 여부를 알려주는 짧은 상태 문구만 표시함
- 현재 분석 모드:
  - `OPENAI_API_KEY`가 있으면 OpenAI embedding 사용
  - 키가 없거나 실패하면 lexical similarity fallback
  - 솔루션 인사이트는 `OPENAI_INSIGHT_MODEL` 사용
  - 현재 기본 insight model: `gpt-5.4-mini`
  - insight model 실패 시 deterministic fallback 카드 사용
- 현재 작업 방식:
  - `Page 1`: 중앙 popup 기반 과정 추가/선택 + chat-style 자료 lane 등록
  - 과정 목록에서 같은 과정을 다시 선택하면 과정별 draft cache 또는 최근 제출 payload 기준으로 강사 자료/유튜브 링크를 복원함
  - YouTube playlist 가 포함되면 `prepare -> confirm` 단계에서 영상 수, 예상 chunk, 예상 시간, 예상 비용을 먼저 확인함
  - `POST /analyze`는 즉시 결과를 반환하지 않음
  - 분석 Job을 생성하고 `/jobs/{job_id}`에서 첫 번째 결과 페이지를 확인함
  - `/jobs/{job_id}/solutions`에서 솔루션 인사이트 페이지를 확인함
  - 단일 강사 1명만 있어도 analyze 제출과 결과 렌더링이 가능함
- 현재 배포 전제:
  - 프로덕션: `Render Web + Worker + Key Value + R2`
  - 로컬: `inline/local` fallback
- 현재 환경 변수 로딩:
  - 저장소 루트 `.env` 자동 로드
  - 이미 export 된 환경 변수가 있으면 `.env`보다 우선
- 현재 로컬 startup 호환성:
  - `REDIS_URL`이 없으면 웹 앱 import 경로에서 `rq`를 지연 로드해 `inline/local` fallback 으로 시작
  - Windows에서도 `uv run python -m final_edu --reload` 웹 실행 경로가 `rq`의 `fork` import 에 막히지 않도록 보강됨
- 현재 운영 문서 체계:
  - `AGENTS.md`: bootstrap entrypoint
  - `.agent/AGENTS.md`: 실제 운영 계약 문서
  - `.agent/STATUS.md`: 현재 상태 스냅샷 + 최근 변경
  - `.agent/DEBUG.md`: 해결된 오류와 재발 방지 규칙
    - preflight 는 `How To Use` → `Always Read` → `Incident Index` 순으로 scan 하고, 현재 작업과 맞는 incident 본문만 추가로 읽는 방식으로 운영
    - `Active Incidents`는 startup / dependency / queue / storage / 디자인 검수 자동화 / wide refactor / release 직전 점검에서 전체 확인
  - `.agent/Components.md`: 페이지별 UI 구성요소 및 상호작용 명세
  - `.agent/DESIGN.md`: 전체 웹 작업물의 시각 톤 및 디자인 시스템 명세
  - `./.codex/skills/final-edu-design/SKILL.md`: repo-local 디자인 구현 스킬
  - `capture_pages.py --backend auto`: `cmux` 우선 / Playwright fallback 디자인 검수 스크립트
  - 협업 규칙 문서는 `.agent/AGENTS.md` 중심으로 단일화되고, 루트 `AGENTS.md`는 bootstrap 으로만 유지
- 현재 브랜치 상태: `dev...origin/dev` (dirty)
- 현재 기준선: Page 1 minimal blue composer 재설계, course instructor roster 저장, 단일 강사 허용, 긴 파일명 안전 처리, 과정별 draft 복원까지 반영된 상태
- 현재 디자인 검수 경로:
  - macOS + `cmux` 가능 시 desktop/tablet 검수는 `cmux` 브라우저 우선
  - mobile 또는 `cmux` 불가 환경은 Playwright fallback
  - reviewer 입력물에는 capture backend 와 fallback 사유를 함께 기록

## Current Goal

- 현재 목표는 **3페이지 데모 UI와 과정 기반 분석 흐름을 안정화**하는 것
- 지금 시점에서 가장 중요한 다음 단계:
  - 새 Airtable 톤 UI를 mobile/tablet 까지 추가 압축할지 판단
  - 현재 UI/분석 확장 변경을 정리하고 커밋 가능한 상태로 마감
  - 실제 데모용 강의자료 2~3세트 확보
  - Render 실배포 검증
  - R2 / Render KV 연결 후 worker 실운영 경로 검증
  - 결과 해석 문구와 경고 메시지 튜닝
  - 외부 동향 슬롯과 모바일 압축에 대한 선택적 polish 판단

## Current Parallel Lanes

- Lane 1. Extraction Hardening
  - 대상: `final_edu/extractors.py`
  - 목적: YouTube transcript 실패 메시지, PDF/PPTX unsupported 경고 개선
- Lane 2. Analysis Tuning
  - 대상: `final_edu/analysis.py`, `final_edu/utils.py`
  - 목적: threshold, evidence 선택, `Other / Unmapped` 해석 개선
- Lane 3. Web / Demo Polish
  - 대상: `final_edu/app.py`, `final_edu/templates/*`, `final_edu/static/*`, `render.yaml`
  - 목적: Job 상태 UX, 결과 화면 가독성, 배포 동선 정리
- Lane 4. Queue / Storage Integration
  - 대상: `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/worker.py`, `final_edu/config.py`
  - 목적: RQ, Redis/KV, R2 연결 안정화
- Sidecar Explorer
  - 목적: Render worker/R2 실배포 제약, YouTube transcript 실패 유형, 데모 데이터 적합성 조사

현재 lane 들은 파일 충돌이 적어서 병렬 subagent 작업 대상으로 적합합니다.

## Implemented So Far

- 협업 환경 초기 세팅 완료
  - `uv` 기반 개발환경 통합
  - Python `3.12.12` 고정
  - GitHub 원격 저장소 연결
- IDE 실행 환경 정리 완료
  - `.vscode` 설정으로 워크스페이스 루트 기준 실행 가능
- 웹 MVP 골격 구현 완료
  - `GET /`, `POST /analyze`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/solutions`, `GET /jobs/{job_id}/status`, `GET /health`
  - FastAPI 앱 팩토리 및 CLI 실행 경로 구현
- 과정 저장/선택 흐름 구현 완료
  - `POST /courses/preview`, `POST /courses`, `GET /courses`, `GET /courses/{course_id}` 추가
  - 커리큘럼 PDF preview, 목표 비중 editable table, 과정 저장, 과정 목록/선택 구현
- 배치 처리 인프라 골격 구현 완료
  - Job payload / Job metadata 모델 추가
  - 로컬 파일 기반 Job 저장소 추가
  - Redis/RQ 기반 Job 저장소 및 큐 어댑터 추가
  - 로컬 inline queue fallback 추가
  - inline/local 모드에서 Redis/RQ import 지연 로드로 Windows 웹 startup 호환성 보강
  - Local object storage / R2 object storage 어댑터 추가
  - worker 실행 엔트리포인트 추가
- 추출 파이프라인 구현 완료
  - PDF 텍스트 추출
  - PPTX 슬라이드 텍스트 추출
  - TXT/MD 텍스트 추출
  - YouTube transcript 기반 텍스트 추출
- 분석 파이프라인 구현 완료
  - 대단원 커리큘럼 파싱
  - 텍스트 청크 정규화
  - 중복 청크 제거
  - 커리큘럼 매핑
  - 강사별 비중 계산
  - `Other / Unmapped` 처리
  - 근거 스니펫 추출
- 분석 결과 확장 구현 완료
  - `material / speech / combined` mode series 계산
  - 강사별 keyword cloud 데이터 계산
  - rose / bar / line chart 시리즈 계산
  - 솔루션 인사이트 1~5용 deterministic metrics 계산
  - `gpt-5.4-mini` 기반 insight 생성 + 실패 시 deterministic fallback 구현
- 3페이지 UI 구현 완료
  - `Page 1`: 과정 생성/목록/선택, 동적 강사 블록, 파일/YouTube 입력, 완료 버튼
  - `Page 2`: 4단 스크롤 결과 페이지, mode toggle, rose chart, wordcloud, 평균/강사별 bar, 목표 대비 line
  - `Page 3`: 솔루션 인사이트 페이지, 외부 동향 슬롯 placeholder
- Airtable 톤 기반 UI 재구성 완료
  - `.agent/DESIGN.md`를 새 reference 기준으로 교체
  - `Page 1`을 헤더 액션 + 중앙 업로드 workspace 중심으로 단순화
  - `Page 2`를 compact 4-panel dashboard 로 재구성
  - `Page 3`를 같은 톤의 compact insight layout 으로 정리
  - 최근 작업 목록과 상태 칩 정리
- 배포 준비 파일 추가 완료
  - `.env.example`
  - `render.yaml`
- 페이지별 UI 요구사항 문서 추가
  - `.agent/Components.md`에 메인 페이지, 첫 번째 결과 페이지, 솔루션 페이지 명세 정리
- 시각 디자인 계약 문서 추가
  - `.agent/DESIGN.md`에 전체 웹 작업물의 톤, 색상, 타이포, 컴포넌트 스타일 규칙 정리
- repo-local 디자인 스킬 추가
  - `final-edu-design` 스킬 생성
  - scored reviewer loop, subagent workflow, screenshot capture script, review rubric 문서화
  - Page 1, Page 2/3 기준 forward-test 로 workflow 전달력 점검
  - 실제 UI 구현 라운드에서 subagent reviewer loop 사용
  - 최신 reviewer pass 점수: `93/100`

## Verified Working

- `uv sync` 성공
- 앱 팩토리 import 및 route 등록 성공
- `GET /health` 정상 응답
- 루트 화면 렌더링 성공
- 샘플 텍스트 자산 2개 기준 Job 생성 -> 상세 화면 -> 결과 렌더링 성공
- `GET /jobs/{job_id}/status` 정상 응답
- 최근 작업 목록에 새 Job 반영 성공
- 잘못된 커리큘럼 입력 시 `400` 에러 렌더링 확인
- `uv run python -m final_edu --help` 정상 응답
- inline 모드에서 `final_edu.jobs.create_job_services()` import / 생성 성공
- `uv run python -m final_edu --reload --port 8011` 정상 기동 및 종료 확인
- `POST /courses/preview`, `POST /courses`, `GET /courses` 흐름 정상
- `/jobs/{job_id}`와 `/jobs/{job_id}/solutions` 렌더링 정상
- `node --check final_edu/static/app.js` 통과
- `python3 -m py_compile final_edu/*.py` 통과
- `final-edu-design` 스킬 `SKILL.md` frontmatter / `agents/openai.yaml` 메타데이터 수동 검증 완료
- `final-edu-design`의 `capture_pages.py` 문법 검증 완료
- `final-edu-design` 스킬을 사용한 subagent forward-test 2건 통과
- `final-edu-design` 스킬을 사용한 실제 screenshot + reviewer loop 완료
- design-review 스크린샷 세트 생성 완료
  - 경로: `.final_edu_runtime/design-review/three-page-ui/`
- 최종 reviewer 결과: `93/100`, hard-fail 없음, pass
- `cmux` 브라우저 surface 로 `GET /`, 모달 열기, 과정 목록 패널 열기 검수 가능 여부 확인
- `capture_pages.py --backend auto`로 desktop은 `cmux`, mobile은 Playwright fallback 이 실제로 동작함을 검증
- Page 1 핵심 요소에 `data-testid`를 추가해 automation selector를 안정화
- Airtable redesign 캡처 세트 생성 완료
  - 경로: `.final_edu_runtime/design-review/airtable-redesign/`
- TestClient 기준 `GET /`, `GET /health`, `/jobs/{job_id}`, `/jobs/{job_id}/solutions` 렌더링 재검증 완료
- TestClient 기준 매우 긴 PDF 파일명으로 `POST /courses/preview`, `POST /courses` 재현 검증 통과
- TestClient 기준 매우 긴 강의자료 파일명으로 단일 강사 `POST /analyze` 재현 검증 통과

## Known Gaps / Next Priorities

- 실제 교육용 데모 데이터셋이 아직 없음
- Render 실배포 검증은 아직 하지 않음
- R2와 Render KV를 실제로 연결한 worker 경로는 아직 검증하지 않음
- 현재 `rq 2.7.0` 기준 Windows의 별도 worker 실행은 `fork` 컨텍스트 제약 가능성이 있어 WSL/Linux 또는 배포 환경 검증이 더 적합함
- YouTube transcript 실패 케이스를 더 다듬을 필요가 있음
- 외부 동향 슬롯은 현재 placeholder 수준이며 실검색/실반영은 미구현
- captionless YouTube STT 파이프라인은 아직 없음
- `Page 2`/`Page 3` 모바일 밀도와 `Page 1` vertical breathing room 은 선택적 polish 여지가 남아 있음
- 현재 `cmux`는 WKWebView 제약으로 mobile viewport를 직접 제어하지 못하므로 mobile 캡처는 Playwright fallback을 사용해야 함
- 실제 Haas 폰트 자산은 저장소에 없으므로 runtime 구현은 `Inter + Korean fallback` 기반이다
- 결과 페이지에서 요구하는 `only발화` 모드는 자막 없는 영상까지 포함하려면 STT 파이프라인이 추가로 필요하다
- 솔루션 페이지의 외부 조사 기반 인사이트는 고위험 확장 기능이며 아직 구현되지 않았다
- 자막 없는 영상 STT fallback 은 아직 미구현
- 스캔 PDF / 이미지 기반 PPTX는 정확도가 낮음

## Working Tree Notes

- 기존 MVP 구현은 현재 `dev` 브랜치에 커밋되어 원격까지 푸시된 상태다
- 다음 작업자는 시작 전에 `git status --short --branch`를 확인해야 한다
- 현재 기준점은 과정 저장/선택, 3페이지 UI, mode별 결과 계산, insight fallback, reviewer pass까지 로컬에서 구현된 상태다
- 현재 라운드 변경은 `dev` 브랜치에서 Page 1 minimal composer 재설계, 단일 강사 허용, 긴 파일명 안전 처리, 과정별 draft 복원, 문서 계약 정리를 포함한다
- 루트 `AGENTS.md`는 bootstrap entrypoint 로 유지되고, canonical 운영 문서는 `.agent/` 아래에서 관리된다
- 다음 작업자는 이 브랜치 기준으로 바로 후속 작업을 이어가면 된다
- `.agent/STATUS.md`는 현재 사실을 기록하는 문서이며, 방금 만든 모든 커밋 해시를 계속 덧붙이는 용도로 쓰지 않는다

## Recent Updates

### 2026-04-06

- 공모전용 공용 저장소 초기화
- `uv` 기반 Python 협업 환경 구성
- `main` 브랜치에 초기 협업 환경 커밋 및 첫 푸시 완료
- IDE 실행 설정 추가

### 2026-04-06 to 2026-04-07

- 강의 커리큘럼 커버리지 분석 MVP 구현 시작
- FastAPI+Jinja 웹 앱, 추출기, 분석기, 템플릿, 배포 설정 추가
- 로컬 smoke test 와 HTTP 레벨 검증 통과

### 2026-04-09

- 루트 `AGENTS.md`와 `.agent/AGENTS.md`의 DEBUG preflight 규칙을 `전체 정독` 대신 `How To Use + Always Read + Incident Index + matched incident 본문` 기준으로 재정의
- subagent handoff template 에 `Consulted DEBUG IDs` 필드를 추가
- `.agent/DEBUG.md`를 stable ID(`DBG-001` 형식), `Always Read`, `Incident Index`, `Active Incidents`, `Archive` 구조로 재편
- 과거 incident 는 index 기반 선택 조회가 가능하도록 재정리하고, 현재 재발 가능성이 높은 항목만 `Active Incidents`로 유지
- `.agent/references/` 의존을 제거하고 Page 1 구현 기준을 첨부 이미지 + 문서 계약으로 단순화
- `.agent/Components.md`를 중앙 popup + chat-style composer + 단일 강사 허용 기준으로 재작성
- 첫 메인페이지를 white/blue minimal shell 로 재구성
- `CourseRecord`와 `/courses` 응답에 `instructor_names`를 추가
- 과정 추가 popup 에서 PDF 1개 + 강사명 comma token 입력을 저장하도록 변경
- `/analyze`와 `analysis.py`의 최소 강사 수 제한을 1명으로 완화
- TestClient 기준 단일 강사 course 생성, analyze, `/jobs/{job_id}`, `/jobs/{job_id}/solutions` 렌더링 재검증 완료
- 과정 PDF와 강의자료 업로드 경로 생성에 공용 safe filename helper 를 적용
- local object storage 에 key component 길이 guard 를 추가해 긴 파일명 오류를 더 빠르게 식별 가능하게 함
- 사용자 긴 파일명 재현 로그의 `OSError: [Errno 63] File name too long` 문제를 해소
- Page 1의 과정 추가/과정 목록 popup 이 좌측에 붙던 CSS 회귀를 수정해 다시 정중앙 overlay 로 표시되도록 복구
- 과정 추가 modal 의 강사명 token input 에서 backspace 로 마지막 token 이 지워지지 않도록 바꾸고 `x` 클릭 삭제만 허용하도록 조정
- 과정 추가 modal 의 파일/강사 token `x` 아이콘을 y축 중앙에 맞추고, 하단 `취소` / `저장` 버튼을 우측 하단 정렬로 정리
- 과정 추가 modal 의 저장 버튼은 preview/save 진행 중에도 텍스트를 `저장`으로 유지하도록 조정
- Page 1 composer 의 상태 메시지를 lane 우측 상단으로 옮기고, 강사 선택 UI를 visible select 대신 icon trigger + dropdown menu 로 전환
- Page 1 composer capsule 높이와 내부 간격을 더 줄여 전체 자료 업로드 lane 을 더 얇게 정리
- 과정 미선택 empty-state 문구를 별도 블록 대신 lane 중앙 문구로 옮기고, 파일 모드 안내 텍스트를 composer 중앙 정렬로 조정
- Page 1 status message 를 lane 우측 상단 바깥쪽으로 더 밀어내어 업로드 capsule 바깥에서 보이도록 조정
- Page 1 자료 업로드 안내 문구가 좌우 아이콘과 y축 기준으로 더 정확히 중앙에 오도록 lane middle surface 의 수직 정렬을 보정
- 과정 목록 popup 에서 과정을 다시 선택하면 현재 세션의 과정별 lane draft 를 보존하고, 저장된 최근 job payload 가 있으면 강사별 파일/유튜브 입력을 복원하도록 보강
- `GET /jobs/{job_id}/assets/{instructor_index}/{asset_index}` 다운로드 경로를 추가해 Page 1 draft 복원 시 저장된 업로드 파일을 다시 `File` 객체로 채울 수 있게 함
- Page 1 lane 상태 메시지에 선택된 강사가 있으면 `상태 / 강사명` 형식으로 함께 표시되도록 조정
- Page 1 lane 상태 메시지가 강사 선택 UI와 드리프트하지 않도록 block state, hidden input, trigger attribute를 함께 참조해 강사명을 안정적으로 표시하도록 보강
- Page 1 lane 상태 메시지는 기본 라벨과 선택 강사명을 분리해 렌더하고, 강사명은 status element attribute + CSS pseudo content로 붙여 보이도록 보강
- Page 1 lane 의 파일/유튜브 토큰을 공통 하단 rail 로 통합해 현재 모드와 관계없이 같은 위치에서 함께 보이도록 정리
- Page 1 공통 asset rail 의 chip 은 동일한 기본 스타일을 유지하고, 작은 파일 / YouTube 표식만으로 타입을 구분하도록 정리
- Page 1 stacked lane 의 상태 메시지가 이전 lane 영역을 침범하지 않도록 lane 간격과 status offset 을 조정
- Page 1 analyze 제출 직전에 hidden input 을 강사 선택 상태와 다시 동기화해 실제 강사명이 job payload 에 저장되도록 보강
- 기존 persisted draft 에 `강사 1/강사 2` 형태로 남은 payload 는 현재 과정 roster 순서를 이용해 강사명 fallback 복원을 시도하도록 보강
- Page 1 파일 drag/drop target 을 중앙 surface 일부가 아니라 lane 의 흰 capsule 전체로 확장
- 유튜브 모드에서도 같은 lane 의 흰 capsule 에 파일을 drop 하면 파일을 추가하고 files 모드로 전환하도록 보강
- YouTube playlist URL 을 `yt-dlp` 기반으로 내부 영상 URL들로 확장하는 prepare 단계 추가
- `POST /analyze/prepare`, `POST /analyze/prepare/{request_id}/confirm` 2단계 제출 흐름 추가
- playlist prepare modal 에 확장 영상 수, 총 재생시간, 예상 chunk, 예상 비용, warning 표시 추가
- 대용량 YouTube 는 threshold hybrid 정책으로 추천 모드를 계산하고, lexical streaming 경로를 기본값으로 사용하도록 보강
- embeddings 호출은 batched request 로 나누어 대용량 input 한도 초과 가능성을 낮추도록 보강
- `/jobs/{job_id}/status` 와 running UI 에 phase / progress / 자막 성공·실패 집계를 노출하도록 확장
- 과정 preview 파이프라인을 휴리스틱-only 성공 흐름에서 API 기반 문서 판별 + 구조화 추출 + 로컬 저장 가드 방식으로 교체
- OpenAI 커리큘럼 검증이 가능하면 실제 커리큘럼 여부, 섹션 구조, 비중 근거를 먼저 판별한 뒤에만 자동 승인하도록 보강
- OpenAI 커리큘럼 검증이 불가한 환경에서는 자동 승인하지 않고 `review_required` 또는 `rejected`만 반환하도록 보수적으로 변경
- 커리큘럼 preview 의 기본 섹션 자동 생성과 텍스트 조각 fallback 자동 성공 경로를 제거
- 비중 근거가 없는 섹션은 자동으로 100으로 정규화하지 않고 수동 입력이 필요하도록 변경
- `/courses` 저장 시 대주제 비중이 비어 있거나 0 이하이면 400으로 거부하도록 서버 검증 추가
- 과정 preview UI 에서 `확인 필요`, `경고`, `판정 근거` 상세 블록은 제거하고, 단일 상태 문구 + 필요 시 편집 표만 남기도록 단순화
- `pypdf`의 `layout` 추출 텍스트를 별도로 보존해 시간표형 PDF의 행/열 구조를 preview 단계에서 활용하도록 보강
- 시간표형 커리큘럼은 로컬 schedule parser 가 `오전/오후` slot 수를 집계해 `schedule_slots` 비중을 자동 산출하고, 신뢰도가 충분하면 `accepted`로 저장 가능 상태까지 올리도록 보강
- OpenAI classification 이 sparse 시간표를 `not_curriculum`으로 오판해도, 주차/요일/세션 구조와 커리큘럼 힌트가 충분하면 로컬 schedule parser 결과를 우선해 false reject 를 피하도록 보강

### 2026-04-07

- 운영 문서 체계 도입 및 반영 완료
- `.agent/AGENTS.md`를 운영 계약 문서 source of truth 로 확장
- `.agent/STATUS.md`, `.agent/DEBUG.md` 생성
- 작업 시작/종료 시 문서 갱신 워크플로우 고정
- 중대한 변경사항 발생 시 `.agent/AGENTS.md`까지 함께 수정하는 규칙 추가
- subagent 병렬 작업 규칙 구체화
- dispatch matrix, 병렬 수 제한, handoff/integration gate, stable parallel lane 개념 추가
- 기능 브랜치 `feat/mvp-curriculum-coverage` 생성
- 커밋 `836c53d` (`feat: add curriculum coverage MVP`) 생성
- 원격 `origin/feat/mvp-curriculum-coverage`로 푸시 및 추적 브랜치 설정 완료
- 중복 역할의 `CONTRIBUTING.md` 삭제
- 협업/운영 규칙 문서를 `.agent/AGENTS.md` 중심으로 정리
- 즉시 분석 구조를 Job 기반 배치 아키텍처로 전환 시작
- `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/worker.py` 추가
- `POST /analyze`를 Job enqueue 방식으로 변경
- `/jobs/{job_id}`, `/jobs/{job_id}/status` 추가
- 로컬 개발용 `inline/local` fallback 추가
- `.env.example`, `README.md`, `render.yaml`을 Web + Worker + KV + R2 기준으로 갱신
- 로컬 TestClient 기준 Job 생성/상태/결과 검증 통과
- 샌드박스 밖 실행으로 `uv.lock` 갱신 완료
- `uv sync` 완료 및 새 의존성(`boto3`, `redis`, `rq`) 설치 반영
- `.agent/STATUS.md`의 작업 트리 상태를 실제 clean 상태로 정정
- `.agent/AGENTS.md`에 커밋/푸시 후 `.agent/STATUS.md` 재검증 규칙 추가
- 커밋/푸시 후 `.agent/STATUS.md`가 무한히 다시 수정되지 않도록 close-out 규칙을 현재 사실 중심으로 정리
- 저장소 루트 `.env` 자동 로딩 추가
- 로컬 개발에서 OpenAI 키를 `.env`에만 두고도 앱이 설정을 읽도록 정리
- `.env` 자동 로딩 변경을 `feat/mvp-curriculum-coverage` 브랜치에 커밋 및 푸시 완료
- Windows에서 `uv run python -m final_edu --reload` 실행 시 `rq`의 `fork` import 로 깨지던 문제 원인 확인
- `final_edu/jobs.py`에서 Redis/RQ import 를 지연 로드로 변경해 inline/local 웹 startup 경로에서 `rq` top-level import 제거
- `final_edu/worker.py`에서 `REDIS_URL` 선검사와 Windows `fork` 제약 안내 메시지 추가
- `README.md`에 Windows 로컬 웹 실행과 worker 제약 메모 반영
- inline 모드 서비스 생성, `/health`, 샘플 job 생성, 실제 `--reload` 기동까지 재검증 완료
- Windows 로컬 startup 호환성 패치 커밋을 `feat/mvp-curriculum-coverage` 브랜치에 푸시 완료
- 현재 지원 범위를 명확히 하기 위해 `.agent/STATUS.md`에 YouTube 재생목록 자동 확장 미구현 상태를 반영
- 메인 페이지 UI 요구사항을 `.agent/Components.md`로 문서화
- `Web / Demo Agent`가 UI 작업 전에 `.agent/Components.md`를 참고하도록 운영 문서에 반영
- 전체 웹 작업물의 시각 톤을 `.agent/DESIGN.md`로 문서화
- `Web / Demo Agent`가 UI 작업 전에 `.agent/Components.md`와 `.agent/DESIGN.md`를 함께 참고하도록 운영 문서에 반영

### 2026-04-08

- `.agent/DESIGN.md`를 Airtable reference 기준으로 교체
- 루트 `AGENTS.md`, `.agent/AGENTS.md`, `.agent/Components.md`, `final-edu-design` 스킬 문서에서 새 reference 파일을 읽도록 갱신
- `base.html`, `styles.css`를 white canvas + deep navy + Airtable blue 톤으로 재구성
- `Page 1`에서 hero, 과정 카드 그리드, 최근 작업 패널을 제거하고 중앙 업로드 workspace 중심으로 단순화
- `Page 2`를 donut + wordcloud + stacked bars + multi-instructor comparison 의 4-panel dashboard 로 재구성
- `Page 3`를 compact intro + insight grid + trend status card 구조로 정리
- `final_edu/static/app.js`에서 선택 과정 표시 sync, Page 2 segmented control, 다중 강사 비교 차트 로직을 보강
- TestClient 기준 `/`, `/health`, `/jobs/{job_id}`, `/jobs/{job_id}/solutions` 200 응답 재확인
- `capture_pages.py --backend auto`로 새 Airtable redesign desktop 캡처 세트 생성

- `test` 브랜치에서 확인한 오래된 데모 버전과 분리해, 실제 구현/수정 기준 브랜치를 다시 `dev`로 고정
- `cmux` 브라우저 surface 로 로컬 Uvicorn 페이지를 직접 열고 snapshot/screenshot/click 검증 경로를 재확인
- 디자인 검수 표준 경로를 `cmux 우선 + Playwright fallback`으로 정리
- `capture_pages.py`를 `auto|cmux|playwright` backend 지원 형태로 확장
- `cmux`는 desktop/tablet, Playwright는 mobile fallback 으로 쓰도록 스킬 문서와 운영 문서 갱신
- Page 1/2/3 핵심 UI 요소에 `data-testid`를 추가해 자동화 selector를 안정화

- 현재 작업 브랜치 이름을 `feat/mvp-curriculum-coverage`에서 `dev`로 변경
- 새 원격 추적 브랜치 `origin/dev` 생성 및 업스트림 전환 완료
- 기존 원격 `origin/feat/mvp-curriculum-coverage` 삭제 완료
- 현재 작업 기준 브랜치는 `dev`로 통일
- `.agent/Components.md`를 3페이지 구조 기준으로 확장
- Page 1에 목표 비중 수정형 `Add Course` 모달과 `enter-like` 완료 버튼 요구사항 추가
- Page 2에 4단 스크롤 결과 페이지와 `only발화 / only자료 / 발화+자료` 토글 요구사항 추가
- Page 3에 5~6개 인사이트 중심의 솔루션 페이지 요구사항 추가
- STT 의존 기능과 외부 조사 기반 인사이트를 고위험 범위로 명시
- repo-local 디자인 스킬 `final-edu-design` 생성
- `.agent/AGENTS.md`에 디자인 관련 작업 시 `final-edu-design` 스킬 참조 의무 추가
- 디자인 작업 완료 정의에 screenshot artifact 와 reviewer `90점` 기준 추가
- subagent 2개로 `Page 1`, `Page 2/3` 기준 forward-test 수행
- forward-test 결과를 반영해 contract lock 항목에 route/state 전달 방식, 차트 구현 방식, editable form 형태를 추가
- 운영 문서 5종을 `.agent/` 폴더 아래로 이동
- 루트 `AGENTS.md`는 다음 에이전트 자동 진입을 위한 bootstrap 파일로 축소
- 디자인 스킬과 README의 문서 참조 경로를 `.agent/` 기준으로 갱신
- 과정 저장/선택을 위한 `courses` 저장소와 preview/save/list/get 라우트 구현
- `Page 1` 메인 입력 화면을 과정 선택형 워크스페이스로 재구성
- `Page 2` 4단 스크롤 결과 페이지 구현
- `Page 3` 솔루션 인사이트 페이지 구현
- 분석 결과에 `material / speech / combined` mode series, keyword cloud, rose/bar/line 시리즈 추가
- 솔루션 인사이트 1~5에 대해 `gpt-5.4-mini` 기반 생성 + deterministic fallback 구현
- `final-edu-design` 스킬 workflow 로 screenshot artifact 세트 생성
- reviewer loop 최종 결과 `93/100` pass 확보
