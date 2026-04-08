# STATUS

Last Updated: 2026-04-08

## Current Snapshot

- 저장소 목적: 강의 자료를 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차를 시각화하는 공모전용 MVP
- 현재 앱 스택: `FastAPI + Jinja + CSS + uv + RQ`
- 현재 실행 명령: `uv run python -m final_edu --reload`
- 현재 worker 실행 명령: `uv run python -m final_edu.worker`
- 현재 입력 포맷: `PDF`, `PPTX`, `TXT/MD`, `YouTube URL`
  - 현재 YouTube 입력은 개별 영상 URL 기준이며, 재생목록 URL의 내부 영상 자동 확장은 아직 미구현
- 현재 분류 기준: 운영자가 직접 입력한 대단원 커리큘럼
- 현재 분석 모드:
  - `OPENAI_API_KEY`가 있으면 OpenAI embedding 사용
  - 키가 없거나 실패하면 lexical similarity fallback
- 현재 작업 방식:
  - `POST /analyze`는 즉시 결과를 반환하지 않음
  - 분석 Job을 생성하고 `/jobs/{job_id}`에서 상태/결과를 확인함
- 현재 배포 전제:
  - 프로덕션: `Render Web + Worker + Key Value + R2`
  - 로컬: `inline/local` fallback
- 현재 환경 변수 로딩:
  - 저장소 루트 `.env` 자동 로드
  - 이미 export 된 환경 변수가 있으면 `.env`보다 우선
- 현재 로컬 startup 호환성:
  - `REDIS_URL`이 없으면 웹 앱 import 경로에서 `rq`를 지연 로드해 `inline/local` fallback 으로 시작
  - Windows에서도 `uv run python -m final_edu --reload` 웹 실행 경로가 `rq`의 `fork` import 에 막히지 않도록 보강됨
- 현재 운영 문서 체계:
  - `AGENTS.md`: bootstrap entrypoint
  - `.agent/AGENTS.md`: 실제 운영 계약 문서
  - `.agent/STATUS.md`: 현재 상태 스냅샷 + 최근 변경
  - `.agent/DEBUG.md`: 해결된 오류와 재발 방지 규칙
  - `.agent/Components.md`: 페이지별 UI 구성요소 및 상호작용 명세
  - `.agent/DESIGN.md`: 전체 웹 작업물의 시각 톤 및 디자인 시스템 명세
  - `./.codex/skills/final-edu-design/SKILL.md`: repo-local 디자인 구현 스킬
  - 협업 규칙 문서는 `.agent/AGENTS.md` 중심으로 단일화되고, 루트 `AGENTS.md`는 bootstrap 으로만 유지
- 현재 브랜치 상태: `dev...origin/dev`
- 현재 작업 트리 상태: clean 상태 유지 기준으로 관리

## Current Goal

- 현재 목표는 **전체 커리큘럼 배치 분석 MVP를 안정화**하는 것
- 지금 시점에서 가장 중요한 다음 단계:
  - 실제 데모용 강의자료 2~3세트 확보
  - Render 실배포 검증
  - R2 / Render KV 연결 후 worker 실운영 경로 검증
  - 결과 해석 문구와 경고 메시지 튜닝

## Current Parallel Lanes

- Lane 1. Extraction Hardening
  - 대상: `final_edu/extractors.py`
  - 목적: YouTube transcript 실패 메시지, PDF/PPTX unsupported 경고 개선
- Lane 2. Analysis Tuning
  - 대상: `final_edu/analysis.py`, `final_edu/utils.py`
  - 목적: threshold, evidence 선택, `Other / Unmapped` 해석 개선
- Lane 3. Web / Demo Polish
  - 대상: `final_edu/app.py`, `final_edu/templates/*`, `final_edu/static/*`, `render.yaml`
  - 목적: Job 상태 UX, 결과 화면 가독성, 배포 동선 정리
- Lane 4. Queue / Storage Integration
  - 대상: `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/worker.py`, `final_edu/config.py`
  - 목적: RQ, Redis/KV, R2 연결 안정화
- Sidecar Explorer
  - 목적: Render worker/R2 실배포 제약, YouTube transcript 실패 유형, 데모 데이터 적합성 조사

현재 lane 들은 파일 충돌이 적어서 병렬 subagent 작업 대상으로 적합합니다.

## Implemented So Far

- 협업 환경 초기 세팅 완료
  - `uv` 기반 개발환경 통합
  - Python `3.12.12` 고정
  - GitHub 원격 저장소 연결
- IDE 실행 환경 정리 완료
  - `.vscode` 설정으로 워크스페이스 루트 기준 실행 가능
