---
name: final-edu-design
description: Implement or refine Final_Edu UI from .agent/Components.md and .agent/DESIGN.md. Use when working on templates, CSS, UI states, layout, visual polish, responsive behavior, or design QA for final_edu/app.py, final_edu/templates/*, final_edu/static/*, and related web flows in this repository.
---

# Final Edu Design

Final_Edu의 웹 UI를 `.agent/Components.md`의 요구사항과 `.agent/DESIGN.md`의 시각 톤에 맞춰 구현하고 검증한다. 구조, 스타일, 상호작용, 스크린샷 아티팩트, 최종 리뷰 점수 루프까지 하나의 작업 체계로 다룬다.

## Quick Start

1. 먼저 repo-root `AGENTS.md` bootstrap 과 `.agent/AGENTS.md`, `.agent/STATUS.md`, `.agent/DEBUG.md`, `.agent/Components.md`, `.agent/DESIGN.md`를 읽는다.
2. 이번 작업이 `small`, `medium`, `large` 중 어느 크기인지 정한다.
3. 구조와 acceptance 기준을 먼저 잠그고 나서 UI를 수정한다.
4. 스크린샷과 로컬 렌더 결과를 만든 뒤 최종 리뷰를 돌린다.
5. 총점 `90점` 이상이 아니면 최대 `3회`까지 재작업 루프를 반복한다.

## Workflow

- 전체 workflow, subagent lane 분해, task packet, remediation loop는 `references/workflow.md`를 읽는다.
- 리뷰 기준과 hard-fail 조건은 `references/review-rubric.md`를 읽는다.
- 스크린샷 아티팩트 규격과 캡처 절차는 `references/artifacts.md`를 읽는다.

## Use Subagents When Allowed

- 현재 세션에서 subagent 사용이 허용되면 `large` UI 작업은 아래 구조를 기본값으로 쓴다.
  - `Structure Worker`
  - `Visual Worker`
  - `Interaction Worker`
  - `Final Reviewer`
- 현재 세션에서 subagent 사용이 허용되지 않으면 같은 역할을 메인 에이전트가 순차적으로 수행한다.
- 최종 reviewer는 코드 수정 금지다.
- reviewer에게는 구현 의도나 예상 정답을 넘기지 말고, `코드 + 로컬 렌더 결과 + 스크린샷 + .agent/Components.md + .agent/DESIGN.md`만 넘긴다.

## Output Requirements

- 어떤 `.agent/Components.md` 섹션을 구현했는지 남긴다.
- 어떤 `.agent/DESIGN.md` 규칙을 적용했는지 남긴다.
- 스크린샷 저장 경로를 남긴다.
- 최종 reviewer 점수와 pass/fail 여부를 남긴다.
- `90점 미만`이면 반드시 must-fix 목록과 남은 리스크를 남긴다.

## Read Only What You Need

- `references/workflow.md`
  - task sizing, lane 분해, contract lock, review loop가 필요할 때 읽는다.
- `references/review-rubric.md`
  - reviewer prompt, 점수표, hard-fail 기준이 필요할 때 읽는다.
- `references/artifacts.md`
  - 로컬 렌더, 스크린샷, Playwright manifest 예시가 필요할 때 읽는다.
- `scripts/capture_pages.py`
  - 스크린샷을 자동 생성할 때 사용한다.
