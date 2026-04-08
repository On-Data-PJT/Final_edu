# Review Rubric

## Pass Rule

- 총점 `90점 이상`
- hard-fail 없음
- 스크린샷과 로컬 렌더 결과가 모두 존재

## Hard-Fail Conditions

아래 중 하나라도 있으면 자동 fail이다.

- `.agent/Components.md`의 필수 섹션 누락
- 핵심 상호작용 불능
- 페이지 렌더링 오류 또는 명백한 런타임 오류
- `.agent/DESIGN.md`의 전체 톤과 명백히 다른 결과
- reviewer가 시각 결과를 판단할 스크린샷이 없음

## Score Table

### 1. Components Requirement Fit — 35점

- 필수 섹션, 버튼, 모달, 패널, 토글, 빈 상태가 `.agent/Components.md`에 맞는가
- 페이지 흐름과 정보 우선순위가 요구사항에 맞는가

### 2. Design Tone Fidelity — 30점

- `.agent/DESIGN.md`의 캔버스, surface, radius, spacing, typography, tone을 지켰는가
- 화면이 `soft academic dashboard` 톤을 유지하는가

### 3. Interaction and State Accuracy — 15점

- 모달, 팝오버, 토글, selected state, empty state, disabled state가 맞게 동작하는가
- 상태에 따라 내용이 자연스럽게 변하는가

### 4. Responsive and Readability Quality — 10점

- desktop과 mobile에서 레이아웃이 무너지지 않는가
- 텍스트 밀도와 여백이 읽기 쉬운가

### 5. Integration and Consistency — 10점

- 같은 페이지 안에서 카드, 칩, 버튼, 라벨 언어가 일관적인가
- 기존 화면과의 톤 충돌이 없는가

## Reviewer Output Format

리뷰어는 아래 형식으로 답한다.

1. `Total Score: NN/100`
2. `Pass/Fail`
3. `Category Scores`
4. `Hard-Fails`
5. `Must-Fix`
6. `Optional Polish`
7. `Referenced Screenshots`

## Reviewer Behavior Rules

- 코드 수정 금지
- 예상 정답이나 구현자의 의도 가정 금지
- `.agent/Components.md`, `.agent/DESIGN.md`, 코드, 로컬 렌더 결과, 스크린샷에만 근거해 판단
- file reference가 가능하면 함께 남기기
- 미관 취향보다 문서 계약 위반 여부를 우선 판단
