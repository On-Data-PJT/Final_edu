# DEBUG

Last Updated: 2026-04-09

이 문서는 **실제로 발생했고 해결된 오류만** 기록합니다.  
각 항목은 다음 에이전트가 같은 실수를 반복하지 않도록 하기 위한 재발 방지 규칙까지 포함해야 합니다.

앞으로 모든 오류 항목에는 가능하면 `Agent / Lane` 도 함께 기록합니다.

---

## 1. `uv_build + src layout` editable import 실패

### Date

2026-04-06

### Agent / Lane

Lead / Integration

### Symptom

- `uv sync` 후 패키지는 설치된 것처럼 보이는데 `uv run final-edu` 또는 `import final_edu`에서 `ModuleNotFoundError` 발생

### Where

- 초기 프로젝트 레이아웃이 `src/final_edu`였던 시점

### Root Cause

- 현재 워크스페이스 환경에서 `uv_build` editable install 이 `src layout`과 안정적으로 맞물리지 않았음

### Resolution

- 패키지 레이아웃을 루트 패키지 방식으로 전환
- 실행 기준을 `uv run python -m final_edu`로 통일
- `pyproject.toml`의 `module-root`를 `""`로 정리

### Prevention Rule

- 현재 저장소에서는 `src layout`을 기본값으로 다시 도입하지 말 것
- 패키지 실행은 콘솔 스크립트보다 `python -m final_edu`를 우선 검증할 것

---

## 2. FastAPI `Annotated + Form default` 선언 오류

### Date

2026-04-06

### Agent / Lane

Web / Demo Agent

### Symptom

- 앱 생성 시 route registration 단계에서 assertion 발생
- 에러 메시지: `Form default value cannot be set in Annotated`

### Where

- `final_edu/app.py`

### Root Cause

- `Annotated[str, Form("")]`처럼 `Form()` 안에 default 값을 넣어 선언했음

### Resolution

- `Annotated[str, Form()] = ""` 형태로 수정
- dependency marker 와 Python default 값을 분리

### Prevention Rule

- FastAPI에서 `Annotated`를 사용할 때 `Form()` / `File()` / `Query()` 안에 default 값을 넣지 말 것
- 기본값은 파라미터의 `=` 오른쪽에 둘 것

---

## 3. `TemplateResponse` 시그니처 차이로 인한 렌더링 오류

### Date

2026-04-06

### Agent / Lane

Web / Demo Agent

### Symptom

- 템플릿 렌더링 시 `TypeError: unhashable type: 'dict'` 발생

### Where

- `final_edu/app.py`
- `templates.TemplateResponse(...)` 호출부

### Root Cause

- 현재 FastAPI / Starlette 버전의 `TemplateResponse` 시그니처는 `(request, name, context)`인데,
  예전 방식처럼 `(name, context)` 형태로 호출했음

### Resolution

- `templates.TemplateResponse(request, "index.html", context)`로 수정

### Prevention Rule

- FastAPI/Starlette 버전을 올리거나 새 프로젝트를 붙일 때는 `inspect.signature(...)`로 런타임 시그니처를 먼저 확인할 것
- 템플릿 예제 코드를 그대로 복사하지 말고 현재 설치 버전에 맞출 것

---

## 4. Jinja 템플릿에서 `row.items` 충돌

### Date

2026-04-06

### Agent / Lane

Web / Demo Agent

### Symptom

- 결과 페이지 렌더링 시 `TypeError: 'builtin_function_or_method' object is not iterable` 발생

### Where

- `final_edu/templates/index.html`
- 비교 결과 루프

### Root Cause

- 템플릿 context 딕셔너리 키 이름을 `items`로 사용해 Jinja가 `dict.items` 메서드와 충돌함

### Resolution

- 템플릿 데이터 키를 `items`에서 `entries`로 변경

### Prevention Rule

- Jinja context 에는 `items`, `keys`, `values`, `get`처럼 dict 메서드와 겹치는 키 이름을 피할 것
- 템플릿 전용 데이터 구조는 메서드명 충돌 가능성을 먼저 점검할 것

