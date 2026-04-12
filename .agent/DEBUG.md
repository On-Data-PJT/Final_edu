# DEBUG

Last Updated: 2026-04-12

이 문서는 **실제로 발생했고 해결된 오류만** 기록합니다.
preflight 목적은 전체 archive 를 정독하는 것이 아니라, 현재 작업과 맞는 재발 방지 규칙을 빠르게 찾는 것입니다.

## How To Use

1. 먼저 `Always Read`를 읽습니다.
2. 그다음 `Incident Index`를 훑고 현재 작업의 `Lane`, `Related Files`, `Trigger Commands`, `Tags`, `Must Read When`과 맞는 incident ID를 찾습니다.
3. 일치하는 incident 본문만 추가로 읽습니다.
4. 아래 작업은 index 매칭과 별개로 `Active Incidents` 전체를 읽습니다.
   - startup / dependency 변경
   - queue / storage 변경
   - 디자인 검수 자동화 변경
   - release 직전 점검
   - wide refactor
   - 원인 불명 회귀 조사
5. 작업 종료 handoff 에는 `Consulted DEBUG IDs`를 남기고, 맞는 항목이 없었으면 `none matched`로 적습니다.

- `active`: 현재 워크플로우에서 다시 발생하기 쉬워 preflight 대상이 되는 incident
- `archived`: 기록은 유지하지만 기본 preflight 에서는 index만 보고, 필요할 때만 본문을 여는 incident
- incident ID 는 stable ID 입니다. 기존 ID 는 바꾸지 말고, 새 항목은 `DBG-018`부터 append-only 로 추가합니다.

## Always Read

- 실행/패키징 이상 징후가 있어도 먼저 `uv run python -m final_edu` 또는 `.venv/bin/python` 기준으로 앱 경로를 검증합니다.
- `inline/local` fallback 이 있는 기능은 fallback 경로를 결정하기 전에 Redis/RQ 같은 optional backend 를 top-level import 하지 않습니다.
- FastAPI `Annotated` 파라미터에서는 default 값을 `Form()` / `File()` / `Query()` 안에 넣지 말고 `=` 오른쪽에 둡니다.
- Jinja context 키에는 `items`, `keys`, `values`, `get`처럼 dict 메서드와 충돌하는 이름을 피합니다.
- 템플릿에 JSON payload 를 심을 때는 `<script type="application/json">`만 믿지 말고 `hidden` 또는 명시적 비표시 처리를 함께 둡니다.

## Incident Index

- `DBG-001` `archived` Lane: `Lead / Integration`
  Tags: `packaging`, `uv`, `src-layout`
  Related Files: `pyproject.toml`, 패키지 레이아웃
  Trigger Commands: `uv sync`, `uv run final-edu`, `python -c "import final_edu"`
  Must Read When: `src layout` 재도입, 실행 entrypoint 전략 변경
- `DBG-002` `archived` Lane: `Web / Demo Agent`
  Tags: `fastapi`, `forms`, `typing`
  Related Files: `final_edu/app.py`
  Trigger Commands: 앱 startup, route registration
  Must Read When: `Form()` / `File()` / `Query()` 선언 변경
- `DBG-003` `archived` Lane: `Web / Demo Agent`
  Tags: `fastapi`, `starlette`, `templates`
  Related Files: `final_edu/app.py`
  Trigger Commands: `GET /`, 템플릿 렌더링
  Must Read When: `TemplateResponse` 호출 방식 변경, FastAPI / Starlette 업그레이드
- `DBG-004` `archived` Lane: `Web / Demo Agent`
  Tags: `jinja`, `template-context`, `naming`
  Related Files: `final_edu/templates/index.html`
  Trigger Commands: 결과 페이지 렌더링
  Must Read When: 템플릿 context 구조/키 이름 변경
- `DBG-005` `active` Lane: `Lead / Integration`
  Tags: `tooling`, `uv`, `sandbox`, `macOS`
  Related Files: `.venv`, `pyproject.toml`, `uv` 실행 경로
  Trigger Commands: `uv lock`, `uv sync`
  Must Read When: 의존성 변경, sandbox 안 `uv` panic 조사
- `DBG-006` `active` Lane: `Lead / Integration`
  Tags: `windows`, `startup`, `rq`, `redis`, `lazy-import`
  Related Files: `final_edu/app.py`, `final_edu/jobs.py`, `final_edu/worker.py`
  Trigger Commands: `uv run python -m final_edu --reload`, worker startup
  Must Read When: queue / startup / backend import 변경
- `DBG-007` `archived` Lane: `Lead / Integration`
  Tags: `skills`, `validation`, `pyyaml`
  Related Files: `skill-creator` 검증 스크립트
  Trigger Commands: `python3 .../quick_validate.py`
  Must Read When: `skill-creator` 검증 스크립트 사용
- `DBG-008` `active` Lane: `Web / Demo Agent`
  Tags: `design-review`, `automation`, `selectors`, `playwright`, `cmux`
  Related Files: `./.codex/skills/final-edu-design/references/artifacts.md`, `final_edu/templates/index.html`
  Trigger Commands: `capture_pages.py`, reviewer manifest 실행
  Must Read When: DOM 구조 변경, 디자인 검수 selector 변경
- `DBG-009` `active` Lane: `Lead / Integration`
  Tags: `cmux`, `playwright`, `mobile`, `viewport`
  Related Files: `final-edu-design` 스킬 문서, 디자인 검수 스크립트
  Trigger Commands: `capture_pages.py --backend auto`, `cmux rpc browser.viewport.set`
  Must Read When: mobile screenshot 경로, capture backend 정책 변경
- `DBG-010` `active` Lane: `Web / Demo Agent`
  Tags: `templates`, `json`, `screenshots`, `visibility`
  Related Files: `final_edu/templates/index.html`, `final_edu/templates/job.html`, `final_edu/templates/solutions.html`
  Trigger Commands: 브라우저 렌더링, 스크린샷 검수
  Must Read When: 템플릿에 JSON payload 삽입/변경
- `DBG-011` `archived` Lane: `Web / Demo Agent`
  Tags: `page1`, `course-selection`, `state-sync`
  Related Files: `final_edu/static/app.js`, `final_edu/templates/index.html`
  Trigger Commands: 과정 선택 UI 상호작용
  Must Read When: `selected-course-name` 또는 선택 과정 hidden field 변경
- `DBG-012` `active` Lane: `Lead / Integration`
  Tags: `uploads`, `storage`, `filenames`, `filesystem`
  Related Files: `final_edu/courses.py`, `final_edu/app.py`, `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/utils.py`
  Trigger Commands: `POST /courses`, `POST /analyze`, 로컬 object storage 저장
  Must Read When: 업로드 key, temp path, local storage path 변경
- `DBG-013` `active` Lane: `Web / Demo Agent`
  Tags: `css`, `overlay`, `modal`, `layout`
  Related Files: `final_edu/static/styles.css`
  Trigger Commands: 과정 추가 popup, 과정 목록 popup 열기
  Must Read When: overlay open state, modal shell, floating panel CSS 변경
- `DBG-014` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `status-label`, `instructor-picker`, `state-sync`
  Related Files: `final_edu/static/app.js`
  Trigger Commands: lane 복원, 강사 선택, 상태 메시지 갱신
  Must Read When: lane status, 강사 picker, draft restore 변경
- `DBG-015` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `submit-sync`, `draft-restore`, `roster`
  Related Files: `final_edu/static/app.js`
  Trigger Commands: `POST /analyze`, persisted draft 복원
  Must Read When: analyze submit payload, roster 복원 로직 변경
- `DBG-016` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `drag-drop`, `hit-area`, `composer`
  Related Files: `final_edu/static/app.js`, `final_edu/templates/index.html`, `final_edu/static/styles.css`
  Trigger Commands: 파일 drag/drop
  Must Read When: composer lane, drop target, mode switching 변경
- `DBG-017` `archived` Lane: `Web / Demo Agent`
  Tags: `page1`, `busy-state`, `validation`, `modal`
  Related Files: `final_edu/static/app.js`
  Trigger Commands: 과정 preview/save 직후 버튼 상태 갱신
  Must Read When: course modal save button, `setBusy()`, validation disabled 로직 변경
- `DBG-019` `active` Lane: `Lead / Integration`
  Tags: `courses`, `preview`, `pdf`, `layout`, `schedule`
  Related Files: `final_edu/courses.py`
  Trigger Commands: `POST /courses/preview`, 시간표형 커리큘럼 PDF preview
  Must Read When: 커리큘럼 preview 추출, PDF text normalization, 시간표형 비중 산출 규칙 변경
- `DBG-020` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `preview`, `openai`, `timeout`, `threadpool`
  Related Files: `final_edu/app.py`, `final_edu/courses.py`, `final_edu/config.py`
  Trigger Commands: `POST /courses/preview`, `GET /health`
  Must Read When: 과정 preview 경로, OpenAI curriculum preview timeout, page1 loading hang 변경
- `DBG-021` `active` Lane: `Lead / Integration`
  Tags: `youtube`, `playlist`, `watch-url`, `prepare-confirm`
  Related Files: `final_edu/youtube.py`, `final_edu/app.py`
  Trigger Commands: `POST /analyze/prepare`, `resolve_youtube_input()`
  Must Read When: YouTube URL 분기 규칙, playlist 확장, prepare 단계의 영상 수 추정 변경
- `DBG-022` `archived` Lane: `Lead / Integration`
  Tags: `youtube`, `proxy`, `ipblocked`, `worker`, `prepare-confirm`
  Related Files: `final_edu/youtube.py`, `final_edu/extractors.py`, `final_edu/config.py`, `render.yaml`
  Trigger Commands: `POST /analyze/prepare`, transcript fetch, `uv run python -m final_edu.worker`
  Must Read When: proxy 경로를 다시 도입하거나 과거 transcript unblock 이력을 확인할 때
- `DBG-023` `active` Lane: `Lead / Integration`
  Tags: `youtube`, `cache`, `throttle`, `worker`, `prepare-confirm`
  Related Files: `final_edu/youtube.py`, `final_edu/extractors.py`, `final_edu/youtube_cache.py`, `final_edu/config.py`
  Trigger Commands: `POST /analyze/prepare`, transcript fetch, `uv run python -m final_edu.worker`
  Must Read When: YouTube cache key / TTL / request spacing / prepare-worker parity 변경
