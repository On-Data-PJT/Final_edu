# STATUS

Last Updated: 2026-04-13

## Current Snapshot

- 저장소 목적: 강의 자료와 YouTube/VOC 입력을 표준 커리큘럼 기준으로 정규화해 강사별 커리큘럼 커버리지 편차와 개선 포인트를 비교하는 공모전용 MVP
- 현재 기준 브랜치: `main`
- 현재 앱 스택: `FastAPI + Jinja + CSS + Vanilla JS + uv + RQ`
- 현재 실행 명령:
  - Web: `uv run python -m final_edu --reload`
  - Worker: `uv run python -m final_edu.worker`
- 선택적 실행 환경 변수:
  - `FINAL_EDU_KIWI_MODEL_PATH`: Windows/비ASCII 경로에서 `Kiwi` 기본 모델 로딩이 실패할 때 ASCII-only 경로를 지정하는 override
- 현재 입력 포맷:
  - 과정 등록: `커리큘럼 PDF`
  - 강의 자료: `PDF`, `PPTX`, `TXT/MD`
  - VOC 자료: `PDF`, `CSV`, `TXT`, `XLSX`, `XLS`
  - 링크 입력: `YouTube URL`, `YouTube Playlist URL`

## Current Product State

- `Page 1`
  - `dev`의 centered composer lane UI를 유지하되, 각 lane 은 좌측 `+` dropdown 으로 `강의자료 / 유튜브 링크 / VOC` 입력면을 전환한다.
  - 과정 추가 popup 은 커리큘럼 preview 결과를 `accepted | review_required | rejected`와 무관하게 항상 editable table 로 보여주고, 사용자가 대주제 row 를 추가/삭제하며 직접 정리할 수 있다.
  - 과정 추가 popup 의 preview 비중 input 은 자동 산출값과 같은 소수 둘째 자리까지 허용하며, browser step validation 때문에 auto-filled weight 가 저장을 막지 않게 맞춘다.
  - 커리큘럼 PDF에 `강의 구성 로드맵`과 `총 N강`이 있으면 preview 비중은 `강수 기준`을 canonical source 로 사용하고, 주차 기반 값은 fallback 으로만 쓴다.
  - `accepted`와 `review_required`는 안내 문구만 다르고 같은 editable preview table 을 사용하며, `rejected`도 빈 row 또는 추출 초안을 바탕으로 직접 정리해 저장할 수 있다.
  - `과정 목록` popup 의 각 row 는 `선택 hit area + 작은 x 삭제 버튼`으로 분리되어 있고, 삭제는 별도 확인 popup 을 거친다.
  - lane 하단 공통 rail 에 파일, 링크, VOC chip 을 함께 유지하고, 현재 보이는 입력면만 바뀐다.
  - persisted draft restore 는 `files`, `vocFiles`, `youtubeUrls`, `instructorName`와 함께 마지막 lane `mode`를 복원한다.
  - lane `mode`는 마지막으로 열어 둔 입력면을 뜻하며, 이미 저장된 자산을 다른 source bucket 으로 재해석하지 않는다.
  - 파일 drag/drop과 picker 업로드는 lane 전체가 아니라 현재 보이는 `files`/`voc` surface 기준으로만 저장된다.
  - `youtube` surface 에서는 파일 업로드를 받지 않고 안내 메시지만 보여준다.
  - analyze submit multipart 는 hidden file input `FileList`가 아니라 lane JS state(`files / youtubeUrls / vocFiles`)에서 직접 조립한다.
  - persisted draft auto-restore 는 `page1_submission_version >= 2`인 저장본만 사용하고, legacy draft 는 notice 후 빈 lane 으로 초기화한다.
  - VOC input 은 `PDF/CSV/TXT/XLSX/XLS`를 받되, Excel workbook 은 `clear response sheet` 또는 `BQ 평점 + 기타 의견` survey matrix sheet를 허용하고 구조가 모호하면 prepare 단계에서 거부한다.
  - VOC chip 은 일반 파일 chip 과 구분되는 `VOC` 배지로 표시된다.
  - analyze submit 과 prepare confirm 대기 중에는 blocking loading overlay 를 띄워 현재 처리 중임을 보여준다.
  - 분석 제출은 `과정 선택 + 유효 lane 1개 이상`일 때만 활성화된다.
  - 현재 선택된 과정을 삭제하면 선택 상태, persisted/local draft, pending prepare 상태를 비우고 composer 를 즉시 초기 empty state 로 리셋한다.
