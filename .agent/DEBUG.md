# DEBUG

Last Updated: 2026-04-09

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

### DBG-016 `active` Page 1 흰 composer capsule 과 실제 파일 드롭 영역이 달랐음

- Date: `2026-04-09`
- Agent / Lane: `Web / Demo Agent`
- Tags: `page1`, `drag-drop`, `hit-area`, `composer`
- Related Files: `final_edu/static/app.js`, `final_edu/templates/index.html`, `final_edu/static/styles.css`
- Trigger Commands: 파일 drag/drop
- Must Read When: composer lane, drop target, mode switching 변경
- Symptom:
  - 흰 자료 입력창 전체가 업로드 영역처럼 보이지만 실제 파일 drop 은 중앙 surface 일부에서만 동작했음
- Root Cause:
  - drag/drop 이벤트를 lane 전체가 아니라 `files-surface` 내부에만 바인딩했음
- Resolution:
  - drag/drop binding 을 `composer-lane` 전체로 올려 시각적 container 와 실제 drop target 을 맞춤
  - 유튜브 모드에서도 같은 lane 에 파일을 drop 하면 files 모드로 전환되도록 정리
- Prevention Rule:
  - drag/drop UI 는 시각적 container 와 실제 drop target 범위를 다르게 두지 말 것
  - lane/capsule 단위 업로드 UX를 설계했다면 이벤트 binding 도 같은 바깥 container 에 걸 것

## Archive

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