- `DBG-024` `active` Lane: `Lead / Integration`
  Tags: `voc`, `payload`, `worker`, `review`, `solution`
  Related Files: `final_edu/app.py`, `final_edu/jobs.py`, `final_edu/models.py`, `final_edu/analysis.py`
  Trigger Commands: `POST /analyze/prepare`, worker execution, `GET /review`, `GET /solution`
  Must Read When: 새 입력 타입 추가, result schema 변경, VOC/별도 분석 경로 연결 변경
- `DBG-025` `active` Lane: `Lead / Integration`
  Tags: `settings`, `openai`, `solution`, `review`, `config-drift`
  Related Files: `final_edu/app.py`, `final_edu/config.py`
  Trigger Commands: `GET /solution`, `POST /api/evaluate`
  Must Read When: route-level model 선택, OpenAI settings 필드 변경
- `DBG-026` `active` Lane: `Lead / Integration`
  Tags: `youtube`, `yt-dlp`, `metadata`, `proxy`, `prepare-confirm`
  Related Files: `final_edu/youtube.py`, `final_edu/app.py`
  Trigger Commands: `POST /analyze/prepare`, `summarize_youtube_inputs()`
  Must Read When: yt-dlp metadata 옵션, ScraperAPI 적용 범위, prepare 단계 500 회귀 변경
- `DBG-027` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `restore`, `manifest`, `voc`, `mode`
  Related Files: `final_edu/static/app.js`, `final_edu/app.py`, `final_edu/models.py`, `tests/test_page1_restore.py`
  Trigger Commands: `GET /`, `POST /analyze/prepare`, persisted draft restore
  Must Read When: lane mode persistence, course restore draft serializer, VOC chip/status 표시 변경
- `DBG-028` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `loading`, `prepare-confirm`, `inline-queue`, `ux`
  Related Files: `final_edu/templates/index.html`, `final_edu/static/app.js`, `final_edu/static/styles.css`
  Trigger Commands: `POST /analyze/prepare`, `POST /analyze/prepare/{request_id}/confirm`, `POST /analyze`
  Must Read When: Page 1 submit loading indicator, prepare modal handoff, inline queue 대기 UX 변경
- `DBG-031` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `page2`, `source-mode`, `voc`, `availability`
  Related Files: `final_edu/templates/index.html`, `final_edu/static/app.js`, `final_edu/templates/job.html`, `final_edu/analysis.py`, `tests/test_page1_restore.py`, `tests/test_page2_dashboard.py`
  Trigger Commands: `GET /`, `POST /analyze/prepare`, `/jobs/{job_id}` Page 2 mode toggle
  Must Read When: Page 1 source input 구조, Page 2 mode availability, material/speech empty-state 계약을 바꿀 때
- `DBG-032` `active` Lane: `Web / Demo Agent`
  Tags: `page1`, `submit`, `formdata`, `restore`, `legacy`
  Related Files: `final_edu/static/app.js`, `final_edu/app.py`, `final_edu/models.py`, `tests/test_page1_restore.py`
  Trigger Commands: `POST /analyze/prepare`, 과정 선택 후 persisted draft auto-restore
  Must Read When: Page 1 submit payload source of truth, hidden file input sync, draft versioning 규칙 변경
- `DBG-033` `active` Lane: `Web / Demo Agent`
  Tags: `page2`, `material`, `chunking`, `unmapped`, `donut`
  Related Files: `final_edu/analysis.py`, `final_edu/utils.py`, `final_edu/templates/job.html`, `tests/test_page2_dashboard.py`
  Trigger Commands: `/jobs/{job_id}` Page 2 material toggle, material PDF/PPTX 분석
  Must Read When: material chunking, Page 2 donut 비율 표시, `미분류` series 계약을 바꿀 때
- `DBG-034` `active` Lane: `Web / Demo Agent`
  Tags: `page2`, `mapped-only`, `coverage`, `wordcloud`, `empty-state`
  Related Files: `final_edu/analysis.py`, `final_edu/templates/job.html`, `tests/test_page2_dashboard.py`
  Trigger Commands: `/jobs/{job_id}` Page 2 source toggle, 강의자료/발화 커버리지 비중 검토
  Must Read When: Page 2 coverage share 분모, `mapped_tokens`, word cloud/coverage 역할 분리를 바꿀 때
- `DBG-035` `active` Lane: `Web / Demo Agent`
  Tags: `material`, `chunking`, `aliases`, `worksheet-noise`, `assignment`
  Related Files: `final_edu/analysis.py`, `final_edu/utils.py`, `tests/test_page2_dashboard.py`
  Trigger Commands: material PDF/PPTX section assignment, `Deep Learning and Boltzmann` 0% 조사
  Must Read When: material semantic subchunk, section alias glossary, worksheet noise filtering, single-label assignment 규칙을 바꿀 때
- `DBG-036` `active` Lane: `Web / Demo Agent`
  Tags: `speech`, `youtube`, `title-prior`, `decision-tree`, `mismatch`
  Related Files: `final_edu/analysis.py`, `final_edu/extractors.py`, `tests/test_page2_dashboard.py`
  Trigger Commands: `/jobs/{job_id}` speech coverage, YouTube chapter playlist 분석, decision-tree 0% 조사
  Must Read When: speech assignment alias, YouTube title reuse, title rescue prior, transcript/title mismatch warning 규칙을 바꿀 때
- `DBG-037` `active` Lane: `Lead / Integration`
  Tags: `voc`, `excel`, `xlsx`, `xls`, `sheet-selection`
  Related Files: `final_edu/extractors.py`, `final_edu/app.py`, `tests/test_page1_restore.py`, `tests/test_voc_analysis.py`
  Trigger Commands: `POST /analyze/prepare`, VOC Excel upload, `analyze_voc_assets()`
  Must Read When: VOC 입력 포맷 확대, workbook sheet 선택 규칙, VOC spreadsheet row serialization 변경

## Active Incidents

### DBG-005 `active` 이 세션에서 `uv lock` 실행 시 Rust panic 발생

- Date: `2026-04-07`
- Agent / Lane: `Lead / Integration`
- Tags: `tooling`, `uv`, `sandbox`, `macOS`
- Related Files: `.venv`, `pyproject.toml`, `uv` 실행 경로
- Trigger Commands: `source ~/.zshrc; UV_CACHE_DIR=/tmp/uv-cache uv lock`, `uv sync`
- Must Read When: 의존성 변경, sandbox 안 `uv` panic 조사
- Symptom:
  - sandbox 내부에서 `uv lock` 또는 `uv sync` 실행 시 `system-configuration` 관련 panic 이 발생할 수 있음
  - 메시지 요약: `Attempted to create a NULL object`, `Tokio executor failed`
- Root Cause:
  - 저장소 코드 문제가 아니라 현재 세션의 macOS / `uv` 런타임 조합에서 생기는 환경 의존 panic 이었음
- Resolution:
  - 코드 검증은 먼저 `.venv/bin/python`과 TestClient 경로로 진행
  - `uv` 명령은 필요할 때 sandbox 밖에서 재시도해 정상 완료
- Prevention Rule:
  - sandbox 안 `uv` panic 을 앱 버그로 바로 단정하지 말 것
  - 먼저 `.venv/bin/python` 기반 import / smoke test 로 코드 경로를 분리 검증할 것
  - 필요하면 같은 `uv` 명령을 sandbox 밖에서 다시 실행할 것

### DBG-006 `active` Windows에서 `uv run python -m final_edu --reload` 시 `fork` context import 실패

- Date: `2026-04-07`
- Agent / Lane: `Lead / Integration`
- Tags: `windows`, `startup`, `rq`, `redis`, `lazy-import`
- Related Files: `final_edu/app.py`, `final_edu/jobs.py`, `final_edu/worker.py`
- Trigger Commands: `uv run python -m final_edu --reload`, worker startup
- Must Read When: queue / startup / backend import 변경
- Symptom:
  - Windows 에서 reloader child process 가 startup 중 즉시 종료
  - 핵심 에러 메시지: `ValueError: cannot find context for 'fork'`
- Root Cause:
  - `REDIS_URL`이 없으면 `inline/local` fallback 을 써야 하는데, 앱 import 시점에 `rq`가 top-level 로 먼저 import 되었음
  - `rq 2.7.0`이 worker/scheduler 를 로드하면서 `multiprocessing.get_context('fork')`를 호출했고, Windows 에는 `fork`가 없음
- Resolution:
  - Redis/RQ import 를 실제 필요 시점의 lazy import 로 이동
  - 웹 startup 경로에서는 `rq` top-level import 를 피하도록 정리
  - worker 는 `REDIS_URL` 선검사와 더 명확한 오류 메시지를 추가
- Prevention Rule:
  - optional backend dependency 를 웹 앱 import 경로에서 top-level 로 가져오지 말 것
  - `inline/local` fallback 이 있는 기능은 fallback 선택 전에 외부 queue 모듈을 import 하지 말 것
  - Windows 호환성이 필요한 실행 명령은 `--reload` 실제 기동까지 확인할 것

### DBG-008 `active` 디자인 검수 예시 selector 와 실제 DOM 이 어긋나 자동 캡처 실패

- Date: `2026-04-08`
- Agent / Lane: `Web / Demo Agent`
- Tags: `design-review`, `automation`, `selectors`, `playwright`, `cmux`
- Related Files: `./.codex/skills/final-edu-design/references/artifacts.md`, `final_edu/templates/index.html`
- Trigger Commands: `capture_pages.py`, reviewer manifest 실행
- Must Read When: DOM 구조 변경, 디자인 검수 selector 변경
- Symptom:
  - manifest 예시를 그대로 실행하면 `open-course-modal` 클릭 단계에서 timeout 이 발생
- Root Cause:
  - 스킬 문서의 selector 예시와 실제 DOM 의 `data-testid` contract 가 drift 했음
- Resolution:
  - Page 1/2/3 핵심 요소에 `data-testid`를 추가
  - 스킬 문서의 manifest 예시와 실제 DOM selector 를 다시 맞춤
- Prevention Rule:
  - 검수용 selector 는 임시 class 나 문구가 아니라 `data-testid`로 고정할 것
  - UI 구조를 바꾸면 스킬 문서의 manifest 예시도 같이 갱신할 것

### DBG-009 `active` `cmux` 브라우저는 WKWebView 제약으로 mobile viewport 캡처를 직접 지원하지 않음

- Date: `2026-04-08`
- Agent / Lane: `Lead / Integration`
- Tags: `cmux`, `playwright`, `mobile`, `viewport`
- Related Files: `final-edu-design` 스킬 문서, 디자인 검수 스크립트
- Trigger Commands: `capture_pages.py --backend auto`, `cmux rpc browser.viewport.set`
- Must Read When: mobile screenshot 경로, capture backend 정책 변경
- Symptom:
  - `cmux rpc browser.viewport.set` 호출 시 `not_supported: browser.viewport.set is not supported on WKWebView`
