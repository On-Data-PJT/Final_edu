# Workflow

## Overview

이 스킬은 `.agent/Components.md`와 `.agent/DESIGN.md` 사이에서 구조와 시각 표현을 동시에 맞추는 UI 작업용 workflow다. 핵심은 먼저 계약을 잠그고, 가능하면 병렬 구현한 뒤, 독립 reviewer가 점수화하고, 기준 점수에 못 미치면 고쳐서 다시 검토받는 것이다.

## 1. Preflight

1. repo-root `AGENTS.md` bootstrap 과 `.agent/AGENTS.md`, `.agent/STATUS.md`, `.agent/DEBUG.md`를 읽는다.
2. `.agent/Components.md`, `.agent/DESIGN.md`를 읽는다.
3. 현재 task가 어느 페이지와 섹션을 다루는지 명확히 적는다.
4. 현재 브랜치와 dirty worktree 상태를 확인한다.

## 2. Size The Task

### Small

- 단일 컴포넌트나 단일 상태 polish
- 예: 버튼 스타일, 모달 radius, empty state 문구
- 권장 구조: 로컬 구현 또는 `worker 1 + reviewer 1`

### Medium

- 단일 페이지 구조 + 스타일 수정
- 예: `Page 1` 전체 정리
- 권장 구조: `Structure Worker + Visual Worker + Reviewer`

### Large

- 다중 페이지 또는 구조 + 스타일 + 상호작용이 함께 바뀌는 작업
- 예: `Page 2`와 `Page 3` 구현, 토글/모달/차트 상태 추가
- 권장 구조: `Structure Worker + Visual Worker + Interaction Worker + Reviewer`

## 3. Contract Lock

코드 수정 전 아래를 먼저 잠근다.

- 이번 라운드에 다룰 `.agent/Components.md` 섹션
- 이번 라운드에 적용할 `.agent/DESIGN.md` 토큰/원칙
- write scope
- acceptance checklist
- 페이지 간 route / state 전달 방식
- 차트 또는 시각화 구현 방식
- 편집 가능한 표나 form 의 컴포넌트 형태
- 필수 스크린샷 대상
- reviewer가 평가할 상태 목록

이 단계가 끝나기 전에는 worker를 병렬로 띄우지 않는다.

## 4. Lane Split

### Structure Worker

- 목적: 템플릿 구조, semantic hierarchy, section ordering, empty state, content grouping
- 권장 write scope: `final_edu/templates/*`
- 필요 시 `final_edu/app.py`에 데이터 훅이나 context 변수만 최소로 추가

### Visual Worker

- 목적: CSS 변수, spacing, card hierarchy, modal/panel styling, responsive adjustments
- 권장 write scope: `final_edu/static/*`

### Interaction Worker

- 목적: 모달 열기/닫기, 토글, 상태 전환, 차트 영역 연결, UI event wiring
- 권장 write scope: `final_edu/app.py`, `final_edu/templates/*`, `final_edu/static/*`
- 가능하면 상호작용 코드는 별도 JS 파일 또는 명확한 script block으로 분리

### Final Reviewer

- 목적: 점수화, blocker 식별, must-fix 정리
- write scope 없음
- 코드 수정 금지

## 5. Task Packet Template

subagent에게는 아래 형식으로 넘긴다.

- Goal
- Write Scope
- Out Of Scope
- Locked Components Sections
- Locked Design Rules
- Acceptance Check
- Review Artifacts Expected
- Blocker Escalation Rule

## 6. Review Artifacts

reviewer에게는 아래만 넘긴다.

- 변경 코드
- 로컬 렌더 결과
- 스크린샷 경로
- `.agent/Components.md`
- `.agent/DESIGN.md`

예상 정답, self-review, 의도 설명은 넘기지 않는다.

## 7. Review Loop

1. 구현 결과를 정리한다.
2. 스크린샷을 캡처한다.
3. reviewer에게 점수화시킨다.
4. 총점이 `90점 이상`이고 hard-fail이 없으면 통과한다.
5. 총점이 `90점 미만`이거나 hard-fail이 있으면 must-fix를 lane별로 다시 나눈다.
6. 필요한 lane만 다시 구현한다.
7. 새 스크린샷을 만든 뒤 fresh reviewer로 다시 검토한다.

최대 `3회`까지 반복한다.

## 8. Stop Conditions

아래 중 하나면 라운드를 종료한다.

- reviewer 총점 `90점 이상`
- 최대 3회 루프를 모두 사용
- 기술적 blocker 때문에 더 이상 개선 불가

2, 3의 경우 `.agent/STATUS.md`에 남은 리스크를 명시한다.

## 9. Suggested Reviewer Prompt Shape

리뷰어에게는 이런 형태로 넘긴다.

- `Use $final-edu-design at <skill-path> to review this Final_Edu UI work. Score it with the skill rubric against .agent/Components.md and .agent/DESIGN.md. Do not edit code. Return total score, per-category scores, hard-fails, must-fix items, and optional polish.`

## 10. When Not To Parallelize

아래 경우는 병렬보다 로컬 처리 우선이다.

- 바로 다음 행동이 특정 한 파일 수정에 막혀 있을 때
- `app.py`와 템플릿 계약이 아직 잠기지 않았을 때
- 제출 직전 미세 조정 단계일 때
- screenshot artifact가 아직 없는 상태에서 reviewer를 돌리려 할 때
