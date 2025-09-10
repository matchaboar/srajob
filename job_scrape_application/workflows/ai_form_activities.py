from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

import httpx
import yaml

from temporalio import activity
from .config import settings
from .temporal_health_check import normalize_convex_base


@activity.defn
async def lease_next_ai_application() -> Optional[Dict[str, Any]]:
    base = normalize_convex_base(settings.convex_http_url or "http://local")
    url = base + "/api/form-fill/lease"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={})
        resp.raise_for_status()
        data = resp.json()
        return data or None


@activity.defn
async def complete_ai_application(
    queue_id: str,
    filled_data: Optional[Dict[str, Any]] = None,
    logs: Optional[Dict[str, str]] = None,
) -> None:
    base = normalize_convex_base(settings.convex_http_url or "http://local")
    url = base + "/api/form-fill/complete"
    payload: Dict[str, Any] = {"id": queue_id}
    if filled_data is not None:
        payload["filledData"] = filled_data
    if logs:
        payload["logs"] = logs
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()


@activity.defn
async def fail_ai_application(queue_id: str, error: str) -> None:
    base = normalize_convex_base(settings.convex_http_url or "http://local")
    url = base + "/api/form-fill/error"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={"id": queue_id, "error": error})
        resp.raise_for_status()


@activity.defn
async def get_resume_for_user(user_id: str) -> Optional[Union[Dict[str, Any], str]]:
    base = normalize_convex_base(settings.convex_http_url or "http://local")
    url = base + f"/api/ai-resume?userId={user_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data")


@activity.defn
async def queue_jobs_for_user(user_id: str, limit: int = 10, only_unqueued: bool = True) -> int:
    base = normalize_convex_base(settings.convex_http_url or "http://local")
    url = base + "/api/form-fill/queue-user-jobs"
    payload = {"userId": user_id, "limit": int(limit), "onlyUnqueued": bool(only_unqueued)}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json() or {}
        try:
            return int(data.get("inserted", 0))
        except Exception:
            return 0


def _import_theorycraft_collect():
    # Import theorycraft-form/main.py's collect_form_labels lazily
    import importlib.util
    import sys

    mod_path = Path("theorycraft-form/main.py").resolve()
    spec = importlib.util.spec_from_file_location("theorycraft_form_main", str(mod_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to import theorycraft-form/main.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["theorycraft_form_main"] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    if not hasattr(mod, "collect_form_labels"):
        raise RuntimeError("collect_form_labels not found in theorycraft-form/main.py")
    return mod.collect_form_labels  # type: ignore[attr-defined]


def _write_resume_yaml(resume: Union[Dict[str, Any], str]) -> Path:
    # Write resume to a temp YAML file for the collector
    tmp = tempfile.NamedTemporaryFile(prefix="ai-resume-", suffix=".yaml", delete=False)
    p = Path(tmp.name)
    tmp.close()
    if isinstance(resume, str):
        # Assume already YAML; write as-is
        p.write_text(resume, encoding="utf-8")
    else:
        p.write_text(yaml.safe_dump(resume, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


def _extract_filled_data_from_log(log_path: Optional[Path]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not log_path or not log_path.exists():
        return out
    try:
        raw = yaml.safe_load(log_path.read_text(encoding="utf-8")) or {}
        events = raw.get("events") or []
        for ev in events:
            field = ev.get("field") or ev.get("name") or ""
            if not field:
                continue
            # Typed text value
            if ev.get("typed"):
                out[field] = ev.get("typed")
            # Multi-tokens typed
            if ev.get("tokens"):
                out[field] = ev.get("tokens")
            # Selected options for radio/checkbox/combobox
            if ev.get("selected"):
                out[field] = ev.get("selected")
    except Exception:
        # If parsing fails, attach raw text
        try:
            out["_raw_log"] = log_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return out


@activity.defn
def run_form_fill(job_url: str, resume: Optional[Union[Dict[str, Any], str]] = None) -> Dict[str, Any]:
    """Run the form-filler against the target job URL.

    Returns a result dict containing filledData and log paths.
    """
    collect = _import_theorycraft_collect()
    resume_yaml: Optional[Path] = None
    try:
        if resume:
            resume_yaml = _write_resume_yaml(resume)
        labels, options_map, buttons_map, roles_map, fields_path, out_dir, fill_log_path = collect(
            job_url,
            max_tabs=300,
            headless=True,
            fields_yaml=None,
            resume_yaml=resume_yaml,
            answers_yaml=None,
            scan_only=False,
            screenshot_name=None,
            out_dir=None,
            loop_detect_threshold=3,
        )
        filled = _extract_filled_data_from_log(fill_log_path)
        logs: Dict[str, str] = {}
        if fields_path:
            logs["fieldsYaml"] = str(fields_path)
        if fill_log_path:
            logs["fillLogYaml"] = str(fill_log_path)
        # Screenshot path is generated inside theorycraft; infer location
        # Not strictly necessary, so skip unless needed later
        return {"filledData": filled, "logs": logs}
    finally:
        if resume_yaml and resume_yaml.exists():
            try:
                resume_yaml.unlink()
            except Exception:
                pass
