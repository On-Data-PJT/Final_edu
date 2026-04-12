# STATUS

Last Updated: 2026-04-12

## Current Snapshot

- 저장소 목적: 강의 자료와 YouTube/VOC 입력을 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차와 개선 포인트를 비교하는 공모전용 MVP
- 현재 기준 브랜치: `dev`
- 현재 앱 스택: `FastAPI + Jinja + CSS + Vanilla JS + uv + RQ`
- 현재 실행 명령:
  - Web: `uv run python -m final_edu --reload`
  - Worker: `uv run python -m final_edu.worker`
- 현재 입력 포맷:
  - 과정 등록: `커리큘럼 PDF`
  - 강의 자료: `PDF`, `PPTX`, `TXT/MD`
  - VOC 자료: `PDF`, `CSV`, `TXT`
  - 링크 입력: `YouTube URL`, `YouTube Playlist URL`

## Current Product State

- `Page 1`
  - `dev`의 centered composer lane UI를 유지하되, 각 lane 은 좌측 `+` dropdown 으로 `강의자료 / 유튜브 링크 / VOC` 입력면을 전환한다.
  - lane 하단 공통 rail 에 파일, 링크, VOC chip 을 함께 유지하고, 현재 보이는 입력면만 바뀐다.
  - persisted draft restore 는 `files`, `vocFiles`, `youtubeUrls`, `instructorName`와 함께 마지막 lane `mode`를 복원한다.
  - lane `mode`는 마지막으로 열어 둔 입력면을 뜻하며, 이미 저장된 자산을 다른 source bucket 으로 재해석하지 않는다.
  - 파일 drag/drop과 picker 업로드는 lane 전체가 아니라 현재 보이는 `files`/`voc` surface 기준으로만 저장된다.
  - `youtube` surface 에서는 파일 업로드를 받지 않고 안내 메시지만 보여준다.
  - analyze submit multipart 는 hidden file input `FileList`가 아니라 lane JS state(`files / youtubeUrls / vocFiles`)에서 직접 조립한다.
  - persisted draft auto-restore 는 `page1_submission_version >= 2`인 저장본만 사용하고, legacy draft 는 notice 후 빈 lane 으로 초기화한다.
  - VOC chip 은 일반 파일 chip 과 구분되는 `VOC` 배지로 표시된다.
  - analyze submit 과 prepare confirm 대기 중에는 blocking loading overlay 를 띄워 현재 처리 중임을 보여준다.
  - 분석 제출은 `과정 선택 + 유효 lane 1개 이상`일 때만 활성화된다.
- `Page 2`
  - `dev`의 `sidebar + 4 panel` dashboard 구조를 유지한다.
  - 첫 패널의 `combined | material | speech` toggle 이 Page 2 전체 데이터셋 source of truth 다.
  - 결과 payload 는 `available_source_modes`, `source_mode_stats`를 함께 내보내고, 데이터가 없는 mode 는 disabled + empty state 로 처리한다.
  - 첫 도넛 차트는 section mapped share 를 raw 값 그대로 보여주고, 남은 비중은 `미분류` slice 로 별도 표시한다.
  - 결과 렌더는 저장된 `course`와 실제 업로드/YouTube 분석 결과만 사용한다.
- `Page 3 / Review`
  - `GET /review`는 강사별 실제 VOC 결과 페이지다.
  - 강사별 `voc_analysis`를 사용해 파일 메타, 감성 키워드, 반복 불만 패턴, 개선 포인트를 렌더한다.
- `Page 4 / Solution`
  - `GET /solution`은 기존 `분석 결과 기반 인사이트`, `최신 업계 동향 분석` 2섹션을 유지한다.
  - 하단에 별도 `VOC 기반 인사이트` 패널이 추가되어 공통 `voc_summary`를 렌더한다.

## Backend Contract

