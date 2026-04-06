# Final Edu

KIT 바이브코딩 공모전용 공용 저장소 초기 세팅입니다. 현재 단계에서는 주제와 서비스 테마가 확정되지 않았으므로, 4인 팀이 같은 개발 환경에서 바로 작업을 시작할 수 있도록 `uv` 기반 Python 협업 환경만 먼저 고정합니다.

## 현재 기준

- Python: `3.12.12`
- 패키지 매니저 및 실행: `uv`
- 원격 저장소: `https://github.com/On-Data-PJT/Final_edu`
- 기본 브랜치: `main`
- 작업 방식: 기능 브랜치 + Pull Request

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

### 3. 가상환경 및 의존성 동기화

```bash
uv sync
```

### 4. 초기 실행 확인

```bash
uv run python -m final_edu
```

정상 동작 시 초기 프로젝트 상태 메시지가 출력됩니다.

## 일상 작업 명령

```bash
uv sync
uv run python -m final_edu
uv run python
```

## IDE 실행

Antigravity/VS Code 계열 IDE에서는 `.vscode/launch.json`과 `.vscode/settings.json`이 포함되어 있어, 워크스페이스 루트를 기준으로 `final_edu` 모듈을 바로 실행할 수 있습니다.

- 인터프리터: `${workspaceFolder}/.venv/bin/python`
- 실행 기준 폴더: 프로젝트 최상위 폴더
- 모듈 경로 기준: `${workspaceFolder}`

우측 상단 실행 또는 디버그에서 `Python: final_edu` 구성을 선택하면 됩니다.

## 협업 규칙

- `main` 브랜치에 직접 커밋하지 않습니다.
- 모든 작업은 `feat/*`, `fix/*`, `docs/*` 브랜치에서 진행합니다.
- 머지는 Pull Request 기준으로만 진행합니다.
- API 키, 비밀번호, 토큰은 절대 커밋하지 않습니다.
- 환경 변수는 `.env`를 사용하고, 공유가 필요한 키 목록만 문서화합니다.

세부 규칙은 `CONTRIBUTING.md`를 따릅니다.

## 제출 문서

공모전 제출 서류 템플릿은 `docs/` 폴더에 보관합니다.

- 개인정보 수집/이용 동의서
- 참가 각서
- AI 리포트 양식

## 공모전 일정 메모

- 최종 제출 마감: `2026-04-13`
- 제출 이후 커밋은 심사 리스크가 될 수 있으므로, 마감 전 코드 프리즈 시점을 팀 내에서 별도로 정해야 합니다.

## 이후 확장 방향

현재는 루트 단일 Python 프로젝트로 시작합니다. 주제 확정 후 필요하면 아래 구조로 확장합니다.

- `apps/web`: 프론트엔드
- `apps/api`: 백엔드 API
- `packages/common`: 공용 로직
- `infra/`: 배포 및 인프라 설정
