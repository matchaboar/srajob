from __future__ import annotations

import json
from pathlib import Path

import pytest

import os, sys
sys.path.insert(0, os.path.abspath('.'))
from form_filler_bot.html_fields import extract_forms
from form_filler_bot.planner import plan_with_rules
from form_filler_bot.resume_loader import load_resume


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_extract_and_plan_on_sample_html(tmp_path: Path):
    html_path = Path("form_filler_bot/test_pages/datadog_form_sample.html")
    resume_path = Path("form_filler_bot/samples/resume.sample.yaml")

    html = _read_text(html_path)
    forms = extract_forms(html)
    assert forms, "Expected at least one form in sample HTML"

    # Pick largest form (same heuristic used by CLI)
    form = max(forms, key=lambda f: len(f.fields))

    resume = load_resume(str(resume_path))
    actions = plan_with_rules(form, resume)

    # Sanity checks
    assert actions, "Expected non-empty plan for sample form"
    # Ensure selectors look like ids or name-based selectors or tags
    assert any(a.selector.startswith("#") for a in actions), "Expect some id-based selectors"

    # Write a plan file to temp just to validate serialization
    plan_file = tmp_path / "plan.json"
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
    plan_file.write_text(json.dumps(serial, ensure_ascii=False, indent=2), encoding="utf-8")
    assert plan_file.exists()