- `dev` UI/레이아웃/라우트는 유지하고, `lexical`의 백엔드를 이식한 상태다.
- YouTube 처리 계약:
  - 명시적 `playlist?list=...`만 playlist 로 확장한다.
  - `watch?v=...&list=...`는 단일 영상으로 유지한다.
  - `prepare`와 worker 는 object-storage 기반 shared cache 를 재사용한다.
  - process-local throttle + distributed throttle + cooldown 을 함께 사용한다.
  - `yt-dlp` metadata/playlist 해석은 direct 경로 + `ignoreconfig=True` + `process=False` 정책을 사용한다.
  - ScraperAPI trial 이 켜져 있으면 transcript fetch 에만 ScraperAPI proxy port 를 사용한다.
  - 공개 자막이 없으면 selective STT fallback 이 동작할 수 있다.
  - 단일 `watch` URL은 metadata 해석이 실패해도 URL에서 video id 를 복구할 수 있으면 계속 진행한다.
  - probe 정책은 `30개 이하 full / 31~200 partial / 200+ skip`이다.
- lexical 분석 계약:
  - `kiwipiepy` 기반 tokenization 을 사용한다.
  - section title 사용자 사전을 미리 등록한다.
  - curriculum-first keyword ranking 을 유지한다.
  - material 파일 chunking 은 PDF/슬라이드 경계를 넘겨 합치지 않고, overlap 없이 page/slide 단위로 처리한다.
- VOC 분석 계약:
  - Page 1 업로드된 `voc_files`는 payload -> worker -> result 로 실제 전달된다.
  - Page 1 lane payload 는 `JobInstructorInput.mode`로 explicit lane mode 를 함께 저장한다.
  - 단일 roster 과정에서 generic 강사명(`강사 1`)이 submit payload 로 남으면 과정 roster 기준으로 정규화한다.
  - 강사별 `voc_analysis`, 공통 `voc_summary`를 result JSON에 저장한다.
  - 커버리지 자료가 없어도 VOC만 있으면 VOC-only 결과를 반환한다.
- 모델 계약:
  - 솔루션 인사이트와 VOC LLM 분석은 `OPENAI_INSIGHT_MODEL`을 사용한다.
  - embedding 경로 실패 시 lexical fallback 으로 내려간다.

## What Changed This Round

- `dev`의 디자인/레이아웃/라우트를 유지한 채 `lexical` 백엔드를 이식했다.
- ScraperAPI, distributed throttle, cooldown, selective STT, playlist probe threshold, Kiwi tokenization 을 `dev` 브랜치에 반영했다.
- Page 1 VOC 업로드를 실제 분석 파이프라인에 연결했다.
  - `JobInstructorInput.voc_files`
  - worker download
  - `InstructorSubmission(voc_files=...)`
  - 강사별 `voc_analysis`
  - 공통 `voc_summary`
- `/review`가 더 이상 placeholder 고정값만 쓰지 않고 실제 결과 JSON 기반으로 렌더되도록 수정했다.
- `/solution`에 기존 2섹션을 유지한 채 별도 `VOC 기반 인사이트` 패널을 추가했다.
- Page 1 lane 을 dropdown 기반 단일 surface + 공통 asset rail 구조로 되돌리고, lane `mode`를 UI 상태로만 유지하도록 정리했다.
- Page 1 파일 업로드를 surface-scoped strict routing 으로 보강해 `study_material.pdf`가 `voc_files`로 잘못 저장되는 회귀를 막았다.
- `youtube` surface 에서는 파일 업로드를 거부하고, 강의자료 또는 VOC surface 로 전환하라는 안내를 보여주도록 정리했다.
- Page 1 analyze submit 이 hidden file input `FileList`를 다시 읽으면서 rail 상태와 서버 payload가 어긋나던 경로를 제거하고, lane JS state에서 multipart 를 직접 조립하도록 수정했다.
- `page1_submission_version=2`를 payload에 저장하고, version 2 미만 legacy draft 는 auto-restore 대신 reset notice 후 빈 lane 으로 초기화하도록 정리했다.
- Page 2 결과 payload 에 `available_source_modes`, `source_mode_stats`를 추가했다.
- Page 2 dataset toggle 은 실제 업로드/분석된 source 만 활성화하고, 비어 있는 mode 는 disabled/empty state 로 노출하도록 보강했다.
- material PDF/PPTX/text chunking 을 page/slide boundary preserving 경로로 분리해 큰 material chunk 가 여러 주차를 한 번에 먹지 않도록 수정했다.
- Page 2 결과 payload 에 `mode_unmapped_series`를 추가하고, 도넛 차트가 보이는 slice 들만 다시 100으로 정규화하지 않도록 수정했다.
- Page 2 첫 도넛은 curriculum section raw share + `미분류` slice 를 함께 렌더하도록 정리했다.
- `/api/evaluate`는 ad-hoc PDF 파싱 대신 공통 VOC 분석 helper 를 재사용하도록 정리했다.
- `job_voc_asset_download`를 추가해 persisted draft 에서 VOC 파일 download URL 을 복원할 수 있게 했다.
- Page 1 analyze manifest 와 payload 가 explicit lane `mode`를 저장하도록 확장했다.
- persisted draft restore 가 mixed lane 에서도 saved `mode`를 우선 사용하도록 보강했다.
- VOC chip 이 일반 파일 chip 과 같은 배지로 보이지 않도록 `VOC` 라벨과 별도 tone 을 적용했다.
- 단일 roster 과정에서 generic 강사명이 저장 payload 에 남지 않도록 submit 정규화를 추가했다.
- `course_restore_drafts_json` 회귀 테스트를 추가해 VOC download URL 과 explicit mode 복원을 검증했다.
- Page 1에 간단한 gear spinner 기반 loading overlay 를 추가해 prepare 전 구간과 confirm/redirect 전 구간의 대기 상태를 사용자에게 노출했다.
- local `inline` queue 모드에서도 결과 페이지로 넘어가기 전까지 loading overlay 가 유지되도록 submit UX를 보강했다.
- `pyproject.toml`과 `uv.lock`에 `kiwipiepy` 의존성을 반영했다.
- `render.yaml`을 현재 ScraperAPI/STT/probe/distributed throttle env 계약과 맞췄다.
- `yt-dlp` metadata 해석은 더 이상 ScraperAPI proxy 를 타지 않고, metadata-only `process=False` 경로와 단일 영상 fallback 을 사용한다.