---

## 5. 이 세션에서 `uv lock` 실행 시 Rust panic 발생

### Date

2026-04-07

### Agent / Lane

Lead / Integration

### Symptom

- 샌드박스 내부에서 `source ~/.zshrc; UV_CACHE_DIR=/tmp/uv-cache uv lock` 실행 시 `system-configuration` 관련 panic 발생
- 메시지 요약: `Attempted to create a NULL object`, `Tokio executor failed`

### Where

- 현재 Codex 세션의 `uv` CLI 실행 경로

### Root Cause

- 저장소 코드 문제가 아니라 현재 세션의 macOS / `uv` 런타임 조합에서 발생하는 환경 의존 panic 으로 보임

### Resolution

- 저장소 코드는 `py_compile`과 `.venv/bin/python` 기반 TestClient 검증으로 먼저 진행
- 새 배치 아키텍처는 `REDIS_URL` / R2 설정이 없을 때도 `inline/local` fallback 으로 로컬 검증 가능하게 구현
- `uv lock`은 샌드박스 밖 실행으로 재시도해 정상 완료
- 이어서 `uv sync`도 샌드박스 밖 실행으로 정상 완료

### Prevention Rule

- 이 세션에서 `uv lock`, `uv sync`가 sandbox 안에서 panic 나면 앱 자체 문제로 단정하지 말 것
- 먼저 `.venv/bin/python` 기반 import / TestClient 검증으로 코드 경로를 확인할 것
- 필요하면 샌드박스 밖에서 같은 `uv` 명령을 다시 시도할 것
- 의존성 추가 작업은 가능하면 `local fallback` 을 함께 두어 `uv` 문제와 앱 문제를 분리할 것

---

## 6. Windows에서 `uv run python -m final_edu --reload` 시 `fork` context import 실패

### Date

2026-04-07

### Agent / Lane

Lead / Integration

### Symptom

- Windows에서 `uv run python -m final_edu --reload` 실행 시 reloader child process 가 startup 중 즉시 종료
- 핵심 에러 메시지: `ValueError: cannot find context for 'fork'`

### Where

- `final_edu/app.py` import 과정
- `final_edu/jobs.py` 의 module-level `from rq import Queue`
- 내부적으로 `rq.scheduler`

### Root Cause

- 로컬 웹 실행은 `REDIS_URL`이 없으면 `inline/local` fallback 을 써야 하지만, 앱 import 시점에 `final_edu/jobs.py`가 `rq`를 top-level 에서 먼저 import 했음
- 현재 설치된 `rq 2.7.0`은 top-level import 중 worker/scheduler 모듈을 함께 로드하며, 그 과정에서 `multiprocessing.get_context('fork')`를 호출함
- Windows에는 `fork` context 가 없어 웹 앱 startup 자체가 실패했음

### Resolution

- `final_edu/jobs.py`에서 Redis/RQ import 를 module-level 에서 제거
- Redis/RQ 경로가 실제로 필요한 시점에만 lazy import 하도록 변경
- `rq`는 top-level 대신 `rq.queue.Queue`만 직접 import 하도록 바꿔 web startup 경로에서 worker/scheduler import 를 피함
- `final_edu/worker.py`는 `REDIS_URL`을 먼저 검사하고, Windows `fork` 제약이 다시 나오면 더 명확한 RuntimeError 를 주도록 정리

### Prevention Rule

- optional backend dependency 를 웹 앱 import 경로에서 top-level 로 가져오지 말 것
- `inline/local` fallback 이 있는 기능은 fallback 선택 전에 Redis/RQ 같은 외부 큐 모듈을 import 하지 말 것
- Windows 호환성이 필요한 개발 명령은 `--reload` 실제 기동까지 확인할 것

---

## 7. `skill-creator`의 `quick_validate.py` 실행 시 `PyYAML` 누락

### Date

2026-04-08

### Agent / Lane

Lead / Integration

### Symptom

