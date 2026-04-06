# Final Edu

강의 자료를 표준 커리큘럼 기준으로 정규화해, 강사별 커리큘럼 커버리지 편차를 시각화하는 공모전용 MVP입니다.

현재 MVP는 다음 문제를 해결하는 데 초점을 둡니다.

- 같은 커리큘럼을 맡은 강사들이 실제로 어느 대단원에 더 많은 비중을 두는지 비교
- PDF, PPTX, YouTube 자막 기반 자료를 하나의 텍스트 기준으로 정규화
- 결과를 웹에서 바로 확인하고, 근거 스니펫까지 함께 제시

## MVP 범위

- 입력 포맷: `PDF`, `PPTX`, `YouTube URL`, `TXT/MD`
- 기준 커리큘럼: 운영자가 대단원 제목과 설명을 직접 입력
- 비교 범위: 강사 2~3명
- 분석 단위: 대단원 수준
- 결과: 장별 비중, 강사 간 편차, 근거 스니펫, 경고 메시지

현재 버전은 `품질 점수`를 계산하지 않습니다. 대신 `커리큘럼 커버리지 편차`를 보여주는 분석 도구로 설계되어 있습니다.

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

### 4. 로컬 서버 실행

```bash
uv run python -m final_edu --reload
```

기본 주소는 `http://127.0.0.1:8000`입니다.

## 환경 변수

`.env` 또는 셸 환경 변수로 아래 값을 줄 수 있습니다.

```bash
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FINAL_EDU_HOST=127.0.0.1
FINAL_EDU_PORT=8000
FINAL_EDU_MAX_UPLOAD_MB=20
```

- `OPENAI_API_KEY`가 있으면 OpenAI 임베딩을 우선 사용합니다.
- 키가 없거나 호출에 실패하면 로컬 lexical similarity로 자동 fallback 됩니다.

## 사용 흐름

1. 표준 커리큘럼을 줄 단위로 입력합니다.
2. 강사별로 자료 파일과 YouTube URL을 넣습니다.
3. 분석을 실행하면 자료를 텍스트 청크로 정규화합니다.
4. 각 청크를 가장 가까운 대단원에 매핑합니다.
5. 강사별 비중, 평균 대비 편차, 근거 스니펫을 확인합니다.

권장 커리큘럼 입력 형식:

```text
1. 문제 정의와 요구사항 | 교육 문제 설정, 기대 성과, 기준 지표
2. 핵심 개념 | 용어 정리, 원리 설명, 필수 배경지식
3. 실습과 적용 | 예제, 실습, 코드 작성, 응용
4. 평가와 피드백 | 복습, 점검, 오류 수정, 피드백
```

## 지원 범위와 한계

- 텍스트형 PDF는 잘 동작하지만, 스캔 PDF는 OCR 없이 정확도가 떨어집니다.
- PPTX는 슬라이드 텍스트와 표 위주로 분석합니다.
- YouTube는 자막 추출 기반입니다. 자막이 없는 영상의 STT fallback은 현재 MVP에 포함하지 않았습니다.
- `Other / Unmapped` 비중은 분류 근거가 약한 텍스트를 따로 보여주기 위한 안전 장치입니다.

## 주요 엔드포인트

- `GET /`: 입력 및 결과 대시보드
- `POST /analyze`: 분석 실행
- `GET /health`: 상태 확인

## IDE 실행

Antigravity/VS Code 계열 IDE에서는 `.vscode/launch.json`과 `.vscode/settings.json`이 포함되어 있어, 워크스페이스 루트를 기준으로 앱을 바로 실행할 수 있습니다.

- 인터프리터: `${workspaceFolder}/.venv/bin/python`
- 실행 기준 폴더: 프로젝트 최상위 폴더
- 모듈 경로 기준: `${workspaceFolder}`

## 배포

Render 배포를 기준으로 `render.yaml`을 포함했습니다.

배포 전 확인 사항:

- `OPENAI_API_KEY`를 Render 환경 변수에 설정할지 결정
- 업로드 가능한 샘플 데이터셋 1세트를 데모용으로 정리
- 제출 직전 코드 프리즈 시점 확보

## 협업 규칙

- `main` 직접 개발은 초기 세팅까지만 허용
- 이후 작업은 `feat/*`, `fix/*`, `docs/*` 브랜치에서 진행
- PR 기준으로만 머지
- 역할 및 subagent 운영 규칙은 `AGENTS.md` 참조

## 제출 문서

공모전 제출 서류 템플릿은 `docs/` 폴더에 보관합니다.

- 개인정보 수집/이용 동의서
- 참가 각서
- AI 리포트 양식
