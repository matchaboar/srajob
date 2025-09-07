from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .html_fields import extract_forms
from .planner import plan_with_rules, plan_with_llm, BaseLLMClient
from .resume_loader import load_resume


def _download_html(url: str, timeout: int = 20) -> str:
    # Avoid external deps; use stdlib
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _load_html_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _save_text(path: str, content: str) -> None:
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Form Filler Bot CLI")
    gsrc = p.add_mutually_exclusive_group(required=True)
    gsrc.add_argument("--url", help="Page URL to analyze/fill")
    gsrc.add_argument("--html-file", help="Local HTML file to analyze")

    p.add_argument("--resume", required=True, help="Path to resume YAML")
    p.add_argument("--plan-only", action="store_true", help="Only create fill plan")
    p.add_argument("--execute", action="store_true", help="Execute plan with browser-use")
    p.add_argument("--headless", action="store_true", help="Run browser in headless mode if executing")
    p.add_argument("--hold-seconds", type=int, default=0, help="Hold browser open after actions")
    p.add_argument(
        "--action-delay-ms",
        type=int,
        default=0,
        help="Delay between actions in milliseconds for visibility",
    )
    p.add_argument("--post-goto-wait-ms", type=int, default=1500, help="Wait after navigation in ms")
    p.add_argument("--window-width", type=int, default=1200, help="Browser window width")
    p.add_argument("--window-height", type=int, default=800, help="Browser window height")
    p.add_argument("--save-html", action="store_true", help="If URL, save HTML snapshot")
    p.add_argument("--out-html", default="form_filler_bot/test_pages/snapshot.html")
    p.add_argument("--out-plan", default="form_filler_bot/test_pages/plan.json")
    p.add_argument("--use-llm", action="store_true", help="Use LLM to build plan")
    p.add_argument("--debug", action="store_true", help="Enable verbose LOG statements during execution")
    p.add_argument("--screenshots", action="store_true", default=True, help="Capture screenshots during execution (default: on)")
    p.add_argument("--screenshot-dir", default="form_filler_bot/test_pages/screenshots", help="Directory to save screenshots")
    p.add_argument("--screenshot-every", type=int, default=1, help="Capture a screenshot every N actions")

    args = p.parse_args(argv)

    resume = load_resume(args.resume)

    if args.url:
        html = _download_html(args.url)
        if args.save_html:
            _save_text(args.out_html, html)
    else:
        html = _load_html_file(args.html_file)

    forms = extract_forms(html)
    if not forms:
        print("No forms detected in the HTML.")
        return 2

    form = max(forms, key=lambda f: len(f.fields))  # pick the largest form heuristic

    if args.use_llm:
        class _DummyLLM(BaseLLMClient):
            def complete(self, prompt: str) -> str:
                raise RuntimeError(
                    "No LLM client wired yet. Provide an implementation of BaseLLMClient "
                    "or use --use-llm=false to fall back to rules."
                )

        actions = plan_with_llm(form, resume, _DummyLLM())
    else:
        actions = plan_with_rules(form, resume)

    # Save plan
    serial = [
        {
            "selector": a.selector,
            "op": a.op,
            "value": a.value,
            "field": {
                "tag": a.field.tag,
                "type": a.field.type,
                "name": a.field.name,
                "id": a.field.id,
                "label": a.field.label,
                "placeholder": a.field.placeholder,
                "required": a.field.required,
                "options": a.field.options,
            },
            "note": a.note,
        }
        for a in actions
    ]
    _save_text(args.out_plan, json.dumps(serial, ensure_ascii=False, indent=2))

    print(f"Planned {len(actions)} actions. Plan saved to {args.out_plan}")
    if args.debug:
        for i, a in enumerate(actions, start=1):
            try:
                print(
                    f"LOG: plan action {i}: op={a.op} selector={a.selector} tag={a.field.tag} type={a.field.type} label={a.field.label or ''} value={(a.value or '')[:40]}"
                )
            except Exception:
                pass

    if args.plan_only:
        return 0

    if args.execute:
        try:
            from .browser_adapters import BrowserUseAdapter
            import time

            adapter = BrowserUseAdapter(
                headless=bool(args.headless),
                window_size=(int(args.window_width), int(args.window_height)),
                debug=bool(args.debug),
                screenshots=bool(args.screenshots),
                screenshot_dir=args.screenshot_dir,
                screenshot_every=int(args.screenshot_every),
            )
            adapter.open()
            # Allow executing against a local HTML file if --url was not provided
            nav_target = args.url or args.html_file or ""
            adapter.goto(nav_target, wait_seconds=max(0.0, float(args.post_goto_wait_ms) / 1000.0))
            delay_sec = max(0.0, float(args.action_delay_ms) / 1000.0)
            adapter.apply_actions(actions, delay_seconds=delay_sec)
            if args.hold_seconds and args.hold_seconds > 0:
                time.sleep(int(args.hold_seconds))
            adapter.close()
            print("Execution complete.")
        except Exception as e:
            print(f"Execution failed: {e}")
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
