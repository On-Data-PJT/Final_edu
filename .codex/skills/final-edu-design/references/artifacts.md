# Review Artifacts

## Required Artifacts

디자인 작업을 reviewer에게 넘기기 전 아래 아티팩트를 만든다.

- 로컬 렌더 결과 확인
- desktop 스크린샷
- mobile 스크린샷
- 새 모달/팝오버/토글 상태가 있으면 상태 스크린샷

기본 저장 경로는 `./.final_edu_runtime/design-review/<task-slug>/`로 둔다.

## Minimum Screenshot Matrix

### Page 1 작업

- `page1-desktop-idle`
- `page1-desktop-course-modal`
- `page1-desktop-course-list`
- `page1-mobile-idle`

### Page 2 작업

- `page2-desktop-top`
- `page2-desktop-mid`
- `page2-desktop-bottom`
- `page2-mobile-top`

### Page 3 작업

- `page3-desktop`
- `page3-mobile`

## Capture Command

Playwright가 없으면 먼저 Chromium을 설치한다.

```bash
uv run --with playwright python -m playwright install chromium
```

그 다음 스크린샷을 캡처한다.

```bash
uv run --with playwright python ./.codex/skills/final-edu-design/scripts/capture_pages.py \
  --manifest /path/to/manifest.json \
  --output-dir ./.final_edu_runtime/design-review/<task-slug>
```

## Manifest Shape

```json
{
  "base_url": "http://127.0.0.1:8011",
  "targets": [
    {
      "name": "page1-desktop-idle",
      "url": "/",
      "viewport": "desktop",
      "wait_for": "body",
      "delay_ms": 300
    },
    {
      "name": "page1-desktop-course-modal",
      "url": "/",
      "viewport": "desktop",
      "actions": [
        { "type": "click", "selector": "[data-testid='open-course-modal']" },
        { "type": "wait_for", "selector": "[data-testid='course-modal']" }
      ]
    }
  ]
}
```

## Action Types

- `click`
- `fill`
- `press`
- `wait_for`
- `wait_ms`
- `scroll_to`
- `scroll_selector`
- `goto`

## Fallback Rule

- 브라우저 설치가 현재 세션에서 불가능하면, 사용자 로컬 브라우저에서 수동 캡처를 받아 reviewer 입력물로 사용한다.
- 단, 스크린샷 없이 reviewer pass를 주지 않는다.