- `python3 /Users/wowjd/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-dir>` 실행 시 즉시 실패
- 핵심 에러 메시지: `ModuleNotFoundError: No module named 'yaml'`

### Where

- `skill-creator` 시스템 스킬의 `scripts/quick_validate.py`

### Root Cause

- 검증 스크립트가 `yaml.safe_load`를 사용하지만, 현재 세션의 기본 `python3`와 프로젝트 `.venv`에는 `PyYAML`이 설치되어 있지 않음

### Resolution

- 이번 라운드에서는 `quick_validate.py`를 직접 돌리지 않고 아래 대체 검증을 수행
  - `SKILL.md` frontmatter 키 수동 검증
  - `agents/openai.yaml` 기본 프롬프트 확인
  - `capture_pages.py` 문법 검증

---

## 8. 디자인 검수 예시 selector 와 실제 DOM 이 어긋나 자동 캡처 실패

### Date

2026-04-08

### Agent / Lane

Web / Demo Agent

### Symptom

- Playwright/검수 manifest 예시를 그대로 실행하면 `open-course-modal` 클릭 단계에서 timeout 발생
- 핵심 증상: selector 를 찾지 못해 모달 오픈 단계가 실패

### Where

- `./.codex/skills/final-edu-design/references/artifacts.md`
- `final_edu/templates/index.html`

### Root Cause

- 스킬 문서 예시는 `data-testid='open-course-modal'` 등을 기준으로 했지만, 실제 템플릿에는 동일한 `data-testid`가 없는 요소가 있었음
- 문서와 DOM automation contract 가 분리되어 drift 가 생김

### Resolution

- Page 1/2/3 핵심 요소에 `data-testid`를 추가
- 스킬 문서의 manifest 예시와 실제 DOM selector 를 다시 맞춤
- 검수 스크립트는 `data-testid` 기반 selector 를 기본값으로 유지

### Prevention Rule

- 디자인 검수용 selector 는 임시 class 나 문구가 아니라 `data-testid`로 고정할 것
- UI 구조를 바꾸면 스킬 문서의 manifest 예시도 같이 갱신할 것

---

## 9. `cmux` 브라우저는 WKWebView 제약으로 mobile viewport 캡처를 직접 지원하지 않음

### Date

2026-04-08

### Agent / Lane

Lead / Integration

### Symptom

- `cmux rpc browser.viewport.set` 호출 시 `not_supported: browser.viewport.set is not supported on WKWebView` 반환
- 즉, `cmux`만으로 desktop 과 mobile screenshot matrix 를 모두 안정적으로 만들 수 없음

### Where

- `cmux` 브라우저 automation 경로

### Root Cause

- 현재 `cmux` 브라우저 backend 가 WKWebView 기반이라 viewport 제어 기능이 제한됨

### Resolution

- 디자인 검수 표준 경로를 `cmux 우선 + Playwright fallback` 으로 정의
- `capture_pages.py --backend auto`가 desktop/tablet 는 `cmux`, mobile 은 Playwright 로 자동 분기하도록 변경

### Prevention Rule

- mobile viewport 검수는 `cmux` 단독 경로로 강제하지 말 것
- `cmux`가 가능해도 mobile screenshot matrix 는 Playwright fallback 을 허용할 것

### Prevention Rule

- `skill-creator` 검증 스크립트를 바로 실행하기 전에 현재 Python 환경에 `PyYAML`이 있는지 먼저 확인할 것
- 스크립트 의존성이 빠져 있으면 구조적 수동 검증으로 먼저 진행하고, 필요할 때만 의존성을 보강할 것

---

## 8. JSON 데이터 스크립트가 페이지에 그대로 노출됨

### Date

2026-04-08

### Agent / Lane

Web / Demo Agent

### Symptom

- Chromium 스크린샷에서 `type="application/json"` 스크립트의 JSON payload가 페이지 하단 텍스트처럼 그대로 노출됨
- `Page 1`, `Page 2`, `Page 3` 모두 시각 결과가 깨져 reviewer 점수에 직접 영향이 있었음