- Root Cause:
  - 현재 `cmux` backend 가 WKWebView 기반이라 viewport 제어 기능이 제한됨
- Resolution:
  - 디자인 검수 표준 경로를 `cmux 우선 + Playwright fallback` 으로 정의
  - `capture_pages.py --backend auto`가 desktop/tablet 와 mobile 을 자동 분기하도록 정리
- Prevention Rule:
  - mobile viewport 검수를 `cmux` 단독 경로로 강제하지 말 것
  - `cmux`가 가능해도 mobile screenshot matrix 는 Playwright fallback 을 허용할 것

### DBG-010 `active` JSON 데이터 스크립트가 페이지에 그대로 노출됨

- Date: `2026-04-08`
- Agent / Lane: `Web / Demo Agent`
- Tags: `templates`, `json`, `screenshots`, `visibility`
- Related Files: `final_edu/templates/index.html`, `final_edu/templates/job.html`, `final_edu/templates/solutions.html`
- Trigger Commands: 브라우저 렌더링, 스크린샷 검수
- Must Read When: 템플릿에 JSON payload 삽입/변경
- Symptom:
  - `type="application/json"` 스크립트 payload 가 페이지 하단 텍스트처럼 그대로 노출돼 스크린샷이 깨졌음
- Root Cause:
  - 데이터 전달용 스크립트 태그에 `hidden` 속성이 없어 렌더링 경로에 따라 레이아웃에 잡혔음
- Resolution:
  - 관련 템플릿의 JSON 스크립트 태그에 `hidden`을 추가
- Prevention Rule:
  - JSON payload 를 심을 때는 `type="application/json"`만 믿지 말고 비표시 처리까지 함께 넣을 것
  - reviewer 용 스크린샷 전 raw JSON, raw token, debug text 노출 여부를 먼저 점검할 것

### DBG-012 `active` 긴 원본 파일명을 storage key basename 으로 직접 써서 로컬 파일시스템 한계를 초과함

- Date: `2026-04-09`
- Agent / Lane: `Lead / Integration`
- Tags: `uploads`, `storage`, `filenames`, `filesystem`
- Related Files: `final_edu/courses.py`, `final_edu/app.py`, `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/utils.py`
- Trigger Commands: `POST /courses`, `POST /analyze`, 로컬 object storage 저장
- Must Read When: 업로드 key, temp path, local storage path 변경
- Symptom:
  - 긴 한글/URL-encoded 파일명으로 `POST /courses` 호출 시 `OSError: [Errno 63] File name too long`
- Root Cause:
  - 원본 파일명을 거의 그대로 storage key basename 에 넣었고, 로컬 fallback 에서는 이 key 가 실제 파일 경로로 사용되었음
- Resolution:
  - `build_safe_storage_name()` helper 를 도입해 저장 basename 을 짧은 ASCII-safe 이름으로 통일
  - 로컬 storage 에 path component 길이 guard 를 추가
- Prevention Rule:
  - user-controlled filename 을 local filesystem path component 나 storage key basename 에 직접 넣지 말 것
  - 로컬 fallback 이 파일 경로를 쓰는지 먼저 확인하고, key 생성 시 파일시스템 길이 제한을 기준으로 bounded helper 를 사용할 것
  - 원본 파일명 보존이 필요하면 display metadata 로만 남길 것

### DBG-013 `active` Overlay open state 가 modal centering layout 을 덮어써 Page 1 popup 이 좌측에 붙음

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `css`, `overlay`, `modal`, `layout`
- Related Files: `final_edu/static/styles.css`
- Trigger Commands: 과정 추가 popup, 과정 목록 popup 열기
- Must Read When: overlay open state, modal shell, floating panel CSS 변경
- Symptom:
  - Page 1 우측 상단 아이콘으로 여는 popup 이 화면 중앙이 아니라 좌측 상단 흐름처럼 붙어 보였음
- Root Cause:
  - `.floating-panel.is-open`이 `display: block`을 강제해 `.modal-shell`의 `display: grid` 중앙 정렬을 무효화했음
- Resolution:
  - open state 를 `display: grid`로 바꿔 shell layout 을 유지하도록 수정
- Prevention Rule:
  - overlay open state 클래스가 shell layout (`grid`, `flex`)을 깨지 않는지 먼저 확인할 것
  - visibility 토글과 layout 토글을 같은 규칙에서 처리할 때 class 조합 우선순위를 점검할 것

### DBG-014 `active` Page 1 lane 상태 메시지와 선택 강사 표시가 드리프트함

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `status-label`, `instructor-picker`, `state-sync`
- Related Files: `final_edu/static/app.js`
- Trigger Commands: lane 복원, 강사 선택, 상태 메시지 갱신
- Must Read When: lane status, 강사 picker, draft restore 변경
- Symptom:
  - 강사가 실제로 선택되어 있어도 lane 우측 상단 상태 메시지에는 강사명이 함께 표시되지 않을 수 있었음
- Root Cause:
  - 상태 메시지가 `blockState.instructorName` 하나만 보고 만들어졌고, 실제 선택 UI 는 hidden input / trigger attribute / 복원 state 를 함께 거쳤음
- Resolution:
  - 상태 메시지용 강사명을 여러 source 에서 해석하는 helper 로 보강
  - picker trigger 와 lane dataset 에 현재 강사명을 명시적으로 동기화
  - 강사명은 status element attribute + CSS pseudo content 로 분리 렌더
- Prevention Rule:
  - 복원 가능한 form UI 에서는 상태 라벨을 단일 in-memory field 하나에만 의존하지 말 것
  - 사용자가 눈으로 확인하는 선택 상태가 있으면 hidden input 또는 dataset attribute 에도 같은 값을 동기화할 것
  - 동적 suffix 가 필요한 상태 라벨은 text node 하나보다 DOM attribute + CSS 조합이 더 견고한지 먼저 검토할 것

### DBG-015 `active` Page 1 analyze 제출 시 선택 강사명이 payload 에 저장되지 않아 `강사 1/강사 2`로 대체됨

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `submit-sync`, `draft-restore`, `roster`
- Related Files: `final_edu/static/app.js`
- Trigger Commands: `POST /analyze`, persisted draft 복원
- Must Read When: analyze submit payload, roster 복원 로직 변경
- Symptom:
  - 과정을 다시 선택하면 파일/링크는 복원되지만 어떤 강사에게 연결됐는지 복원되지 않았고, payload 에는 `강사 1`, `강사 2`가 저장돼 있었음
- Root Cause:
  - analyze 제출 직전에 hidden input 의 강사명 값이 최종 UI 상태와 다시 동기화되지 않았음
  - 이미 저장된 draft 중 일부는 generic 강사명을 source 로 삼고 있었음
- Resolution:
  - analyze 제출 직전에 lane 별 hidden input 과 manifest 를 다시 동기화
  - persisted draft 복원 시 generic 강사명은 현재 roster 순서 기반으로 실제 강사명에 재매핑
- Prevention Rule:
  - 화면 선택 상태가 hidden input 을 통해 서버로 넘어가면 submit 직전에 한 번 더 sync 하는 경로를 둘 것
  - 복원 데이터에 generic fallback 값이 남을 수 있으면 canonical roster 와 연결해 복원 보정 규칙을 함께 둘 것

### DBG-016 `active` Page 1 실제 업로드 target 은 현재 source surface 와 일치해야 함

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `drag-drop`, `hit-area`, `composer`
- Related Files: `final_edu/static/app.js`, `final_edu/templates/index.html`, `final_edu/static/styles.css`
- Trigger Commands: 파일 drag/drop
- Must Read When: composer lane, drop target, mode switching 변경
- Symptom:
  - 사용자가 파일을 올린 위치와 실제 저장 bucket 이 다르게 해석되면 `files`와 `voc_files`가 섞일 수 있었음
- Root Cause:
  - visual container 범위를 기준으로 drop target 을 넓히면, dropdown lane 에서는 현재 mode/state 와 source bucket 의미가 다시 뒤섞일 수 있었음
- Resolution:
  - `files`/`voc`는 각 source surface에만 drag/drop과 picker를 바인딩하고, 저장 bucket도 그 surface에 고정
  - `youtube` surface 에서는 파일 drop 을 거부하고 안내를 보여 주도록 정리
- Prevention Rule:
  - dropdown lane 에서 drag/drop과 picker는 항상 현재 source surface 기준으로만 연결할 것
  - lane 전체나 shared mode 값을 보고 upload bucket 을 결정하지 말 것

### DBG-019 `active` 커리큘럼 preview 에서 표 레이아웃을 납작하게 정규화해 시간표형 문서의 비중 근거를 잃음

- Date: `2026-04-09`
- Agent / Lane: `Lead / Integration`
- Tags: `courses`, `preview`, `pdf`, `layout`, `schedule`
- Related Files: `final_edu/courses.py`
- Trigger Commands: `POST /courses/preview`, 시간표형 커리큘럼 PDF preview
- Must Read When: 커리큘럼 preview 추출, PDF text normalization, 시간표형 비중 산출 규칙 변경
- Symptom:
  - 주차별 시간표 PDF를 커리큘럼으로 인식하면서도 비중은 전부 `직접 입력`으로 떨어질 수 있었음
  - 같은 문서가 OpenAI classification 에서는 sparse schedule 로 오판돼 `rejected`까지 내려갈 수 있었음
- Root Cause:
  - `pypdf` 기본 `extract_text()` 결과를 바로 평탄화해 주차/요일/오전·오후의 행 구조가 거의 한 줄로 눌렸음
  - preview 는 `%`, `시간`, `주차`, `일수` 같은 직접 지표만 비중 근거로 봤고, 시간표의 반복 slot 수를 비중으로 환산하지 않았음
  - sparse timetable 은 OpenAI classification 이 syllabus 가 아니라 단순 calendar/schedule 로 보수적으로 판정할 수 있었음
- Resolution:
  - `extract_text(extraction_mode="layout")`를 함께 보존해 preview 에서는 줄 구조가 살아 있는 layout text 를 사용하도록 변경
  - 로컬 schedule parser 를 추가해 `주차 행 + 오전/오후 세션 행`에서 과목 slot 수를 집계하고 `schedule_slots` 비중으로 정규화
  - OpenAI classification 이 timetable 을 `not_curriculum`으로 오판해도, 로컬 parser 가 주차/요일/세션 구조와 커리큘럼 힌트를 충분히 잡으면 parser 결과를 우선하도록 보강
