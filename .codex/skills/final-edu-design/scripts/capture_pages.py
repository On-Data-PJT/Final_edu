#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin


VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1200},
    "tablet": {"width": 1024, "height": 1366},
    "mobile": {"width": 390, "height": 844},
}

SURFACE_PATTERN = re.compile(r"(surface:\d+)")
WORKSPACE_PATTERN = re.compile(r"(workspace:\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture page screenshots from a manifest.")
    parser.add_argument("--manifest", required=True, help="Path to the JSON manifest.")
    parser.add_argument("--output-dir", required=True, help="Directory where screenshots are written.")
    parser.add_argument(
        "--backend",
        choices=["auto", "cmux", "playwright"],
        default="auto",
        help="Capture backend. 'auto' prefers cmux for desktop/tablet and falls back to Playwright.",
    )
    parser.add_argument(
        "--keep-cmux-workspace",
        action="store_true",
        help="Keep the temporary cmux workspace open after capture for manual inspection.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "targets" not in payload:
        raise ValueError("Manifest must be a JSON object with a 'targets' field.")
    return payload


def resolve_viewport(target: dict) -> tuple[str, dict]:
    viewport = target.get("viewport", "desktop")
    if isinstance(viewport, str):
        if viewport not in VIEWPORTS:
            raise ValueError(f"Unknown viewport preset: {viewport}")
        return viewport, VIEWPORTS[viewport]
    if isinstance(viewport, dict) and "width" in viewport and "height" in viewport:
        width = int(viewport["width"])
        height = int(viewport["height"])
        if width <= 640:
            label = "mobile"
        elif width <= 1100:
            label = "tablet"
        else:
            label = "desktop"
        return label, {"width": width, "height": height}
    raise ValueError("Viewport must be a preset string or an object with width/height.")


def resolve_url(base_url: str | None, raw_url: str) -> str:
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    if not base_url:
        raise ValueError("Relative target URL requires base_url in the manifest.")
    return urljoin(base_url.rstrip("/") + "/", raw_url.lstrip("/"))


def run_subprocess(args: list[str], *, text: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, capture_output=True, text=text)


def cmux_available() -> bool:
    try:
        run_subprocess(["cmux", "ping"])
        capabilities = run_subprocess(["cmux", "capabilities"]).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return '"browser.click"' in capabilities and '"browser.screenshot"' in capabilities


class CmuxCaptureSession:
    def __init__(self, cwd: Path, keep_workspace: bool = False) -> None:
        self.cwd = cwd
        self.keep_workspace = keep_workspace
        self.workspace_ref: str | None = None
        self.surface_ref: str | None = None

    def start(self, initial_url: str) -> None:
        workspace_name = f"FinalEdu Design Review {os.getpid()}"
        workspace_output = run_subprocess(
            ["cmux", "new-workspace", "--name", workspace_name, "--cwd", str(self.cwd)]
        ).stdout
        workspace_match = WORKSPACE_PATTERN.search(workspace_output)
        if not workspace_match:
            raise RuntimeError(f"Could not parse cmux workspace ref from: {workspace_output}")
        self.workspace_ref = workspace_match.group(1)

        pane_output = run_subprocess(
            [
                "cmux",
                "new-pane",
                "--type",
                "browser",
                "--workspace",
                self.workspace_ref,
                "--url",
                initial_url,
            ]
        ).stdout
        surface_match = SURFACE_PATTERN.search(pane_output)
        if not surface_match:
            raise RuntimeError(f"Could not parse cmux surface ref from: {pane_output}")
        self.surface_ref = surface_match.group(1)
        self.wait_for_load()

    def ensure_started(self, initial_url: str) -> None:
        if self.workspace_ref is None or self.surface_ref is None:
            self.start(initial_url)

    def close(self) -> None:
        if self.keep_workspace or self.workspace_ref is None:
            return
        try:
            run_subprocess(["cmux", "close-workspace", "--workspace", self.workspace_ref])
        except subprocess.CalledProcessError:
            pass

    def browser(self, *args: str) -> subprocess.CompletedProcess[str]:
        if self.surface_ref is None:
            raise RuntimeError("cmux browser surface is not initialized.")
        return run_subprocess(["cmux", "browser", *args, "--surface", self.surface_ref])

    def goto(self, url: str) -> None:
        self.browser("goto", url)
        self.wait_for_load()

    def wait_for_load(self) -> None:
        self.browser("wait", "--load-state", "complete")

    def run_action(self, base_url: str | None, action: dict) -> None:
        action_type = action.get("type")
        if action_type == "click":
            self.browser("click", action["selector"])
            return
        if action_type == "fill":
            self.browser("fill", action["selector"], action.get("value", ""))
            return
        if action_type == "press":
            self.browser("press", action["key"])
            return
        if action_type == "wait_for":
            self.browser("wait", "--selector", action["selector"])
            return
        if action_type == "wait_ms":
            wait_ms = int(action.get("ms", action.get("duration_ms", 250)))
            time.sleep(wait_ms / 1000)
            return
        if action_type == "scroll_to":
            x = int(action.get("x", 0))
            y = int(action.get("y", 0))
            self.browser("eval", f"window.scrollTo({x}, {y});")
            return
        if action_type == "scroll_selector":
            self.browser("scroll-into-view", action["selector"])
            return
        if action_type == "goto":
            self.goto(resolve_url(base_url, action["url"]))
            return
        raise ValueError(f"Unsupported action type for cmux backend: {action_type}")

    def capture(self, output_path: Path, snapshot_path: Path) -> None:
        if self.surface_ref is None:
            raise RuntimeError("cmux browser surface is not initialized.")
        run_subprocess(["cmux", "browser", "screenshot", "--surface", self.surface_ref, "--out", str(output_path)])
        snapshot = run_subprocess(
            ["cmux", "browser", "snapshot", "--surface", self.surface_ref, "--compact"]
        ).stdout
        snapshot_path.write_text(snapshot, encoding="utf-8")


def import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "playwright is required for this capture run. Run with "
            "`uv run --with playwright python ./.codex/skills/final-edu-design/scripts/capture_pages.py ...`"
        ) from exc
    return sync_playwright


