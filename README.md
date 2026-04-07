# Final Edu

강의 자료를 표준 커리큘럼 기준으로 정규화해, 강사별 커리큘럼 커버리지 편차를 시각화하는 공모전용 MVP입니다.

현재 버전은 **전체 커리큘럼 자료를 배치 작업으로 등록한 뒤 백그라운드에서 분석**하는 구조를 기준으로 설계되어 있습니다. 결과는 작업 페이지에서 대단원별 비중, 평균 대비 편차, 근거 스니펫, 처리 경고까지 함께 확인합니다.

## 현재 목표

- 한 커리큘럼 전체 자료를 강사별로 한 번에 등록
- PDF, PPTX, TXT/MD, YouTube URL을 공통 텍스트 청크로 정규화
- 대단원 기준 커버리지 편차를 배치 분석
- 결과를 작업 상태 페이지에서 단계적으로 확인

현재 버전은 `품질 점수`를 계산하지 않습니다. 대신 `커리큘럼 커버리지 편차`를 보여주는 분석 도구로 유지합니다.

## 현재 아키텍처

- Web: FastAPI + Jinja
- Worker: RQ worker
- Queue / metadata: Render Key Value 또는 Redis 호환 저장소
- Object storage: Cloudflare R2 권장
- Embedding:
  - `OPENAI_API_KEY`가 있으면 OpenAI embedding 사용
  - 키가 없거나 호출에 실패하면 lexical similarity fallback

로컬 개발에서는 `REDIS_URL`과 R2 설정이 없을 경우 자동으로 `inline/local` fallback으로 동작합니다. 즉, 큐와 오브젝트 스토리지가 없어도 기본 화면과 분석 흐름을 로컬에서 검증할 수 있습니다.

## 지원 범위

- 입력 포맷: `PDF`, `PPTX`, `TXT/MD`, `YouTube URL`
- 기준 커리큘럼: 운영자가 대단원 제목과 설명을 직접 입력
- 강사 수: 최대 3명
- 분석 단위: 대단원 수준
- 결과: 장별 비중, 강사 간 편차, 근거 스니펫, 경고 메시지

## 의도적으로 제외한 범위

- 자막 없는 영상 STT fallback
- 스캔 PDF OCR
- 로그인/사용자 계정
- 영구 이력 보관
- 품질 점수 단일화

## 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/On-Data-PJT/Final_edu.git
cd Final_edu
```

### 2. Python 확인

```bash
python3.12 --version
```

반드시 `Python 3.12.12`여야 합니다.

### 3. 의존성 동기화

```bash
uv sync
```

### 4. 환경 변수 준비

```bash
cp .env.example .env
```

기본 개발 추천:

```env
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FINAL_EDU_HOST=127.0.0.1
FINAL_EDU_PORT=8000
FINAL_EDU_MAX_UPLOAD_MB=100
```

저장소 루트의 `.env`는 앱 시작 시 자동으로 읽습니다.  
단, 이미 셸이나 배포 환경에 export 된 값이 있으면 그 값이 `.env`보다 우선합니다.

### 5. 로컬 서버 실행

```bash
uv run python -m final_edu --reload
```

기본 주소는 `http://127.0.0.1:8000`입니다.

로컬 웹 실행은 `REDIS_URL`이 비어 있으면 `inline/local` fallback 경로를 사용하므로 별도 worker 없이 동작합니다.
Windows 개발 환경에서도 이 웹 실행 경로는 RQ worker import 없이 시작되도록 맞춰져 있습니다.

## Worker 실행

Redis와 R2까지 붙인 프로덕션 구조에서는 별도 worker가 필요합니다.

```bash
uv run python -m final_edu.worker
```

`REDIS_URL`이 없으면 로컬 fallback 경로를 사용하므로 worker는 필수가 아닙니다.
현재 설치된 `rq` 버전 기준으로 Windows의 별도 worker 실행은 제약이 있을 수 있으므로, worker는 WSL/Linux 또는 배포 환경에서 실행하는 쪽을 권장합니다.

## 환경 변수

### 핵심 분석 설정

