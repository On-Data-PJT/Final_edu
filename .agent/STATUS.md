# STATUS

Last Updated: 2026-04-09

## Current Snapshot

- 저장소 목적: 강의 자료를 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차를 비교하는 공모전용 MVP
- 현재 앱 스택: `FastAPI + Jinja + CSS + Vanilla JS + uv + RQ`
- 현재 실행 명령:
  - Web: `uv run python -m final_edu --reload`
  - Worker: `uv run python -m final_edu.worker`
- 현재 입력 포맷: `PDF`, `PPTX`, `TXT/MD`, `YouTube URL`, `YouTube Playlist URL`
- 현재 과정 계약:
  - `Page 1`에서 과정명, 커리큘럼 PDF, 담당 강사 roster 를 등록
  - `POST /courses/preview`는 커리큘럼 PDF를 `accepted | review_required | rejected`로 판정하고 저장 가능 여부를 함께 반환
  - 시간표형 커리큘럼 PDF는 `layout` 텍스트를 기준으로 slot 수를 집계해 목표 비중을 자동 산출할 수 있음
  - `review_required`에서만 편집 표를 다시 노출하고, `rejected`는 저장을 차단함
- 현재 분석 계약:
  - `Page 1`에서 선택한 과정과 강사별 업로드 파일/YouTube 입력으로 job 을 생성
  - YouTube playlist 입력은 `prepare -> confirm -> enqueue` 2단계로 확장 확인 후 분석
  - YouTube `watch?v=...&list=...` 형태의 재생목록 내 단일 영상 URL은 전체 playlist 가 아니라 단일 영상으로 유지
  - `playlist?list=...`처럼 명시적 playlist URL만 전체 playlist 로 확장
  - YouTube metadata/playlist 해석과 transcript fetch 는 process-local throttle 과 object-storage 기반 shared cache 를 사용한다
  - `prepare` transcript probe 와 worker 본분석 transcript fetch 는 같은 cache key / storage 경로를 공유한다
  - 결과는 `GET /jobs/{job_id}`의 Page 2 와 `GET /jobs/{job_id}/solutions`의 Page 3 에서 확인
  - 결과 렌더링은 샘플 데이터가 아니라 저장된 `course`와 실제 업로드/YouTube 분석 결과만 사용
- 현재 Page 2 데이터 계약:
  - `mode_series`
  - `rose_series_by_mode`
  - `keywords_by_mode`
  - `line_series_by_mode`
  - `rose_series_by_instructor`, `keywords_by_instructor`는 `combined` alias 호환용으로 유지
- 현재 분석 모드:
  - `OPENAI_API_KEY`가 있으면 embedding 기반 분석 사용
  - 키가 없거나 실패하면 lexical fallback
  - 솔루션 인사이트는 `OPENAI_INSIGHT_MODEL` 사용, 실패 시 deterministic fallback
  - 커리큘럼 preview 는 bounded timeout 안에서 OpenAI 검증을 시도하고, 지연/실패 시 로컬 fallback 으로 전환
  - YouTube 요청 완화는 `FINAL_EDU_YOUTUBE_REQUEST_MIN_INTERVAL_SECONDS`, `FINAL_EDU_YOUTUBE_METADATA_CACHE_TTL_SECONDS`, `FINAL_EDU_YOUTUBE_TRANSCRIPT_CACHE_TTL_SECONDS`로 조정 가능
- 현재 브랜치 상태: `dev...origin/dev` (dirty)

## What Changed This Round

- `test` 브랜치의 `demo.html` 시각 톤과 Page 2 구조를 `dev` 기준 구현 계약으로 반영했다.
- `.agent/DESIGN.md`를 demo 기반 연한 초록색 디자인 시스템으로 교체했다.
  - `Page 1`은 색감/재질감만 변경하고 구조, 크기, 기능, interaction contract 는 유지하도록 명시했다.
  - `Page 2`는 좌측 sticky sidebar + 우측 4개 패널 stack 구조를 기준으로 고정했다.
  - `Page 3`는 기존 insight 구조를 유지하면서 같은 green tone 으로 연결하도록 정리했다.
- `.agent/Components.md`를 실제 결과 기준으로 갱신했다.
  - Page 2 첫 패널 우측 상단 toggle 하나가 `combined | material | speech` 전체 dataset source 를 제어하도록 명시했다.
  - fake demo 데이터 사용 금지, 실제 `course`/업로드/YouTube 결과만 사용하도록 잠갔다.
  - 특정 mode 에 데이터가 없으면 다른 mode 로 치환하지 않고 해당 mode empty state 를 보여줘야 한다고 고정했다.