- Prevention Rule:
  - 표/시간표형 PDF는 line-preserving layout text 와 flat text 를 분리해 다룰 것
  - preview 단계에서 전체 텍스트를 바로 한 줄로 눌러버리지 말고, row/column 구조가 필요한 parser 가 있는지 먼저 판단할 것
  - OpenAI classification 이 sparse timetable 을 보수적으로 거절할 수 있으므로, 고신뢰 로컬 parser 가 있으면 reject 조건과 충돌하는지 별도 smoke 로 확인할 것

### DBG-020 `active` Page 1 커리큘럼 preview 가 OpenAI 호출에 막히면 서버 전체가 같이 멈춘 것처럼 보임

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `preview`, `openai`, `timeout`, `threadpool`
- Related Files: `final_edu/app.py`, `final_edu/courses.py`, `final_edu/config.py`
- Trigger Commands: `POST /courses/preview`, `GET /health`
- Must Read When: 과정 preview 경로, OpenAI curriculum preview timeout, page1 loading hang 변경
- Symptom:
  - 과정 추가 popup 에서 PDF를 올린 뒤 `커리큘럼 PDF를 분석하는 중입니다.` 문구만 오래 남고 완료되지 않는 것처럼 보였음
  - 같은 시점에 `GET /health`까지 응답하지 않아 서버 전체가 멈춘 것처럼 보였음
- Root Cause:
  - `POST /courses/preview` route 가 async 안에서 `preview_course_pdf()`의 동기 PDF 추출과 OpenAI curriculum preview 호출을 직접 수행했음
  - OpenAI preview 호출이 지연되면 단일 event loop 가 그 작업에 묶여 다른 요청도 함께 지연될 수 있었음
  - timeout 이 명시되지 않아 느린 외부 호출을 오래 기다릴 수 있었음
- Resolution:
  - `/courses/preview`에서 `preview_course_pdf()`를 `run_in_threadpool()`로 실행해 event loop 를 막지 않도록 변경
  - OpenAI curriculum preview client 에 `curriculum_preview_timeout_seconds`와 `max_retries=0`을 적용해 지연 시 빠르게 로컬 fallback 으로 전환하도록 보강
- Prevention Rule:
  - async route 안에서 PDF 파싱이나 외부 API처럼 오래 걸릴 수 있는 동기 작업을 직접 실행하지 말 것
  - preview/validation 같은 interactive page1 경로에는 명시적 timeout 을 둘 것
  - preview 요청이 오래 걸릴 때는 `/health`까지 함께 멈추는지 확인해 event loop blocking 여부를 먼저 의심할 것

### DBG-021 `active` 재생목록 안의 단일 영상 URL을 전체 playlist 로 잘못 확장함

- Date: `2026-04-09`
- Agent / Lane: `Lead / Integration`
- Tags: `youtube`, `playlist`, `watch-url`, `prepare-confirm`
- Related Files: `final_edu/youtube.py`, `final_edu/app.py`
- Trigger Commands: `POST /analyze/prepare`, `resolve_youtube_input()`
- Must Read When: YouTube URL 분기 규칙, playlist 확장, prepare 단계의 영상 수 추정 변경
- Symptom:
  - `https://www.youtube.com/watch?v=...&list=...&index=...` 같은 URL을 넣으면 단일 영상이 아니라 전체 playlist 로 확장되어 수백 개 영상으로 집계됐음
- Root Cause:
  - `resolve_youtube_input()`가 URL 형태를 먼저 구분하지 않고 모든 입력에 `noplaylist=False`를 사용해 `yt_dlp` 기본 playlist 해석에 맡겼음
  - 그 결과 `watch` URL에 붙은 `list` query 도 전체 playlist 로 해석되었음
- Resolution:
  - `playlist?list=...`처럼 사용자가 명시적으로 playlist URL을 준 경우만 playlist 로 취급하도록 `is_explicit_playlist_url()` helper 를 추가
  - `watch?v=...`, `youtu.be/...`, `shorts/...`, `live/...`, `embed/...` 계열은 `list` query 가 있어도 `noplaylist=True`로 단일 영상만 해석하도록 수정
- Prevention Rule:
  - YouTube 입력은 `list` query 존재 여부만으로 playlist 로 판단하지 말 것
  - `watch` URL과 `playlist` URL을 별도 테스트로 항상 분리 검증할 것
  - prepare 단계의 예상 영상 수가 비정상적으로 커지면 URL canonicalization 규칙부터 다시 확인할 것

### DBG-023 `active` YouTube rate limit 완화는 prepare / worker shared cache 와 request spacing 이 함께 있어야 함

- Date: `2026-04-09`
- Agent / Lane: `Lead / Integration`
- Tags: `youtube`, `cache`, `throttle`, `worker`, `prepare-confirm`
- Related Files: `final_edu/youtube.py`, `final_edu/extractors.py`, `final_edu/youtube_cache.py`, `final_edu/config.py`
- Trigger Commands: `POST /analyze/prepare`, transcript fetch, `uv run python -m final_edu.worker`
- Must Read When: YouTube cache key / TTL / request spacing / prepare-worker parity 변경
- Symptom:
  - 같은 YouTube URL을 prepare 와 worker 가 각각 다시 호출하면서 rate limit 또는 temporary block 이 더 쉽게 재현될 수 있었음
  - 첫 probe 는 성공했는데 본분석 transcript fetch 에서 다시 막히거나, 반대로 같은 입력을 반복 제출할 때 매번 네트워크를 다시 치는 문제가 있었음
- Root Cause:
  - `yt_dlp` metadata/playlist resolution 과 `youtube-transcript-api` transcript fetch 모두 네트워크 재호출 기반이었고, prepare 와 worker 사이에서 공유되는 cache 가 없었음
  - 호출 간 최소 간격도 강제되지 않아 같은 프로세스에서 짧은 시간에 연속 요청이 나갈 수 있었음
- Resolution:
  - env 기반 proxy 경로를 제거하고 object-storage 기반 shared cache 를 추가해 metadata / transcript 결과를 저장하도록 정리
  - YouTube 네트워크 호출 직전에 process-local minimum interval throttle 을 적용
  - transcript cache 가 stale 이어도 YouTube 요청이 일시 제한되면 stale transcript 를 warning 과 함께 재사용
  - request-limit 상황은 generic no-text 대신 explicit user-facing warning / error 문구로 승격
- Prevention Rule:
  - YouTube 완화 정책을 바꿀 때는 prepare / worker 가 같은 cache key 와 같은 storage 경로를 쓰는지 먼저 확인할 것
  - `yt_dlp`와 transcript fetch 둘 다 throttle 을 우회하지 않는지 함께 점검할 것
  - cache hit, stale fallback, minimum interval 이 회귀 테스트로 남아 있는지 확인할 것

### DBG-024 `active` VOC 업로드 UI만 존재하고 payload / worker / result 경로에서 `voc_files`가 빠져 실제 분석이 비어 있었음

- Date: `2026-04-10`
- Agent / Lane: `Lead / Integration`
- Tags: `voc`, `payload`, `worker`, `review`, `solution`
- Related Files: `final_edu/app.py`, `final_edu/jobs.py`, `final_edu/models.py`, `final_edu/analysis.py`
- Trigger Commands: `POST /analyze/prepare`, worker execution, `GET /review`, `GET /solution`
- Must Read When: 새 입력 타입 추가, result schema 변경, VOC/별도 분석 경로 연결 변경
- Symptom:
  - Page 1에는 VOC 업로드 블록이 있었지만, 실제 분석 결과에서는 강사별 VOC 카드가 placeholder로만 남거나 공통 VOC 인사이트가 비어 있었음
  - persisted draft restore 에서 VOC 파일은 보이는데 `/review`, `/solution`에는 실데이터가 내려오지 않았음
- Root Cause:
  - `voc_files`가 UI submit payload, worker download, result schema, page payload builder 전체를 관통하지 못하고 중간 단계에서 누락됐음
  - 입력 UI를 추가하면서 `files` / `youtube`와 별도로 grep 하지 않아 payload-builder, worker, serializer, renderer 사이 contract drift 가 생겼음
- Resolution:
  - `JobInstructorInput` / `InstructorSubmission` / result schema 에 `voc_files`, `voc_analysis`, `voc_summary`를 추가
  - `app.py` payload builder 와 persisted draft restore 에 VOC 경로를 포함
  - worker 가 VOC 파일을 다운로드하고 `analysis.py`가 강사별 VOC 분석과 공통 VOC 요약을 저장하도록 연결
  - `/review`, `/solution`이 실제 result JSON 기반 VOC 데이터를 렌더하도록 수정
- Prevention Rule:
  - 새 입력 타입을 추가할 때는 UI, submit payload, worker download, result schema, page renderer 를 한 세트로 grep 해서 연결 여부를 함께 확인할 것
  - placeholder UI가 있더라도 실제 JSON source 가 연결됐는지 route payload builder 기준으로 확인할 것
  - Page 1 입력과 Review/Solution 출력 사이에 별도 asset class 가 생기면 dedicated round-trip 테스트를 추가할 것

### DBG-025 `active` 존재하지 않는 `settings.openai_solution_model` 참조로 route-level 모델 선택이 drift 했음

- Date: `2026-04-10`
- Agent / Lane: `Lead / Integration`
- Tags: `settings`, `openai`, `solution`, `review`, `config-drift`
- Related Files: `final_edu/app.py`, `final_edu/config.py`
- Trigger Commands: `GET /solution`, `POST /api/evaluate`
- Must Read When: route-level model 선택, OpenAI settings 필드 변경
- Symptom:
  - `solution` 또는 ad-hoc evaluation 경로가 별도 모델을 쓰는 것처럼 보였지만, 실제 `Settings`에는 해당 필드가 없어 route-level config drift 가능성이 있었음
  - 환경 변수 문서와 라우트 코드의 모델 선택 계약이 일치하지 않았음
- Root Cause:
  - 초기 prototype 단계의 `openai_solution_model` 참조가 남아 있었고, 이후 설정 체계가 `OPENAI_INSIGHT_MODEL` 중심으로 정리되면서 코드 일부만 갱신됐음
- Resolution:
  - 솔루션 인사이트와 VOC 분석 경로의 모델 선택을 `OPENAI_INSIGHT_MODEL`로 통일
  - `config.py`, `.env.example`, 라우트 코드를 같은 설정 계약으로 정리
