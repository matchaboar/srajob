"""
The purpose of this python module is to test a form evaluation script.

How this works:
- Launch a local Chrome browser with playwright.
- Create a form-data-<timestamp>.txt file to store the form field labels.
- Issue the TAB command
- If you are within an editable form field, write that field's label to the file.
- Repeat the tab command until you have hit the end of the page.
- Print the file contents to the console.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path
from typing import Optional
from patchright.sync_api import sync_playwright as _sync_playwright  # type: ignore
import random
import yaml

_ENGINE = "patchright"


def _prune_old_logs(logs_dir: Path, keep: int = 5, patterns: list[str] | None = None) -> None:
    """Keep only the most recent `keep` files in `logs_dir` for each pattern.

    Intended for test artifact hygiene and only invoked when writing
    under the tests/test-artifacts tree.
    """
    try:
        pats = patterns or ["form-fill-*.yaml"]
        for pat in pats:
            files = [p for p in logs_dir.glob(pat) if p.is_file()]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for p in files[keep:]:
                try:
                    p.unlink()
                except Exception:
                    pass
    except Exception:
        # Never disrupt the main flow due to pruning issues
        pass


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://") or s.startswith("file://")


def _to_url(path_or_url: str) -> str:
    if _is_url(path_or_url):
        return path_or_url
    p = Path(path_or_url).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")
    return p.as_uri()


"""Label extraction uses the browser accessibility tree to avoid injecting page JS."""


def _is_editable_role(role: Optional[str], node: dict) -> bool:
    if not role:
        return False
    role = role.lower()
    interactive_roles = {
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "checkbox",
        "radio",
        "switch",
        "spinbutton",
        "slider",
        "menuitemcheckbox",
        "menuitemradio",
        "textarea",
        "select",
    }
    if role not in interactive_roles:
        return False
    if node.get("disabled"):
        return False
    if node.get("readonly"):
        return False
    return True


def _find_focused_node(ax_tree: Optional[dict], path: Optional[list[dict]] = None) -> tuple[Optional[dict], list[dict]]:
    if not ax_tree:
        return None, []
    if path is None:
        path = []
    new_path = path + [ax_tree]
    if ax_tree.get("focused"):
        return ax_tree, path
    for child in ax_tree.get("children", []) or []:
        found, anc = _find_focused_node(child, new_path)
        if found is not None:
            return found, anc
    return None, []


def _norm_text(s: str) -> str:
    # Collapse all whitespace (including newlines) to single spaces
    import re
    if s is None:
        return ""
    # Normalize non-breaking spaces to regular spaces
    s = s.replace("\u00A0", " ").replace("\u202F", " ").replace("\u2007", " ")
    return re.sub(r"\s+", " ", s).strip()


def _walk(node: Optional[dict]):
    if not node:
        return
    yield node
    for child in node.get("children", []) or []:
        yield from _walk(child)


def _nearest_container(node: Optional[dict], ancestors: list[dict]) -> tuple[Optional[dict], str]:
    container_roles = {"radiogroup", "group", "form", "listbox", "combobox"}
    role = (node or {}).get("role") if node else None
    if node and role in {"combobox", "listbox"}:
        return node, _norm_text(node.get("name") or "")
    for anc in reversed(ancestors):
        if anc.get("role") in container_roles:
            return anc, _norm_text(anc.get("name") or "")
    if node:
        return node, _norm_text(node.get("name") or "")
    return None, ""


def _collect_options_for_container(container: dict) -> tuple[list[str], Optional[str]]:
    if not container:
        return [], None
    role = container.get("role")
    if role in {"combobox", "listbox"}:
        target_roles = {"option"}
    elif role in {"radiogroup", "group"}:
        target_roles = {"radio", "checkbox"}
    else:
        return [], None
    options: list[str] = []
    for n in _walk(container):
        if n.get("role") in target_roles:
            name = _norm_text(n.get("name") or "")
            if name:
                options.append(name)
    # dedupe preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for o in options:
        if o not in seen:
            seen.add(o)
            deduped.append(o)
    return deduped, role


def _find_nodes_by_role(ax_tree: Optional[dict], role: str) -> list[dict]:
    out: list[dict] = []
    if not ax_tree:
        return out
    def walk(n: Optional[dict]):
        if not n:
            return
        if n.get("role") == role:
            out.append(n)
        for c in n.get("children", []) or []:
            walk(c)
    walk(ax_tree)
    return out


def _stable_label(label: str, node: Optional[dict]) -> str:
    """Return a stable label by removing any trailing injected value text."""
    import re
    lbl = _norm_text(label or "")
    if not node:
        return lbl
    val = _norm_text((node or {}).get("value") or "")
    if not val:
        return lbl
    # Trim common separators before value at end
    pattern = r"[\s:\-–—]*" + re.escape(val) + r"\s*$"
    return re.sub(pattern, "", lbl)


TEXT_INPUT_ROLES = {"textbox", "searchbox", "textarea", "spinbutton"}


def _choose_option(options: list[str], *preferred: str) -> Optional[str]:
    if not options:
        return None
    norm = [o.strip() for o in options]
    # Try preferred in order (case-insensitive contains match)
    for p in preferred:
        pl = p.lower()
        for o in norm:
            if o.lower() == pl:
                return o
    # Skip placeholders
    placeholders = {"please select", "--", "select", "select one", "choose"}
    for o in norm:
        if o and o.lower() not in placeholders:
            return o
    return norm[0]


def _guess_example(name: str, role: Optional[str], options: list[str]) -> str:
    import re
    n = (name or "").lower().strip()
    # Text-like heuristics
    if role in TEXT_INPUT_ROLES or (role is None and not options):
        # Specific fields first
        if "first name" in n:
            return "Jane"
        if "last name" in n:
            return "Doe"
        if n == "name" or "full name" in n:
            return "Jane Doe"
        if "city" in n or "cities" in n or "location" in n:
            return "San Francisco"
        if "linkedin" in n:
            return "https://www.linkedin.com/in/jane-doe"
        if "github" in n:
            return "https://github.com/janedoe"
        if "website" in n or "portfolio" in n:
            return "https://janedoe.dev"
        # More general patterns next
        if re.search(r"\b(phone|mobile|cell)\b", n):
            return "555-555-1234"
        if re.search(r"^(work )?email( address)?\b", n) or n in {"email", "email *", "email address"}:
            return "jane.doe@example.com"
        return "Example text"
    # Options-based heuristics
    if options:
        if "how did you hear" in n:
            v = _choose_option(options, "Hacker News", "LinkedIn (Job Posting)")
            return v or options[0]
        if "gender" in n:
            v = _choose_option(options, "Decline To Self Identify")
            return v or options[0]
        if "disability" in n:
            v = _choose_option(options, "I do not want to answer")
            return v or options[0]
        if "veteran" in n:
            v = _choose_option(
                options,
                "I am not a protected veteran",
                "I don't wish to answer",
            )
            return v or options[0]
        if "hispanic" in n:
            v = _choose_option(options, "No")
            return v or options[0]
        if "race" in n:
            v = _choose_option(options, "Asian", "Two or More Races", "White")
            return v or options[0]
        # Work authorization / visa / sponsorship/permit questions: let LLM decide; don't default here
        if any(token in n for token in [
            "authoris", "authoriz", "work authorization", "work authorisation",
            "visa", "sponsor", "sponsorship", "work permit", "eligib"
        ]):
            return ""
        if "certify" in n or "privacy" in n or "policy" in n:
            v = _choose_option(options, "Yes")
            return v or options[0]
        # Default non-placeholder
        v = _choose_option(options)
        return v or options[0]
    # No options available (e.g., closed combobox); use label hints
    if role == "combobox" and ("city" in n or "location" in n):
        return "San Francisco"
    return ""


def _scan_all_fields(ax_tree: Optional[dict]) -> list[dict]:
    fields: list[dict] = []
    if not ax_tree:
        return fields

    # Track which group labels have been recorded to avoid duplicates
    recorded_group_labels: set[str] = set()
    # Accumulate grouped options for radios/checkboxes and combobox/listbox
    grouped: dict[str, dict] = {}
    # grouped[label] = { 'role': 'radiogroup'|'group'|'combobox'|'listbox', 'options': set([...]) }

    def add_grouped(label: str, role: str, options: list[str]):
        g = grouped.setdefault(label, {"role": role, "options": set()})
        if role and g.get("role") != role:
            g["role"] = role
        for o in options:
            g["options"].add(o)

    def visit(node: Optional[dict], ancestors: list[dict]):
        if not node:
            return
        role = node.get("role")
        name = _norm_text(node.get("name") or "")
        # Grouped options (radio/checkbox within labeled container) and ARIA combobox/listbox
        if role in {"radio", "checkbox", "combobox", "listbox", "radiogroup", "group"}:
            container, container_label = _nearest_container(node, ancestors)
            label = container_label or name
            if container and label:
                opts, detected_role = _collect_options_for_container(container)
                field_role = detected_role or role
                # If combobox has separate listbox elsewhere, scan whole tree for matching listbox by name
                if (field_role == "combobox" or role == "combobox") and (not opts):
                    for lb in _find_nodes_by_role(ax_tree, "listbox"):
                        if _norm_text(lb.get("name") or "") == label:
                            lb_opts, _ = _collect_options_for_container(lb)
                            opts.extend(lb_opts)
                add_grouped(label, field_role, opts)
                # Do not emit field immediately; will flush after traversal
        # Text-like inputs
        elif role in TEXT_INPUT_ROLES and name:
            fields.append(
                {
                    "name": name,
                    "role": role,
                    "options": [],
                    "example": _guess_example(name, role, []),
                }
            )
        # Recurse
        for child in node.get("children", []) or []:
            visit(child, ancestors + [node])

    visit(ax_tree, [])

    # Flush grouped fields first
    for label, meta in grouped.items():
        role = meta.get("role") or ""
        options = sorted(list(meta.get("options") or []))
        fields.append(
            {
                "name": label,
                "role": role,
                "options": options,
                "example": _guess_example(label, role, options),
                "multi": True if role == "listbox" else False,
            }
        )

    # Deduplicate by (role, name) preserving first occurrence
    seen: set[tuple[str, str]] = set()
    uniq: list[dict] = []
    for f in fields:
        k = (f.get("role") or "", f.get("name") or "")
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def collect_form_labels(
    url: str,
    *,
    max_tabs: int = 300,
    headless: bool = False,
    fields_yaml: Optional[Path] = None,
    resume_yaml: Optional[Path] = None,
    answers_yaml: Optional[Path] = None,
    scan_only: bool = False,
    screenshot_name: Optional[str] = None,
    out_dir: Optional[Path] = None,
    loop_detect_threshold: int = 3,
) -> tuple[
    list[str],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, str],
    Path,
    Path,
    Optional[Path],
]:
    labels: list[str] = []
    seen_keys: set[str] = set()
    field_options: dict[str, set[str]] = {}
    field_roles: dict[str, str] = {}
    field_buttons: dict[str, set[str]] = {}
    last_container_label: Optional[str] = None
    fields_for_fill: dict[str, dict] = {}

    with _sync_playwright() as pw:
        # Prefer system Chrome; fall back to bundled Chromium if Chrome unavailable
        try:
            browser = pw.chromium.launch(channel="chrome", headless=headless)
            channel_used = "chrome"
        except Exception:
            browser = pw.chromium.launch(headless=headless)
            channel_used = "chromium"

        context = browser.new_context()
        page = context.new_page()

        # Navigate and prepare focus
        page.goto(url, wait_until="load", timeout=60_000)
        try:
            page.evaluate("document.body && document.body.focus && document.body.focus()")
        except Exception:
            pass

        # Allow dynamic widgets to render
        try:
            page.wait_for_timeout(1200)
        except Exception:
            pass
        # Scan all fields without tabbing and write YAML
        ax_full = page.accessibility.snapshot()
        all_fields = _scan_all_fields(ax_full)
        # Persist fields YAML
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        script_dir = Path(__file__).resolve().parent
        default_out_dir = (script_dir / "form-data").resolve()
        target_out_dir = out_dir or default_out_dir
        target_out_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = target_out_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        # Augment with DOM multi-select <select multiple> detection and mark multi=True
        try:
            dom_multi = page.evaluate(
                "Array.from(document.querySelectorAll('select[multiple]')).map(sel => {\n"
                "  const lab = sel.closest('label') || (sel.labels && sel.labels[0]) || null;\n"
                "  const labelText = (lab ? (lab.innerText || lab.textContent) : sel.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim();\n"
                "  const opts = Array.from(sel.querySelectorAll('option')).map(o => (o.textContent||'').trim()).filter(Boolean);\n"
                "  return { label: labelText, options: opts };\n"
                "})"
            ) or []
        except Exception:
            dom_multi = []

        # Merge DOM multi-select info into AX-derived fields
        by_name = {f.get("name"): f for f in all_fields}
        for item in dom_multi:
            try:
                dn = _norm_text((item or {}).get("label") or "")
                opts = list((item or {}).get("options") or [])
            except Exception:
                dn = ""
                opts = []
            if not dn:
                continue
            # Find exact match; else try startswith/substring match
            target = by_name.get(dn)
            if not target:
                for k, v in list(by_name.items()):
                    if _norm_text(k) == dn or dn.startswith(_norm_text(k)) or _norm_text(k).startswith(dn):
                        target = v
                        break
            entry = {
                "name": dn,
                "role": "listbox",
                "options": opts,
                "example": _guess_example(dn, "listbox", opts),
                "multi": True,
            }
            if target:
                target.update(entry)
            else:
                all_fields.append(entry)
                by_name[dn] = entry

        # Ensure multi flag is present for listbox entries
        for f in all_fields:
            if f.get("role") == "listbox" and "multi" not in f:
                f["multi"] = True

        # Write fields YAML into logs directory
        fields_path = logs_dir / f"form-fields-{ts}.yaml"
        fields_doc = {"fields": all_fields}
        fields_path.write_text(
            yaml.safe_dump(fields_doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        # If writing into tests' artifacts, prune old field logs to the latest 5
        try:
            from srajob.constants import TEST_ARTIFACTS_DIR

            if str((target_out_dir or Path(".")).resolve()).startswith(str(TEST_ARTIFACTS_DIR.resolve())):
                _prune_old_logs(logs_dir, keep=5, patterns=["form-fields-*.yaml"])
        except Exception:
            pass

        # If a fields YAML is supplied, load it and use for filling; otherwise, use freshly scanned doc
        use_fields_doc = None
        if fields_yaml and fields_yaml.exists():
            try:
                use_fields_doc = yaml.safe_load(fields_yaml.read_text(encoding="utf-8"))
            except Exception:
                use_fields_doc = fields_doc
        else:
            use_fields_doc = fields_doc

        # Optional: load answers YAML (with fields: [ { name, role, value } ])
        from typing import Any as _Any
        answers_map: dict[str, _Any] = {}
        if answers_yaml and answers_yaml.exists():
            try:
                ans_doc = yaml.safe_load(answers_yaml.read_text(encoding="utf-8")) or {}
                for f in ans_doc.get("fields", []) or []:
                    r = (f or {}).get("role") or ""
                    n = (f or {}).get("name") or ""
                    v = (f or {}).get("value")
                    if r and n and v is not None:
                        if isinstance(v, list):
                            answers_map[f"{r}|{n}"] = [str(x) for x in v]
                        else:
                            answers_map[f"{r}|{n}"] = str(v)
            except Exception:
                answers_map = {}

        # Optional: map resume YAML answers into field values
        resume_answers: dict[str, str] = {}
        resume_data = None
        if resume_yaml and resume_yaml.exists():
            try:
                resume_data = yaml.safe_load(resume_yaml.read_text(encoding="utf-8")) or {}
            except Exception:
                resume_data = None

        def _resume_answers_dict(data: Optional[dict]) -> dict:
            out: dict[str, str] = {}
            if not isinstance(data, dict):
                return out
            for item in data.get("answers", []) or []:
                if isinstance(item, dict):
                    for k, v in item.items():
                        out[str(k)] = v
            return out

        def _map_resume_value(field_name: str, role: str, options: list[str], rdict: dict) -> str:
            n = field_name.lower()
            # Work authorization / visa mapping
            if "authoris" in n or "authoriz" in n or "visa" in n or "sponsor" in n or "work permit" in n or "eligib" in n:
                status = str(rdict.get("work_visa_status", "")).lower()
                if options:
                    # Try to find best option based on status
                    if any(k in status for k in ["citizen", "permanent", "no sponsorship", "authorized"]):
                        # Prefer unrestricted
                        for cand in ["Yes, no restriction.", "Yes, no restriction", "Yes"]:
                            if cand in options:
                                return cand
                    # If needs sponsorship soon
                    if any(k in status for k in ["future", "will need", "student", "opt", "stem"]):
                        for cand in ["Yes, but I will need sponsorship in the future.", "Yes, but I will need sponsorship in the future"]:
                            if cand in options:
                                return cand
                    # Otherwise assume needs now
                    for cand in ["No, I need sponsorship now.", "No"]:
                        if cand in options:
                            return cand
                else:
                    # No options provided; best-effort default based on role
                    if role in {"combobox", "listbox"}:
                        return "Yes, no restriction."
                    if role in {"radiogroup", "group"}:
                        return "Yes"
                return ""
            # City availability
            if "what cities" in n or "available to work" in n or (role in TEXT_INPUT_ROLES and ("city" in n or "cities" in n)):
                cities = rdict.get("location_preference_city_ordered") or []
                try:
                    topn = int(rdict.get("location_preference_top_selections") or 3)
                except Exception:
                    topn = 3
                if isinstance(cities, list) and cities:
                    return ", ".join(map(str, cities[:topn]))
                return ""
            # How did you hear
            if "how did you hear" in n:
                heard = str(rdict.get("heard_about_us", "")).lower()
                mapping = {
                    "company_website": "Datadog's Careers Page",
                    "github": "Github",
                    "hacker_news": "Hacker News",
                    "linkedin": "LinkedIn (Job Posting)",
                }
                desired = mapping.get(heard)
                if desired and desired in options:
                    return desired
                # Fallback to a safe choice present in options
                for cand in ["Datadog's Careers Page", "Github", "Hacker News", "LinkedIn (Job Posting)"]:
                    if cand in options:
                        return cand
                return options[0] if options else ""
            return ""

        if resume_data:
            resume_answers = _resume_answers_dict(resume_data)

        # Build lookup for filling by role|name
        for f in (use_fields_doc.get("fields") or []):
            r = f.get("role") or ""
            n = f.get("name") or ""
            key = f"{r}|{n}"
            # Prefer answers value; else use example from schema
            if key in answers_map:
                fields_for_fill[key] = {"value": answers_map[key]}
            else:
                # derive from resume if provided
                value = ""
                if resume_data is not None:
                    value = _map_resume_value(n, r, f.get("options") or [], resume_answers)
                if not value:
                    value = f.get("example")
                fields_for_fill[key] = {"value": value}

        if scan_only:
            # Close and return with paths for fields and out_dir
            context.close()
            browser.close()
            # Return empty labels; produce empty maps too
            empty: dict[str, list[str]] = {}
            return [], empty, empty, {}, fields_path, target_out_dir, None

        # Nudge focus into the document for tabbing
        try:
            page.keyboard.press("Tab")
        except Exception:
            pass
        page.wait_for_timeout(50)

        last_key: Optional[str] = None
        seen_labels: set[str] = set()
        fill_events: list[dict] = []
        first_stable_label: Optional[str] = None
        unique_stable_labels: set[str] = set()
        tabs_sent = 0
        ended_reason: Optional[str] = None
        backtracked = False
        stuck_count = 0

        for _ in range(max_tabs):
            # Use accessibility tree to avoid injecting JS
            ax = page.accessibility.snapshot()
            node, ancestors = _find_focused_node(ax)
            key = None
            if node:
                role = node.get("role")
                name = _norm_text(node.get("name") or "")
                key = f"{role}|{name}"
                if _is_editable_role(role, node):
                    # Compute stable container label every time for loop detection
                    container, container_label = _nearest_container(node, ancestors)
                    raw_label = container_label or (name if name else "<unlabeled-field>")
                    stable_label = _stable_label(raw_label, node)
                    if first_stable_label is None:
                        first_stable_label = stable_label
                    unique_stable_labels.add(stable_label)
                    # If we returned to the first label after encountering multiple unique labels, go back one and stop
                    if stable_label == first_stable_label and len(unique_stable_labels) >= loop_detect_threshold and len(seen_labels) >= 1:
                        try:
                            page.keyboard.press("Shift+Tab")
                            page.wait_for_timeout(60)
                        except Exception:
                            pass
                        ended_reason = "loop_detected"
                        backtracked = True
                        break
                    if key not in seen_keys:
                        seen_keys.add(key)
                        # Prefer stable container label for text fields to avoid duplication
                        label_text = stable_label
                        if label_text not in seen_labels:
                            seen_labels.add(label_text)
                            labels.append(label_text)
                        last_container_label = container_label or label_text
                        if container:
                            options, detected_role = _collect_options_for_container(container)
                            if options:
                                lbl = container_label or label_text
                                optset = field_options.setdefault(lbl, set())
                                for o in options:
                                    optset.add(o)
                                if detected_role:
                                    field_roles[lbl] = detected_role
                        # Attempt to fill from mapped value
                        entry = fields_for_fill.get(key)
                        if (not entry) and last_container_label:
                            # Try container-based role keys (e.g., listbox/combobox)
                            for alt_role in ("listbox", "combobox", "radiogroup", "group"):
                                entry = fields_for_fill.get(f"{alt_role}|{last_container_label}")
                                if entry:
                                    break
                        ex = (entry.get("value") if entry else "") or ""
                        # Fill strategy by role
                        if role in TEXT_INPUT_ROLES:
                            try:
                                page.keyboard.press("Control+A")
                                page.keyboard.press("Delete")
                            except Exception:
                                pass
                            confirmed = None
                            # Heuristic: if this appears to be a multi-value chip input (e.g. cities),
                            # type each token and commit with Enter/Tab so it is visible in screenshots.
                            is_multi_value = False
                            tokens_committed: list[str] = []
                            if ex:
                                try:
                                    import re
                                    label_lc = (label_text or "").lower()
                                    looks_multi_label = any(k in label_lc for k in [
                                        "cities", "skills", "technolog", "languages", "keywords", "locations",
                                        "select one or more",
                                    ])
                                    has_multi_delims = bool(re.search(r",|;|\band\b", str(ex), flags=re.IGNORECASE)) if not isinstance(ex, list) else True
                                    is_multi_value = looks_multi_label and (has_multi_delims or isinstance(ex, list))
                                except Exception:
                                    is_multi_value = False

                            if ex and is_multi_value:
                                import re
                                if isinstance(ex, list):
                                    pieces = [str(p).strip() for p in ex if str(p).strip()]
                                else:
                                    pieces = [p.strip() for p in re.split(r",|;|\band\b", str(ex)) if p and p.strip()]
                                # Gather available options from multi-selects on page to improve matching
                                available_options: list[str] = []
                                try:
                                    available_options = page.evaluate(
                                        "Array.from(document.querySelectorAll('select[multiple] option')).map(o => (o.textContent || '').trim()).filter(Boolean)"
                                    ) or []
                                except Exception:
                                    available_options = []

                                def _best_option(token: str, opts: list[str]) -> str:
                                    t = token.strip()
                                    if not opts:
                                        return t
                                    tl = t.lower()
                                    # Simple synonyms for common cases
                                    synonyms = {
                                        "new york city": "New York",
                                        "nyc": "New York",
                                        "sf": "San Francisco",
                                        "sfo": "San Francisco",
                                        "mountain view": "San Jose (Campbell)",
                                    }
                                    if tl in synonyms and synonyms[tl] in opts:
                                        return synonyms[tl]
                                    import re as _re
                                    def canon(s: str) -> str:
                                        s = s.lower()
                                        s = _re.sub(r"\(.*?\)", "", s)
                                        s = s.replace("city", "")
                                        s = _re.sub(r"[^a-z0-9\s]", " ", s)
                                        s = _re.sub(r"\s+", " ", s).strip()
                                        return s
                                    tlc = canon(t)
                                    # Exact canonical match
                                    for o in opts:
                                        if canon(o) == tlc:
                                            return o
                                    # Substring contains either way
                                    for o in opts:
                                        oc = canon(o)
                                        if tlc in oc or oc in tlc:
                                            return o
                                    # Token overlap heuristic
                                    tset = set(tlc.split())
                                    best = (0, None)
                                    for o in opts:
                                        oc = canon(o)
                                        oset = set(oc.split())
                                        score = len(tset & oset)
                                        if score > best[0]:
                                            best = (score, o)
                                    if best[1] is not None and best[0] > 0:
                                        return best[1]
                                    return t

                                for idx, piece in enumerate(pieces):
                                    try:
                                        piece_to_type = _best_option(piece, available_options)
                                        page.keyboard.type(piece_to_type, delay=random.randint(15, 40))
                                        page.wait_for_timeout(random.randint(120, 260))
                                        # Try to click the matching suggestion by role/name
                                        clicked = False
                                        try:
                                            opt = page.get_by_role("option", name=piece_to_type)
                                            opt.click(timeout=1000)
                                            clicked = True
                                        except Exception:
                                            clicked = False
                                        if not clicked:
                                            # Fallback: navigate suggestions then Enter
                                            try:
                                                page.keyboard.press("ArrowDown")
                                                page.wait_for_timeout(80)
                                            except Exception:
                                                pass
                                            try:
                                                page.keyboard.press("Enter")
                                            except Exception:
                                                pass
                                        page.wait_for_timeout(random.randint(90, 160))
                                        tokens_committed.append(piece_to_type)
                                    except Exception:
                                        pass
                                # Confirmation via page text presence
                                try:
                                    page_text_probe = _norm_text(page.inner_text("body"))
                                    confirmed = all(t in page_text_probe for t in tokens_committed) if tokens_committed else None
                                except Exception:
                                    confirmed = None
                            else:
                                if ex:
                                    page.keyboard.type(str(ex), delay=random.randint(15, 40))
                                # Confirm via AX value if possible
                                try:
                                    curr, _ = _find_focused_node(page.accessibility.snapshot())
                                    curr_val = _norm_text((curr or {}).get("value") or "")
                                    confirmed = bool(ex) and (str(ex).strip() == curr_val)
                                except Exception:
                                    confirmed = None
                            fill_events.append({
                                "field": label_text,
                                "typed": str(ex) if ex else "",
                                **({"tokens": tokens_committed} if is_multi_value else {}),
                                "confirmed": confirmed,
                            })
                        elif role in {"combobox", "listbox"} and ex:
                            # Prefer role-based click on the target option to handle custom widgets
                            values = [str(v) for v in (ex if isinstance(ex, list) else [ex])]
                            selected_items: list[str] = []
                            for desired in values:
                                confirmed = None
                                try:
                                    if role == "combobox":
                                        # Open combobox then click matching option
                                        page.keyboard.press("Enter")
                                        page.wait_for_timeout(120)
                                    # Try clicking by role/name
                                    opt = page.get_by_role("option", name=desired)
                                    opt.click(timeout=1000)
                                    page.wait_for_timeout(80)
                                    confirmed = True
                                except Exception:
                                    # Fallback to type + enter sequence
                                    try:
                                        if role == "combobox":
                                            page.keyboard.press("Enter")
                                            page.wait_for_timeout(80)
                                        page.keyboard.type(desired, delay=10)
                                        page.wait_for_timeout(80)
                                        page.keyboard.press("Enter")
                                        confirmed = True
                                    except Exception:
                                        confirmed = None
                                selected_items.append(desired)
                                fill_events.append({
                                    "field": label_text,
                                    "selected": desired,
                                    "confirmed": confirmed,
                                })
                        elif role == "radio":
                            # Try to navigate radios to match example
                            # For radios, prefer container-level planned value if available
                            target = str(ex)
                            if not target:
                                # Fall back to container-level plan (radiogroup/group)
                                cnode, clabel = _nearest_container(node, ancestors)
                                if clabel:
                                    centry = fields_for_fill.get(f"radiogroup|{clabel}") or fields_for_fill.get(f"group|{clabel}")
                                    if centry and centry.get("value"):
                                        target = str(centry.get("value"))
                            # Still no target? Try deriving from resume answers directly
                                if (not target) and resume_data is not None:
                                    cnode, clabel = _nearest_container(node, ancestors)
                                    # Try a generic radiogroup mapping from resume using detected options
                                    opts, _r = _collect_options_for_container(cnode or {}) if cnode else ([], None)
                                    # First attempt label-aware mapping
                                    derived = _map_resume_value(clabel or name, "radiogroup", opts or ["Yes", "No"], resume_answers)
                                    if not derived and opts and set(["Yes", "No"]).issubset(set(opts)):
                                        # Fallback: assume authorization-style yes/no
                                        status = str(resume_answers.get("work_visa_status", "")).lower()
                                        if any(k in status for k in ["citizen", "permanent", "authorized"]):
                                            derived = "Yes" if "Yes" in opts else ""
                                        elif any(k in status for k in ["future", "will need", "student", "opt", "stem"]):
                                            derived = "No" if "No" in opts else ""
                                    if derived:
                                        target = derived
                                    else:
                                        # As a last resort, if resume indicates citizen and current radio is 'Yes', toggle it
                                        try:
                                            status = str(resume_answers.get("work_visa_status", "")).lower()
                                        except Exception:
                                            status = ""
                                        desired = "Yes" if any(k in status for k in ["citizen", "permanent", "authorized"]) else ""
                                        if desired and name == desired:
                                            try:
                                                page.keyboard.press("Space")
                                            except Exception:
                                                pass
                                            fill_events.append({
                                                "field": label_text,
                                                "selected": desired,
                                                "confirmed": True,
                                            })
                                            # Consider this radio handled
                                            target = ""
                            tries = 0
                            curr_name = ""
                            while target and tries < 6:
                                # Re-snapshot focused node
                                curr, _anc = _find_focused_node(page.accessibility.snapshot())
                                curr_name = _norm_text((curr or {}).get("name") or "")
                                if curr_name == target:
                                    break
                                try:
                                    page.keyboard.press("ArrowDown")
                                except Exception:
                                    break
                                page.wait_for_timeout(60)
                                tries += 1
                            if target:
                                fill_events.append({
                                    "field": label_text,
                                    "selected": target,
                                    "confirmed": (curr_name == target),
                                })
                            elif role == "checkbox":
                                # Toggle to checked if example implies yes/true
                                if str(ex).lower() in {"yes", "true", "checked"}:
                                    try:
                                        page.keyboard.press("Space")
                                    except Exception:
                                        pass
                                fill_events.append({
                                    "field": label_text,
                                    "toggled_to": str(ex).lower() in {"yes", "true", "checked"},
                                    "confirmed": None,
                                })
                elif role == "button":
                    _, btn_container_label = _nearest_container(node, ancestors)
                    if btn_container_label and last_container_label and btn_container_label == last_container_label and name:
                        bset = field_buttons.setdefault(btn_container_label, set())
                        bset.add(name)

            # Prepare next focus advance with randomized human-like delay
            try:
                page.keyboard.press("Tab")
                tabs_sent += 1
            except Exception:
                ended_reason = "tab_press_failed"
                break
            page.wait_for_timeout(random.randint(30, 120))

            # Stop conditions: focus not changing repeatedly (allow a few retries)
            if key and last_key == key:
                stuck_count += 1
                if stuck_count >= 3:
                    ended_reason = "focus_stuck"
                    break
            else:
                stuck_count = 0
            last_key = key

        # Write fill log YAML if we attempted any fills
        fill_log_path: Optional[Path] = None
        if fill_events or ended_reason is not None:
            fill_log_path = logs_dir / f"form-fill-{ts}.yaml"
            fill_doc = {
                "channel": channel_used,
                "ended_reason": ended_reason,
                "loop_detected": True if ended_reason == "loop_detected" else False,
                "backtracked": backtracked,
                "tabs_sent": tabs_sent,
                "unique_fields": sorted(list(seen_labels)),
                "events": fill_events,
            }
            # Attach page text dump to help validate visibility in screenshots
            try:
                fill_doc["page_text"] = page.inner_text("body")
            except Exception:
                pass
            fill_log_path.write_text(
                yaml.safe_dump(fill_doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            # If writing into tests' artifacts, prune old logs to the latest 5
            try:
                from srajob.constants import TEST_ARTIFACTS_DIR

                if str((target_out_dir or Path(".")).resolve()).startswith(str(TEST_ARTIFACTS_DIR.resolve())):
                    _prune_old_logs(logs_dir, keep=5, patterns=["form-fill-*.yaml"])
            except Exception:
                pass

        # Full-page screenshot after filling (not during scan-only)
        screenshot_path: Optional[Path] = None
        if not scan_only:
            try:
                # Prefer centralized test-artifacts screenshots directory when available
                screenshots_dir = None
                try:
                    from srajob.constants import TEST_ARTIFACTS_DIR, TEST_ARTIFACTS_SCREENSHOTS_DIR

                    # If our target output is inside the test artifacts tree, write screenshots there
                    if str((target_out_dir or Path(".")).resolve()).startswith(str(TEST_ARTIFACTS_DIR.resolve())):
                        screenshots_dir = TEST_ARTIFACTS_SCREENSHOTS_DIR
                except Exception:
                    screenshots_dir = None

                if screenshots_dir is None:
                    screenshots_dir = logs_dir / "screenshots"
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                # Use provided name if given; otherwise fall back to timestamped file
                shot_name = screenshot_name if screenshot_name else f"screenshot-{ts}.png"
                screenshot_path = screenshots_dir / shot_name
                page.wait_for_timeout(200)
                try:
                    page.set_viewport_size({"width": 1280, "height": 2000})
                except Exception:
                    pass
                data = None
                try:
                    data = page.screenshot(full_page=True)
                except Exception:
                    try:
                        data = page.screenshot(full_page=False)
                    except Exception:
                        try:
                            data = page.locator("html").screenshot()
                        except Exception:
                            data = None
                if data:
                    with open(screenshot_path, 'wb') as fh:
                        fh.write(data)
            except Exception:
                screenshot_path = None

        context.close()
        browser.close()

    # Convert to list forms for YAML
    options_out = {k: sorted(list(v)) for k, v in field_options.items()}
    buttons_out = {k: sorted(list(v)) for k, v in field_buttons.items()}
    return labels, options_out, buttons_out, field_roles, fields_path, target_out_dir, fill_log_path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Form evaluator: iterate focus and capture field labels."
    )
    parser.add_argument("target", help="A URL or local HTML file path")
    parser.add_argument(
        "--max-tabs", type=int, default=300, dest="max_tabs", help="Safety cap on Tab presses"
    )
    # Default is headful; pass --headless to hide the browser
    parser.add_argument("--headless", action="store_true", help="Run browser headless (default: headful)")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to save form-data files (default: theorycraft-form/form-data)",
    )
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="Only scan and write form-fields YAML; do not tab through the page",
    )
    parser.add_argument(
        "--fields-yaml",
        default=None,
        help="Path to an existing fields YAML to use for filling during tabbing",
    )
    parser.add_argument(
        "--answers-yaml",
        default=None,
        help="Path to an LLM answers YAML to use for filling (overrides examples)",
    )
    parser.add_argument(
        "--resume-yaml",
        default=None,
        help="Path to a resume YAML to infer answers (used when --answers-yaml not provided)",
    )
    parser.add_argument(
        "--screenshot-name",
        default=None,
        help="Fixed screenshot filename (e.g., tricky.png) for deterministic artifacts",
    )
    parser.add_argument(
        "--loop-detect-threshold",
        type=int,
        default=3,
        help="Number of unique fields before loop detection stops tabbing (default 3)",
    )
    args = parser.parse_args(argv)

    url = _to_url(args.target)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    # Determine output directory
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser().resolve()
    else:
        script_dir = Path(__file__).resolve().parent
        out_dir = (script_dir / "form-data").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Write form-data into logs subdir, not the top-level out_dir
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_file = logs_dir / f"form-data-{ts}.txt"
    def _latest_in_dir(dir_path: Path, pattern: str) -> Optional[Path]:
        files = sorted(dir_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else None

    fields_yaml_path: Optional[Path]
    if args.fields_yaml:
        f_in = Path(args.fields_yaml).expanduser()
        if f_in.is_dir():
            fields_yaml_path = _latest_in_dir(f_in.resolve(), "form-fields-*.yaml")
        elif args.fields_yaml.lower() == "latest":
            search_dir = logs_dir
            fields_yaml_path = _latest_in_dir(search_dir, "form-fields-*.yaml")
        else:
            fields_yaml_path = f_in.resolve()
    else:
        fields_yaml_path = None

    answers_yaml_path: Optional[Path]
    if args.answers_yaml:
        a_in = Path(args.answers_yaml).expanduser()
        if a_in.is_dir():
            answers_yaml_path = _latest_in_dir(a_in.resolve(), "llm-answers-*.yaml")
        elif args.answers_yaml.lower() == "latest":
            search_dir = logs_dir
            answers_yaml_path = _latest_in_dir(search_dir, "llm-answers-*.yaml")
        else:
            answers_yaml_path = a_in.resolve()
    else:
        answers_yaml_path = None

    resume_yaml_path: Optional[Path]
    if args.resume_yaml:
        r_in = Path(args.resume_yaml).expanduser()
        resume_yaml_path = r_in.resolve()
    else:
        resume_yaml_path = None

    labels, options_map, buttons_map, roles_map, fields_path, actual_out_dir, fill_log_path = collect_form_labels(
        url,
        max_tabs=args.max_tabs,
        headless=args.headless,
        fields_yaml=fields_yaml_path,
        resume_yaml=resume_yaml_path,
        answers_yaml=answers_yaml_path,
        scan_only=args.scan_only,
        screenshot_name=args.screenshot_name,
        out_dir=out_dir,
        loop_detect_threshold=args.loop_detect_threshold,
    )

    if args.scan_only:
        print(f"Scanned fields written to {fields_path} (engine={_ENGINE})")
        return 0

    out_text = "\n".join(labels) + ("\n" if labels else "")
    out_file.write_text(out_text, encoding="utf-8")
    # Prune form-data logs to keep only the last 5 when under tests' artifacts
    try:
        from srajob.constants import TEST_ARTIFACTS_DIR

        if str(out_dir.resolve()).startswith(str(TEST_ARTIFACTS_DIR.resolve())):
            _prune_old_logs(logs_dir, keep=5, patterns=["form-data-*.txt"])
    except Exception:
        pass

    # Buttons YAML (tab-encountered)
    if buttons_map:
        buttons_doc = {
            "fields": [
                {"name": k, "buttons": buttons_map[k]} for k in sorted(buttons_map.keys())
            ]
        }
        (actual_out_dir / f"form-buttons-{ts}.yaml").write_text(
            yaml.safe_dump(buttons_doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    # Print summary + contents to console
    extra = f", fill log: {fill_log_path}" if fill_log_path else ""
    print(
        f"Wrote {len(labels)} field label(s) to {out_file} and fields YAML to {fields_path}{extra} (engine={_ENGINE})"
    )
    if labels:
        print("--- File contents ---")
        print(out_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
