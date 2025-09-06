from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from .html_fields import Form, FormField


@dataclass
class FillAction:
    selector: str
    value: Optional[str]
    field: FormField
    op: str  # 'type', 'select', 'check', 'upload', 'click'
    note: Optional[str] = None


class BaseLLMClient:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _guess_key(field: FormField) -> Optional[str]:
    # Normalize candidates
    candidates = [
        _norm(field.label),
        _norm(field.placeholder),
        _norm(field.name),
        _norm(field.id),
    ]
    for c in candidates:
        if not c:
            continue
        if any(k in c for k in ["first name", "given name"]):
            return "first_name"
        if any(k in c for k in ["last name", "family name", "surname"]):
            return "last_name"
        if "full name" in c or c == "name":
            return "full_name"
        if "email" in c:
            return "email"
        if any(k in c for k in ["phone", "mobile", "cell"]):
            return "phone"
        if any(k in c for k in ["linkedin", "linked in"]):
            return "linkedin"
        if any(k in c for k in ["github", "git hub"]):
            return "github"
        if any(k in c for k in ["portfolio", "website", "site", "url"]):
            return "portfolio"
        if any(k in c for k in ["cover letter", "motivation"]):
            return "cover_letter"
        if any(k in c for k in ["resume", "cv"]):
            return "resume_file"
        if any(k in c for k in ["company", "current employer"]):
            return "current_company"
        if any(k in c for k in ["location", "city", "address"]):
            return "location"
        if any(k in c for k in ["experience", "years"]):
            return "years_experience"
        if any(k in c for k in ["salary", "compensation", "pay"]):
            return "salary_expectation"
        if "start date" in c:
            return "start_date"
        if any(k in c for k in ["visa", "sponsorship"]):
            return "work_authorization"
        if any(k in c for k in ["authorized", "legally"]):
            return "work_authorized"
        if any(k in c for k in ["relocate", "remote", "onsite"]):
            return "relocation"
        if any(k in c for k in ["pronoun"]):
            return "pronouns"
    return None


def plan_with_rules(form: Form, resume: Dict) -> List[FillAction]:
    actions: List[FillAction] = []
    # Flatten resume keys for convenience
    r = resume.copy()
    candidate = r.get("candidate", {}) if isinstance(r.get("candidate"), dict) else {}
    for k, v in candidate.items():
        r.setdefault(k, v)

    def rget(*keys: str, default: Optional[str] = None) -> Optional[str]:
        for k in keys:
            if k in r and isinstance(r[k], (str, int, float)):
                return str(r[k])
        return default

    for f in form.fields:
        sel = f.selector()
        op = "type"
        value: Optional[str] = None

        # Decide op based on field type
        if f.tag == "select":
            op = "select"
        elif f.type in ["checkbox", "radio"]:
            op = "check"
        elif f.type == "file":
            op = "upload"
        else:
            op = "type"

        key = _guess_key(f)
        if key == "full_name":
            value = rget("full_name") or " ".join(
                filter(None, [rget("first_name"), rget("last_name")])
            )
        elif key:
            value = rget(key)

        # Some convenience fallbacks
        if not value and f.type == "email":
            value = rget("email")
        if not value and f.type in ("tel", "phone"):
            value = rget("phone")

        actions.append(
            FillAction(selector=sel, value=value, field=f, op=op)
        )

    return actions


LLM_INSTRUCTIONS = (
    "You are an expert at filling job application forms."
    " Given the candidate profile and a list of form fields,"
    " produce a strict JSON object mapping each field selector to the value,"
    " and include an 'op' key with one of: type, select, check, upload."
)


def plan_with_llm(form: Form, resume: Dict, llm: BaseLLMClient) -> List[FillAction]:
    # Build prompt
    fields_summary = [
        {
            "selector": f.selector(),
            "type": f.type,
            "tag": f.tag,
            "label": f.label,
            "placeholder": f.placeholder,
            "required": f.required,
            "options": f.options,
        }
        for f in form.fields
    ]
    prompt = (
        f"{LLM_INSTRUCTIONS}\n\n"
        f"Candidate (YAML-like JSON):\n{json.dumps(resume, ensure_ascii=False, indent=2)}\n\n"
        f"Fields: {json.dumps(fields_summary, ensure_ascii=False)}\n\n"
        "Return JSON with keys: selector, value, op per field."
    )
    try:
        raw = llm.complete(prompt)
        data = json.loads(raw)
    except Exception:
        # If LLM fails, fall back to rule-based
        return plan_with_rules(form, resume)

    actions: List[FillAction] = []
    for f in form.fields:
        sel = f.selector()
        item = data.get(sel) if isinstance(data, dict) else None
        value = None
        op = "type"
        if isinstance(item, dict):
            value = item.get("value")
            op = item.get("op") or op
        elif isinstance(item, str):
            value = item

        actions.append(FillAction(selector=sel, value=value, field=f, op=op))

    return actions

