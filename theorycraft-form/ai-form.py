#!/usr/bin/env python3
"""
AI-assisted form answering tool using OpenRouter.

Inputs:
- fields YAML produced by theorycraft-form/main.py (form-fields-<timestamp>.yaml)
- candidate resume YAML (see form_filler_2/prompt/example_resume)
- optional prior answers YAML to guide choices

Output:
- llm-answers-<timestamp>.yaml with a value or selection for every field
- logs/llm-chat-<timestamp>.yaml capturing the prompt and model response

This script does not submit any form; it only prepares answers.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from openai import OpenAI  # OpenAI client works with OpenRouter via base_url
except Exception as e:  # pragma: no cover
    print("The 'openai' package is required.", file=sys.stderr)
    raise


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def save_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


SYSTEM_INSTRUCTIONS = """
You are an assistant that fills job application form fields based on:
- a machine-readable schema of fields with roles and options (from accessibility tree)
- a candidate's resume YAML
- optional prior answers YAML

Return STRICT YAML only, no prose, with this shape:

fields:
  - name: <exact field label from schema>
    role: <same role from schema>
    # For text-like fields (textbox, textarea, searchbox, spinbutton)
    value: <single-line string>
  - name: <select-like field>
    role: <combobox|listbox|radiogroup|group>
    # For multi-select fields (e.g., listbox), return a YAML list of exact options.
    # Example: value: ["Seattle", "New York", "San Jose (Campbell)"]
    value: <exact option OR list of options>

Rules:
- Only use options that are EXACTLY present in the schema for option fields
- Keep values single-line (replace internal newlines with spaces)
- Do not include extra keys. Every item MUST have: name, role, value.
- If a field is not relevant, pick the safest allowed option (e.g., 'Decline To Self Identify', 'I do not want to answer', 'No').
- Never include instructions to submit the form. This is planning only.

Important:
- For questions about work authorization, visa, sponsorship, work permit, or eligibility, infer the correct answer from the resume and prior answers. Do not assume defaults; choose 'Yes'/'No' or the exact option that matches the candidate's situation.
""".strip()


def build_user_prompt(fields_doc: Dict[str, Any], resume_doc: Dict[str, Any], answers_doc: Optional[Dict[str, Any]]) -> str:
    fields_yaml = yaml.safe_dump(fields_doc, sort_keys=False, allow_unicode=True)
    resume_yaml = yaml.safe_dump(resume_doc, sort_keys=False, allow_unicode=True)
    answers_yaml = yaml.safe_dump(answers_doc, sort_keys=False, allow_unicode=True) if answers_doc else "{}\n"

    prompt = f"""
You will be given three YAML documents:

1) fields_schema:
{fields_yaml}

2) candidate_resume:
{resume_yaml}

3) prior_answers (optional):
{answers_yaml}

