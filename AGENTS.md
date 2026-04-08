# AGENTS

이 파일은 **bootstrap entrypoint**입니다.

실제 운영 문서는 저장소 루트가 아니라 `.agent/` 아래에서 관리합니다.  
새 에이전트나 자동 로더는 이 파일을 진입점으로만 사용하고, 실제 규칙은 아래 순서대로 읽어야 합니다.

## Mandatory Reading Order

1. `.agent/AGENTS.md`
2. `.agent/STATUS.md`
3. `.agent/DEBUG.md`
4. `git status --short --branch`
5. UI/디자인 작업이라면 `.agent/Components.md`, `.agent/DESIGN.md`, `./.codex/skills/final-edu-design/SKILL.md`

## Bootstrap Rules

- 장기 운영 규칙, 역할, close-out 규칙, 아키텍처 계약은 **`.agent/AGENTS.md`**를 source of truth 로 사용합니다.
- 현재 상태 스냅샷은 **`.agent/STATUS.md`**를 사용합니다.
- 해결된 오류와 재발 방지는 **`.agent/DEBUG.md`**를 사용합니다.
- UI 구조 요구사항은 **`.agent/Components.md`**를 사용합니다.
- 시각 톤과 디자인 규칙은 **`.agent/DESIGN.md`**를 사용합니다.
- 이 루트 파일에는 bootstrap 목적의 최소 안내만 유지합니다.
