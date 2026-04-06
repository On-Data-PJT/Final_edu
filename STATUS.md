# STATUS

Last Updated: 2026-04-07

## Current Snapshot

- 저장소 목적: 강의 자료를 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차를 시각화하는 공모전용 MVP
- 현재 앱 스택: `FastAPI + Jinja + CSS + uv`
- 현재 실행 명령: `uv run python -m final_edu --reload`
- 현재 입력 포맷: `PDF`, `PPTX`, `TXT/MD`, `YouTube URL`
- 현재 분류 기준: 운영자가 직접 입력한 대단원 커리큘럼
- 현재 분석 모드:
  - `OPENAI_API_KEY`가 있으면 OpenAI embedding 사용
  - 키가 없거나 실패하면 lexical similarity fallback
- 현재 운영 문서 체계:
  - `AGENTS.md`: 운영 계약 문서
  - `STATUS.md`: 현재 상태 스냅샷 + 최근 변경
  - `DEBUG.md`: 해결된 오류와 재발 방지 규칙
- 현재 브랜치 상태: `feat/mvp-curriculum-coverage...origin/feat/mvp-curriculum-coverage`
- 현재 작업 트리 상태: 현재 브랜치 기준 clean 상태

## Current Goal

- 현재 목표는 **웹 MVP를 데모 가능한 수준으로 안정화**하는 것
- 지금 시점에서 가장 중요한 다음 단계:
  - 실제 데모용 강의자료 2~3세트 확보
  - Render 실배포 검증
  - 결과 해석 문구와 경고 메시지 튜닝
  - 데모 안정화용 후속 작업을 기능별로 다시 분리

## Current Parallel Lanes

- Lane 1. Extraction Hardening
  - 대상: `final_edu/extractors.py`
  - 목적: YouTube transcript 실패 메시지, PDF/PPTX unsupported 경고 개선
- Lane 2. Analysis Tuning
  - 대상: `final_edu/analysis.py`, `final_edu/utils.py`
  - 목적: threshold, evidence 선택, `Other / Unmapped` 해석 개선
- Lane 3. Web / Demo Polish
  - 대상: `final_edu/app.py`, `final_edu/templates/*`, `final_edu/static/*`, `render.yaml`
  - 목적: UX 문구, 결과 화면 가독성, 배포 동선 정리
- Sidecar Explorer
  - 목적: Render 제약, YouTube transcript 실패 유형, 데모 데이터 적합성 조사

현재 lane 들은 파일 충돌이 적어서 병렬 subagent 작업 대상으로 적합합니다.

## Implemented So Far

- 협업 환경 초기 세팅 완료
  - `uv` 기반 개발환경 통합
  - Python `3.12.12` 고정
  - GitHub 원격 저장소 연결
- IDE 실행 환경 정리 완료
  - `.vscode` 설정으로 워크스페이스 루트 기준 실행 가능
- 웹 MVP 골격 구현 완료
  - `GET /`, `POST /analyze`, `GET /health`
  - FastAPI 앱 팩토리 및 CLI 실행 경로 구현
- 추출 파이프라인 구현 완료
  - PDF 텍스트 추출
  - PPTX 슬라이드 텍스트 추출
  - TXT/MD 텍스트 추출
  - YouTube transcript 기반 텍스트 추출
- 분석 파이프라인 구현 완료
  - 대단원 커리큘럼 파싱
  - 텍스트 청크 정규화
  - 중복 청크 제거
  - 커리큘럼 매핑
  - 강사별 비중 계산
  - `Other / Unmapped` 처리
  - 근거 스니펫 추출
- 결과 UI 구현 완료
  - 강사별 비교 바
  - 평균 대비 편차 표시
  - 근거 스니펫 표시
  - 경고 메시지 표시
- 배포 준비 파일 추가 완료
  - `.env.example`
  - `render.yaml`

## Verified Working

- `uv sync` 성공
- 앱 팩토리 import 및 route 등록 성공
- `GET /health` 정상 응답
- 샘플 텍스트 자산 2개 기준 분석 파이프라인 성공
- FastAPI `TestClient` 기준 `POST /analyze` 렌더링 성공
- `uv run python -m final_edu --help` 정상 응답

## Known Gaps / Next Priorities

- 실제 교육용 데모 데이터셋이 아직 없음
- Render 실배포 검증은 아직 하지 않음
- YouTube transcript 실패 케이스를 더 다듬을 필요가 있음
- 자막 없는 영상 STT fallback 은 아직 미구현
- 스캔 PDF / 이미지 기반 PPTX는 정확도가 낮음
- 현재 브랜치는 clean 상태지만, 이후 작업은 이 브랜치에서 의도된 단위로 이어갈 것

## Working Tree Notes

- 현재 MVP 구현은 `feat/mvp-curriculum-coverage` 브랜치에 커밋되어 원격까지 푸시된 상태다
- 다음 작업자는 시작 전에 `git status --short --branch`를 확인해야 한다
- 이후 변경도 dirty worktree 전제를 유지해 신중히 다루되, 현재 기준점은 clean 이다

## Recent Updates

### 2026-04-06

- 공모전용 공용 저장소 초기화
- `uv` 기반 Python 협업 환경 구성
- `main` 브랜치에 초기 협업 환경 커밋 및 첫 푸시 완료
- IDE 실행 설정 추가

### 2026-04-06 to 2026-04-07

- 강의 커리큘럼 커버리지 분석 MVP 구현 시작
- FastAPI+Jinja 웹 앱, 추출기, 분석기, 템플릿, 배포 설정 추가
- 로컬 smoke test 와 HTTP 레벨 검증 통과

### 2026-04-07

- 운영 문서 체계 도입 및 반영 완료
- `AGENTS.md`를 운영 계약 문서로 확장
- `STATUS.md`, `DEBUG.md` 생성
- 작업 시작/종료 시 문서 갱신 워크플로우 고정
- 중대한 변경사항 발생 시 `AGENTS.md`까지 함께 수정하는 규칙 추가
- subagent 병렬 작업 규칙 구체화
- dispatch matrix, 병렬 수 제한, handoff/integration gate, stable parallel lane 개념 추가
- 기능 브랜치 `feat/mvp-curriculum-coverage` 생성
- 커밋 `836c53d` (`feat: add curriculum coverage MVP`) 생성
- 원격 `origin/feat/mvp-curriculum-coverage`로 푸시 및 추적 브랜치 설정 완료