- Prevention Rule:
  - route-level LLM 선택 로직을 바꾼 뒤에는 `settings.openai_` 검색으로 선언되지 않은 필드 참조가 없는지 확인할 것
  - 문서/env 계약과 실제 `Settings` 필드를 같이 검토할 것
  - prototype 전용 설정명을 남겨두지 말고, 공용 모델 계약으로 빨리 수렴시킬 것

### DBG-026 `active` ScraperAPI를 탄 `yt-dlp` metadata 해석이 prepare 단계에서 포맷 선택 오류나 장시간 지연을 유발했음

- Date: `2026-04-10`
- Agent / Lane: `Lead / Integration`
- Tags: `youtube`, `yt-dlp`, `metadata`, `proxy`, `prepare-confirm`
- Related Files: `final_edu/youtube.py`, `final_edu/app.py`
- Trigger Commands: `POST /analyze/prepare`, `summarize_youtube_inputs()`
- Must Read When: yt-dlp metadata 옵션, ScraperAPI 적용 범위, prepare 단계 500 회귀 변경
- Symptom:
  - `POST /analyze/prepare`에서 단일 YouTube `watch` URL도 `500 Internal Server Error`로 실패할 수 있었음
  - 대표 에러는 `Requested format is not available`였고, 어떤 환경에서는 metadata 조회가 비정상적으로 오래 멈추기도 했음
  - 반면 같은 영상의 transcript fetch 자체는 별도 경로에서 정상 동작할 수 있었음
- Root Cause:
  - `prepare` 단계의 `yt-dlp` metadata/playlist resolution 에 ScraperAPI proxy 를 그대로 붙였고, `extract_info(..., process=True)` 기본 경로로 들어가면서 metadata-only 요청에서도 내부 video processing / format selection 단계가 실행됐음
  - proxy를 통과한 YouTube 응답은 metadata 조회 목적과 달리 포맷 선택 단계에서 불안정할 수 있어, 단일 영상 메타데이터 조회가 format error 또는 장시간 지연으로 무너졌음
- Resolution:
  - `yt-dlp` metadata/playlist resolution 을 direct 경로로 분리
  - metadata 옵션에 `ignoreconfig=True`, `socket_timeout`, `process=False`를 적용해 local/global config 오염과 format selection 을 차단
  - 단일 `watch` URL은 metadata 해석이 실패해도 URL에서 `video_id`를 복구하면 fallback 으로 계속 진행
  - explicit playlist metadata 실패는 `ValueError`로 정리해 route 에서 user-facing 4xx 로 반환되게 함
- Prevention Rule:
  - transcript unblock 용 proxy와 `yt-dlp` metadata resolution 경로를 같은 것으로 가정하지 말 것
  - metadata-only `yt-dlp` 호출은 `process=False`와 `ignoreconfig=True` 여부를 먼저 점검할 것
  - 단일 YouTube `watch` URL은 metadata 실패만으로 `prepare` 전체가 500으로 끝나지 않게 할 것
  - `POST /analyze/prepare` 회귀 테스트에는 direct metadata + transcript proxy 분리 시나리오를 남길 것

### DBG-027 `active` Page 1 mixed lane 이 명시적 mode 없이 저장돼 복원 시 VOC가 사라진 것처럼 보였음

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `restore`, `manifest`, `voc`, `mode`
- Related Files: `final_edu/static/app.js`, `final_edu/app.py`, `final_edu/models.py`, `tests/test_page1_restore.py`
- Trigger Commands: `GET /`, `POST /analyze/prepare`, persisted draft restore
- Must Read When: lane mode persistence, course restore draft serializer, VOC chip/status 표시 변경
- Symptom:
  - Page 1에서 YouTube와 VOC를 함께 붙인 lane 이 저장된 뒤 다시 복원되면, 어떤 mode로 작업했는지 일관되지 않게 열릴 수 있었음
  - VOC chip 이 일반 파일과 같은 `파일` 배지로 표시돼, 상태 메시지의 `VOC 1개`와 화면의 chip 구분이 맞지 않아 저장이 누락된 것처럼 보였음
- Root Cause:
  - analyze submit manifest 가 lane `id`만 저장하고 현재 `mode`를 저장하지 않았음
  - persisted payload / restore serializer 는 lane mode 를 자산 존재 여부로 추론했기 때문에 mixed lane 에서 마지막 UI mode 를 보존하지 못했음
  - chip renderer 가 `voc` 타입에도 일반 파일 배지 텍스트를 재사용했음
- Resolution:
  - Page 1 manifest 와 `JobInstructorInput` payload 에 lane `mode`를 명시적으로 저장하도록 확장
  - restore serializer 가 추론 대신 저장된 explicit mode 를 우선 사용하게 수정
  - submit 시 single-roster / generic 강사명을 과정 roster 기준으로 정규화해 저장 payload drift 를 줄였음
  - VOC chip 을 `VOC` 배지와 별도 tone 으로 렌더하고, `course_restore_drafts_json` 회귀 테스트를 추가했음
- Prevention Rule:
  - lane 단위 UI 상태는 자산 존재 여부로 재구성하지 말고 explicit mode 를 payload 에 함께 저장할 것
  - 서로 다른 asset class 는 count/status 뿐 아니라 chip label 도 명시적으로 구분할 것
  - `course_restore_drafts_json`를 건드리면 `GET /` 기준 round-trip 테스트를 함께 추가할 것

### DBG-028 `active` Page 1 submit/confirm 요청 중 시각적 로딩 표시가 없어 앱이 멈춘 것처럼 보였음

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `loading`, `prepare-confirm`, `inline-queue`, `ux`
- Related Files: `final_edu/templates/index.html`, `final_edu/static/app.js`, `final_edu/static/styles.css`
- Trigger Commands: `POST /analyze/prepare`, `POST /analyze/prepare/{request_id}/confirm`, `POST /analyze`
- Must Read When: Page 1 submit loading indicator, prepare modal handoff, inline queue 대기 UX 변경
- Symptom:
  - 대용량 자료/YouTube/VOC를 넣고 submit 하면 `분석 범위 확인` 모달이 뜨기 전까지 화면 변화가 거의 없어 멈춘 것처럼 보였음
  - local `inline` queue 모드에서는 confirm 이후 실제 분석이 끝날 때까지 응답이 돌아오지 않아, 결과 페이지로 넘어가기 전 대기 구간이 특히 길게 느껴졌음
- Root Cause:
  - submit/confirm 흐름이 내부적으로는 busy 상태를 관리했지만, 사용자가 볼 수 있는 blocking loading surface 가 없었음
  - `confirm`은 redirect 직전까지 기다리는 동안 hidden button busy 상태만 바뀌었고, inline queue 에서는 그 대기 시간이 실제 분석 시간과 겹쳤음
- Resolution:
  - Page 1에 공용 blocking loading overlay 를 추가하고 prepare 요청 시작 직전과 confirm 시작 직전에 즉시 노출되도록 수정
  - prepare 결과가 confirmation required 이면 overlay 를 닫고 기존 분석 범위 modal 로 넘기며, confirm/redirect 경로에서는 overlay 를 유지하도록 정리
  - request 시작 전에 `requestAnimationFrame` 2프레임을 양보해 spinner paint 가 fetch 전에 보이도록 보강
  - reduced-motion 환경에서는 회전 애니메이션만 제거하고 loading state 자체는 유지
- Prevention Rule:
  - Page 1 interactive submit 경로에 500ms 이상 걸릴 수 있는 요청이 있으면 최소한의 visible loading surface 를 둘 것
  - hidden button busy 상태만으로 사용자 피드백을 대신하지 말 것
  - inline queue 경로는 redirect 전까지 실제 분석 시간이 포함될 수 있으므로, local UX 검토 시 queue mode 를 함께 확인할 것

## Archive

### DBG-022 `archived` YouTube transcript unblock 은 proxy 설정이 web / worker / yt_dlp / transcript API 에 동시에 반영돼야 함

- Date: `2026-04-09`
- Agent / Lane: `Lead / Integration`
- Tags: `youtube`, `proxy`, `ipblocked`, `worker`, `prepare-confirm`
- Related Files: `final_edu/youtube.py`, `final_edu/extractors.py`, `final_edu/config.py`, `render.yaml`
- Trigger Commands: `POST /analyze/prepare`, transcript fetch, `uv run python -m final_edu.worker`
- Must Read When: proxy 경로를 다시 도입하거나 과거 transcript unblock 이력을 확인할 때
- Symptom:
  - 같은 YouTube URL이 prepare 단계에서는 집계가 되는데 실제 worker 분석에서 transcript fetch 가 막히거나, 반대로 prepare warning 과 본분석 결과가 서로 다를 수 있었음
  - `IpBlocked`가 발생해도 사용자에게는 generic no-text 에러로만 보였음
- Root Cause:
  - YouTube 네트워크 경로가 `yt_dlp` metadata/playlist resolution 과 `youtube-transcript-api` transcript fetch 로 분리되어 있었고, proxy 설정이 한쪽에만 들어가면 prepare 와 본분석이 어긋날 수 있었음
  - web 과 worker 가 별도 프로세스라 env parity 가 맞지 않으면 같은 입력이 서로 다르게 동작할 수 있었음
- Resolution:
  - env 기반 YouTube proxy helper 를 추가해 `yt_dlp`와 `youtube-transcript-api` 모두 같은 proxy URL 해석을 사용하도록 통일
  - proxy 가 설정되면 proxy 우선, direct 1회 fallback 으로 동작하도록 정리
  - prepare probing 과 실제 분석 transcript fetch 가 같은 proxy 정책을 공유하도록 맞춤
  - `IpBlocked`는 explicit user-facing warning / error 문구로 승격
- Prevention Rule:
  - YouTube unblock 기능을 만질 때는 `yt_dlp`, transcript API, prepare probing, worker 분석 4개 경로를 함께 점검할 것
  - proxy env 는 web 과 worker 에 동시에 주입할 것
  - transcript block 이 generic no-text 로 뭉개지지 않는지 별도 테스트로 확인할 것

### DBG-001 `archived` `uv_build + src layout` editable import 실패

- Date: `2026-04-06`
- Agent / Lane: `Lead / Integration`
- Tags: `packaging`, `uv`, `src-layout`
- Related Files: `pyproject.toml`, 패키지 레이아웃
- Trigger Commands: `uv sync`, `uv run final-edu`, `python -c "import final_edu"`
- Must Read When: `src layout` 재도입, 실행 entrypoint 전략 변경
- Symptom:
  - `uv sync` 후 패키지는 설치된 것처럼 보여도 `uv run final-edu` 또는 `import final_edu`에서 `ModuleNotFoundError`가 발생했음
