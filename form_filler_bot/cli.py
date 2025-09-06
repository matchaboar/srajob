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
    p.add_argument("--save-html", action="store_true", help="If URL, save HTML snapshot")
    p.add_argument("--out-html", default="form_filler_bot/test_pages/snapshot.html")
    p.add_argument("--out-plan", default="form_filler_bot/test_pages/plan.json")
    p.add_argument("--use-llm", action="store_true", help="Use LLM to build plan")

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

    if args.plan_only:
        return 0

    if args.execute:
        try:
            from .browser_adapters import BrowserUseAdapter
            adapter = BrowserUseAdapter()
            adapter.open()
            adapter.goto(args.url or "")
            adapter.apply_actions(actions)
            adapter.close()
            print("Execution complete.")
        except Exception as e:
            print(f"Execution failed: {e}")
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