## Verification

- 정적/문법 검증
  - `python3 -m py_compile final_edu/*.py tests/test_page1_restore.py tests/test_page2_dashboard.py tests/test_voc_analysis.py`
  - `node --check final_edu/static/app.js`
- 테스트
  - `python3 -m unittest tests.test_page1_restore tests.test_page2_dashboard tests.test_voc_analysis`
- 검증 내용
- `course_restore_drafts_json`가 dropdown lane shell 과 explicit `mode` restore 를 유지하는지
- mixed lane restore 에서 `files`와 `voc_files`가 동시에 separate download URL 로 유지되는지
- legacy draft payload 가 reset metadata 와 빈 restore block 으로 직렬화되는지
- `/analyze/prepare` multipart 가 `files`와 `voc_files`를 분리 저장하고 `page1_submission_version`을 payload에 남기는지
- persisted draft JSON 이 `voc_files`와 VOC restore download URL 을 따로 내보내는지
- `/` 렌더에 Page 1 loading overlay shell 과 기본 문구가 포함되는지
- `/` 렌더가 versioned `/static/styles.css?v=...`와 `/static/app.js?v=...`를 내보내는지
- 분석 결과 payload 가 `available_source_modes`, `source_mode_stats`를 내보내는지
- 분석 결과 payload 가 `mode_unmapped_series`를 함께 내보내는지
- material 자산이 없는 job payload 에서 `material` mode 가 unavailable 로 표시되는지
- `/jobs/{id}` 렌더가 disabled source toggle shell 과 empty-state shell 을 포함하는지
- material multi-page PDF 가 page boundary preserving chunk 로 처리되어 여러 section 에 분산되는지

## Known Gaps / Next Priorities

- `POST /analyze/prepare`부터 저장 결과까지 가는 VOC-only HTTP end-to-end 테스트는 아직 없다.
- `job_voc_asset_download`의 실제 파일 응답 body/download header 자체를 검증하는 direct route 테스트는 아직 없다.
- 이미 잘못 저장된 기존 job/draft 의 `files`/`voc_files` 오분류를 자동 복구하는 migration 은 아직 없다.
- OCR 기반 스캔 PDF 지원은 아직 없다.
- 기존 completed job 은 자동 재계산되지 않으므로, material 분포 개선은 재분석 후에만 반영된다.
- 외부 동향 인사이트는 deterministic fallback 중심이며 실검색 기반 고도화는 아직 없다.
- Render 실배포 smoke test 는 아직 별도로 수행하지 않았다.

## Working Tree Notes

