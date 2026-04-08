# AGENTS

## Mission

이 저장소는 강의 자료를 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차를 비교하는 공모전용 MVP를 개발합니다.

현재 우선순위는 아래 순서입니다.

1. 데모 안정성
2. 결과 설명 가능성
3. 실제 교육 현장 문제와의 연결성
4. 기능 추가

`품질 점수` 자체를 계산하는 서비스로 과장하지 말고, 현재 MVP는 `커리큘럼 커버리지 편차 분석기`라는 메시지를 유지합니다.

## Mandatory Reading Order

루트 `AGENTS.md` bootstrap 을 읽은 뒤, 모든 에이전트는 **작업 시작 전에 아래 순서를 반드시 지켜야 합니다.**

1. `.agent/AGENTS.md`
2. `.agent/STATUS.md`
3. `.agent/DEBUG.md`
4. `git status --short --branch` 확인
5. 그 다음에만 작업 시작

이 순서는 선택사항이 아닙니다. 다음 에이전트가 이 워크스페이스에 처음 들어와도 바로 이어서 작업할 수 있게 하기 위한 필수 preflight 절차입니다.

세 문서 중 하나라도 현재 상태와 어긋나면, 작업자는 자신의 작업 범위 안에서 즉시 바로잡아야 합니다.

## Mandatory Close-Out Workflow

모든 에이전트는 **작업 종료 전에 아래 순서를 반드시 지켜야 합니다.**

1. 자신이 처리한 변경 내용을 `.agent/STATUS.md`에 반영
2. 작업 중 발생했고 해결한 오류가 있으면 `.agent/DEBUG.md`에 반영
3. 아래의 `Major Change Triggers` 중 하나에 해당하면 `.agent/AGENTS.md`도 반영
4. 커밋이나 푸시를 했다면 `git status --short --branch`를 다시 확인
5. 커밋/푸시 이후 브랜치명, clean/dirty 여부, 원격 동기화 상태처럼 **현재 사실**이 `.agent/STATUS.md`와 달라졌다면 `.agent/STATUS.md`를 한 번 더 갱신
6. 최종적으로 작업 트리 상태를 확인

`.agent/STATUS.md` 또는 `.agent/DEBUG.md`를 반영하지 않고 작업을 끝낸 것으로 간주하지 않습니다.
단, 방금 만든 문서 커밋의 해시까지 `.agent/STATUS.md`에 다시 적기 위해 후속 커밋을 만드는 것은 금지합니다.

## Document Responsibilities

### `AGENTS.md` at repo root

이 파일은 **bootstrap entrypoint**입니다.

- 일부 에이전트/툴이 저장소 루트 `AGENTS.md`를 자동 진입점으로 읽을 수 있으므로 삭제하지 않습니다.
- 실제 운영 계약은 `.agent/AGENTS.md`가 source of truth 입니다.
- 루트 `AGENTS.md`에는 최소한의 안내만 유지하고, 운영 규칙을 여기에 중복 기록하지 않습니다.

### `.agent/AGENTS.md`

이 파일은 역할 소개 문서가 아니라 **운영 계약 문서**입니다.

여기에는 아래처럼 앞으로도 유효해야 하는 규칙만 씁니다.

- 저장소 목적과 MVP 범위
- 작업 시작/종료 절차
- 역할 분담과 파일 소유권
- subagent 사용 규칙
- 완료 정의
- 중대한 변경사항 발생 시 문서 갱신 규칙

일회성 로그, 사소한 작업 메모, 단순 실행 결과는 여기에 쓰지 않습니다.

### `.agent/STATUS.md`

이 파일은 **현재 스냅샷 + 최근 변경 로그** 문서입니다.

여기에는 아래를 씁니다.

- 지금 무엇이 구현되어 있는가
- 지금 브랜치/작업 트리는 어떤 상태인가
- 다음 우선순위는 무엇인가
- 방금 끝낸 작업으로 무엇이 바뀌었는가

다음 에이전트가 1분 안에 “지금 어디까지 왔는지”를 파악할 수 있어야 합니다.

`.agent/STATUS.md`는 현재 스냅샷 문서이므로, 모든 최신 커밋 해시를 추적하는 changelog로 쓰지 않습니다.

### `.agent/DEBUG.md`

이 파일은 **해결된 오류와 재발 방지 규칙** 문서입니다.

여기에는 아래만 씁니다.

- 실제로 발생했던 오류
- 증상
- 발생 위치
- 근본 원인
- 해결 방법
- 다음에 같은 실수를 막는 규칙