- 웹 MVP 골격 구현 완료
  - `GET /`, `POST /analyze`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/status`, `GET /health`
  - FastAPI 앱 팩토리 및 CLI 실행 경로 구현
- 배치 처리 인프라 골격 구현 완료
  - Job payload / Job metadata 모델 추가
  - 로컬 파일 기반 Job 저장소 추가
  - Redis/RQ 기반 Job 저장소 및 큐 어댑터 추가
  - 로컬 inline queue fallback 추가
  - inline/local 모드에서 Redis/RQ import 지연 로드로 Windows 웹 startup 호환성 보강
  - Local object storage / R2 object storage 어댑터 추가
  - worker 실행 엔트리포인트 추가
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
  - Job 상태 화면
  - 강사별 비교 바
  - 평균 대비 편차 표시
  - 근거 스니펫 표시
  - 경고 메시지 표시
  - 최근 작업 목록
- 배포 준비 파일 추가 완료
  - `.env.example`
  - `render.yaml`
- 페이지별 UI 요구사항 문서 추가
  - `.agent/Components.md`에 메인 페이지, 첫 번째 결과 페이지, 솔루션 페이지 명세 정리
- 시각 디자인 계약 문서 추가
  - `.agent/DESIGN.md`에 전체 웹 작업물의 톤, 색상, 타이포, 컴포넌트 스타일 규칙 정리
- repo-local 디자인 스킬 추가
  - `final-edu-design` 스킬 생성
  - scored reviewer loop, subagent workflow, screenshot capture script, review rubric 문서화
  - Page 1, Page 2/3 기준 forward-test 로 workflow 전달력 점검

## Verified Working

- `uv sync` 성공
- 앱 팩토리 import 및 route 등록 성공
- `GET /health` 정상 응답
- 루트 화면 렌더링 성공
- 샘플 텍스트 자산 2개 기준 Job 생성 -> 상세 화면 -> 결과 렌더링 성공
- `GET /jobs/{job_id}/status` 정상 응답
- 최근 작업 목록에 새 Job 반영 성공
- 잘못된 커리큘럼 입력 시 `400` 에러 렌더링 확인
- `uv run python -m final_edu --help` 정상 응답
- inline 모드에서 `final_edu.jobs.create_job_services()` import / 생성 성공
- `uv run python -m final_edu --reload --port 8011` 정상 기동 및 종료 확인
- `final-edu-design` 스킬 `SKILL.md` frontmatter / `agents/openai.yaml` 메타데이터 수동 검증 완료
- `final-edu-design`의 `capture_pages.py` 문법 검증 완료
- `final-edu-design` 스킬을 사용한 subagent forward-test 2건 통과

## Known Gaps / Next Priorities

- 실제 교육용 데모 데이터셋이 아직 없음
- Render 실배포 검증은 아직 하지 않음
- R2와 Render KV를 실제로 연결한 worker 경로는 아직 검증하지 않음
- 현재 `rq 2.7.0` 기준 Windows의 별도 worker 실행은 `fork` 컨텍스트 제약 가능성이 있어 WSL/Linux 또는 배포 환경 검증이 더 적합함
- YouTube transcript 실패 케이스를 더 다듬을 필요가 있음
- YouTube 재생목록 URL을 내부 영상 URL들로 펼쳐 분석하는 기능은 아직 없음
- `.agent/Components.md`는 3페이지 구조까지 정리됐지만, 아직 실제 템플릿/CSS에는 반영되지 않았다
- 결과 페이지에서 요구하는 `only발화` 모드는 자막 없는 영상까지 포함하려면 STT 파이프라인이 추가로 필요하다
- 솔루션 페이지의 외부 조사 기반 인사이트는 고위험 확장 기능이며 아직 구현되지 않았다
- `.agent/DESIGN.md`는 작성되지만 아직 실제 템플릿/CSS에 전면 반영되지는 않은 상태다
- 자막 없는 영상 STT fallback 은 아직 미구현
- 스캔 PDF / 이미지 기반 PPTX는 정확도가 낮음
- 배치 아키텍처 전환과 운영 문서 보강은 현재 브랜치에 반영되어 있다
- `final-edu-design` 스킬은 생성되었고 forward-test 는 통과했지만, 아직 실제 UI 코드 변경 라운드에서 full loop 로 사용되지는 않았다

## Working Tree Notes

- 기존 MVP 구현은 현재 `dev` 브랜치에 커밋되어 원격까지 푸시된 상태다
- 다음 작업자는 시작 전에 `git status --short --branch`를 확인해야 한다
- 현재 기준점은 Windows 로컬 startup 호환성 패치, repo-local 디자인 스킬, `.agent/` 문서 체계 전환이 `dev` 브랜치에 반영된 상태다
- 루트 `AGENTS.md`는 bootstrap entrypoint 로 유지되고, canonical 운영 문서는 `.agent/` 아래에서 관리된다
- 다음 작업자는 이 브랜치 기준으로 바로 후속 작업을 이어가면 된다
- `.agent/STATUS.md`는 현재 사실을 기록하는 문서이며, 방금 만든 모든 커밋 해시를 계속 덧붙이는 용도로 쓰지 않는다

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
- `.agent/AGENTS.md`를 운영 계약 문서 source of truth 로 확장
- `.agent/STATUS.md`, `.agent/DEBUG.md` 생성
- 작업 시작/종료 시 문서 갱신 워크플로우 고정
- 중대한 변경사항 발생 시 `.agent/AGENTS.md`까지 함께 수정하는 규칙 추가
- subagent 병렬 작업 규칙 구체화
- dispatch matrix, 병렬 수 제한, handoff/integration gate, stable parallel lane 개념 추가
- 기능 브랜치 `feat/mvp-curriculum-coverage` 생성
- 커밋 `836c53d` (`feat: add curriculum coverage MVP`) 생성
- 원격 `origin/feat/mvp-curriculum-coverage`로 푸시 및 추적 브랜치 설정 완료
- 중복 역할의 `CONTRIBUTING.md` 삭제
- 협업/운영 규칙 문서를 `.agent/AGENTS.md` 중심으로 정리
- 즉시 분석 구조를 Job 기반 배치 아키텍처로 전환 시작
- `final_edu/jobs.py`, `final_edu/storage.py`, `final_edu/worker.py` 추가
- `POST /analyze`를 Job enqueue 방식으로 변경
- `/jobs/{job_id}`, `/jobs/{job_id}/status` 추가
- 로컬 개발용 `inline/local` fallback 추가
- `.env.example`, `README.md`, `render.yaml`을 Web + Worker + KV + R2 기준으로 갱신
- 로컬 TestClient 기준 Job 생성/상태/결과 검증 통과
- 샌드박스 밖 실행으로 `uv.lock` 갱신 완료
- `uv sync` 완료 및 새 의존성(`boto3`, `redis`, `rq`) 설치 반영
- `.agent/STATUS.md`의 작업 트리 상태를 실제 clean 상태로 정정
- `.agent/AGENTS.md`에 커밋/푸시 후 `.agent/STATUS.md` 재검증 규칙 추가
- 커밋/푸시 후 `.agent/STATUS.md`가 무한히 다시 수정되지 않도록 close-out 규칙을 현재 사실 중심으로 정리
- 저장소 루트 `.env` 자동 로딩 추가
- 로컬 개발에서 OpenAI 키를 `.env`에만 두고도 앱이 설정을 읽도록 정리
- `.env` 자동 로딩 변경을 `feat/mvp-curriculum-coverage` 브랜치에 커밋 및 푸시 완료
- Windows에서 `uv run python -m final_edu --reload` 실행 시 `rq`의 `fork` import 로 깨지던 문제 원인 확인
- `final_edu/jobs.py`에서 Redis/RQ import 를 지연 로드로 변경해 inline/local 웹 startup 경로에서 `rq` top-level import 제거
- `final_edu/worker.py`에서 `REDIS_URL` 선검사와 Windows `fork` 제약 안내 메시지 추가
- `README.md`에 Windows 로컬 웹 실행과 worker 제약 메모 반영
- inline 모드 서비스 생성, `/health`, 샘플 job 생성, 실제 `--reload` 기동까지 재검증 완료
- Windows 로컬 startup 호환성 패치 커밋을 `feat/mvp-curriculum-coverage` 브랜치에 푸시 완료
- 현재 지원 범위를 명확히 하기 위해 `.agent/STATUS.md`에 YouTube 재생목록 자동 확장 미구현 상태를 반영
- 메인 페이지 UI 요구사항을 `.agent/Components.md`로 문서화
- `Web / Demo Agent`가 UI 작업 전에 `.agent/Components.md`를 참고하도록 운영 문서에 반영
- 전체 웹 작업물의 시각 톤을 `.agent/DESIGN.md`로 문서화
- `Web / Demo Agent`가 UI 작업 전에 `.agent/Components.md`와 `.agent/DESIGN.md`를 함께 참고하도록 운영 문서에 반영

### 2026-04-08

- 현재 작업 브랜치 이름을 `feat/mvp-curriculum-coverage`에서 `dev`로 변경
- 새 원격 추적 브랜치 `origin/dev` 생성 및 업스트림 전환 완료
- 기존 원격 `origin/feat/mvp-curriculum-coverage` 삭제 완료
- 현재 작업 기준 브랜치는 `dev`로 통일
- `.agent/Components.md`를 3페이지 구조 기준으로 확장
- Page 1에 목표 비중 수정형 `Add Course` 모달과 `enter-like` 완료 버튼 요구사항 추가
- Page 2에 4단 스크롤 결과 페이지와 `only발화 / only자료 / 발화+자료` 토글 요구사항 추가
- Page 3에 5~6개 인사이트 중심의 솔루션 페이지 요구사항 추가
- STT 의존 기능과 외부 조사 기반 인사이트를 고위험 범위로 명시
- repo-local 디자인 스킬 `final-edu-design` 생성
- `.agent/AGENTS.md`에 디자인 관련 작업 시 `final-edu-design` 스킬 참조 의무 추가
- 디자인 작업 완료 정의에 screenshot artifact 와 reviewer `90점` 기준 추가
- subagent 2개로 `Page 1`, `Page 2/3` 기준 forward-test 수행
- forward-test 결과를 반영해 contract lock 항목에 route/state 전달 방식, 차트 구현 방식, editable form 형태를 추가
- 운영 문서 5종을 `.agent/` 폴더 아래로 이동
- 루트 `AGENTS.md`는 다음 에이전트 자동 진입을 위한 bootstrap 파일로 축소
- 디자인 스킬과 README의 문서 참조 경로를 `.agent/` 기준으로 갱신