- `Page 2`
  - `dev`의 `sidebar + 4 panel` dashboard 구조를 유지한다.
  - 첫 패널의 `combined | material | speech` toggle 이 Page 2 전체 데이터셋 source of truth 다.
  - 결과 payload 는 `available_source_modes`, `source_mode_stats`를 함께 내보내고, 데이터가 없는 mode 는 disabled + empty state 로 처리한다.
  - 커버리지 도넛/bar/radar 는 `커리큘럼 대단원과 실제로 매칭된 텍스트만`을 분모로 쓰는 mapped-only share 를 표시한다.
  - word cloud 는 raw 텍스트 기준을 유지하고, 주변 발화/비커리큘럼 표현도 계속 관찰할 수 있다.
  - `전체 평균` word cloud 는 `average_keywords_by_mode`를 사용해 실제 강사 keyword list만 집계하고, 공개 `keywords_by_mode`에는 더 이상 `__off_curriculum` pseudo-key를 넣지 않는다.
  - 강사가 1명뿐인 결과에서는 `전체 평균` word cloud 와 해당 강사 word cloud 가 같은 term/value set 을 사용한다.
  - word cloud keyword 생성은 coverage/tokenizer 경로와 분리된 전용 tokenizer 를 사용하고, 저신호 구어체(`다음`, `생각`, `모양`)와 숫자형 noise 를 더 공격적으로 제거한다.
  - word cloud ranking 은 현재 분석 run 내부 chunk 집합 기준 TF-IDF 와 반복 등장 가중을 사용하되, 저장소 전체 historical job 상태에 따라 결과가 변하지 않게 유지한다.
  - source 는 있었지만 mapped coverage 가 0인 mode 는 toggle 을 유지한 채 차트 대신 empty state 를 보여준다.
  - speech 분류는 transcript 를 1차 근거로 쓰되, section `title + description`에서 뽑은 generic fragment anchor 와 strict glossary anchor 를 함께 사용해 coverage 후보를 만든다.
  - YouTube chapter title 은 semantic nearest-neighbor 가 아니라 exact/normalized fragment match 와 bounded chapter-index rescue 로만 보조되고, title만 비슷한 off-curriculum 영상은 coverage 에 넣지 않는다.
  - `mapped_tokens / total_tokens`가 낮은 mode 는 coverage note 를 함께 보여 mapped-only `100%`가 전체 발화/자료 `100%`처럼 읽히지 않게 한다.
  - 영상 제목과 transcript 주제가 크게 어긋나면 non-blocking warning 을 남겨 explainability 를 보강한다.
  - 결과 렌더는 저장된 `course`와 실제 업로드/YouTube 분석 결과만 사용한다.
- `Page 3 / Review`
  - `GET /review`는 강사별 실제 VOC 결과 페이지다.
  - 강사별 `voc_analysis`를 사용해 파일 메타, 문항별 평균 점수, 감성 키워드, 반복 불만 패턴, 개선 포인트를 렌더한다.
- `Page 4 / Solution`
  - `GET /solution`은 기존 `분석 결과 기반 인사이트`, `최신 업계 동향 분석` 2섹션을 유지한다.
  - solution gap/benchmark 비교는 강사 평균 actual share 가 아니라 과정의 `target_weight`를 기준으로 계산한다.
  - `강사별 갭 현황` 카피는 `강사별 표준커리큘럼 준수도` 기준 문구로 정리되어 있다.
  - 하단에 별도 `VOC 기반 인사이트` 패널이 추가되어 공통 `voc_summary`의 전체 문항 평균 점수와 자유의견 요약을 함께 렌더한다.
  - legacy `/jiye` 실험 페이지와 `/jobs/{job_id}/solutions` 별도 solutions 페이지는 제거되고, 메인 결과 흐름은 `/jobs/{job_id}` → `/review` → `/solution`만 유지한다.

## Backend Contract

