#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "playwright is required. Run with "
        "`uv run --with playwright python ./.codex/skills/final-edu-design/scripts/capture_pages.py ...`"
    ) from exc


VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1200},
    "tablet": {"width": 1024, "height": 1366},
    "mobile": {"width": 390, "height": 844},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture page screenshots from a manifest.")
    parser.add_argument("--manifest", required=True, help="Path to the JSON manifest.")
    parser.add_argument("--output-dir", required=True, help="Directory where screenshots are written.")
    return parser.parse_args()


def load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "targets" not in payload:
        raise ValueError("Manifest must be a JSON object with a 'targets' field.")
    return payload


def resolve_viewport(target: dict) -> dict:
    viewport = target.get("viewport", "desktop")
    if isinstance(viewport, str):
        if viewport not in VIEWPORTS:
            raise ValueError(f"Unknown viewport preset: {viewport}")
        return VIEWPORTS[viewport]
    if isinstance(viewport, dict) and "width" in viewport and "height" in viewport:
        return {"width": int(viewport["width"]), "height": int(viewport["height"])}
    raise ValueError("Viewport must be a preset string or an object with width/height.")


def resolve_url(base_url: str | None, raw_url: str) -> str:
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    if not base_url:
        raise ValueError("Relative target URL requires base_url in the manifest.")
    return urljoin(base_url.rstrip("/") + "/", raw_url.lstrip("/"))


def run_action(page, base_url: str | None, action: dict) -> None:  # noqa: ANN001
    action_type = action.get("type")
    if action_type == "click":
        page.locator(action["selector"]).click()
        return
    if action_type == "fill":
        page.locator(action["selector"]).fill(action.get("value", ""))
        return
    if action_type == "press":
        page.locator(action["selector"]).press(action["key"])
        return
    if action_type == "wait_for":
        page.locator(action["selector"]).wait_for()
        return
    if action_type == "wait_ms":
        page.wait_for_timeout(int(action.get("ms", 250)))
        return
    if action_type == "goto":
        page.goto(resolve_url(base_url, action["url"]), wait_until="networkidle")
        return
    raise ValueError(f"Unsupported action type: {action_type}")


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path)
    base_url = manifest.get("base_url")
    targets = manifest.get("targets", [])
    if not isinstance(targets, list) or not targets:
        raise ValueError("Manifest 'targets' must be a non-empty list.")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for target in targets:
                name = target["name"]
                url = resolve_url(base_url, target["url"])
                viewport = resolve_viewport(target)
                wait_for = target.get("wait_for")
                delay_ms = int(target.get("delay_ms", 250))
                full_page = bool(target.get("full_page", True))
                actions = target.get("actions", [])

                context = browser.new_context(
                    viewport=viewport,
                    color_scheme="light",
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle")
                if wait_for:
                    page.locator(wait_for).wait_for()
                if delay_ms:
                    page.wait_for_timeout(delay_ms)
                for action in actions:
                    run_action(page, base_url, action)
                if delay_ms:
                    page.wait_for_timeout(delay_ms)

                output_path = output_dir / f"{name}.png"
                page.screenshot(path=str(output_path), full_page=full_page)
                print(str(output_path))
                context.close()
            browser.close()
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "Executable doesn't exist" in message or "browserType.launch" in message:
            print(
                "Chromium is not installed for Playwright. Run "
                "`uv run --with playwright python -m playwright install chromium` first.",
                file=sys.stderr,
            )
        raise

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