- `.agent/AGENTS.md`의 아키텍처 계약을 현재 구현에 맞게 갱신했다.
  - Page 2 결과 페이지를 `sidebar + 4 panel` dashboard 로 정의했다.
  - Page 2 toggle 이 페이지 전체 데이터셋을 제어한다는 인터페이스 계약을 추가했다.
  - 결과 payload contract 에 `rose_series_by_mode`, `keywords_by_mode`를 포함시켰다.
- YouTube 완화 정책을 proxy 기반에서 `throttle + shared cache` 기반으로 교체했다.
  - proxy env 와 관련 helper 를 제거했다.
  - `prepare`와 worker 가 같은 object-storage cache 를 재사용하도록 연결했다.
  - rate limit 시 stale transcript cache fallback 과 explicit warning/error 문구를 유지했다.

## Implemented UI / Data State

- `Page 1`
  - 기존 중앙 composer 레이아웃, modal 구조, lane hit area, 입력 흐름은 유지
  - 전체 배경, border, hover, 버튼, notice, chip 을 demo 계열의 연한 초록 톤으로 전환
- `Page 2`
  - 기존 compact toolbar/dashboard 를 demo-inspired `sidebar + 4 panel` 레이아웃으로 교체
  - sidebar 에 Home 링크, Overview active item, 패널 anchor 링크, 현재 선택 강사/상태/대주제 수/업데이트 정보 표시
  - Panel 1에 dataset toggle, donut, prev/next 강사 이동, 강사 chip row 배치
  - Panel 2 word cloud 는 선택 강사와 dataset mode 에 동기화
  - Panel 3는 평균 bar + 강사별 stacked bar 를 한 카드 안에서 divider 로 연결
  - Panel 4는 목표 비교 차트와 강사 on/off control, `솔루션 보기` CTA 로 구성
- Page 2 mode toggle 연동 범위:
  - donut
  - word cloud
  - 평균 bar
  - 강사별 stacked bar
  - 목표 대비 비교 차트
- 결과 payload 확장:
  - `AnalysisRun`에 `rose_series_by_mode`, `keywords_by_mode` 추가
  - 분석기에서 `combined`, `material`, `speech` 별 rose/keyword 집계를 생성
  - 기존 `rose_series_by_instructor`, `keywords_by_instructor`는 `combined` alias 로 유지
- Page 1 preview 안정화:
  - `/courses/preview`는 `preview_course_pdf()`를 threadpool 에서 실행해 event loop blocking 을 피함
  - OpenAI curriculum preview client 에 timeout 과 `max_retries=0`을 적용해 오래 걸리면 로컬 fallback 으로 전환
- YouTube 입력 안정화:
  - `watch?v=...&list=...&index=...`는 단일 영상으로 해석
  - 명시적 `playlist?list=...` URL만 playlist 확장
  - `yt_dlp` metadata/playlist resolution 과 `youtube-transcript-api` transcript fetch 둘 다 process-local throttle 을 사용
  - metadata / transcript 결과는 object storage 기반 shared cache 로 저장돼 `prepare`와 worker 가 재사용한다
  - transcript cache 가 stale 이어도 YouTube 요청이 일시 제한되면 stale transcript 를 warning 과 함께 재사용한다
  - cache miss 상태에서 요청 제한이 걸리면 generic no-text 대신 explicit warning/error 를 반환한다
- 현재 Page 2는 `Study Labs`, 샘플 강사명, 샘플 비율 배열, 샘플 keyword 같은 demo seed content 를 쓰지 않는다.

## Verification

- 정적/문법 검증
  - `python3 -m py_compile final_edu/*.py tests/test_page2_dashboard.py tests/test_course_preview.py tests/test_youtube_inputs.py tests/test_youtube_cache.py`
  - `node --check final_edu/static/app.js`
- 테스트
  - `python3 -m unittest tests.test_page2_dashboard`
  - `python3 -m unittest tests.test_course_preview`
  - `python3 -m unittest tests.test_youtube_inputs`
  - `python3 -m unittest tests.test_youtube_cache`
  - 검증 내용:
    - `material / speech / combined` mode 별 rose/keyword payload 생성
    - `/jobs/{job_id}`의 새 dashboard shell 렌더링
    - demo seed 문자열 미노출
    - `/courses/preview` 업로드 응답
    - OpenAI curriculum preview timeout 설정 반영
    - `watch URL + list query`와 `playlist URL`의 YouTube 분기 검증
    - metadata cache hit 시 `yt_dlp` 미호출
    - transcript cache hit 의 prepare -> analysis 재사용
    - stale transcript cache fallback 과 throttle 최소 간격 적용
    - explicit request-limit warning/error 유지