- `dev` UI/레이아웃/라우트는 유지하고, `lexical`의 백엔드를 이식한 상태다.
- 과정 preview/save 계약은 `preview decision`이 아니라 최종 `sections_json` 유효성 기준으로 저장 가능 여부를 판단한다.
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
  - 공식 웹 실행은 factory entrypoint(`uv run python -m final_edu --reload`) 기준이며, module-level `final_edu.app:app` 객체 존재를 전제로 하지 않는다.
  - worker startup 은 `Kiwi` readiness 를 먼저 검증하고, web 은 lexical 경로에서만 `Kiwi`를 lazy-load 한다.
  - `Kiwi` 초기화 실패는 worker startup 또는 실제 lexical 분석 경로에서 명시적 runtime error 로 드러나야 하며, Render starter web 에서는 startup preload 를 하지 않는다.
  - `FINAL_EDU_KIWI_MODEL_PATH`가 설정되면 해당 경로로 `Kiwi` 모델을 로드하고, 없으면 패키지 기본 경로를 사용한다.
  - section title 사용자 사전을 미리 등록한다.
  - curriculum-first keyword ranking 을 유지한다.
  - material 파일 chunking 은 PDF/슬라이드 경계를 넘겨 합치지 않고, overlap 없이 page/slide 단위로 처리한다.
  - material section assignment 는 section `title + description`에서 뽑은 generic fragment anchor 를 기본으로 사용하고, glossary 는 보강용으로만 남긴다.
  - material chunk 에 explicit anchor evidence 가 없으면 nearest-neighbor 로 억지 배정하지 않고 unmapped 로 남긴다.
  - 커버리지 share 는 raw total token 이 아니라 mapped token 만을 분모로 계산한다.
  - word cloud keyword 집계는 전역 `tokenize()`와 별도의 `tokenize_keywords()` 경로를 사용해 coverage 분류 규칙과 분리한다.
  - word cloud keyword ranking 은 current-run TF-IDF 와 per-chunk repeat weighting 을 쓰고, storage 전체 과거 job 결과를 문서 집합으로 쓰지 않는다.
  - speech section assignment 는 section `title + description` 기반 generic fragment anchor 와 strict speech anchor glossary 를 함께 사용한다.
  - speech anchor matching 은 substring 이 아니라 token/boundary 기준으로 계산해 `지니고` 같은 일반 어절이 `지니` anchor 로 오탐되지 않게 한다.
  - YouTube source label 은 cache 된 human title 을 우선 사용한다.
  - speech title prior 는 exact/normalized fragment match 와 bounded chapter-index rescue 만 사용하고, transcript score 가 최소 plausibility 를 넘지 못하면 강제 배정하지 않는다.
- VOC 분석 계약:
  - Page 1 업로드된 `voc_files`는 payload -> worker -> result 로 실제 전달된다.
  - VOC OpenAI text analysis 호출은 `temperature=0`으로 고정해 같은 입력에서 요약 drift 를 줄인다.
  - VOC spreadsheet 는 `BQ 평점 문항 점수 집계`와 `자유의견 row text 분석`을 함께 지원한다.
  - `xlsx/xls` survey workbook 은 multi-row header 를 collapse 해 `BQ` 평점 문항과 `기타 의견` 열을 동시에 추출한다.
  - `AQ` 계열 문항은 점수 집계에서 제외하고, `기타 의견` 같은 자유의견 열만 텍스트 VOC 분석 source 로 사용한다.
  - `xlsx/xls` workbook 에 응답 후보 sheet 가 여러 개이거나 survey/text 구조가 모두 모호하면 prepare 단계에서 명시적 오류로 거부한다.
  - Page 1 lane payload 는 `JobInstructorInput.mode`로 explicit lane mode 를 함께 저장한다.
  - 단일 roster 과정에서 generic 강사명(`강사 1`)이 submit payload 로 남으면 과정 roster 기준으로 정규화한다.
  - 강사별 `voc_analysis`, 공통 `voc_summary`를 result JSON에 저장하고, 둘 다 `question_scores`를 포함할 수 있다.
  - 커버리지 자료가 없어도 VOC만 있으면 VOC-only 결과를 반환한다.