Using these, produce the STRICT YAML as specified. Ensure the 'name' exactly matches the schema.
For option fields, the 'value' must be one of the provided options, exactly. If a field clearly allows multiple selections (e.g., role is 'listbox', the field text indicates 'Select one or more', or the field object contains multi: true), return a YAML list of options instead of a single string.
"""
    return textwrap.dedent(prompt).strip()


def llm_complete(model: str, api_key: str, system_prompt: str, user_prompt: str, timeout: int = 90) -> str:
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=timeout)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=1000,
        top_p=1.0,
    )
    content = resp.choices[0].message.content or ""
    return content


def _best_option(token: str, options: List[str]) -> str:
    """Return the best-matching option for a token when the LLM did not choose
    an exact value. Uses simple synonyms and fuzzy canonical matching.

    This is intentionally lightweight and deterministic to keep tests reliable.
    """
    if not options:
        return token
    t = (token or "").strip()
    tl = t.lower()
    # Common synonyms for locations
    synonyms = {
        "new york city": "New York",
        "nyc": "New York",
        "sf": "San Francisco",
        "sfo": "San Francisco",
        "mountain view": "San Jose (Campbell)",
    }
    if tl in synonyms and synonyms[tl] in options:
        return synonyms[tl]

    import re

    def canon(s: str) -> str:
        s = (s or "").lower()
        s = re.sub(r"\(.*?\)", "", s)  # drop qualifiers in parens
        s = s.replace("city", "")
        s = re.sub(r"[^a-z0-9\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    tlc = canon(t)
    # Exact canonical match
    for o in options:
        if canon(o) == tlc:
            return o
    # Substring contains either way
    for o in options:
        oc = canon(o)
        if tlc in oc or oc in tlc:
            return o
    # Token overlap heuristic
    tset = set(tlc.split())
    best = (0, None)
    for o in options:
        oc = canon(o)
        oset = set(oc.split())
        score = len(tset & oset)
        if score > best[0]:
            best = (score, o)
    if best[1] is not None and best[0] > 0:
        return best[1]
    # Fall back to first option deterministically
    return options[0]


def validate_and_normalize(fields_schema: Dict[str, Any], llm_yaml: Dict[str, Any]) -> List[Dict[str, str]]:
    schema_fields = fields_schema.get("fields") or []
    by_name = {f.get("name"): f for f in schema_fields}
    out: List[Dict[str, str]] = []
    for item in llm_yaml.get("fields", []):
        name = (item or {}).get("name")
        role = (item or {}).get("role")
        value = (item or {}).get("value")
        if not name or name not in by_name:
            continue
        schema_item = by_name[name]
        schema_role = schema_item.get("role")
        # normalize role to schema role
        role = schema_role
        # enforce option validity if options provided
        options = schema_item.get("options") or []
        if options:
            # Must choose option(s) from provided list.
            lower_map = {str(o).lower(): o for o in options}
            if isinstance(value, list):
                vals: List[str] = []
                for v in value:
                    token = str(v)
                    chosen = lower_map.get(token.lower())
                    if chosen is None:
                        chosen = _best_option(token, [str(o) for o in options])
                    if chosen and chosen not in vals:
                        vals.append(chosen)
                value = vals
            else:
                token = str(value)
                chosen = lower_map.get(token.lower())
                if chosen is None:
                    chosen = _best_option(token, [str(o) for o in options])
                value = chosen
        else:
            # normalize to single line
            if isinstance(value, str):
                value = " ".join(value.split())
        out.append({"name": name, "role": role, "value": value})
    return out


def _latest_in_dir(dir_path: Path, pattern: str) -> Optional[Path]:
    files = sorted(dir_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Use OpenRouter to generate answers for a form")
    parser.add_argument("--fields-yaml", required=True, help="Path to fields YAML (from scanner)")
    parser.add_argument(
        "--resume-yaml",
        default=str(Path("theorycraft-form/example_resume/priya_desi.yml")),
        help="Path to resume YAML",
    )
    parser.add_argument("--answers-yaml", default=None, help="Path to prior answers YAML")
    parser.add_argument("--model", default=os.getenv("OPENROUTER_MODEL", "x-ai/grok-4"))
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to write outputs (default: theorycraft-form/form-data)",
    )
    args = parser.parse_args(argv)

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("Warning: OPENROUTER_API_KEY is not set in the environment.", file=sys.stderr)

    fields_path_input = Path(args.fields_yaml).expanduser()
    # Resolve latest fields YAML if a directory or 'latest' is provided
    if fields_path_input.is_dir():
        cand = _latest_in_dir(fields_path_input.resolve(), "form-fields-*.yaml")
        if not cand:
            print(f"No fields YAML found in {fields_path_input}", file=sys.stderr)
            return 4
        fields_path = cand
    elif str(fields_path_input).lower() == "latest":
        default_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else (Path(__file__).resolve().parent / "form-data")
        cand = _latest_in_dir(default_dir, "form-fields-*.yaml")
        if not cand:
            print(f"No fields YAML found in {default_dir}", file=sys.stderr)
            return 4
        fields_path = cand
    else:
        fields_path = fields_path_input.resolve()
    resume_path = Path(args.resume_yaml).expanduser().resolve()
    answers_path = Path(args.answers_yaml).expanduser().resolve() if args.answers_yaml else None

    fields_doc = load_yaml(fields_path)
    resume_doc = load_yaml(resume_path)
    answers_doc = load_yaml(answers_path) if answers_path and answers_path.exists() else None

    # Output paths
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    script_dir = Path(__file__).resolve().parent
    default_out_dir = (script_dir / "form-data").resolve()
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else default_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = (out_dir / "logs").resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Build prompts
    user_prompt = build_user_prompt(fields_doc, resume_doc, answers_doc)
    system_prompt = SYSTEM_INSTRUCTIONS

    # Call LLM with timeout cap
    try:
        completion = llm_complete(args.model, api_key, system_prompt, user_prompt, timeout=90)
    except Exception as e:
        print(f"LLM request failed: {e}", file=sys.stderr)
        return 2

    # Attempt to parse YAML
    try:
        llm_yaml = yaml.safe_load(completion) or {}
    except Exception:
        # Save raw output for debugging
        (logs_dir / f"llm-raw-{ts}.txt").write_text(completion or "", encoding="utf-8")
        print("Model did not return valid YAML. Raw output saved to logs.", file=sys.stderr)
        return 3

    normalized = validate_and_normalize(fields_doc, llm_yaml)

    answers_out = {
        "model": args.model,
        "source_fields": str(fields_path),
        "source_resume": str(resume_path),
        "source_answers": str(answers_path) if answers_path else None,
        "fields": normalized,
    }

    out_answers = out_dir / f"llm-answers-{ts}.yaml"
    save_yaml(out_answers, answers_out)

    # Save chat record
    chat_log = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": completion},
        ],
    }
    save_yaml(logs_dir / f"llm-chat-{ts}.yaml", chat_log)

    print(f"LLM answers written to {out_answers}")
    print(f"Chat log written to {logs_dir / f'llm-chat-{ts}.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
