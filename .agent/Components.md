# Components

Last Updated: 2026-04-09

## Purpose

이 문서는 현재 웹 UI의 **구조와 상호작용 contract**를 잠그는 문서입니다.

- `Page 1`: 강의 자료 업로드 메인 페이지
- `Page 2`: 첫 번째 결과 페이지
- `Page 3`: 솔루션 인사이트 페이지
- 시각 톤은 `.agent/DESIGN.md`

## Shared Data Contracts

- `course`는 과정명, 커리큘럼 PDF, 대주제 목록, 목표 비중, 등록 강사명 목록을 가진다.
- Page 1 제출 버튼은 `과정 선택 + 유효 강사 1명 이상`일 때만 활성화한다.
- 결과 페이지는 **샘플 데이터가 아니라** 사용자가 등록한 실제 `course`, 실제 업로드 파일, 실제 YouTube 분석 결과만 사용한다.
- 결과 페이지의 `view mode`는 `combined`, `material`, `speech` 3종이다.
- `view mode`는 Page 2 첫 패널 우측 상단 toggle 하나로 바꾸고, Page 2 전체 차트에 일관되게 반영된다.
- Page 2는 최소한 아래 payload 들을 실제 결과 JSON에서 받아 쓴다.
  - `mode_series`
  - `rose_series_by_mode`
  - `keywords_by_mode`
  - `line_series_by_mode`
- 특정 mode 데이터가 비어 있으면 해당 mode 기준 empty 상태를 보여주고 다른 mode 결과로 치환하지 않는다.

## Page 1. Main Page

### Structure

- 헤더는 유지한다.
  - 좌측 상단: 작은 텍스트 로고 `final_edu`
  - 우측 상단: `과정 추가`, `과정 목록` 아이콘 2개
- 헤더 아이콘은 **icon-only**여야 한다.
  - 원형 배경 없음
  - pill 배경 없음
  - outline 버튼처럼 보이지 않게 처리
- 본문에는 아래만 남긴다.
  - 중앙 headline `강의 자료를 올리고, 비교를 시작`
  - 채팅 입력창처럼 보이는 composer lane 들
  - 작은 `+` / enter-like submit icon
- 본문에서 제거한다.
  - 카드형 hero
  - 과정 요약 카드
  - 최근 작업 목록
  - 부차적 설명 문구

### Overlay Rules

- `과정 추가`와 `과정 목록`은 둘 다 **중앙 popup overlay**로 열려야 한다.
- 두 overlay 모두 화면 좌우 측면이 아니라 정중앙에 배치한다.
- `Escape`, 바깥 영역 클릭, 닫기 버튼으로 닫을 수 있어야 한다.
- YouTube 재생목록이 포함된 제출에는 **분석 범위 확인 overlay**가 추가된다.
- 이 overlay 는 확장 영상 수, 총 재생시간, 예상 chunk, 예상 시간, 예상 비용, warning 을 보여준 뒤 실제 분석 시작 여부를 확정해야 한다.

### Course Creation Popup

- visible UI는 아래만 둔다.
  - 과정명 입력
  - 커리큘럼 PDF single-file dropzone
  - 업로드된 PDF 1개 표시 및 삭제
  - 강사명 comma-token input
  - 저장 / 취소
- 하단 action row 는 popup 의 우측 하단 정렬로 배치한다.
- 저장 버튼 라벨은 busy 상태에서도 `저장`으로 유지한다.
- PDF는 드래그앤드롭과 클릭 업로드를 모두 지원한다.
- PDF는 1개만 받고, 새 파일 선택 시 교체한다.
- 강사명 input 규칙
  - 이름 입력 후 `,` 입력 시 chip 으로 확정
  - 빈 값은 확정하지 않음
  - 중복 이름은 막음
  - 확정된 chip 은 키보드 backspace 로 삭제하지 않고 chip 내부 `x` 클릭으로만 삭제한다
