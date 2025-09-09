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


def test_tricky_form_scan_and_fill(tmp_path: Path):
    mod = load_main_module()
    out_dir = (TEST_ARTIFACTS_DIR / "tricky").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = Path("theorycraft-form/test-pages/tricky_form.html").resolve()

    # Scan only (headless)
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
    assert "Full Name *" in names
    # Preferred City exists and is a combobox
    city = next((f for f in schema.get("fields", []) if f.get("name") == "Preferred City"), None)
    assert city is not None
    assert city.get("role") == "combobox"

    # Fill using latest fields, and resume for authorization mapping
    rc = mod.main([
        str(target),
        "--fields-yaml", str(out_dir / "logs"),
        "--resume-yaml", str(Path("theorycraft-form/example_resume/priya_desi.yml").resolve()),
        "--screenshot-name", "tricky.png",
        "--headless",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    logs_dir = out_dir / "logs"
    fill_log = latest(logs_dir, "form-fill-*.yaml")
    fill = yaml.safe_load(fill_log.read_text(encoding="utf-8"))
    events = fill.get("events", [])
    # Ensure at least Full Name and Preferred City handled
    assert any(e.get("field") == "Full Name *" and e.get("typed") for e in events)
    assert any(e.get("field") == "Preferred City" and e.get("selected") for e in events)

    # Authorization (radio) should be selected to 'Yes' based on resume
    assert any(e.get("selected") == "Yes" for e in events), "Expected authorized radio to select 'Yes'"

    # Screenshot must be created at a deterministic path (central screenshots dir)
    screenshot_path = TEST_ARTIFACTS_SCREENSHOTS_DIR / "tricky.png"
    assert screenshot_path.exists(), f"Expected screenshot at {screenshot_path}"
    assert screenshot_path.stat().st_size > 0, "Screenshot file is empty"
