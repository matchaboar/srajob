# Form Filler Bot (Scaffold)

This module bootstraps a browser-assisted job application form filler designed to:

- Extract form fields from any job page (using an HTML snapshot or a live URL).
- Plan values for each field based on a candidate resume (YAML).
- Execute the plan with the `browser-use` library.

The Datadog job page is used as a first test input, but the logic is abstract to support any website.

## Quick Start

1) Download test HTML (PowerShell 7):

```
# Saves to form_filler_bot/test_pages/datadog_job_7073137.html
pwsh ./form_filler_bot/scripts/fetch_test_pages.ps1
```

2) Prepare a resume YAML. A sample is included at:

```
form_filler_bot/samples/resume.sample.yaml
```

3) Create a fill plan (no execution):

```
uv run python -m form_filler_bot.cli --html-file form_filler_bot/test_pages/datadog_job_7073137.html \
  --resume form_filler_bot/samples/resume.sample.yaml \
  --plan-only --out-plan form_filler_bot/test_pages/plan.json
```

4) Use the live Greenhouse application embed URL (saves a snapshot for testing):

```
uv run python -m form_filler_bot.cli --url "https://boards.greenhouse.io/embed/job_app?for=datadog&token=7073137" \
  --save-html --out-html form_filler_bot/test_pages/datadog_job_7073137_app.html \
  --resume form_filler_bot/samples/resume.sample.yaml --plan-only
```

5) Execute a plan with `browser-use` (headful):

```
uv add browser-use pyyaml beautifulsoup4
# Install Chromium if needed (headful)
uvx playwright install chromium --with-deps --no-shell

# Option A: run against the live application embed (Greenhouse)
uv run python -m form_filler_bot.cli --url "https://boards.greenhouse.io/embed/job_app?for=datadog&token=7073137" \
  --resume form_filler_bot/samples/resume.sample.yaml --execute --headless

# Option B: run against the saved local HTML snapshot (file://)
uv run python -m form_filler_bot.cli --html-file form_filler_bot/test_pages/datadog_job_7073137_app.html \
  --resume form_filler_bot/samples/resume.sample.yaml --execute
```

Note: The adapter maps `FillAction`s to browser-use events. Pass `--headless` or set `BROWSER_HEADLESS=1` for headless runs (useful in CI). On desktops you can omit `--headless` to see the browser.

## Files

- `form_filler_bot/html_fields.py`: Extracts forms and fields (BeautifulSoup if available; regex fallback).
- `form_filler_bot/planner.py`: Rule-based planner and LLM-based planner interface; outputs `FillAction`s.
- `form_filler_bot/browser_adapters.py`: `BrowserUseAdapter` stub to run actions.
- `form_filler_bot/resume_loader.py`: YAML loader (requires `pyyaml`).
- `form_filler_bot/cli.py`: CLI for planning and executing.
- `form_filler_bot/scripts/fetch_test_pages.ps1`: Downloads Datadog test HTML.
- `form_filler_bot/samples/resume.sample.yaml`: Example resume.

## LLM Integration

- Implement a concrete `BaseLLMClient` (e.g., OpenAI, local LLM) and pass it into `plan_with_llm()`.
- `cli.py` defaults to rule-based planning (`--use-llm` off). Turn it on when an LLM client is wired.

## Notes

- Keep command timeouts short and avoid long-running processes.
- Use `uv` for Python execution and dependency management.
- For execution, ensure `browser-use` and its browser dependencies are installed/configured.
