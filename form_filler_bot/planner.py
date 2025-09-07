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

    def _pick_select_value(f: FormField) -> Optional[str]:
        lab = _norm(f.label) + " " + _norm(f.name or "") + " " + _norm(f.id or "")
        # Generic boolean selects
        if "boolean_value" in lab or "i certify" in lab:
            return "Yes"
        if "privacy policy" in lab or "processed in accordance" in lab:
            return "Yes"
        # Work authorization (Greenhouse specific wording)
        if "legally authorised" in lab or "legally authorized" in lab:
            wa = _norm(rget("work_authorization") or rget("work_authorized") or "")
            if any(k in wa for k in ["citizen", "green card", "permanent", "yes", "authorized", "authorised", "no restriction"]):
                return "Yes, no restriction."
            if "future" in wa or "later" in wa:
                return "Yes, but I will need sponsorship in the future."
            if "sponsor" in wa or "need" in wa or wa == "no":
                return "No, I need sponsorship now."
            return "Yes, no restriction."
        # City availability multi-select
        if "what cities" in lab or "available to work" in lab or f.id == "question_5":
            return "Remote"
        # Source: how did you hear
        if "how did you hear" in lab:
            return "LinkedIn (Job Posting)" if rget("linkedin") else "Other"
        # EEOC convenience defaults
        if "gender" in lab:
            return "Decline To Self Identify"
        if "hispanic" in lab:
            return "Decline To Self Identify"
        if "race" in lab:
            return "Decline To Self Identify"
        # Unknown select
        return None

    for f in form.fields:
        # Skip hidden and Greenhouse internal wiring fields
        if f.type == "hidden":
            continue
        if (f.name and ("question_id" in f.name or "priority" in f.name)):
            continue
        if (f.id or "").lower() in {"security_code", "submit_app"}:
            continue

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

        if op != "select":
            key = _guess_key(f)
            if key == "full_name":
                value = rget("full_name") or " ".join(
                    filter(None, [rget("first_name"), rget("last_name")])
                )
            elif key:
                value = rget(key)

        # Some convenience fallbacks
        if not value and (f.type == "email" or _norm(f.label).find("email") != -1):
            value = rget("email")
        if not value and (f.type in ("tel", "phone") or _norm(f.label).find("phone") != -1):
            value = rget("phone")

        # Textareas specific mapping
        if not value and f.tag == "textarea":
            lab = _norm(f.label) + " " + _norm(f.id or "")
            if "resume" in lab or (f.id or "").lower() == "resume_text":
                value = r.get("answers", {}).get("cover_letter") or rget("cover_letter")
            if not value and "cover" in lab:
                value = r.get("answers", {}).get("cover_letter") or rget("cover_letter")

        # Selects: choose sensible defaults (ignore LLM/rule key guesses for selects)
        if op == "select":
            value = _pick_select_value(f) if not value else _pick_select_value(f) or value

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