### Where

- `final_edu/templates/index.html`
- `final_edu/templates/job.html`
- `final_edu/templates/solutions.html`

### Root Cause

- 데이터 전달용 `<script type="application/json">` 태그를 DOM에 넣었지만 `hidden` 속성이 없었음
- 브라우저별 렌더링/스크린샷 경로에서 이 노드가 레이아웃에 잡히며 텍스트가 그대로 표시됨

### Resolution

- 세 템플릿의 JSON 스크립트 태그에 `hidden` 속성을 추가
- 이후 Playwright 스크린샷을 다시 생성해 노출이 사라진 것을 확인

### Prevention Rule

- 템플릿에 JSON payload를 심을 때는 `type="application/json"`만 믿지 말고 `hidden` 또는 명시적 `display:none` 처리까지 함께 넣을 것
- reviewer용 스크린샷을 찍기 전에 raw JSON, raw token, debug text가 화면에 보이지 않는지 먼저 점검할 것
- 이후 `quick_validate.py`가 꼭 필요하면 `PyYAML`이 있는 환경에서 실행하거나 임시 의존성으로 실행

### Prevention Rule

- repo-local skill을 만들 때 `quick_validate.py`를 바로 실행하기 전에 현재 Python 환경에 `yaml` 모듈이 있는지 먼저 확인할 것
- `quick_validate.py`가 막히면 스킬 메타데이터 수동 검증과 스크립트 문법 검증으로 최소 검증을 먼저 완료할 것

---

## 10. 선택 과정 라벨이 실제 선택 상태와 동기화되지 않음

### Date

2026-04-08

### Agent / Lane

Web / Demo Agent

### Symptom

- 과정 목록 패널에서 다른 과정을 선택해도 중앙 workspace 상단의 `선택 과정` 텍스트가 즉시 바뀌지 않음
- 내부 submit hidden input 은 갱신되지만 사용자가 보는 라벨은 이전 값을 유지할 수 있었음

### Where

- `final_edu/static/app.js`
- `final_edu/templates/index.html`

### Root Cause

- Page 1 상태 동기화 함수가 visible label 대신 form 내부 hidden input `course_name`만 갱신하는 경로를 사용했음
- 화면 표시용 요소와 submit payload 요소가 분리되어 있었는데, UI label 업데이트가 빠져 있었음

### Resolution

- `syncPage1State()`에서 hidden input 과 함께 visible `selected-course-name` 텍스트도 항상 갱신하도록 수정
- 새 중앙 workspace 레이아웃에서도 같은 selector contract 를 유지

### Prevention Rule

- 화면에 보이는 선택 상태와 submit hidden field 를 분리해 둘 때는 둘을 동시에 갱신하는 단일 sync 함수로 묶을 것
- 시각적 state label 이 있는 페이지는 selector 기반 브라우저 캡처 또는 UI 검증으로 drift 여부를 한 번 더 확인할 것

---

## 11. Busy 해제 직후 저장 버튼이 잘못 다시 활성화됨

### Date

2026-04-09

### Agent / Lane

Web / Demo Agent

### Symptom

- 과정 추가 popup 에서 PDF preview 또는 과정 저장이 끝난 직후, 조건을 만족하지 않아야 하는데도 `저장` 버튼이 잠깐 다시 활성화될 수 있었음
- 원인은 busy 상태 해제 이후 disabled 상태를 다시 덮어쓰는 순서 문제였음

### Where

- `final_edu/static/app.js`
- `previewCourse()`
- `saveCourse()`

### Root Cause

- `setBusy(button, false)`가 내부적으로 `button.disabled = false`를 수행하는데, 그 뒤에 validation 기반 disabled 상태를 다시 적용하지 않았음
- preview/save 흐름에서 busy 종료와 validation sync 순서가 반대로 되어 있었음

### Resolution

- `setBusy(..., false)` 호출 뒤에 `updateCourseSaveButtonState()` 또는 명시적 disabled 처리를 다시 적용하도록 순서를 수정
- course modal validation 은 busy 상태와 별개로 항상 마지막에 재평가되게 정리

