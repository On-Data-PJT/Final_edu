# Design System

Last Updated: 2026-04-09

## 1. Visual Theme

- 기준 레퍼런스는 `test` 브랜치의 `final_edu/templates/demo.html`이다.
- 전체 톤은 **연한 초록 배경 + 흰 카드 + 차분한 슬레이트 텍스트** 조합이다.
- 제품 인상은 Airtable식 SaaS가 아니라, **교육용 분석 대시보드 프로토타입**에 더 가깝게 유지한다.
- 결과 화면은 차트를 과하게 장식하지 않고, 카드/패널 바탕과 공간감으로 정리한다.

## 2. Color Palette

### Primary

- Canvas: `#f1f8f1`
- Subtle surface: `#f6fbf6`
- Card surface: `#ffffff`
- Deep green accent: `#166534`
- Hover green: `#f0fdf4`
- Active green: `#dcfce7`

### Text

- Primary text: `#1e293b`
- Secondary text: `#64748b`
- Muted text: `#94a3b8`

### Borders And States

- Default border: `#dbe7db`
- Strong border: `#c3d5c4`
- Success bg: `rgba(34, 197, 94, 0.12)`
- Warning bg: `rgba(240, 162, 2, 0.12)`
- Danger bg: `rgba(165, 68, 68, 0.10)`

### Chart Palette

- 대시보드 chart palette 는 demo와 같은 muted multi-color 조합을 쓴다.
- 기본 순서:
  - `#2e303b`
  - `#cd483f`
  - `#888c67`
  - `#e89b8d`
  - `#92c393`
  - `#edb6c3`
  - `#b3d3c5`
  - `#f2e7e7`

## 3. Typography

- 기본 폰트는 `Pretendard Variable`, fallback은 `Noto Sans KR`, `Inter`, system sans-serif.
- 헤드라인은 과장된 display 대신 묵직한 medium/bold 계층으로 간다.
- 대시보드 패널 제목은 `18px`, `800` weight 기준으로 통일한다.
- 본문/설명 텍스트는 `13px~14px`의 조밀한 dashboard density 를 허용한다.

## 4. Components

### Cards And Panels

- 패널은 흰 배경, `20px` radius, 얕은 shadow를 사용한다.
- 결과 페이지에서는 차트 container 자체보다 바깥 패널이 시각 중심이어야 한다.
- 차트 영역 내부 보더는 최소화하고, 패널 외곽만 정리한다.

### Buttons

- Primary button 은 deep green solid를 사용한다.
- Secondary button 은 흰 배경 + 연한 green border 로 처리한다.
- icon button 은 원형 유지 가능하지만 Page 1 header icon 은 예외다.

### Segmented Control

- 배경은 `#f1f5f9` 계열의 옅은 neutral capsule을 사용한다.
- 활성 버튼은 흰색 capsule + 얕은 shadow + green text 를 쓴다.
- 결과 페이지의 dataset toggle 은 시각적으로 가볍지만 분명해야 한다.

### Navigation

- Page 2 sidebar 는 흰 카드형 sticky panel 로 처리한다.
- active item 은 `#dcfce7` 배경과 deep green text 로 강조한다.
- sub-nav 는 main nav 보다 한 단계 작은 typography 를 쓴다.

## 5. Page-Specific Rules

### Page 1 Exception

- Page 1은 **구조, 크기, interaction contract 를 유지**하고 색감과 재질감만 바꾼다.
- 금지:
  - composer lane 구조 변경
  - modal 구조 변경
  - 입력 hit area 크기 변경
  - 버튼 위치/개수 변경
- 허용:
  - 배경 그라데이션을 green 계열로 전환
  - border/shadow/hover 색상 전환
  - chip / modal / notice / dropzone tone 전환

### Page 2

- Page 2는 `demo.html`의 첫 결과 페이지 구조를 직접 참조한다.
- 좌측 sticky sidebar + 우측 세로 panel stack 을 기본 골격으로 쓴다.
- 첫 패널 우측 상단의 dataset toggle 이 페이지 전체 dataset source 를 바꾸는 기준 control 이어야 한다.
- 강사 이동 UI는 donut 패널 아래 중앙 정렬을 유지한다.

### Page 3

- Page 3는 기존 insight card 구조를 유지하되, Page 2와 같은 green tone 으로 자연스럽게 이어져야 한다.
- 결과 차트 페이지보다 밀도는 낮추고 카드 가독성을 우선한다.

## 6. Responsive Rules

- desktop 에서는 `sidebar + content` 2열 구조를 유지한다.
- tablet 이하에서는 sidebar 를 content 위의 full-width panel 로 내린다.
- mobile 에서는 panel padding 을 줄이고 donut 중심 avatar 크기를 줄인다.
- Page 1은 mobile 에서도 기존 composer lane 구조를 그대로 유지한다.

## 7. Do / Don't

### Do

- 연한 초록 배경과 흰 패널의 대비를 유지한다.
- green accent 는 hover, active, CTA, nav selection 에 집중 사용한다.
- chart 색상은 과포화 대신 muted palette 를 유지한다.

### Don't

- Page 1 레이아웃을 demo sidebar 구조처럼 바꾸지 않는다.
- Page 2에 샘플 이름, 샘플 비중, 샘플 keyword 같은 fake content 를 남기지 않는다.
- dark mode, purple bias, heavy glow shadow 를 도입하지 않는다.
