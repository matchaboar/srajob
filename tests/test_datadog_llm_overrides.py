import yaml
from pathlib import Path
import importlib.util
import sys
from srajob.constants import TEST_ARTIFACTS_DIR, TEST_ARTIFACTS_SCREENSHOTS_DIR


def load_main_module():
    mod_path = Path("theorycraft-form/main.py").resolve()
    spec = importlib.util.spec_from_file_location("theorycraft_form_main", str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["theorycraft_form_main"] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def latest(path: Path, pattern: str) -> Path:
    return sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[0]


def test_datadog_llm_overrides(tmp_path: Path):
    mod = load_main_module()
    out_dir = (TEST_ARTIFACTS_DIR / "datadog").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = Path("theorycraft-form/test-pages/datadog_job_7073137_app.html").resolve()

    # 1) Scan fields
    rc = mod.main([
        str(target),
        "--scan-only",
        "--headless",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    fields_yaml = latest(out_dir / "logs", "form-fields-*.yaml")
    schema = yaml.safe_load(fields_yaml.read_text(encoding="utf-8"))
    names = [f.get("name") for f in schema.get("fields", [])]

    # 2) Fill run using resume YAML (answers embedded in resume)
    auth_label = next(n for n in names if n.startswith("Are you legally authorised"))
    hear_label = next(n for n in names if n.startswith("How did you hear about this opportunity?"))
    rc = mod.main([
        str(target),
        "--headless",
        "--loop-detect-threshold", "10",
        "--out-dir", str(out_dir),
        "--fields-yaml", str(fields_yaml),
        "--resume-yaml", str(Path("theorycraft-form/example_resume/priya_desi.yml").resolve()),
        "--screenshot-name", "datadog.png",
    ])
    assert rc == 0

    logs_dir = out_dir / "logs"
    fill_log = latest(logs_dir, "form-fill-*.yaml")
    fill = yaml.safe_load(fill_log.read_text(encoding="utf-8"))
    events = fill.get("events", [])

    def selected_for(label: str) -> str:
        for e in events:
            if e.get("field") == label and ("selected" in e or "typed" in e):
                return e.get("selected") or e.get("typed")
        return ""

    assert selected_for(auth_label) == "Yes, no restriction."
    assert selected_for(hear_label) == "Datadog's Careers Page"
    # Screenshot must be created at a deterministic path (central screenshots dir)
    screenshot_path = TEST_ARTIFACTS_SCREENSHOTS_DIR / "datadog.png"
    assert screenshot_path.exists(), f"Expected screenshot at {screenshot_path}"
    assert screenshot_path.stat().st_size > 0, "Screenshot file is empty"