- 과정 삭제 계약:
  - `DELETE /courses/{course_id}`는 과정 JSON, curriculum PDF object, 해당 과정의 completed/failed job metadata와 `jobs/{job_id}/...` object prefix, matching prepare cache 를 함께 hard delete 한다.
  - `queued/running` job 이 있으면 삭제는 `409`로 거부되고 기존 데이터는 그대로 유지된다.
  - `POST /analyze/prepare/{request_id}/confirm`는 enqueue 직전 course 존재 여부를 다시 확인하고, 이미 삭제된 과정이면 stale prepare 를 지우고 `404`로 차단한다.
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
- material page 내부에 `■/▷/Q1` 같은 semantic marker 가 있으면 smaller subchunk 로 재분할하고, `확인 문제/답:/빈칸 채우기/필기 공간` 같은 worksheet noise 는 coverage assignment 입력에서 제외하도록 보강했다.
- section assignment 는 이제 title/description 원문만이 아니라 bilingual alias search text 를 함께 사용해 `Deep Learning and Boltzmann Machine` 같은 영어 section 도 `딥 러닝`, `제한적 볼츠만 기계`, `RBM` 표현을 잡을 수 있게 했다.
- speech section assignment 에 YouTube chapter title rescue prior 를 추가해 `[2-3] Introduction to Decision Trees`, `[2-4] Entropy and Information Gain` 같은 chapter title 이 transcript near-tie/unmapped 를 보조하도록 보강했다.
- YouTube extraction 은 metadata cache 의 human title 을 source label 로 재사용해 evidence 와 warning 에서 실제 영상 제목이 보이게 했다.
- `결정 트리` section alias 를 `entropy`, `information gain`, `지니`, `가지치기`, `root/leaf node`까지 확장해 decision-tree 발화가 `Deep Learning`/`Other`로 밀리던 회귀를 줄였다.
- speech coverage 에 strict anchor gate 를 추가해 `Decision Boundary`, `Rule-Based`, `Regularization` 같은 off-curriculum/인접 주제가 nearest-neighbor 로 `결정 트리`에 빨려 들어가지 않도록 조정했다.
- speech anchor matching 을 token sequence 기준으로 바꿔 `지니고` 같은 일반 어절이 `지니`로 오탐되던 회귀를 막고, exact title match + 단일 transcript anchor 가 있는 SVM/Decision Tree chapter 는 rescue 되도록 보강했다.
- chapter형 커리큘럼에서도 특정 대단원만 anchor 가 풍부해 `SVM 100%`처럼 붕괴하지 않도록, speech anchor 를 section `title + description`에서 generic fragment 로 추출하고 title rescue 를 exact fragment / bounded chapter index 로 일반화했다.
- Page 2 coverage 패널에 low mapped coverage note 를 추가해, 실제로는 `mapped_tokens`만 작게 잡힌 결과가 mapped-only normalization 때문에 `100%`처럼 보일 때 해석 근거를 함께 보여주도록 했다.
- material lexical-streaming aggregate 가 raw total token 분모를 쓰던 회귀를 고쳐, material `mode_series`와 `rose_series_by_mode`도 openai path 와 같은 mapped-only share 계약을 따르도록 통일했다.
- material section assignment 는 ML 강의 전용 glossary 편향을 줄이기 위해 section `title + description` 기반 generic fragment anchor 를 1차 기준으로 재구성했고, explicit anchor evidence 가 없는 chunk 는 unmapped 로 남기도록 보수적으로 조정했다.
- Page 2 결과 payload 에 `mode_unmapped_series`를 추가하고, 도넛 차트가 보이는 slice 들만 다시 100으로 정규화하지 않도록 수정했다.
- Page 2 `source_mode_stats`에 `mapped_tokens`를 추가하고, 커버리지 도넛/bar/radar를 mapped-only share 기준으로 재정의했다.
- Page 2 상단 도넛에서 `미분류` slice 를 제거하고, source는 있으나 mapped coverage가 0인 mode는 empty state 로 처리하도록 정리했다.
- word cloud 는 raw mode tokens 기준을 유지해 비커리큘럼 표현을 계속 관찰할 수 있게 했다.
- Page 2 결과 payload 에 `average_keywords_by_mode`를 추가하고, `전체 평균` word cloud 가 더 이상 `keywords_by_mode` 전체를 flatten 하거나 `__off_curriculum` internal key 를 섞지 않도록 정리했다.
- 단일 강사 결과에서는 `전체 평균` word cloud 와 개별 강사 word cloud 가 같은 keyword set 을 쓰도록 맞추고, word cloud 색상도 token 기반 stable color 로 고정했다.
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
- VOC input 에 `xlsx/xls`를 추가하고, prepare 단계에서 ambiguous workbook 을 거부하는 sheet-selection validator 를 넣었다.
- VOC survey workbook(`BQ 점수 + 기타 의견`)을 first-class 로 지원하도록 extractor 를 확장하고, 강사별/전체 `question_scores`를 result payload 에 추가했다.
- `review`는 강사별 문항 평균 점수와 자유의견 기반 VOC 요약을 함께 보여주고, `solution`의 `VOC 기반 인사이트`는 전체 문항 평균 점수와 전체 자유의견 요약을 함께 보여주도록 정리했다.
- 과정 목록 popup 에 과정 삭제 버튼과 확인 popup 을 추가하고, `DELETE /courses/{course_id}` hard delete 경로를 연결했다.
- 삭제는 관련 completed/failed job metadata, `jobs/{job_id}` object prefix, matching `analysis-preparations/*.json`까지 함께 정리하도록 보강했다.
- 진행 중 job 이 있는 과정 삭제는 `409`로 거부하고, stale prepare confirm 은 course existence check 로 차단하도록 정리했다.
- VOC extractor 는 clear response sheet 뿐 아니라 multi-row-header survey workbook 에서 `BQ` 점수 문항과 `기타 의견` 열을 동시에 추출하도록 보강했다.
- 과정 추가 popup 의 preview table 을 `accepted/review_required/rejected` 모두에서 항상 editable 하게 바꾸고, `대주제 추가`/행 삭제를 지원하도록 보강했다.
- Page 1 course save gating 에서 `preview.decision === "rejected"` 차단을 제거하고, 유효한 preview rows 가 있으면 사용자가 직접 정리한 커리큘럼도 저장할 수 있게 맞췄다.
- 과정 추가 popup 의 preview 비중 input step 을 `0.01`로 맞춰 자동 산출된 `13.33`, `20.01` 같은 값이 브라우저 native validation 에 걸리지 않도록 보강했다.
- 커리큘럼 preview 에 `강의 구성 로드맵` 기반 local parser 를 추가해 `Chapter ... 총 N강` 형식의 PDF는 OpenAI 변동과 무관하게 `lecture_count` 기준의 고정 비중을 사용하도록 정리했다.
- `render.yaml`을 현재 ScraperAPI/STT/probe/distributed throttle env 계약과 맞췄다.
- `yt-dlp` metadata 해석은 더 이상 ScraperAPI proxy 를 타지 않고, metadata-only `process=False` 경로와 단일 영상 fallback 을 사용한다.