### Prevention Rule

- `busy`와 `validation disabled`가 같은 버튼을 제어하면, busy 해제 직후 validation 상태를 반드시 다시 적용할 것
- `setBusy()`가 `disabled`까지 만지는 helper 인지 먼저 확인한 뒤 후속 상태 업데이트 순서를 정할 것

---

## 12. 긴 원본 파일명을 storage key basename으로 직접 써서 로컬 파일시스템 한계를 초과함

### Date

2026-04-09

### Agent / Lane

Lead / Integration

### Symptom

- 긴 한글/URL-encoded PDF 파일명으로 `POST /courses` 호출 시 `500 Internal Server Error`
- 핵심 에러 메시지: `OSError: [Errno 63] File name too long`
- 실패 위치는 `LocalObjectStorage.put_file()`의 `shutil.copyfile(...)`

### Where

- `final_edu/courses.py`
- `final_edu/app.py`
- `final_edu/jobs.py`
- `final_edu/storage.py`

### Root Cause

- 과정 PDF storage key를 `courses/{course_id}/curriculum/{uuid8}-{original_filename}` 형태로 만들면서 원본 파일명을 거의 그대로 path basename에 넣었음
- 로컬 개발용 `LocalObjectStorage`는 object key를 실제 파일 경로로 그대로 쓰므로, 매우 긴 파일명은 macOS/APFS path component 한계를 바로 넘겼음
- 같은 위험이 과정 preview temp path, 강사 자료 temp path, job upload key, 분석용 download destination 에도 같이 존재했음

### Resolution

- `final_edu/utils.py`에 공용 `build_safe_storage_name()` helper 를 추가
- 과정 PDF 저장 key, 과정 preview/create temp path, 강사 자료 temp path, job upload key, 분석용 temp destination 전부 이 helper 를 사용하도록 통일
- 원본 표시명은 `original_name` metadata 에만 남기고, 실제 파일시스템용 basename 은 짧은 ASCII-safe 이름으로 생성
- `LocalObjectStorage`에는 path component 길이 guard 를 추가해 future regression 시 raw `OSError` 전에 더 명확히 실패하도록 보강

### Prevention Rule

- user-controlled filename 을 local filesystem path component 나 local storage key basename 에 직접 넣지 말 것
- object storage key가 로컬 fallback 에서 파일 경로로 사용되는지 먼저 확인하고, key 생성 시 로컬 파일시스템 한계를 기준으로 길이를 제한할 것
- 원본 파일명 보존이 필요하면 display metadata 로만 저장하고, 실제 저장 경로는 별도의 bounded safe filename helper 를 사용할 것

---

## 13. Overlay open state 가 modal centering layout 을 덮어써 Page 1 popup 이 좌측에 붙음

### Date

2026-04-09

### Agent / Lane

Web / Demo Agent

### Symptom

- Page 1 우측 상단 아이콘으로 여는 `과정 추가`, `과정 목록` popup 이 화면 정중앙이 아니라 좌측 상단 흐름처럼 붙어서 열림

### Where

- `final_edu/static/styles.css`
- `.floating-panel.is-open`
- `.modal-shell`

### Root Cause

- overlay 공통 open state 인 `.floating-panel.is-open`이 `display: block`을 강제로 적용하고 있었음
- 이 규칙이 `.modal-shell { display: grid; place-items: center; }`보다 우선해 modal shell 의 중앙 정렬 grid layout 을 무효화했음

### Resolution

- `.floating-panel.is-open`을 `display: grid`로 변경해 overlay 가 열린 상태에서도 shell class 의 정렬 규칙을 유지하도록 수정

### Prevention Rule

- overlay open state 클래스에서는 `display`를 지정할 때 shell layout (`grid`, `flex`)을 깨지 않는지 먼저 확인할 것
- modal/drawer 공용 overlay 에서 visibility 토글과 layout 토글을 같은 규칙에서 처리할 때는 class 조합 우선순위를 점검할 것