- PDF preview 결과의 대주제/비중 표는 사용자에게 노출하지 않는다.
- preview 결과는 `accepted | review_required | rejected` 세 상태를 가진다.
- `accepted`면 compact summary 만 보여주고, preview 편집 표는 계속 숨긴다.
- `accepted`면 상세 경고/근거 블록 없이 `저장 가능` 성격의 짧은 상태 문구만 보여준다.
- 주차별 시간표형 커리큘럼에서 과목 반복 slot 수를 신뢰할 수 있게 읽은 경우에는 비중을 자동 채워 `accepted`로 올릴 수 있어야 한다.
- `review_required`면 대주제/설명/비중 편집 표를 노출하고 사용자가 직접 수정할 수 있어야 한다.
- `review_required`도 상세 판정 근거는 숨기고, `확인 후 저장` 성격의 짧은 상태 문구만 보여준다.
- `rejected`면 저장을 막고 PDF 교체만 유도해야 한다.
- `rejected`면 상세 사유 목록 없이 `커리큘럼으로 판정되지 않아 저장할 수 없음` 성격의 짧은 상태 문구만 보여준다.
- save 활성 조건은 `과정명 + 저장 가능한 preview 상태 + 강사 1명 이상`이다.
- 저장 가능한 preview 상태란 아래 둘 중 하나다.
  - `accepted`이고 대주제/비중이 자동 검증된 상태
  - `review_required`이지만 사용자가 대주제와 비중을 모두 채워 유효한 `sections_json`을 만든 상태

### Course List Popup

- 목록은 중앙 popup 안에서 단순 리스트로 보여준다.
- 각 항목은 아래 정보를 가진다.
  - 과정명
  - 등록 강사 수
  - 대주제 수
  - 현재 선택 여부
- 클릭 시 과정이 즉시 선택되고 popup 은 닫힌다.
- 과정 전환 시 현재 입력 중이던 lane 상태는 과정별로 보존한다.
- 선택한 과정에 과거 분석 제출 이력이 있으면 마지막 제출 기준의 강사명, 업로드 자료, 유튜브 링크를 복원한다.
- 과정 복원은 lane 단위가 아니라 `선택 강사 + 그 강사에게 연결된 파일/유튜브` 묶음 단위로 복원되어야 한다.

### Main Composer

- 메인 입력 구조는 `lane` 반복형이다.
- 각 lane 은 아래 3부분으로 구성한다.
  - 좌측 mode trigger
  - 가운데 업로드 / 링크 입력 surface
  - 우측 강사 icon trigger
- 좌측 mode trigger 규칙
  - 기본은 `+`
  - 클릭 시 dropdown 으로 `파일 업로드`, `유튜브 링크` 표시
  - `유튜브 링크` 선택 시 trigger 아이콘이 YouTube 아이콘으로 바뀐다.
- 가운데 surface 규칙
  - 파일 모드에서는 drag/drop + click 업로드 surface
  - 유튜브 모드에서는 comma-token input
  - 파일은 여러 개 허용, 개별 삭제 가능