사소한 시행착오, 의미 없는 추측, 미해결 잡담은 쓰지 않습니다.

### `.agent/Components.md`

이 파일은 **페이지별 UI 구성요소와 상호작용 명세** 문서입니다.

- 화면에 어떤 요소가 들어가야 하는지
- 어떤 모달/패널/버튼이 필요한지
- 어떤 상태에서 무엇이 비활성/활성인지
- 페이지별 요구사항이 어디까지 확정됐는지

를 정리합니다.

특히 `Web / Demo Agent`가 템플릿, 스타일, 화면 흐름을 수정할 때는 `.agent/AGENTS.md`, `.agent/STATUS.md`, `.agent/DEBUG.md`를 읽은 뒤 `.agent/Components.md`도 확인해야 합니다.

### `.agent/DESIGN.md`

이 파일은 **전체 웹 작업물의 시각 계약 문서**입니다.

- 어떤 분위기와 톤으로 보여야 하는지
- 색상 역할과 타이포 계층이 무엇인지
- 카드, 모달, 패널, 버튼, 상태 UI가 어떤 성격을 가져야 하는지
- 반경, 그림자, 밀도, 반응형 원칙이 무엇인지

를 정리합니다.

역할 분리는 아래처럼 고정합니다.

- `.agent/Components.md`: 무엇이 어디에 들어가는가
- `.agent/DESIGN.md`: 그것이 어떻게 보여야 하는가

UI 작업 시 구조는 `.agent/Components.md`, 시각 표현은 `.agent/DESIGN.md`를 우선합니다.

### `./.codex/skills/final-edu-design/SKILL.md`

이 파일은 **이 저장소 전용 디자인 구현 스킬**입니다.

- `.agent/Components.md`의 구조 요구사항을 `.agent/DESIGN.md`의 시각 톤에 맞춰 구현하는 방법
- 디자인 작업의 contract lock 방식
- subagent 를 허용하는 세션에서의 `Structure / Visual / Interaction / Reviewer` workflow
- screenshot artifact 와 reviewer 점수 루프

를 정의합니다.

디자인 관련 작업에서는 이 스킬을 **반드시 참조**합니다.

## Major Change Triggers

아래 중 하나라도 발생하면 `.agent/STATUS.md`만이 아니라 `.agent/AGENTS.md`도 함께 수정해야 합니다.

- 제품 목표 또는 MVP 범위가 바뀐 경우
- 작업 시작/종료 절차가 바뀐 경우
- 역할 분담, 파일 소유권, subagent 사용 규칙이 바뀐 경우
- 핵심 실행 명령, 배포 방식, 필수 환경 변수가 바뀐 경우
- 공통 타입/인터페이스 계약이 바뀐 경우
- fallback 정책이나 지원 포맷 범위처럼 다음 에이전트의 판단에 직접 영향을 주는 규칙이 바뀐 경우

판단이 애매하면 `.agent/AGENTS.md`를 업데이트하는 쪽을 기본값으로 삼습니다.

## Current Architecture Contract

- 앱 스택: `FastAPI + Jinja + CSS + RQ worker`
- 실행 명령:
  - Web: `uv run python -m final_edu --reload`
  - Worker: `uv run python -m final_edu.worker`
