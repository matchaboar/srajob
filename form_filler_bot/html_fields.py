from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class FormField:
    tag: str
    type: str
    name: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False
    options: List[str] = field(default_factory=list)  # for selects/radios

    def selector(self) -> str:
        if self.id:
            return f"#{self.id}"
        if self.name:
            return f"{self.tag}[name=\"{self.name}\"]"
        # Fallback: by placeholder or label is non-trivial with CSS; return tag only
        return self.tag


@dataclass
class Form:
    action: Optional[str]
    method: str
    fields: List[FormField]


def _text(el: "Any") -> str:
    try:
        return (el.get_text(strip=True) or "").strip()
    except Exception:
        return ""


def extract_forms(html: str) -> List[Form]:
    """Extract forms and fields from HTML.

    Tries BeautifulSoup if available for better accuracy; otherwise uses a
    very simple regex-based fallback sufficient for bootstrapping.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        forms: List[Form] = []
        for form in soup.find_all("form"):
            action = form.get("action")
            method = (form.get("method") or "get").lower()

            # Build label map
            label_for: Dict[str, str] = {}
            for lb in form.find_all("label"):
                lab_text = _text(lb)
                if not lab_text:
                    continue
                f = lb.get("for")
                if f:
                    label_for[f] = lab_text
                else:
                    # label wrapping input
                    inp = lb.find(["input", "textarea", "select"])  # type: ignore
                    if inp and inp.get("id"):
                        label_for[inp.get("id")] = lab_text

            fields: List[FormField] = []
            for inp in form.find_all(["input", "textarea", "select"]):
                tag = inp.name or "input"
                itype = (inp.get("type") or ("text" if tag != "select" else "select")).lower()
                name = inp.get("name")
                id_ = inp.get("id")
                ph = inp.get("placeholder")
                req = True if inp.get("required") is not None else False
                label = label_for.get(id_ or "")

                options: List[str] = []
                if tag == "select":
                    for opt in inp.find_all("option"):
                        val = opt.get("value") or _text(opt)
                        if val:
                            options.append(val)
                elif itype == "radio":
                    # Radios may share name; we still represent as distinct options
                    val = inp.get("value")
                    if val:
                        options.append(val)

                fields.append(
                    FormField(
                        tag=tag,
                        type=itype,
                        name=name,
                        id=id_,
                        label=label,
                        placeholder=ph,
                        required=req,
                        options=options,
                    )
                )

            forms.append(Form(action=action, method=method, fields=fields))
        return forms

    except Exception:
        # Minimal fallback parser using regex; not robust but avoids extra deps.
        import re

        input_re = re.compile(
            r"<(input|textarea|select)([^>]*)>", re.IGNORECASE | re.MULTILINE
        )
        attr_re = re.compile(r"(\w+)=\"([^\"]*)\"|
                              (\w+)=\'([^\']*)\'|
                              (\w+)=([^\s>]+)", re.IGNORECASE | re.VERBOSE)

        def parse_attrs(s: str) -> Dict[str, str]:
            out: Dict[str, str] = {}
            for m in attr_re.finditer(s):
                if m.group(1):
                    out[m.group(1).lower()] = m.group(2)
                elif m.group(3):
                    out[m.group(3).lower()] = m.group(4)
                elif m.group(5):
                    out[m.group(5).lower()] = m.group(6)
            return out

        fields: List[FormField] = []
        for m in input_re.finditer(html):
            tag = m.group(1).lower()
            attrs = parse_attrs(m.group(2) or "")
            itype = attrs.get("type", "text" if tag != "select" else "select").lower()
            fields.append(
                FormField(
                    tag=tag,
                    type=itype,
                    name=attrs.get("name"),
                    id=attrs.get("id"),
                    label=None,
                    placeholder=attrs.get("placeholder"),
                    required=("required" in attrs),
                )
            )

        return [Form(action=None, method="get", fields=fields)]

