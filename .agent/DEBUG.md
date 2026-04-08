# DEBUG

Last Updated: 2026-04-08

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
- 이후 `quick_validate.py`가 꼭 필요하면 `PyYAML`이 있는 환경에서 실행하거나 임시 의존성으로 실행

### Prevention Rule

- repo-local skill을 만들 때 `quick_validate.py`를 바로 실행하기 전에 현재 Python 환경에 `yaml` 모듈이 있는지 먼저 확인할 것
- `quick_validate.py`가 막히면 스킬 메타데이터 수동 검증과 스크립트 문법 검증으로 최소 검증을 먼저 완료할 것