```env
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FINAL_EDU_MAX_UPLOAD_MB=100
FINAL_EDU_JOB_TTL_DAYS=7
FINAL_EDU_MAX_SAVED_JOBS=20
FINAL_EDU_JOB_TIMEOUT_SECONDS=7200
```

### 웹 실행 설정

```env
FINAL_EDU_HOST=127.0.0.1
FINAL_EDU_PORT=8000
FINAL_EDU_RUNTIME_DIR=.final_edu_runtime
```

### 큐 / 저장소 설정

```env
REDIS_URL=
R2_ENDPOINT_URL=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
R2_REGION=auto
```

## 사용 흐름

1. 표준 커리큘럼을 줄 단위로 입력합니다.
2. 강사별로 자료 파일과 YouTube URL을 넣습니다.
3. `배치 분석 작업 생성` 버튼을 누릅니다.
4. 작업 상세 페이지에서 `queued / running / completed / failed` 상태를 확인합니다.
5. 완료되면 대단원별 비중, 평균 대비 편차, 근거 스니펫을 확인합니다.

권장 커리큘럼 입력 형식:

```text
1. 문제 정의와 요구사항 | 교육 문제 설정, 기대 성과, 기준 지표
2. 핵심 개념 | 용어 정리, 원리 설명, 필수 배경지식
3. 실습과 적용 | 예제, 실습, 코드 작성, 응용
4. 평가와 피드백 | 복습, 점검, 오류 수정, 피드백
```

## 주요 엔드포인트

- `GET /`: 분석 입력 폼 + 최근 작업
- `POST /analyze`: 새 분석 작업 생성
- `GET /jobs/{job_id}`: 작업 상태/결과 상세 화면
- `GET /jobs/{job_id}/status`: polling용 JSON 상태 확인
- `GET /health`: 앱 상태 확인

## Render 배포

현재 `render.yaml`은 아래 구조를 가정합니다.

- Web Service: `starter`
- Worker: `standard`
- Key Value: `starter`
- 외부 Object Storage: Cloudflare R2

예상 고정비는 대략 `약 $42/월`입니다.

- Web Starter: `$7`
- Worker Standard: `$25`
- Key Value Starter: `$10`

R2는 공모전 MVP 규모에서는 거의 비용이 들지 않는 쪽을 기본 전제로 둡니다.

## 로컬 검증 예시

### 도움말 확인

```bash
uv run python -m final_edu --help
```

### 상태 확인

```bash
./.venv/bin/python -c "from fastapi.testclient import TestClient; from final_edu.app import create_app; client=TestClient(create_app()); print(client.get('/health').json())"
```

### 분석 작업 생성 검증

```bash
./.venv/bin/python -c "from pathlib import Path; import tempfile; from fastapi.testclient import TestClient; from final_edu.app import create_app; client=TestClient(create_app()); curriculum='1. 기초 | 변수와 자료형\n2. 실습 | 문제 풀이와 코드 작성'; d=Path(tempfile.mkdtemp()); p1=d/'a.txt'; p2=d/'b.txt'; p1.write_text('변수 자료형 조건문 반복문 기초 개념 설명', encoding='utf-8'); p2.write_text('문제 풀이 실습 코드 작성 예제 적용', encoding='utf-8'); files=[('instructor_1_files', ('a.txt', p1.read_bytes(), 'text/plain')), ('instructor_2_files', ('b.txt', p2.read_bytes(), 'text/plain'))]; data={'curriculum_text': curriculum, 'instructor_1_name': '강사 A', 'instructor_2_name': '강사 B'}; response=client.post('/analyze', data=data, files=files, follow_redirects=False); print(response.status_code, response.headers.get('location'))"
```

## 협업 규칙

- `main` 직접 개발은 초기 세팅까지만 허용
- 이후 작업은 `feat/*`, `fix/*`, `docs/*` 브랜치에서 진행
- PR 기준으로만 머지
- 운영 규칙과 subagent 규칙은 `AGENTS.md` 참조

## 제출 문서

공모전 제출 서류 템플릿은 `docs/` 폴더에 보관합니다.

- 개인정보 수집/이용 동의서
- 참가 각서
- AI 리포트 양식