- 문서 기준 source branch 는 `dev`다.
- 현재 구현은 `dev` UI 유지 + `lexical` 백엔드 이식 + 실제 VOC 분석 연결 상태를 기준으로 한다.
- `.codex/config.toml`은 로컬 Codex 실행 설정으로 취급하며 저장소 커밋 대상이 아니다.

## Consulted DEBUG IDs

- `DBG-014`
- `DBG-015`
- `DBG-016`
- `DBG-017`
- `DBG-020`
- `DBG-024`
- `DBG-027`
- `DBG-028`
- `DBG-029`
- `DBG-030`
- `DBG-031`
- `DBG-032`
- `DBG-033`

## Recent Updates

### 2026-04-12

- Page 1 lane manifest/payload 가 explicit `mode`를 저장하도록 수정해 mixed lane restore drift 를 줄였다.
- VOC chip 을 `VOC` 배지로 분리해 상태 메시지와 화면 표시가 일치하도록 맞췄다.
- single-roster 과정에서 generic 강사명이 payload 에 남지 않도록 submit 정규화를 추가했다.
- `tests/test_page1_restore.py`로 persisted draft JSON 회귀를 추가했다.
- Page 1 submit/confirm 대기 구간에 gear spinner 기반 loading overlay 를 추가했다.
- local `inline` queue 모드에서도 redirect 전까지 로딩 상태가 유지되도록 prepare/confirm 흐름을 보강했다.
- 브라우저가 구버전 `app.js`/`styles.css`를 계속 쓰는 문제를 막기 위해 static asset URL에 `?v=<mtime_ns>` cache-busting 을 추가했다.
- Page 2 상단 도넛 차트의 내부 ECharts legend 를 바깥 HTML legend 로 교체해 긴 과목명과 퍼센트가 겹치지 않도록 수정했다.
- 새 donut legend 는 한 줄 ellipsis + `title` tooltip + slice highlight 연동을 사용한다.
- Page 1 lane 을 다시 `+` dropdown 기반 입력으로 되돌리되, 저장 구조는 `files / youtube / voc` 분리를 유지하도록 정리했다.
- dropdown lane 복원 뒤에도 lane 전체 drop/picker가 `mode`를 따라 bucket 을 바꾸던 회귀를 잡고, `files`/`voc` surface 자체만 업로드를 받도록 다시 고정했다.
- `youtube` surface 에서는 파일 drop 을 거부하고, mixed restore 테스트에 `files + voc + youtube` 동시 케이스를 추가했다.
- submit 단계에서 hidden file input sync가 다시 rail 상태와 어긋나던 회귀를 제거하고, FormData source of truth를 lane JS state로 옮겼다.
- version 없는 legacy draft는 auto-restore하지 않고 `구버전 저장 상태` notice 후 빈 lane으로 초기화하도록 바꿨다.
- Page 2 결과 payload 에 `available_source_modes`, `source_mode_stats`를 추가했다.
- Page 2 toggle 은 실제 데이터가 없는 `material`/`speech` mode 를 disabled 처리하고, 차트 대신 empty state 를 보여주도록 보강했다.
- material PDF/PPTX/text chunking 을 page/slide boundary preserving 경로로 분리해, 여러 주차가 한 chunk 로 합쳐져 첫 section 으로 쏠리던 회귀를 줄였다.
- Page 2 결과 payload 에 `mode_unmapped_series`를 추가해 `미분류` 비중을 별도로 전달하도록 정리했다.
- Page 2 첫 도넛/legend/tooltip 은 visible slice 재정규화 대신 raw share 를 그대로 보여주고, 남는 비중은 `미분류` slice 로 표시하도록 바꿨다.

### 2026-04-11

- `dev` 기준으로 `lexical`의 ScraperAPI/STT/Kiwi/YouTube 완화 백엔드를 통합했다.
- VOC 업로드를 실제 분석 파이프라인과 `/review`, `/solution` 렌더에 연결했다.
- `/solution`에 별도 `VOC 기반 인사이트` 패널을 추가했다.
- 운영문서와 Render/env 계약을 현재 구현 기준으로 정리했다.
- `prepare` 단계의 `yt-dlp` metadata 500 회귀를 막기 위해 metadata direct / transcript proxy 분리와 단일 영상 fallback 을 도입했다.