- Root Cause:
  - 현재 워크스페이스 환경에서 `uv_build` editable install 이 `src layout`과 안정적으로 맞물리지 않았음
- Resolution:
  - 패키지 레이아웃을 루트 패키지 방식으로 전환
  - 실행 기준을 `uv run python -m final_edu`로 통일
  - `pyproject.toml`의 `module-root`를 `""`로 정리
- Prevention Rule:
  - 현재 저장소에서는 `src layout`을 기본값으로 다시 도입하지 말 것
  - 패키지 실행은 콘솔 스크립트보다 `python -m final_edu`를 우선 검증할 것

### DBG-002 `archived` FastAPI `Annotated + Form default` 선언 오류

- Date: `2026-04-06`
- Agent / Lane: `Web / Demo Agent`
- Tags: `fastapi`, `forms`, `typing`
- Related Files: `final_edu/app.py`
- Trigger Commands: 앱 startup, route registration
- Must Read When: `Form()` / `File()` / `Query()` 선언 변경
- Symptom:
  - route registration 단계에서 `Form default value cannot be set in Annotated` assertion 이 발생했음
- Root Cause:
  - `Annotated[str, Form("")]`처럼 default 값을 `Form()` 안에 넣어 선언했음
- Resolution:
  - `Annotated[str, Form()] = ""` 형태로 수정
- Prevention Rule:
  - FastAPI `Annotated` 사용 시 default 값은 dependency marker 안이 아니라 파라미터 오른쪽에 둘 것

### DBG-003 `archived` `TemplateResponse` 시그니처 차이로 인한 렌더링 오류

- Date: `2026-04-06`
- Agent / Lane: `Web / Demo Agent`
- Tags: `fastapi`, `starlette`, `templates`
- Related Files: `final_edu/app.py`
- Trigger Commands: `GET /`, 템플릿 렌더링
- Must Read When: `TemplateResponse` 호출 방식 변경, FastAPI / Starlette 업그레이드
- Symptom:
  - 템플릿 렌더링 시 `TypeError: unhashable type: 'dict'`가 발생했음
- Root Cause:
  - 현재 버전의 `TemplateResponse` 시그니처는 `(request, name, context)`인데 예전 방식처럼 `(name, context)`로 호출했음
- Resolution:
  - `templates.TemplateResponse(request, "index.html", context)`로 수정
- Prevention Rule:
  - 템플릿 예제를 그대로 복사하지 말고 현재 설치 버전의 런타임 시그니처를 먼저 확인할 것

### DBG-004 `archived` Jinja 템플릿에서 `row.items` 충돌

- Date: `2026-04-06`
- Agent / Lane: `Web / Demo Agent`
- Tags: `jinja`, `template-context`, `naming`
- Related Files: `final_edu/templates/index.html`
- Trigger Commands: 결과 페이지 렌더링
- Must Read When: 템플릿 context 구조/키 이름 변경
- Symptom:
  - 결과 페이지 렌더링 시 `TypeError: 'builtin_function_or_method' object is not iterable`가 발생했음
- Root Cause:
  - 템플릿 context 딕셔너리 키 이름을 `items`로 사용해 Jinja가 `dict.items` 메서드와 충돌했음
- Resolution:
  - 템플릿 데이터 키를 `items`에서 `entries`로 변경
- Prevention Rule:
  - Jinja context 에는 dict 메서드명과 겹치는 키를 피할 것

### DBG-007 `archived` `skill-creator`의 `quick_validate.py` 실행 시 `PyYAML` 누락

- Date: `2026-04-08`
- Agent / Lane: `Lead / Integration`
- Tags: `skills`, `validation`, `pyyaml`
- Related Files: `skill-creator` 검증 스크립트
- Trigger Commands: `python3 .../quick_validate.py`
- Must Read When: `skill-creator` 검증 스크립트 사용
- Symptom:
  - 검증 스크립트 실행 시 `ModuleNotFoundError: No module named 'yaml'`이 발생했음
- Root Cause:
  - 스크립트가 `yaml.safe_load`를 사용하지만 현재 Python 환경에 `PyYAML`이 없었음
- Resolution:
  - 이번 라운드에서는 `quick_validate.py`를 직접 돌리지 않고 frontmatter, `agents/openai.yaml`, 스크립트 문법을 수동 검증했음
- Prevention Rule:
  - `quick_validate.py`를 실행하기 전에 현재 Python 환경에 `yaml` 모듈이 있는지 먼저 확인할 것
  - 의존성이 빠져 있으면 구조적 수동 검증으로 먼저 진행하고, 필요할 때만 의존성을 보강할 것

### DBG-011 `archived` 선택 과정 라벨이 실제 선택 상태와 동기화되지 않음

- Date: `2026-04-08`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `course-selection`, `state-sync`
- Related Files: `final_edu/static/app.js`, `final_edu/templates/index.html`
- Trigger Commands: 과정 선택 UI 상호작용
- Must Read When: `selected-course-name` 또는 선택 과정 hidden field 변경
- Symptom:
  - 과정 목록 패널에서 다른 과정을 선택해도 중앙 workspace 상단의 `선택 과정` 텍스트가 즉시 바뀌지 않았음
- Root Cause:
  - 상태 동기화 함수가 visible label 대신 hidden input 만 갱신했음
- Resolution:
  - `syncPage1State()`가 hidden input 과 visible label 을 함께 갱신하도록 수정
- Prevention Rule:
  - 화면에 보이는 선택 상태와 submit hidden field 를 분리해 둘 때는 둘을 동시에 갱신하는 단일 sync 함수로 묶을 것

### DBG-017 `archived` Busy 해제 직후 저장 버튼이 잘못 다시 활성화됨

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `busy-state`, `validation`, `modal`
- Related Files: `final_edu/static/app.js`
- Trigger Commands: 과정 preview/save 직후 버튼 상태 갱신
- Must Read When: course modal save button, `setBusy()`, validation disabled 로직 변경
- Symptom:
  - 과정 추가 popup 에서 PDF preview 또는 과정 저장 직후, 조건을 만족하지 않아야 하는데도 `저장` 버튼이 잠깐 다시 활성화될 수 있었음
- Root Cause:
  - `setBusy(button, false)`가 내부적으로 `button.disabled = false`를 수행했고, 그 뒤에 validation 기반 disabled 상태를 다시 적용하지 않았음
- Resolution:
  - `setBusy(..., false)` 뒤에 `updateCourseSaveButtonState()` 또는 명시적 disabled 처리를 다시 적용하도록 순서를 수정
- Prevention Rule:
  - `busy`와 `validation disabled`가 같은 버튼을 제어하면 busy 해제 직후 validation 상태를 반드시 다시 적용할 것
  - `setBusy()`가 `disabled`까지 만지는 helper 인지 먼저 확인한 뒤 후속 상태 업데이트 순서를 정할 것

### DBG-018 `active` `prepare/confirm` 리팩터링 후 confirm/direct fallback 경로가 보조 의존성 누락으로 깨질 수 있음

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `prepare-confirm`, `fallback`, `imports`
- Related Files: `final_edu/app.py`
- Trigger Commands: `POST /analyze/prepare/{request_id}/confirm`, `POST /analyze`
- Must Read When: 분석 submit flow 를 multi-step 으로 바꾸거나 upload helper import 를 정리할 때
- Symptom:
  - confirm route 에서 redirect URL 생성 시 `Request` 파라미터 누락으로 `NameError`가 날 수 있었음
  - 기존 file-only direct submit 경로는 `build_upload_key` import 누락 시 즉시 실패할 수 있었음
- Root Cause:
  - 새 `prepare -> confirm` 흐름을 추가하면서 confirm route 의 시그니처와 기존 direct fallback helper import 를 함께 재검증하지 않았음
- Resolution:
  - confirm route 에 `Request`를 추가해 redirect URL 생성을 복구
  - `_build_job_instructor()`가 계속 사용하는 `build_upload_key` import 를 복원
  - playlist prepare/confirm smoke 와 file-only direct submit smoke 를 각각 다시 통과시켰음
- Prevention Rule:
  - submit flow 를 분기시키면 `prepare`, `confirm`, 기존 direct fallback 세 경로를 모두 별도 smoke 로 확인할 것
  - helper import 를 정리할 때는 route refactor 뒤에 남은 call site 를 다시 grep 해 누락 여부를 확인할 것

### DBG-029 `active` static JS/CSS 캐시 때문에 새 Page 1 UI 수정이 반영되지 않음

- Date: `2026-04-12`
- Agent / Lane: `Lead / Web`
- Tags: `page1`, `static`, `cache`, `loading-overlay`, `voc-chip`
- Related Files: `final_edu/app.py`, `final_edu/templates/base.html`, `tests/test_page1_restore.py`
- Trigger Commands: `uv run python -m final_edu --reload`, 브라우저 재방문/새로고침
- Must Read When: Page 1 static JS/CSS 변경 후 사용자가 이전 동작을 계속 본다고 제보할 때
- Symptom:
  - 서버 재기동 후에도 `분석 시작` 클릭 시 prepare modal 이 닫히지 않고 버튼만 `시작 중`으로 보였음
  - VOC chip 라벨 수정이 들어갔는데도 화면에는 여전히 `파일`로 보였음
- Root Cause:
  - `base.html`이 local static asset을 버전 없는 `/static/app.js`, `/static/styles.css`로 직접 참조해 브라우저가 구버전 자산을 계속 재사용했음
- Resolution:
  - Jinja helper로 static asset URL에 `?v=<mtime_ns>`를 붙여 파일이 바뀌면 즉시 새 URL을 받도록 변경
  - `/` 렌더 테스트에서 versioned static URL 존재를 검증
- Prevention Rule:
  - 로컬 static 자산은 버전 없는 고정 URL로 템플릿에 직접 박지 말 것
  - Page 1 상호작용 수정 후에는 DOM/assertion뿐 아니라 rendered HTML의 static URL versioning도 함께 확인할 것

### DBG-030 `active` Page 2 도넛 차트 내부 legend 가 긴 과목명에서 퍼센트와 겹침