## Verification

- 정적/문법 검증
  - `python3 -m py_compile final_edu/*.py tests/test_page1_restore.py tests/test_page2_dashboard.py tests/test_voc_analysis.py`
  - `node --check final_edu/static/app.js`
- 테스트
  - `source ~/.zshrc; UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest tests.test_page1_restore tests.test_page2_dashboard tests.test_voc_analysis`
- 검증 내용
- `course_restore_drafts_json`가 dropdown lane shell 과 explicit `mode` restore 를 유지하는지
- mixed lane restore 에서 `files`와 `voc_files`가 동시에 separate download URL 로 유지되는지
- legacy draft payload 가 reset metadata 와 빈 restore block 으로 직렬화되는지
- `/analyze/prepare` multipart 가 `files`와 `voc_files`를 분리 저장하고 `page1_submission_version`을 payload에 남기는지
- material semantic subchunk 가 worksheet question block 을 제거하는지
- `Deep Learning and Boltzmann Machine`와 `랜덤 포레스트 / 오토인코더`가 같은 material 페이지에서 동시에 non-zero 로 배정되는지
- `결정 트리` assignment text 가 `entropy / information gain / 가지치기` alias 를 포함하는지
- speech title prior 가 near-tie decision-tree chunk 를 rescue 하고, title-transcript mismatch 에서는 hard override 대신 warning 을 남기는지
- `Decision Boundary` title 이 `결정 트리` exact title anchor 로 오인되지 않는지
- `지니고` 같은 한국어 어절이 `지니` anchor 로 오탐되지 않는지
- exact title match 가 있는 `Soft Margin with SVM` chunk 가 단일 transcript anchor 만 있어도 SVM rescue 후보가 되는지
- persisted draft JSON 이 `voc_files`와 VOC restore download URL 을 따로 내보내는지
- `/` 렌더에 Page 1 loading overlay shell 과 기본 문구가 포함되는지
- `/` 렌더가 versioned `/static/styles.css?v=...`와 `/static/app.js?v=...`를 내보내는지
- `/analyze/prepare`가 clear `review.xlsx` VOC upload 를 허용하고 payload 에 별도 `voc_files`로 저장하는지
- `/analyze/prepare`가 응답 후보 sheet 가 둘 이상인 ambiguous `review.xlsx`를 400 오류로 거부하는지
- `DELETE /courses/{id}`가 course JSON, curriculum PDF, related completed job object prefix, matching prepare cache 를 함께 삭제하는지
- `DELETE /courses/{id}`가 `running` job 이 있으면 `409`로 거부하고 기존 파일을 보존하는지
- 삭제된 과정을 참조하는 stale `POST /analyze/prepare/{request_id}/confirm`이 `404`로 차단되고 prepare cache 를 지우는지
- VOC 분석이 `review.xlsx` workbook 을 CSV와 같은 row-text 로 읽고 response count / sentiment / suggestions 를 만드는지
- `.xls` VOC input 이 row-style sheet reader 를 통해 same extractor contract 를 따르는지
- 분석 결과 payload 가 `available_source_modes`, `source_mode_stats`를 내보내는지
- 분석 결과 payload 가 `mode_unmapped_series`를 함께 내보내는지
- 분석 결과 payload 의 `source_mode_stats`가 `mapped_tokens`를 함께 내보내는지
- material 자산이 없는 job payload 에서 `material` mode 가 unavailable 로 표시되는지
- `/jobs/{id}` 렌더가 disabled source toggle shell 과 empty-state shell 을 포함하는지
- material multi-page PDF 가 page boundary preserving chunk 로 처리되어 여러 section 에 분산되는지
- mapped-only share 기준에서 mode별 section 비중 합이 100%가 되는지
- source는 있으나 mapped coverage가 0인 mode가 available 상태를 유지하면서 coverage empty state 로 전환되는지