- 핵심 엔드포인트: `GET /`, `POST /analyze`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/status`, `GET /health`
- 입력 포맷: `PDF`, `PPTX`, `TXT/MD`, `YouTube URL`
- 커리큘럼 기준: 운영자가 직접 입력한 대단원
- 분석 방식: 업로드/URL 등록 → Job enqueue → 배경 분석 → 결과 조회
- 임베딩: `OPENAI_API_KEY`가 있으면 OpenAI 사용, 없으면 lexical fallback
- 환경 변수 로딩: 로컬 실행 시 저장소 루트 `.env`를 자동 로드하고, 이미 export 된 환경 변수가 있으면 그 값을 우선 사용
- 저장소:
  - 프로덕션: `Render Web + Worker + Key Value + Cloudflare R2`
  - 로컬 개발: `inline/local` fallback 허용
- 의도적 비기능 범위: 자막 없는 영상 STT fallback 미구현, 스캔 PDF OCR 미구현, 영구 이력 보관 미구현

이 계약이 바뀌면 `.agent/AGENTS.md` 수정 대상입니다.

## Working Tree Rules

- 이 저장소는 작업 중인 dirty worktree일 수 있습니다.
- 자신이 만든 것이 아닌 변경사항을 함부로 되돌리지 않습니다.
- `git reset --hard`, `git checkout --`, 광범위 삭제 같은 파괴적 명령은 금지입니다.
- 현재 기준 개발 브랜치는 `dev`이며, 시작 전에 반드시 `git status`로 범위를 확인합니다.

## Roles And File Ownership

### 1. Lead / Integration

- 책임: 제품 정의, 공통 타입, 문서 계약, 결과 해석, PR 리뷰
- 주 소유 파일: `README.md`, `AGENTS.md`, `.agent/AGENTS.md`, `.agent/STATUS.md`, `.agent/DEBUG.md`, `final_edu/models.py`, `final_edu/config.py`, `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/worker.py`
- 타 역할의 인터페이스 변경은 이 역할이 먼저 확인

### 2. Extraction Agent

- 책임: 업로드 파일/URL에서 원문 텍스트를 뽑아 공통 세그먼트로 정규화
- 주 소유 파일: `final_edu/extractors.py`
- 금지: 점수 로직, 템플릿, 운영 계약 문서 직접 변경

### 3. Analysis Agent

- 책임: 커리큘럼 파싱, chunking, similarity, coverage aggregation, `Other / Unmapped`
- 주 소유 파일: `final_edu/analysis.py`, `final_edu/utils.py`
- 금지: 추출기 로직과 템플릿 직접 수정

### 4. Web / Demo Agent

- 책임: FastAPI 라우트, 템플릿, 스타일, 배포 동선
- 주 소유 파일: `final_edu/app.py`, `final_edu/templates/*`, `final_edu/static/*`, `render.yaml`
- UI 구현 전 `.agent/Components.md`를 현재 페이지 요구사항의 기준 문서로 확인
- UI 구현 전 `.agent/DESIGN.md`를 전체 시각 톤의 기준 문서로 확인
- 디자인 관련 구현 전 `./.codex/skills/final-edu-design/SKILL.md`를 반드시 확인
- 현재 세션에서 subagent 사용이 허용되면 디자인 작업은 스킬의 `Structure / Visual / Interaction / Reviewer` workflow 를 우선 사용
- 현재 세션에서 subagent 사용이 허용되지 않으면 같은 lane 분리를 로컬에서 순차적으로 수행
- 금지: 분석 기준 자체 변경

## Subagent Dispatch Matrix

작업을 시작할 때는 먼저 “이 일을 지금 로컬에서 직접 처리할지, subagent 로 보낼지”를 결정해야 합니다.

### Lead / Local First

아래 작업은 **Lead 가 직접 처리**합니다.

- 지금 당장 다음 행동이 그 결과에 막히는 urgent blocking 작업
- 공통 타입, 운영 계약, 문서 계약 변경
- 서로 다른 lane 의 변경을 통합하는 작업
- 최종 검증, 커밋 범위 정리, 제출 직전 안정화

### Explorer Dispatch

아래 작업은 **explorer** 로 보냅니다.

- 문서 조사
- 배포 제약 확인
- 특정 오류 원인 파악
- 샘플 데이터 적합성 조사

explorer 는 코드 수정 금지입니다.

### Worker Dispatch

아래 작업은 **worker** 로 보냅니다.

- 명확한 write scope 가 있는 구현 작업
- 파일 소유권이 분명한 독립 개선 작업
- 다른 lane 과 충돌하지 않는 테스트/튜닝 작업

worker 는 자신의 write scope 밖 파일 수정 금지입니다.

## Stable Parallel Lanes

현재 MVP에서 안정적으로 병렬화 가능한 lane 은 아래 4개입니다.

### Lane 1. Extraction Hardening

- 소유 agent: `Extraction Agent`
- write scope: `final_edu/extractors.py`
- 예시 작업:
  - PDF/PPTX 경고 메시지 개선
  - YouTube transcript 실패 유형 구분
  - 텍스트 추출 실패 시 사용자 메시지 개선

### Lane 2. Analysis Tuning

- 소유 agent: `Analysis Agent`
- write scope: `final_edu/analysis.py`, `final_edu/utils.py`
- 예시 작업:
  - threshold 조정
  - evidence 선택 품질 개선
  - `Other / Unmapped` 비중 설명 개선

### Lane 3. Web / Demo Polish

- 소유 agent: `Web / Demo Agent`
- write scope: `final_edu/app.py`, `final_edu/templates/*`, `final_edu/static/*`, `render.yaml`
- 예시 작업:
  - 입력/결과 화면 문구 정리
  - 빈 상태 / 오류 상태 UI 개선
  - 배포 동선 정리

### Lane 4. Queue / Storage Integration

- 소유 agent: `Lead / Integration`
- write scope: `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/worker.py`, `final_edu/config.py`
- 예시 작업:
  - RQ / Redis 연결 안정화
  - R2 저장소 연동
  - Job 상태 저장 구조 조정
  - 로컬 fallback 과 프로덕션 경로 간 계약 유지

### Sidecar Explorer

- write scope 없음
- 예시 작업:
  - Render worker / KV / R2 배포 제약 조사
  - YouTube transcript 라이브러리 실패 원인 조사
  - 데모용 자료셋 적합성 조사

## Parallelism Limits

- 기본 최대 병렬 수: `worker 3개 + explorer 1개`
- 공통 계약 변경이 필요한 순간: 병렬 작업 중단 후 Lead 가 계약을 잠금
- 배포 직전 / 제출 직전: `worker 1개 또는 local only` 로 축소

## Subagent Rules

- explorer 는 코드베이스 질문이나 장애 원인 조사에만 사용
- worker 는 명확한 파일 소유권이 있을 때만 사용
- 서로 다른 subagent 가 같은 파일을 동시에 수정하지 않음
- 공통 타입이나 운영 계약이 바뀌면 먼저 Lead 가 기준을 고정한 뒤 다른 작업을 진행
- 배포 직전에는 병렬성보다 통합 안정성을 우선

## Contract Lock Before Parallel Work

worker 를 병렬로 띄우기 전에 Lead 가 아래를 먼저 고정해야 합니다.

- 이번 라운드 목표 1개
- 공통 타입 변경 여부
- 각 worker 의 write scope
- 각 worker 의 acceptance check
- 문서 갱신 필요 여부

이 계약이 잠기기 전에는 worker 병렬 실행을 시작하지 않습니다.

## Agent Task Packet Template

worker 또는 explorer 에 작업을 넘길 때는 아래 항목을 포함합니다.

- Goal
- Write Scope
- Out Of Scope
- Acceptance Check
- Blocker Escalation Rule
- Doc Update Trigger

이 형식 없이 막연하게 “고쳐줘” 식으로 넘기지 않습니다.

## Agent Handoff Report Template

subagent 는 작업 종료 시 아래를 반드시 보고합니다.

- Changed Files
- What Was Done
- Checks Run
- Remaining Risks
- STATUS update needed?
- DEBUG update needed?
- AGENTS update needed?

Lead 는 이 handoff 를 읽고 통합 여부를 결정합니다.

## Integration Gate

Lead 가 병렬 작업 결과를 통합하기 전에 아래를 확인합니다.

- write scope 충돌 없음
- 공통 타입/운영 계약 충돌 없음
- acceptance check 통과
- 최소 공통 검증 통과
- `.agent/STATUS.md` 반영 필요 여부 판단
- 해결된 오류가 있으면 `.agent/DEBUG.md` 반영 여부 판단
- 규칙 변경이 있으면 `.agent/AGENTS.md` 반영 여부 판단

## Standard Round Flow

모든 병렬 작업 라운드는 아래 순서를 따릅니다.

1. `AGENTS.md` bootstrap → `.agent/AGENTS.md` → `.agent/STATUS.md` → `.agent/DEBUG.md` → `git status` 확인
2. 이번 라운드 목표 정의
3. Lead 가 계약 잠금
4. worker / explorer 병렬 실행
5. Lead 가 handoff report 검토 및 통합
6. 공통 검증
7. `.agent/STATUS.md` / `.agent/DEBUG.md` / `.agent/AGENTS.md` close-out 반영

## Definition Of Done

아래 조건이 모두 맞아야 작업이 끝난 것으로 봅니다.

- 기능 또는 문서 변경이 실제 요청을 충족
- `.agent/STATUS.md` 반영 완료
- 오류가 있었다면 `.agent/DEBUG.md` 반영 완료
- 중대한 변경사항이 있었다면 `.agent/AGENTS.md` 반영 완료
- 검증 결과 또는 검증 불가 사유가 남아 있음
- 디자인/UI 작업이라면 `final-edu-design` 스킬 workflow 를 따름
- 디자인/UI 작업이라면 screenshot artifact 와 로컬 렌더 결과가 남아 있음
- 디자인/UI 작업이라면 final reviewer 점수 `90점 이상`, 또는 최대 3회 루프 후 잔여 리스크가 `.agent/STATUS.md`에 기록되어 있음

## Release / Contest Caution

- 공모전 제출 마감: `2026-04-13`
- 내부 코드 프리즈는 최소 하루 전 확보 권장
- 제출 직전에는 기능 추가보다 데모 데이터 정리, 리허설, AI 리포트 정리가 우선