- Date: `2026-04-12`
- Agent / Lane: `Lead / Web`
- Tags: `page2`, `legend`, `echarts`, `layout`, `dashboard`
- Related Files: `final_edu/templates/job.html`, `tests/test_page2_dashboard.py`
- Trigger Commands: `/jobs/{job_id}` 상단 `강사별 커리큘럼 구성 비중` 렌더
- Must Read When: page2 상단 도넛 차트 legend, 긴 과목명, 퍼센트 정렬 문제를 수정할 때
- Symptom:
  - 과목명이 긴 경우 ECharts legend의 과목명 텍스트가 퍼센트 수치까지 침범해 서로 겹쳐 보였음
- Root Cause:
  - `job.html` inline chart 코드가 ECharts 내부 `rich text` legend를 쓰고 있었고, 이름 영역 폭이 고정이라 긴 문자열이 퍼센트 칼럼과 충돌했음
- Resolution:
  - 내부 legend를 끄고 차트 바깥 HTML legend로 교체
  - legend row를 `swatch / ellipsis label / right-aligned percent` 3열로 렌더
  - `title` tooltip과 pie slice highlight 연동을 추가
- Prevention Rule:
  - 긴 라벨과 수치를 같은 ECharts `rich text` row에 고정폭으로 넣지 말 것
  - page2처럼 label 길이가 가변적인 legend는 DOM legend를 우선 고려할 것

### DBG-031 `active` Page 1 mode-switch lane 이 자료를 잘못된 source bucket 에 저장하고, Page 2는 비어 있는 mode 를 `0%`로 오해하게 만듦

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `page2`, `source-mode`, `voc`, `availability`
- Related Files: `final_edu/templates/index.html`, `final_edu/static/app.js`, `final_edu/templates/job.html`, `final_edu/analysis.py`, `tests/test_page1_restore.py`, `tests/test_page2_dashboard.py`
- Trigger Commands: `GET /`, `POST /analyze/prepare`, `/jobs/{job_id}` Page 2 source toggle
- Must Read When: Page 1 source input 구조, Page 2 mode availability, material/speech empty-state 계약을 바꿀 때
- Symptom:
  - 사용자가 `study_material.pdf`를 올렸다고 인식했는데 payload 상에서는 `voc_files`로 저장되어 Page 2 `강의자료`가 전부 `0%`로 보였음
  - 결과 페이지 상단 toggle 은 실제로 데이터가 없는 `material` mode 도 그대로 활성화해 사용자가 misleading `0%` 차트를 보게 했음
- Root Cause:
  - 기존 Page 1은 한 lane 안에서 `mode`를 바꿔 같은 file picker/dropzone을 `files` 또는 `vocFiles`로 라우팅했기 때문에, 업로드 시점 mode에 따라 파일이 다른 bucket으로 들어갈 수 있었음
  - 기존 Page 2는 source availability 메타데이터가 없어 `combined/material/speech`를 무조건 모두 활성화했고, 비어 있는 mode 를 명시적으로 구분하지 못했음
- Resolution:
  - Page 1은 `+` dropdown lane UI를 유지하되, lane `mode`를 마지막 visible surface 로만 사용하고 저장 bucket 은 계속 `files / youtubeUrls / vocFiles`로 분리 유지
  - file picker 와 drag/drop 을 lane 공통 상태가 아니라 `files`/`voc` surface identity로만 라우팅하도록 수정
  - `youtube` surface 에서는 파일 업로드를 받지 않고 사용자 안내만 보여주도록 정리
  - lane 공통 asset rail 에 자료/링크/VOC chip 을 함께 보여주고, restore 시 explicit `mode`를 그대로 연다
  - result payload 에 `available_source_modes`, `source_mode_stats`를 추가
  - Page 2 toggle 은 unavailable mode 를 disabled 처리하고, 차트 대신 empty state 를 노출
  - `tests.test_page1_restore`, `tests.test_page2_dashboard`에 source 분리/availability 회귀 추가
- Prevention Rule:
  - lane `mode`는 visible surface 용 UI 상태로만 쓰고, 이미 저장된 자산 source bucket 을 바꾸는 의미로 재사용하지 말 것
  - mixed lane 회귀 테스트에는 `files + youtube + voc`가 동시에 있는 restore 케이스를 반드시 포함할 것
  - Page 2 source toggle 을 유지할 때는 결과 payload 에 availability 메타데이터를 함께 두고, unavailable mode 를 `0% 차트`로 대신하지 말 것

### DBG-032 `active` Page 1 rail 상태와 실제 submit multipart 가 어긋나 새 job도 `study_material.pdf -> voc_files`로 저장됨

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `submit`, `formdata`, `restore`, `legacy`
- Related Files: `final_edu/static/app.js`, `final_edu/app.py`, `final_edu/models.py`, `tests/test_page1_restore.py`
- Trigger Commands: `POST /analyze/prepare`, 과정 선택 후 persisted draft auto-restore
- Must Read When: Page 1 submit payload source of truth, hidden file input sync, draft versioning 규칙 변경
- Symptom:
  - 화면 rail에는 `파일 1개 · 링크 1개 · VOC 1개`처럼 보이는데, 새로 생성된 job payload 에서는 `files=[]`, `voc_files=[TalkFile_study_material.pdf.pdf]`만 저장될 수 있었음
  - 같은 과정 선택 시 legacy draft 가 자동 복원되면서 깨진 상태가 반복 제출돼, 사용자는 새로 올린 VOC가 사라진 것처럼 느꼈음
- Root Cause:
  - Page 1 state 는 `blockState.files / vocFiles / youtubeUrls`에 있었지만, 실제 submit 은 `new FormData(refs.analysisForm)`로 hidden file input `FileList`를 다시 읽었음
  - 이 경로는 rail을 그리는 JS state와 별개라, hidden input sync 가 조금만 드리프트해도 서버 payload 가 다른 bucket 으로 저장될 수 있었음
  - 기존 persisted draft 는 version 정보가 없어, 이미 깨진 구버전 payload 도 다음 선택 시 그대로 auto-restore 되었음
- Resolution:
  - analyze submit multipart 를 hidden input 이 아니라 lane JS state에서 직접 조립하는 `buildAnalysisFormData()`로 교체
  - payload 에 `page1_submission_version=2`를 저장하고, restore serializer 는 version 2 미만 draft 를 `requires_reset` metadata 와 함께 빈 block 으로 직렬화
  - course 선택 시 legacy draft 는 auto-restore 대신 reset notice 후 빈 lane 으로 초기화
  - `tests.test_page1_restore`에 legacy reset serializer 회귀와 prepare multipart bucket 분리 회귀를 추가
- Prevention Rule:
  - JS가 asset rail/state를 별도로 관리하는 폼에서는 submit source of truth를 hidden file input `FileList`에 두지 말 것
  - upload bucket 검증은 restore 테스트만으로 충분하지 않으므로 `/analyze/prepare` multipart 저장 회귀를 반드시 함께 둘 것
  - persisted draft schema가 submit contract를 바꾸면 version 필드를 올리고, legacy auto-restore 정책을 명시적으로 둘 것

### DBG-033 `active` Page 2 material 도넛이 raw share가 아닌 visible slice 재정규화와 과도한 chunk 병합 때문에 한 과목 100%처럼 보임

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page2`, `material`, `chunking`, `unmapped`, `donut`
- Related Files: `final_edu/analysis.py`, `final_edu/utils.py`, `final_edu/templates/job.html`, `tests/test_page2_dashboard.py`
- Trigger Commands: `/jobs/{job_id}` Page 2 `강의자료` toggle, material PDF/PPTX 분석
- Must Read When: material chunking, Page 2 donut 비율 표시, `미분류` series 계약을 바꿀 때
- Symptom:
  - multi-topic 강의자료 PDF를 올렸는데 material 도넛이 첫 과목 `100.0%`처럼 보였음
  - 실제 PDF에는 SVM, 결정 트리, 신경망, 딥러닝/오토인코더, 종합 정리까지 포함돼 있었음
- Root Cause:
  - material 파일도 일반 transcript와 같은 `build_chunks(... overlap=1)` 경로를 타면서 여러 페이지가 `p.1 -> p.8` 같은 큰 chunk로 합쳐졌음
  - 그 큰 chunk는 첫 section 쪽으로 배정되고, 뒤 chunk는 `unmapped`로 빠질 수 있어 material section share가 과도하게 한 과목으로 쏠렸음
  - Page 2 도넛/legend/tooltip은 backend raw share를 쓰지 않고, 보이는 section value들의 합으로 다시 100%를 계산해 `75.46% -> 100.0%`처럼 보이게 했음
- Resolution:
  - material source(`pdf/pptx/text`)는 page/slide/segment 경계를 넘겨 합치지 않는 preserving chunk 경로로 분리하고 overlap을 제거
  - 긴 단일 segment만 내부에서 다시 잘라 chunk를 만들고, locator에는 `(1/n)` suffix를 붙임
  - result payload에 `mode_unmapped_series`를 추가해 mode별 미분류 비중을 별도로 전달
  - Page 2 첫 도넛은 raw section share를 그대로 쓰고, 남는 비중은 `미분류` slice로 함께 렌더
  - `tests.test_page2_dashboard`에 page-boundary preserving chunk 회귀와 material multi-section 분산 회귀를 추가
- Prevention Rule:
  - material 문서는 transcript처럼 여러 page/slide를 overlap으로 이어 붙이지 말 것
  - Page 2 비율 시각화는 visible slice끼리 재정규화하지 말고, raw share와 미분류를 명시적으로 함께 보여줄 것
  - material 분석 회귀에는 실제로 여러 주차가 섞인 multi-page fixture를 넣어 section 분산 여부를 확인할 것

### DBG-034 `active` Page 2 커버리지 차트를 raw total token 기준으로 계산하면 미사여구/주변 발화 때문에 `미분류`가 차트를 잠식함

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page2`, `mapped-only`, `coverage`, `wordcloud`, `empty-state`
- Related Files: `final_edu/analysis.py`, `final_edu/templates/job.html`, `tests/test_page2_dashboard.py`
- Trigger Commands: `/jobs/{job_id}` Page 2 source toggle, 강의자료/발화 커버리지 비중 검토
- Must Read When: Page 2 coverage share 분모, `mapped_tokens`, word cloud/coverage 역할 분리를 바꿀 때
- Symptom:
  - 강의자료나 발화에 커리큘럼과 직접 상관없는 연결 멘트, 추임새, 주변 설명이 많으면 `미분류`가 크게 늘어나고 실제 대단원 비중이 작게 눌려 보였음
  - 사용자는 커리큘럼 비중 차트가 `전체 텍스트 대비 비중`보다 `커리큘럼에 연관된 내용들 안에서의 비중`을 보여주길 원했음