- 파일 drag/drop 인식 범위는 중앙 안내 텍스트 일부가 아니라 lane 의 흰 capsule 전체여야 한다.
- 유튜브 모드에서도 lane 의 흰 capsule 전체에 파일을 drop 하면 같은 lane 에 파일이 추가되고 files 모드로 전환되어야 한다.
- 유튜브 URL은 comma 로 chip 확정, 개별 삭제 가능
- 파일 토큰과 유튜브 토큰은 현재 모드와 관계없이 lane 하단의 공통 rail 에서 함께 보여야 한다.
- 공통 rail 의 chip 은 같은 기본 스타일을 유지하고, 작은 파일 / YouTube 표식만으로 타입을 구분한다.
- 과정이 선택되지 않았을 때는 별도 empty-state 문구를 두지 않고 lane 중앙 문구를 `과정을 먼저 선택하거나 추가하세요`로 대체한다.
- 파일 모드의 기본 문구는 lane 중앙 정렬이어야 한다.
- 상태 메시지는 lane 내부가 아니라 lane 우측 상단 바깥쪽에 붙어 보여야 한다.
- 상태 메시지는 기본 상태 문구를 유지하되, 강사가 선택된 lane 에서는 `상태 / 강사명` 형식으로 현재 선택 강사를 함께 보여야 한다.
- 여러 lane 이 쌓여 있을 때도 각 lane 의 상태 메시지는 이전 lane 의 capsule 이나 asset rail 을 침범하지 않아야 한다.
- 우측 강사 아이콘을 클릭하면 dropdown menu 로 현재 선택된 과정의 `instructor_names`만 보여준다.
- 강사 선택 UI는 아이콘-only 를 유지하고, 항상 select field 처럼 보이면 안 된다.
- 같은 강사를 여러 lane 에 중복 배치하지 않는다.
- 한 lane 은 한 강사 전용이며 파일과 유튜브 자산을 함께 누적할 수 있다.
- composer lane 은 현재보다 더 얇은 capsule 밀도를 유지한다.

### Submission Controls

- composer 아래에는 아래 두 액션만 둔다.
  - 작은 `+` lane 추가
  - enter-like submit icon
- submit 활성 조건은 아래를 모두 만족할 때다.
  - 선택 course 존재
  - 유효 lane 1개 이상
  - 각 유효 lane 에 강사 선택 + 자산 1개 이상
- lane 추가 버튼은 선택한 과정의 강사 roster 를 모두 사용하면 비활성화한다.
- YouTube 재생목록 또는 대용량 YouTube 입력이 있으면 submit 직후 바로 enqueue 하지 않고 `prepare` 단계로 먼저 보낸다.
- `prepare` 단계는 raw YouTube 입력을 유지한 채 내부 영상 수와 추천 분석 모드를 계산해야 한다.
- playlist가 현재 상한을 넘으면 enqueue 대신 분할 또는 축소가 필요하다는 에러를 반환해야 한다.

### Page 1 Acceptance Checklist

- 메인 화면에는 headline 과 composer 중심 구조만 보여야 한다.
- 우측 상단 2개 아이콘은 배경 없는 icon-only 상태로 동작해야 한다.
- 과정 추가/과정 목록 overlay 는 모두 중앙 popup 으로 열려야 한다.
- 과정 추가 popup 은 과정명, PDF 1개, 강사명 chip 입력만 가져야 한다.
- 메인 composer 는 파일/유튜브 모드 전환, 강사 dropdown, lane 추가, submit icon 을 가져야 한다.
- 메인 composer 의 강사 선택은 icon trigger + dropdown menu 방식이어야 한다.
- 강사 1명만 있어도 유효 lane 하나로 분석 제출이 가능해야 한다.

## Page 2. Result Page 1

### Role

- 첫 결과 페이지는 복잡한 리포트가 아니라 **compact dashboard**여야 한다.
- hero, 과도한 요약 카드, 중복 설명 영역은 제거한다.
- `test` 브랜치 `demo.html`의 첫 결과 페이지 구조를 기준 레퍼런스로 사용한다.

### Overall Layout

- 페이지 상단에는 compact intro 만 두고, 본문은 `sidebar + dashboard panel stack` 구조를 사용한다.
- 좌측 sidebar 는 sticky 로 유지한다.
- sidebar 에는 아래가 있어야 한다.
  - 홈으로 돌아가는 링크
  - 현재 결과 페이지 active item
  - 각 패널 anchor 링크
- `view mode` segmented control 은 상단 공통 toolbar 가 아니라 **Panel 1 우측 상단**에 둔다.
- mode 는 `combined`, `material`, `speech`를 전환한다.
- 이 toggle 이 Page 2 전체 dataset source 의 source of truth 다.
- job 이 아직 running 이면 status panel 에 단순 상태값만이 아니라 현재 phase 와 영상 처리 progress 를 함께 보여줘야 한다.