- 디자인 검수 아티팩트
  - 경로: `.final_edu_runtime/design-review/demo-port/`
  - backend: desktop은 `cmux`, mobile 은 Playwright fallback
  - 생성물:
    - `page1-desktop-idle.png`
    - `page2-desktop-top.png`
    - `page2-desktop-mid.png`
    - `page2-desktop-bottom.png`
    - `page2-mobile-top.png`
    - `page3-desktop.png`
    - `page3-mobile.png`
- 로컬 미리보기
  - `.final_edu_runtime/object_store/jobs/ui-preview-job/result.json`
  - `.final_edu_runtime/jobs/ui-preview-job.json`
  - 필요 시 `uv run python -m final_edu --reload`로 동일 흐름 재확인 가능

## Known Gaps / Next Priorities

- 실제 교육용 데모 데이터셋 자체는 아직 별도로 정리되지 않음
- Render 실배포 검증은 아직 하지 않음
- R2 / Render KV 를 연결한 worker 실운영 경로는 아직 검증하지 않음
- 첫 uncached YouTube 요청이 hard block 상태인 경우 throttle + cache 만으로는 즉시 해소되지 않을 수 있음
- 자막 없는 YouTube 영상에 대한 STT fallback 은 아직 미구현
- 외부 동향 슬롯은 placeholder 수준이며 실검색 기반 확장은 아직 없음
- `Page 2`에서 특정 mode 데이터가 완전히 비는 실제 운영 케이스에 대한 추가 UX 문구 polish 는 여지 있음
- 8000에서 이미 멈춰 있는 기존 `--reload` 프로세스는 새 코드가 반영되려면 재시작이 필요함
- 모바일 밀도와 스크롤 길이에 대한 추가 polish 는 선택 과제

## Working Tree Notes

- 현재 dirty 변경 파일:
  - `.env.example`
  - `.agent/AGENTS.md`
  - `.agent/Components.md`
  - `.agent/DESIGN.md`
  - `.agent/DEBUG.md`
  - `.agent/STATUS.md`
  - `final_edu/app.py`
  - `final_edu/analysis.py`
  - `final_edu/config.py`
  - `final_edu/courses.py`
  - `final_edu/extractors.py`
  - `final_edu/jobs.py`
  - `final_edu/models.py`
  - `final_edu/static/app.js`
  - `final_edu/static/styles.css`
  - `final_edu/templates/job.html`
  - `final_edu/youtube_cache.py`
  - `tests/test_page2_dashboard.py`
  - `tests/test_course_preview.py`
  - `final_edu/youtube.py`
  - `tests/test_youtube_inputs.py`
  - `tests/test_youtube_cache.py`
  - `render.yaml`
- 이번 라운드 작업은 `dev` 브랜치에서만 진행했고, `test` 브랜치는 수정하지 않았다.
- 다음 작업자는 현재 문서 계약을 기준으로 Page 2 실데이터 UX와 배포 검증을 이어가면 된다.

## Recent Updates

### 2026-04-09

- `test` 브랜치 demo 톤을 기준으로 `.agent/DESIGN.md`를 연한 초록색 디자인 시스템으로 재정의
- `.agent/Components.md`에 Page 2 sidebar + 4 panel 구조, 전역 dataset toggle, 실데이터 only 계약 반영
- `.agent/AGENTS.md`에 Page 2 결과 payload / dataset toggle 인터페이스 계약 반영
- `AnalysisRun`과 분석기에 mode 별 rose/keyword payload 추가
- `Page 2`를 demo-inspired sidebar dashboard 로 재구성하고 toggle 이 페이지 전체 차트를 동기화하도록 수정
- Page 1 / Page 3를 같은 green tone 으로 리스킨
- `tests/test_page2_dashboard.py` 추가로 mode payload와 새 dashboard 렌더링 회귀 검증 추가
- `/courses/preview`가 OpenAI curriculum preview 지연에 서버 전체를 묶지 않도록 threadpool + timeout 보호를 추가
- `tests/test_course_preview.py` 추가로 preview endpoint와 OpenAI timeout 설정 회귀 검증 추가
- `watch?v=...&list=...` URL이 전체 playlist 로 확장되던 오류를 수정하고, 명시적 playlist URL만 확장하도록 `final_edu/youtube.py`를 보강
- `tests/test_youtube_inputs.py` 추가로 watch URL / playlist URL 분기 회귀 검증 추가
- YouTube proxy support 를 제거하고, request throttle + shared cache 기반 완화 정책으로 교체
- `final_edu/youtube_cache.py`를 추가해 cache key, TTL, stale transcript fallback, request spacing 을 공통화
- `tests/test_youtube_cache.py` 추가로 metadata cache hit, transcript cache reuse, stale fallback, throttle 회귀 검증 추가