## Known Gaps / Next Priorities

- `POST /analyze/prepare`부터 저장 결과까지 가는 VOC-only HTTP end-to-end 테스트는 아직 없다.
- `job_voc_asset_download`의 실제 파일 응답 body/download header 자체를 검증하는 direct route 테스트는 아직 없다.
- 이미 잘못 저장된 기존 job/draft 의 `files`/`voc_files` 오분류를 자동 복구하는 migration 은 아직 없다.
- OCR 기반 스캔 PDF 지원은 아직 없다.
- VOC workbook 자동 보정은 conservative 하므로, 응답 sheet 가 둘 이상인 Excel 은 사용자가 단일 sheet 나 CSV 로 정리해 다시 올려야 한다.
- 기존 completed job 은 자동 재계산되지 않으므로, material 분포 개선은 재분석 후에만 반영된다.
- 외부 동향 인사이트는 deterministic fallback 중심이며 실검색 기반 고도화는 아직 없다.
- Render 실배포 smoke test 는 아직 별도로 수행하지 않았다.

## Working Tree Notes

- 현재 작업 브랜치는 `main`이다.
- 현재 구현은 `dev` UI 유지 + `lexical` 백엔드 이식 + 실제 VOC 분석 연결 상태를 기준으로 한다.
- `.codex/config.toml`은 로컬 Codex 실행 설정으로 취급하며 저장소 커밋 대상이 아니다.

## Consulted DEBUG IDs

