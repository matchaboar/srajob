# srajob

Utilities for job scraping and application automation.

## form-filler-bot

The form-filler bot reads a user's `resume.yaml` and, when a job application has been queued, operates on the job application link.
Resume data and queued applications are stored in the Convex database. The actual form-filling behavior is not yet implemented.

## theorycraft-form: Form Evaluation Script

`theorycraft-form/main.py` can either scan all form fields (no tabbing) or tab through the page. It records a fields YAML with options and example inputs, and can optionally fill fields while tabbing using that YAML.

- Works with any local HTML file or any URL.
- Test pages are in `theorycraft-form/test-pages`.

Examples:

- Local file: `uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html`
- Absolute path: `uv run theorycraft-form/main.py /home/boarcoder/github/srajob/theorycraft-form/test-pages/datadog_job_7073137_app.html`
- URL: `uv run theorycraft-form/main.py https://example.com/form`

Optional flags:

- `--scan-only`: scan all fields and write the fields YAML, without tabbing.
- `--fields-yaml PATH`: use an existing fields YAML to fill fields while tabbing.
- `--max-tabs N`: cap Tab presses (default 300).
- `--headful`: run the browser with a visible window.
- `--out-dir PATH`: write results into a specific directory. Defaults to `theorycraft-form/form-data` next to the script.

Outputs:

- Fields: `form-fields-<timestamp>.yaml` — all detected fields with:
  - `name`: field label
  - `role`: accessibility role
  - `options`: for selects/radio/checkbox groups
  - `example`: suggested example input to use when filling
- Tab log: `form-data-<timestamp>.txt` — order of fields encountered via Tab (one per line).
- Buttons: `form-buttons-<timestamp>.yaml` — per-field buttons encountered while tabbing within that field container.

To only generate the fields YAML (no tabbing):

`uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --scan-only`

To tab through and fill fields using a saved plan:

`uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --fields-yaml theorycraft-form/form-data/form-fields-YYYYMMDD-HHMMSS.yaml`

To fill using LLM-generated answers (overrides examples):

`uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --fields-yaml theorycraft-form/form-data/form-fields-YYYYMMDD-HHMMSS.yaml --answers-yaml theorycraft-form/form-data/llm-answers-YYYYMMDD-HHMMSS.yaml`

## theorycraft-form: AI Form Answers

Generate LLM-driven answers from a fields schema + resume YAML.

Usage:

- `uv run theorycraft-form/ai-form.py --fields-yaml theorycraft-form/form-data/form-fields-YYYYMMDD-HHMMSS.yaml --out-dir theorycraft-form/form-data`

Optional:

- `--resume-yaml form_filler_2/prompt/example_resume/priya_desi.yml`
- `--answers-yaml <path>` to bias selections
- `--model <openrouter-model>` (defaults to `OPENROUTER_MODEL` or `x-ai/grok-4`)

Env:

- Requires `OPENROUTER_API_KEY`. If you use encrypted `.env`, run via `dotenvx run -- uv run ...` so the env is populated.

Output:

- `llm-answers-<timestamp>.yaml` with `fields: [ { name, role, value } ]`
- `logs/llm-chat-<timestamp>.yaml` with the prompt and model response

Note: AI script does not submit any form. Pair with the tab-filling run by passing the generated answers YAML to the filler via `--answers-yaml`.

Stealth:

- The script prefers `patchright` (a stealth-enabled Playwright drop-in). If present, it is used automatically; otherwise it falls back to the standard Playwright. The script avoids in-page JS and uses the browser accessibility tree for label extraction.
