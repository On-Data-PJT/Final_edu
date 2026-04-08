# Design System Inspiration of Final_Edu

## 1. Visual Theme & Atmosphere

Final_Edu의 웹 작업물은 차갑고 복잡한 분석 툴이 아니라, 학습 데이터를 다루되 사용자에게 부담을 주지 않는 **soft academic dashboard**로 보여야 합니다. 전체 분위기는 사용자가 제공한 참고 이미지처럼 옅은 라벤더 톤의 캔버스 위에 밝은 카드들이 떠 있는 구조를 기본으로 삼습니다. 화면은 깨끗하고 가벼워 보여야 하지만, 장난감처럼 가볍거나 지나치게 귀여운 방향으로 흐르면 안 됩니다. 핵심 인상은 `차분함`, `신뢰감`, `교육 서비스다운 친절함`, `정돈된 데이터 경험`입니다.

이 시스템의 중요한 특징은 강한 브랜드 색 하나로 화면을 장악하는 방식이 아니라, **중성적인 흰색 표면 + 연한 캔버스 + 제한된 액센트 색**으로 계층을 만드는 데 있습니다. 배경은 아주 부드러운 퍼플-그레이 계열, 카드와 모달은 거의 흰색, 상호작용 포인트는 블루와 바이올렛 계열로 조절합니다. 알림이나 경고는 과장된 레드 대신 코랄 계열을 쓰고, 성공은 탁하지 않은 세이지 그린으로 제한합니다.

현재 프로젝트는 `커리큘럼 커버리지 편차 분석기`이므로, 결과를 “세게 밀어붙이는 대시보드”보다 “이해하기 쉽게 정리된 교육 운영 화면”처럼 보여야 합니다. 따라서 과한 그래디언트, 무거운 그림자, 지나친 유리질감, 네온 포인트, 지나친 다크 테마는 피합니다. 구조는 `.agent/Components.md`를 따르고, 시각 언어는 이 `.agent/DESIGN.md`를 따릅니다.

**Key Characteristics:**
- Pale lavender canvas with soft white cards
- Large rounded corners, but not toy-like blobs
- Blue-violet accents used selectively for interaction and emphasis
- Calm academic SaaS tone rather than fintech or devtool tone
- Low-contrast shadows and whisper-light borders
- Friendly Korean-readable typography using `SUIT Variable` / `Pretendard Variable`
- Spacious cards with clear grouping rather than dense admin tables
- Visual softness without sacrificing analytical clarity

## 2. Color Palette & Roles

### Primary Brand
- **Canvas Lavender** (`#eef0ff`): 전체 페이지 배경, 메인 캔버스
- **Primary Surface** (`#ffffff`): 카드, 모달, 패널, 드롭박스 표면
- **Accent Blue** (`#5b6cff`): 주요 상호작용, 강조 버튼, 선택 상태
- **Accent Violet** (`#7a6ff0`): 보조 강조, 교육 서비스 특유의 부드러운 포인트

### Neutral Scale
- **Primary Ink** (`#23263a`): 주요 제목, 핵심 수치, 중요 텍스트
- **Secondary Ink** (`#7b8199`): 설명 문구, 메타 정보, 보조 텍스트
- **Soft Border** (`rgba(35, 38, 58, 0.08)`): 카드 경계, 입력 경계, 구획선
- **Muted Fill** (`#f5f7ff`): 비활성 영역, 드롭존 바탕, hover 전 배경

### Support Colors
- **Success Sage** (`#63b68b`): 성공 상태, 정상 처리, 완료
- **Alert Coral** (`#ff7b7b`): 오류, 경고, 실패
- **Warm Amber** (`#f2c66d`): 진행 중, 업로드 대기, 임시 주의
- **Sky Soft** (`#8fc9ff`): 데이터 보조 시리즈, 차트 세컨더리 라인

### Interactive States
- Hover는 강한 반전보다 **밝기/채도 소폭 상승**으로 처리합니다.
- Active/selected 상태는 `Accent Blue` 또는 `Accent Violet` 계열의 연한 배경과 진한 텍스트 조합을 사용합니다.
- Focus는 접근성을 위해 `#5b6cff` 계열 2px outline 또는 ring을 사용합니다.

### Shadows
- 기본 그림자: `0 18px 40px rgba(70, 76, 120, 0.10)`
- 가벼운 카드 그림자: `0 8px 22px rgba(70, 76, 120, 0.08)`
- 모달/플로팅 패널 그림자: `0 24px 60px rgba(70, 76, 120, 0.16)`
- 깊이는 그림자 하나로 과장하지 않고, 배경-표면 대비와 radius로 함께 만듭니다.

## 3. Typography Rules