- `DBG-005`
- `DBG-012`
- `DBG-014`
- `DBG-015`
- `DBG-016`
- `DBG-017`
- `DBG-020`
- `DBG-021`
- `DBG-023`
- `DBG-024`
- `DBG-027`
- `DBG-028`
- `DBG-029`
- `DBG-030`
- `DBG-031`
- `DBG-032`
- `DBG-033`
- `DBG-035`
- `DBG-036`
- `DBG-037`
- `DBG-026`
- `DBG-047`
- `DBG-048`
- `DBG-049`
- `DBG-038`
- `DBG-043`
- `DBG-006`
- `DBG-044`
- `DBG-039`
- `DBG-040`
- `DBG-041`

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
- Page 2 coverage share 분모를 raw total token 에서 mapped token 으로 바꿔, `그럼/다음/그리고` 같은 주변 발화가 미분류 비중으로 차트를 잠식하지 않도록 수정했다.
- `source_mode_stats`에 `mapped_tokens`를 추가하고, source는 있지만 mapped coverage가 0인 mode는 toggle 을 유지한 채 coverage empty state 로 분기하도록 보강했다.
- word cloud 는 raw token 기준을 유지해 비커리큘럼 표현을 별도로 관찰할 수 있게 했다.
- VOC 업로드 허용 형식에 `XLSX/XLS`를 추가했고, workbook 에 응답 후보 sheet 가 여러 개면 prepare 단계에서 명시적으로 거부하도록 보강했다.
- VOC Excel extractor 는 clear response sheet 뿐 아니라 survey matrix workbook 도 읽어 `BQ` 점수 집계와 `기타 의견` row text 분석을 함께 수행하도록 보강했다.
- 과정 목록 popup 에 row별 삭제 버튼과 중앙 확인 popup 을 추가했다.
- `DELETE /courses/{course_id}` hard delete route 를 추가해 course/curriculum PDF/관련 completed job/prepare cache 를 함께 정리하도록 보강했다.
- 진행 중 분석이 걸린 과정 삭제는 `409`로 막고, stale prepare confirm 은 course existence 재검사 후 `404`로 차단하도록 정리했다.
- 과정 목록 삭제 버튼이 `svg/path`를 직접 클릭하면 delegated click handler의 `HTMLElement` guard 때문에 첫 클릭이 무시되던 회귀를 잡고, `Element` 기준 target 정규화와 40px hit area로 first-click 반응성을 복구했다.

### 2026-04-13