def run_playwright_target(browser, target: dict, base_url: str | None, output_dir: Path) -> None:
    name = target["name"]
    url = resolve_url(base_url, target["url"])
    _, viewport = resolve_viewport(target)
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
        run_playwright_action(page, base_url, action)
    if delay_ms:
        page.wait_for_timeout(delay_ms)

    output_path = output_dir / f"{name}.png"
    page.screenshot(path=str(output_path), full_page=full_page)
    print(str(output_path))
    context.close()


def run_playwright_action(page, base_url: str | None, action: dict) -> None:  # noqa: ANN001
    action_type = action.get("type")
    if action_type == "click":
        page.locator(action["selector"]).click()
        return
    if action_type == "fill":
        page.locator(action["selector"]).fill(action.get("value", ""))
        return
    if action_type == "press":
        if "selector" in action:
            page.locator(action["selector"]).press(action["key"])
        else:
            page.keyboard.press(action["key"])
        return
    if action_type == "wait_for":
        page.locator(action["selector"]).wait_for()
        return
    if action_type == "wait_ms":
        page.wait_for_timeout(int(action.get("ms", action.get("duration_ms", 250))))
        return
    if action_type == "scroll_to":
        x = int(action.get("x", 0))
        y = int(action.get("y", 0))
        page.evaluate(
            "(coords) => window.scrollTo(coords.x, coords.y)",
            {"x": x, "y": y},
        )
        return
    if action_type == "scroll_selector":
        page.locator(action["selector"]).scroll_into_view_if_needed()
        return
    if action_type == "goto":
        page.goto(resolve_url(base_url, action["url"]), wait_until="networkidle")
        return
    raise ValueError(f"Unsupported action type: {action_type}")


def resolve_backend(requested_backend: str, cmux_is_ready: bool, viewport_label: str) -> str:
    if requested_backend == "playwright":
        return "playwright"
    if requested_backend == "cmux":
        if viewport_label == "mobile":
            raise ValueError("cmux backend does not support mobile viewport capture. Use --backend auto or playwright.")
        if not cmux_is_ready:
            raise RuntimeError("cmux backend requested but cmux is unavailable.")
        return "cmux"
    if cmux_is_ready and viewport_label != "mobile":
        return "cmux"
    return "playwright"


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

    cmux_is_ready = cmux_available()
    cmux_session: CmuxCaptureSession | None = None
    playwright_manager = None
    playwright_browser = None

    try:
        for target in targets:
            name = target["name"]
            url = resolve_url(base_url, target["url"])
            viewport_label, _ = resolve_viewport(target)
            backend = resolve_backend(args.backend, cmux_is_ready, viewport_label)
            wait_for = target.get("wait_for")
            delay_ms = int(target.get("delay_ms", 250))
            actions = target.get("actions", [])

            if backend == "cmux":
                if cmux_session is None:
                    cmux_session = CmuxCaptureSession(cwd=Path.cwd(), keep_workspace=args.keep_cmux_workspace)
                    cmux_session.ensure_started(url)
                else:
                    cmux_session.goto(url)

                if wait_for:
                    cmux_session.browser("wait", "--selector", wait_for)
                if delay_ms:
                    time.sleep(delay_ms / 1000)
                for action in actions:
                    cmux_session.run_action(base_url, action)
                if delay_ms:
                    time.sleep(delay_ms / 1000)

                output_path = output_dir / f"{name}.png"
                snapshot_path = output_dir / f"{name}.snapshot.txt"
                cmux_session.capture(output_path, snapshot_path)
                print(str(output_path))
                print(str(snapshot_path))
                continue

            if playwright_manager is None:
                sync_playwright = import_playwright()
                playwright_manager = sync_playwright().start()
                playwright_browser = playwright_manager.chromium.launch()
            run_playwright_target(playwright_browser, target, base_url, output_dir)

        return 0
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "Executable doesn't exist" in message or "browserType.launch" in message:
            print(
                "Chromium is not installed for Playwright. Run "
                "`uv run --with playwright python -m playwright install chromium` first.",
                file=sys.stderr,
            )
        raise
    finally:
        if playwright_browser is not None:
            playwright_browser.close()
        if playwright_manager is not None:
            playwright_manager.stop()
        if cmux_session is not None:
            cmux_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