### Panel 1. Coverage Donut

- 선택 강사의 구성 비중을 보여주는 대표 패널이다.
- 패널 안에 아래가 함께 있어야 한다.
  - 패널 제목
  - 우측 상단 dataset toggle
  - donut/rose 차트
  - 이전/다음 이동 버튼
  - 현재 선택 강사 표시
  - 강사 chip row
- 강사 선택 변경 시 Panel 2도 같이 바뀌어야 한다.
- Panel 1의 toggle 을 바꾸면 Panel 2, Panel 3, Panel 4도 모두 같은 mode 데이터로 갱신되어야 한다.

### Panel 2. Word Cloud

- 선택 강사의 키워드 패널이다.
- 제목에 현재 선택 강사명이 바로 드러나야 한다.
- Panel 1과 동기화된다.
- keyword cloud 데이터도 `view mode`에 따라 실제 material/speech/combined 결과를 써야 한다.

### Panel 3. Average + Instructor Bars

- 평균 구성 비중과 강사별 stacked bar를 **하나의 카드 안**에서 연속 배치한다.
- 중간 divider 로만 구분하고 패널 수를 늘리지 않는다.
- 두 차트 모두 Panel 1의 `view mode`를 그대로 따라야 한다.

### Panel 4. Goal Comparison

- 목표 대비 비교는 단순해야 한다.
- 목표선 또는 목표 기준과 함께 여러 강사를 한 번에 비교할 수 있어야 한다.
- 강사가 한 명뿐이면 목표선 + 단일 강사 비교 상태로 자연스럽게 동작해야 한다.
- 강사별 on/off control 을 카드 상단에 둔다.
- 최하단에는 `솔루션 보기` 이동 버튼을 둔다.
- Page 4의 강사 on/off 는 비교 대상만 제어하고, dataset source 는 Panel 1 toggle 이 계속 관리한다.

### Page 2 Acceptance Checklist

- Page 2는 sidebar + 4개 핵심 패널 구조여야 한다.
- 강사 선택은 Panel 1에서 일어나고 Panel 2와 동기화되어야 한다.
- Page 2 첫 패널의 toggle 하나가 Page 2 전체 dataset source 를 바꿔야 한다.
- donut, word cloud, 평균 bar, 강사별 bar, 목표 비교가 모두 같은 `view mode`를 따라야 한다.
- fake instructor 이름, fake keyword, fake 비중 배열은 남아 있으면 안 된다.
- 마지막 비교 패널은 단일 강사와 다중 강사 둘 다 처리해야 한다.

## Page 3. Solution Page

### Page Role

- 이 페이지는 첫 번째 결과 페이지의 지표를 바탕으로 도출 가능한 **순수 인사이트**만 보여주는 페이지다.
- 차트를 반복하지 않고 사람이 바로 읽을 수 있는 개선 포인트 카드 중심으로 구성한다.

### Layout

- 대형 hero 대신 compact intro 를 사용한다.
- 세로 스크롤형 카드 목록으로 구성한다.
- 핵심 영역은 아래 2개면 충분하다.
  - insight card grid
  - external trend status card

### Insight Cards

- 기본적으로 `5~6개`를 목표로 한다.
- 각 카드에는 작은 아이콘, 짧은 제목, 문제 요약, 근거, 개선 제안이 있어야 한다.
- 인사이트 1~5는 내부 분석 결과만으로 생성 가능해야 한다.
- 인사이트 6은 외부 조사 실패 시에도 페이지 전체를 깨뜨리지 않아야 한다.

### Page 3 Acceptance Checklist

- Page 2에서 넘어왔을 때 시각 톤이 자연스럽게 이어져야 한다.
- 솔루션 페이지는 차트보다 카드형 인사이트 중심이어야 한다.
- insight card 는 읽기 쉬운 card grid 로 유지한다.
- external trend slot 은 과장 없이 상태 중심으로 보여준다.