### Font Families
- **Display / UI / Body**: `SUIT Variable`, `Pretendard Variable`, `Noto Sans KR`, `sans-serif`
- 단일 서체 계열을 유지하되, weight와 size 차이로 계층을 만듭니다.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Notes |
|------|------|------|--------|-------------|-------|
| Display Hero | SUIT / Pretendard | 44px (2.75rem) | 700 | 1.12 | 메인 헤드라인, 중앙 집중형 화면 |
| Section Heading | SUIT / Pretendard | 28px (1.75rem) | 700 | 1.20 | 주요 섹션 타이틀 |
| Card Title | SUIT / Pretendard | 20px (1.25rem) | 700 | 1.25 | 카드/모달 제목 |
| Body Large | SUIT / Pretendard | 16px (1rem) | 500 | 1.65 | 핵심 설명 문구 |
| Body | SUIT / Pretendard | 15px (0.9375rem) | 400 | 1.65 | 기본 본문 |
| Meta / Label | SUIT / Pretendard | 13px (0.8125rem) | 500 | 1.45 | 입력 라벨, 메타 정보 |
| Button | SUIT / Pretendard | 14px (0.875rem) | 600 | 1.20 | CTA 및 아이콘 버튼 텍스트 |

### Principles
- **Soft authority**: 헤드라인은 무겁지만 공격적이지 않아야 합니다.
- **Readable Korean first**: 한국어 본문은 넉넉한 line-height를 유지합니다.
- **Short labels, calm body**: UI 라벨은 짧고 명확하게, 본문은 친절하게.
- **No extreme compression**: BMW 같은 압축형 line-height는 사용하지 않습니다.
- **No decorative display font**: 교육 서비스이므로 장식 서체보다 안정적인 가독성이 우선입니다.

## 4. Component Stylings

### Shell / Page Background
- 페이지 전체는 `Canvas Lavender` 기반의 넓은 여백 캔버스를 사용합니다.
- 메인 컨테이너는 중앙 정렬되며, 안쪽에 큰 반경의 카드/패널이 떠 있는 느낌을 줍니다.

### Header
- 좌측 상단의 `Final_Edu` 로고는 작고 간결해야 합니다.
- 우측 아이콘 버튼 2개는 원형 또는 소형 rounded-square에 가깝게 처리합니다.
- 헤더는 시끄럽지 않게, 그러나 화면의 상단 프레임 역할을 분명히 해야 합니다.

### Icon Buttons
- 작은 크기, 넉넉한 패딩, 부드러운 hover 상태를 갖습니다.
- hover 시 액센트 배경을 강하게 깔지 말고 미세한 tint와 shadow만 추가합니다.
- destructive가 아닌 일반 action이므로 경쾌하고 부담 없는 톤을 유지합니다.

### Cards & Containers
- 카드 반경은 큽니다. 기본 `20px`, 강조 카드 `28px`.
- 표면은 흰색, 경계는 아주 연한 border, 그림자는 약하게.
- 내부 spacing은 빽빽하지 않게 16px, 20px, 24px 단위로 구성합니다.

### Modals & Popovers
- Add Course 모달과 Course List 패널은 모두 soft floating surface로 취급합니다.
- 모달은 중심 정렬, 목록 패널은 상단 아이콘에 맞닿는 플로팅 패널이 적합합니다.
- 배경 dimming은 너무 어둡게 깔지 않고 `rgba(24, 28, 45, 0.20)` 내외로 둡니다.

### Forms & Dropzones
- 입력 필드는 흰색 또는 연한 tinted background 위에 얇은 border를 둡니다.
- Dropzone은 카드 내부에 들어가는 2차 표면처럼 보여야 합니다.
- 상태 표현:
  - idle: muted fill + dotted/soft border
  - hover: accent tint 소폭 증가
  - active/dragging: accent outline + 약한 blue/violet wash
  - error: coral border + soft red tint
  - success: sage border + soft green tint

### Status Pills & Chips
- Pill은 지나치게 진하지 않게, 연한 배경과 진한 텍스트 조합을 사용합니다.
- `queued`, `running`, `completed`, `failed`는 서로 다른 색을 가지되 모두 pastel family 안에 있어야 합니다.

### Evidence Blocks
- 근거 스니펫은 읽기용 카드처럼 보여야 합니다.
- 정보 밀도는 높되, 논문 본문처럼 빽빽하게 보이면 안 됩니다.
- source label, locator, score는 meta tone으로, 본문 snippet은 body tone으로 구분합니다.

### Tables & Data Views
- 표는 딱딱한 gridline보다 row separation과 whitespace 중심으로 설계합니다.
- 중요한 수치만 진하게, 나머지는 보조 톤으로 내려야 합니다.
- bar, progress, 비교 시각화는 2~4색 이내로 제한합니다.

## 5. Layout Principles

### Spacing System
- Base unit: `8px`
- Scale: `4px, 8px, 12px, 16px, 20px, 24px, 28px, 32px, 40px, 48px, 56px`

