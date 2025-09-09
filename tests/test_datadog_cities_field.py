import yaml
from pathlib import Path
import importlib.util
import sys
from srajob.constants import TEST_ARTIFACTS_DIR


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


def test_datadog_cities_field_is_filled(tmp_path: Path):
    mod = load_main_module()
    out_dir = (TEST_ARTIFACTS_DIR / "datadog").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = Path("theorycraft-form/test-pages/datadog_job_7073137_app.html").resolve()

    # 1) Scan fields (headless)
    rc = mod.main([
        str(target),
        "--scan-only",
        "--headless",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0

    # 2) Fill using resume YAML to drive cities answer
    rc = mod.main([
        str(target),
        "--headless",
        "--loop-detect-threshold", "10",
        "--out-dir", str(out_dir),
        "--fields-yaml", "latest",
        "--resume-yaml", str(Path("theorycraft-form/example_resume/priya_desi.yml").resolve()),
        "--screenshot-name", "datadog.png",
    ])
    assert rc == 0

    logs_dir = out_dir / "logs"
    fill_log = latest(logs_dir, "form-fill-*.yaml")
    fill = yaml.safe_load(fill_log.read_text(encoding="utf-8"))
    events = fill.get("events", [])

    # Find the city availability field and ensure it was filled from resume
    def typed_for(label_prefix: str) -> str:
        for e in events:
            if e.get("field", "").startswith(label_prefix) and e.get("typed"):
                return e.get("typed")
        return ""

    typed = typed_for("In what cities are you available to work?")
    assert typed != "", "Expected a typed value for the cities availability field"
    # Resume has 'New York City' and 'Mountain View', but widget expects allowed options.
    # We still log the raw intent, but UI should show mapped allowed options.
    assert typed == "Seattle, New York City, Mountain View"

    # The page text (captured before screenshot) must include committed tokens
    page_text = (fill.get("page_text") or "").replace("\u00A0", " ")
    # Screenshot text should show committed, allowed option chips
    expected_visible = ["Seattle", "New York", "San Jose (Campbell)"]
    for t in expected_visible:
        assert t in page_text, f"Expected token '{t}' to be visible on page before screenshot"