- `render.yaml`에 Render Blueprint 검증용 `region`, Key Value `ipAllowList: []`, `maxmemoryPolicy: noeviction`를 추가해 Blueprint schema 오류 없이 web/worker/keyvalue를 같은 리전으로 생성할 수 있게 정리했다.
- Render 대상 사용자 지연시간을 줄이기 위해 Blueprint의 `web`, `worker`, `keyvalue` 리전을 `singapore`로 통일했다.
- Render secret env 는 저장소의 `.env`를 자동 sync 하지 않으므로, `OPENAI_API_KEY`, `FINAL_EDU_YOUTUBE_SCRAPERAPI_KEY`, `R2_*` 값은 계속 `sync: false` 상태로 Render 대시보드에서 직접 입력해야 한다.
- Render 실배포 로그에서 보인 보호 PDF 500 회귀를 잡기 위해, `/courses/preview`가 `FileNotDecryptedError`와 주요 PDF parse 오류를 더 이상 route-level 500으로 올리지 않고 `rejected/unreadable` preview payload로 반환하도록 보강했다.
- YouTube prepare에서 단일 영상 metadata anti-bot/format 오류가 fallback으로 숨겨질 때도, prepare warnings 에 `재생시간 추정은 제외하고 계속 진행` 문구를 남기고 서버 로그에도 `metadata fallback used`를 기록하도록 정리했다.
- transcript fetch 실패 로그에 `scraperapi_enabled`, `proxy_active`, 예외 타입을 함께 남겨 Render에서 ScraperAPI 사용 여부와 transcript 제한을 더 쉽게 판별할 수 있게 보강했다.
- `tests.test_course_preview`, `tests.test_youtube_inputs`에 encrypted/broken PDF rejected preview와 single-video metadata fallback warning surface 회귀를 추가했다.
- `origin/jiye`의 오래된 브랜치를 merge 하지 않고, 현재 `dev` 위에 필요한 세 변경만 선별 이식했다.
- VOC OpenAI text analysis 호출에 `temperature=0`을 추가해 강사별 자유의견 요약의 비결정성을 줄였다.
- solution payload 의 gap benchmark 를 강사 평균 actual share 대신 과정 `target_weight` 기준으로 바꿔, `표준커리큘럼 준수도` 해석이 목표 비중과 직접 비교되도록 정리했다.
- `solution.html`의 커버리지/표준커리큘럼 준수도 카피와 trend fallback 문구를 `jiye` 기준으로 일부 갱신하면서도, 최근 `dev`의 VOC question score 그룹 렌더는 그대로 보존했다.
- route만 남아 있던 `/jiye`, `/jobs/{job_id}/solutions`와 관련 legacy template/scratch 파일을 정리하고, 메인 서비스 플로우에 영향이 없는지 회귀 테스트로 확인했다.
- `Kiwi` 모델 경로를 repo 코드에 하드코딩하지 않고, 선택적 `FINAL_EDU_KIWI_MODEL_PATH` 설정으로 override 할 수 있게 정리했다.
- worker startup 에서만 `Kiwi` readiness 를 fail-fast 로 검증하고, web startup 은 preload 를 제거해 Render starter 메모리 압박을 줄이도록 정리했다.
- 공식 실행 경로는 계속 factory entrypoint(`uv run python -m final_edu --reload`)로 유지하고, module-level `app` 객체 추가는 기본 계약으로 채택하지 않았다.
- Render Blueprint web/worker `startCommand`를 `.venv/bin/python -m ...`로 바꿔 `uv run` 재기동 오버헤드를 줄였다.
- `/jobs/{job_id}/status`가 `queue_wait_seconds`, `last_update_seconds`, `is_stalled`, `stalled_message`를 함께 내려 queued/running 정체를 UI와 로그에서 더 쉽게 식별할 수 있게 했다.
- job polling 화면은 stalled job 과 반복 poll 실패 때 generic spinner 대신 Render worker/restart 점검 안내를 보여주도록 보강했다.
- Page 1 `prepare`/`confirm` 요청에는 Render 재시작/OOM 상황을 감안한 timeout 과 명시적 네트워크 오류 문구를 추가했다.
- `tests.test_render_runtime`에 web startup no-Kiwi preload, worker fail-fast, stalled job status, Render start command, Page 1 timeout 회귀를 추가했다.
- `tests.test_voc_analysis`에 configured `Kiwi` model path 사용과 startup failure 메시지 회귀를 추가했다.
- chapter형 커리큘럼 speech 분류에서 특정 대단원만 anchor 가 풍부해 `SVM 100%`처럼 붕괴하던 문제를 줄이기 위해, section `title + description` 기반 generic fragment anchor 와 exact/normalized fragment + bounded chapter-index title rescue 를 도입했다.
- Page 2 coverage 패널에 low mapped coverage note 를 추가해, 실제 `mapped_tokens` 비율이 낮을 때 mapped-only `100%`가 전체 발화/자료 `100%`처럼 읽히지 않게 보조 설명을 노출하도록 정리했다.
- `yeon_copy`의 wordcloud filtering 강화 의도는 최신 `dev` 계약 위로 선별 이식했고, 전역 tokenizer 회귀나 storage-wide TF-IDF 대신 wordcloud 전용 tokenizer + current-run TF-IDF 로 재구성했다.
- `tests.test_page2_dashboard`에 chaptered playlist title rescue 회귀와 coverage note shell 회귀를 추가했다.

### 2026-04-11

- `dev` 기준으로 `lexical`의 ScraperAPI/STT/Kiwi/YouTube 완화 백엔드를 통합했다.
- VOC 업로드를 실제 분석 파이프라인과 `/review`, `/solution` 렌더에 연결했다.
- `/solution`에 별도 `VOC 기반 인사이트` 패널을 추가했다.
- 운영문서와 Render/env 계약을 현재 구현 기준으로 정리했다.
- `prepare` 단계의 `yt-dlp` metadata 500 회귀를 막기 위해 metadata direct / transcript proxy 분리와 단일 영상 fallback 을 도입했다.