### Grid & Container
- 메인 페이지는 “넓은 여백 속 중앙 집중형”이 기본입니다.
- 콘텐츠는 하나의 거대한 admin grid보다, **작은 수의 명확한 카드 묶음**으로 나뉘어야 합니다.
- 중앙 입력 경험이 핵심인 페이지는 수평 분산보다 수직 흐름을 우선합니다.

### Whitespace Philosophy
- 빈 공간은 낭비가 아니라 안정감의 일부입니다.
- 교육 서비스 특성상 사용자가 다음 액션을 쉽게 이해하도록 **숨 쉴 수 있는 여백**이 필요합니다.
- 단, 지나치게 텅 비어 보이지 않도록 카드와 안내 문구로 리듬을 잡습니다.

### Border Radius Scale
- Small: `14px`
- Medium: `20px`
- Large: `28px`
- 원형 요소: 아이콘 버튼, 아바타, 상태 도트 등 제한적으로만 사용

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Level 0 | Lavender canvas, no border | 전체 배경 |
| Level 1 | White card + soft border + light shadow | 기본 카드, 입력 박스 |
| Level 2 | Stronger shadow + larger radius | 모달, 팝오버, 핵심 플로팅 패널 |
| Level 3 | Accent tint + focus ring | 선택 상태, 활성 드롭존, 현재 항목 |

**Depth Philosophy**: 이 시스템은 무거운 shadow stack이 아니라, 밝은 표면의 층위와 radius 차이로 깊이를 만듭니다. 모든 요소가 떠다니는 느낌이 아니라, 필요한 것만 한 단계씩 떠오르는 구조가 맞습니다.

## 7. Do's and Don'ts

### Do
- Use pale canvas backgrounds and white surfaces
- Keep cards rounded, soft, and readable
- Use blue-violet accents only where interaction or hierarchy requires them
- Favor calm whitespace over dense dashboard clutter
- Design for Korean readability first
- Make forms feel approachable, not bureaucratic
- Keep modals and popovers light, friendly, and clearly layered
- Use CSS variables for tokens such as `--bg-canvas`, `--surface-primary`, `--accent-blue`

### Don't
- Don't use harsh black backgrounds as the primary tone
- Don't mix more than a few accent colors in one view
- Don't use thick borders or heavy gridlines
- Don't overdo gradients, glassmorphism, or neon effects
- Don't make cards pillowy or cartoonishly round
- Don't compress line-height too tightly for Korean body copy
- Don't turn the product into a fintech dashboard or devtool admin panel

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile Small | <375px | 최소 지원, 단일 열 |
| Mobile | 375–480px | 중앙 카드 단일 열, 헤더 단순화 |
| Mobile Large | 480–640px | 카드 spacing 소폭 확장 |
| Tablet Small | 640–768px | 2열 보조 배치 가능 |
| Tablet | 768–920px | 패널 분리 시작 |
| Desktop Small | 920–1024px | 메인 데스크톱 레이아웃 시작 |
| Desktop | 1024–1280px | 표준 데스크톱 |
| Large Desktop | 1280–1440px | 넉넉한 여백과 확장 카드 |
| Ultra-wide | 1440–1600px | 최대 폭 유지, 지나친 확장 금지 |

### Collapsing Strategy
- Header: 좌우 요소 간격을 줄이고 아이콘 우선 유지
- Main workspace: 다중 블록은 세로 스택 유지
- Panels: 상단 플로팅 패널은 모바일에서 bottom sheet 성격으로 변환 가능
- Cards: 복잡한 멀티컬럼보다 단일 열 리듬 우선
- Modals: 작은 화면에서는 거의 full-width card로 확장

## 9. Agent Prompt Guide

### Quick Color Reference
- Background: `#eef0ff`
- Surface: `#ffffff`
- Primary text: `#23263a`
- Secondary text: `#7b8199`
- Accent blue: `#5b6cff`
- Accent violet: `#7a6ff0`
- Success: `#63b68b`
- Alert: `#ff7b7b`
- Border: `rgba(35, 38, 58, 0.08)`

### Example Component Prompts
- "Create a centered education dashboard on a pale lavender canvas with white floating cards, large rounded corners, and calm blue-violet accents."
- "Design a small top header with a minimal `Final_Edu` wordmark on the left and two soft icon buttons on the right."
- "Build an add-course modal: white floating surface, 28px radius, soft shadow, clear Korean form labels, and a gentle PDF dropzone."
- "Create an instructor submission block with a left-side name field, center dropzone, and two small action icons underneath."
- "Render evidence snippets as readable academic note cards: soft borders, muted metadata, strong body readability."

### Iteration Guide
1. Keep the canvas light and the surfaces white
2. Preserve generous radius and soft shadows
3. Use accents sparingly, only to guide action and hierarchy
4. Favor calm educational trust over flashy product energy
5. If a screen starts feeling like a devtool, reduce density and hard contrast