- Root Cause:
  - 기존 coverage share는 `section_tokens / total_tokens`로 계산돼, mapped token보다 unmapped token이 많으면 실제 section 비중이 과소평가됐음
  - 상단 도넛에 `미분류`를 함께 넣으면서 차트 목적이 `커리큘럼 구성 비교`보다 `분류 성공률 표시`에 가까워졌음
- Resolution:
  - coverage share 분모를 `mapped_tokens = total_tokens - unmapped_tokens`로 변경
  - `source_mode_stats`에 `mapped_tokens`를 추가해 source 존재와 coverage 성립 여부를 분리
  - 도넛/bar/radar는 mapped-only share만 표시하고, `미분류` slice는 제거
  - source는 있지만 mapped coverage가 0인 mode는 toggle을 유지한 채 coverage empty state를 렌더
  - word cloud는 raw tokens를 유지해 비커리큘럼 표현과 주변 발화는 별도로 관찰하게 함
- Prevention Rule:
  - 커리큘럼 비교 차트와 raw 텍스트 관찰 도구를 같은 분모로 섞지 말 것
  - coverage chart를 설계할 때는 `source 존재`, `분석 가능한 텍스트 존재`, `커리큘럼에 실제 매칭된 텍스트 존재`를 각각 분리해 다룰 것
  - source는 있지만 mapped coverage가 0인 회귀 케이스를 반드시 테스트에 포함할 것

### DBG-035 `active` `Deep Learning and Boltzmann` 관련 키워드가 material PDF에 있어도 page-level single-label assignment 때문에 0%로 사라짐

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `material`, `chunking`, `aliases`, `worksheet-noise`, `assignment`
- Related Files: `final_edu/analysis.py`, `final_edu/utils.py`, `tests/test_page2_dashboard.py`
- Trigger Commands: material PDF/PPTX section assignment, `Deep Learning and Boltzmann` 0% 조사
- Must Read When: material semantic subchunk, section alias glossary, worksheet noise filtering, single-label assignment 규칙을 바꿀 때
- Symptom:
  - PDF `p.8` 같은 페이지에 `딥 러닝`, `제한적 볼츠만 기계`, `오토인코더`가 같이 있어도 `Deep Learning and Boltzmann Machine`은 0%로 남고 `랜덤 포레스트 / 오토인코더`만 커졌음
  - `Q1.`, `답: _____`, `확인 문제` 같은 workbook 문구가 별도 개념 chunk 로 섞여 엉뚱한 section 으로 튀었음
- Root Cause:
  - section assignment 가 title/description 원문만 써서, 영어 중심 section 은 한국어 교안 표현과 직접 맞물리지 않았음
  - material PDF는 page boundary 는 보존했지만 페이지 내부를 의미 단위로 다시 쪼개지 않아 mixed-topic page 가 단일 section 으로 통째로 배정됐음
  - worksheet question/answer block 을 coverage assignment 입력에서 그대로 사용해 semantic score 를 흐렸음
- Resolution:
  - section assignment text 에 bilingual alias glossary 를 추가해 `딥 러닝`, `제한적 볼츠만 기계`, `RBM`, `오토인코더` 같은 교안 표현을 embedding/lexical scorer 가 함께 보게 함
  - material preserving chunk 경로에 semantic subchunk 를 추가해 `■/▷/Q1` marker 와 token budget 기준으로 페이지 내부를 더 작게 나눔
  - `확인 문제`, `빈칸 채우기`, `답:`, `필기 공간`, placeholder underscore 는 coverage assignment 입력에서 제외함
  - `tests.test_page2_dashboard`에 material semantic split 회귀와 deep-learning/autoencoder 동시 배정 회귀를 추가함
- Prevention Rule:
  - material page-level single-label assignment 결과가 의심스러우면 먼저 page 내부 semantic split 여부를 확인할 것
  - 영어 section title 만으로 교안 한글 표현을 설명하지 말고 alias glossary 를 함께 유지할 것
  - workbook question block 이 coverage assignment 에 들어가지 않도록 fixture 기반 회귀를 유지할 것

### DBG-036 `active` Decision Tree chapter 영상이 플레이리스트에 있어도 speech coverage 에서 0%가 나옴

- Date: `2026-04-12`
- Agent / Lane: `Web / Demo Agent`
- Tags: `speech`, `youtube`, `title-prior`, `decision-tree`, `mismatch`
- Related Files: `final_edu/analysis.py`, `final_edu/extractors.py`, `tests/test_page2_dashboard.py`
- Trigger Commands: `/jobs/{job_id}` speech coverage, YouTube chapter playlist 분석, decision-tree 0% 조사
- Must Read When: speech assignment alias, YouTube title reuse, title rescue prior, transcript/title mismatch warning 규칙을 바꿀 때
- Symptom:
  - 재생목록 title 기준으로는 `[2-3] Introduction to Decision Trees`, `[2-4] Entropy and Information Gain`, `[2-5] How to create a decision tree...`가 분명히 있는데 Page 2 speech coverage 에서 `결정 트리`가 `0%`로 보였음
  - 실제 transcript 를 확인하면 decision-tree 발화가 있었지만 `Other / Unmapped`로 보류되거나 다른 section 과 near-tie 상태였음
  - 후속 보정 뒤에는 반대로 `Decision Boundary`, `Rule-Based`, `Regularization` 같은 off-curriculum / 인접 주제가 `결정 트리`로 과매핑돼 speech coverage 가 `65%+`까지 치솟는 회귀가 생겼음
- Root Cause:
  - speech assignment 는 transcript 텍스트만 사용했고, YouTube metadata cache 에 있는 chapter title 을 전혀 활용하지 않았음
  - `결정 트리` section alias 가 `decision tree` 정도로만 얇아 `entropy`, `information gain`, `gini`, `pruning` 같은 핵심 강의 용어를 충분히 설명하지 못했음
  - extraction 단계에서 source label 이 `YouTube <video_id>`라 evidence/warning 에도 실제 chapter title 이 남지 않았음
  - 이후 rescue 보정은 transcript anchor 가 없는 chunk 도 nearest-neighbor 로 확정했고, substring 기반 anchor match 가 `지니고 -> 지니`처럼 한국어 어절 내부를 잘못 잡아 false positive 를 만들었음
- Resolution:
  - YouTube extraction 이 metadata cache 의 human title 을 source label 로 재사용하도록 변경
  - `결정 트리` section alias 를 `entropy / information gain / 지니 / 가지치기 / root node / leaf node`까지 확장
  - speech assignment 에 `strict transcript anchor gate + exact title rescue`를 추가해, section-specific anchor 가 확인된 chunk만 coverage 후보로 인정하도록 변경
  - title rescue 는 semantic title similarity 가 아니라 exact chapter anchor match 에만 적용하고, transcript 에 최소 anchor 근거가 있을 때만 bounded bonus 를 주도록 제한
  - speech anchor matching 을 substring 이 아니라 token/boundary 기준으로 계산해 `지니고` 같은 일반 어절 오탐을 제거
  - `tests.test_page2_dashboard`에 decision-tree alias 회귀, decision-boundary non-match, intro chunk rejection, token-boundary 오탐 방지, exact-title SVM rescue 회귀를 추가
- Prevention Rule:
  - chapter형 YouTube playlist 를 speech coverage 로 해석할 때는 transcript만 보지 말고 metadata title 도 explainability 보조 근거로 유지할 것
  - title prior 는 exact chapter anchor match 에만 적용하고, transcript anchor 없이 semantic similarity만으로 강제 배정하지 말 것
  - speech anchor 는 substring 검색으로 구현하지 말고 token/boundary 기준으로 계산할 것
  - `Decision Boundary`, `Rule-Based`, `Regularization` 같은 off-curriculum 인접 주제가 `결정 트리`로 빨려 들어가지 않는 회귀 테스트를 유지할 것

### DBG-037 `active` VOC Excel workbook 을 그대로 선형화하면 요약 시트/다중 응답 시트가 함께 섞여 맥락 오분석이 생김

- Date: `2026-04-12`
- Agent / Lane: `Lead / Integration`
- Tags: `voc`, `excel`, `xlsx`, `xls`, `sheet-selection`
- Related Files: `final_edu/extractors.py`, `final_edu/app.py`, `tests/test_page1_restore.py`, `tests/test_voc_analysis.py`
- Trigger Commands: `POST /analyze/prepare`, VOC Excel upload, `analyze_voc_assets()`
- Must Read When: VOC 입력 포맷 확대, workbook sheet 선택 규칙, VOC spreadsheet row serialization 변경
- Symptom:
  - VOC 업로드는 CSV까지는 안정적으로 동작했지만, Excel workbook 을 그대로 지원하면 `응답 시트 + 요약 시트`가 함께 들어 있는 파일을 잘못 합쳐 읽을 위험이 있었음
  - 숫자 집계표, 피벗, 관리자용 시트가 함께 있는 workbook 은 LLM/rule-based VOC 분석에 잡음을 크게 넣어 explainability 를 해칠 수 있었음
- Root Cause:
  - 기존 VOC 경로는 `CSV -> row text` 직렬화만 있었고, workbook 구조를 판별하거나 응답이 담긴 단일 sheet 를 고르는 정책이 없었음
  - 여러 시트가 비슷하게 text-rich 하면 어느 sheet 를 진짜 VOC 응답으로 봐야 하는지 계약이 비어 있었음
- Resolution:
  - VOC 입력 포맷에 `XLSX/XLS`를 추가하되, extractor 는 workbook 을 시트별로 읽고 `header + text-rich row` 패턴을 기준으로 clear response sheet 후보만 점수화하도록 정리
  - 후보가 하나로 명확하면 그 시트만 선택하고, 둘 이상이 비슷하게 후보이면 prepare 단계에서 `단일 시트 또는 CSV로 다시 업로드` 오류를 반환하도록 보강
  - 선택된 시트는 CSV와 동일하게 `header: value | ...` row text 로 직렬화하고, `tests.test_page1_restore`와 `tests.test_voc_analysis`에 XLSX accept / ambiguous reject / XLS extractor 회귀를 추가
- Prevention Rule:
  - VOC spreadsheet 지원을 넓힐 때는 `모든 시트 합치기`를 기본값으로 두지 말 것
  - workbook 구조가 애매하면 억지로 LLM에 넘기지 말고 업로드 단계에서 명시적으로 거부할 것
  - VOC spreadsheet extractor 회귀에는 `clear response sheet 1개`, `ambiguous response sheet 2개`, `.xls` 경로를 각각 포함할 것
