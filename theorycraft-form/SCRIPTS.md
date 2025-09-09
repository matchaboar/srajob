Handy Commands (Latest Files)

These commands auto-pick the most recent outputs so you don’t have to copy timestamps.

Prereqs
- Ensure Playwright/Chrome is available (the script prefers Chrome). Headful by default.
- Set `OPENROUTER_API_KEY` in your environment (use `dotenvx run --` if using encrypted `.env`).

Bash (Linux/macOS)
- Scan fields (no tabbing), save to default out dir:
  `uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --scan-only --out-dir theorycraft-form/form-data`

- Generate LLM answers from latest fields YAML:
  `uv run theorycraft-form/ai-form.py --fields-yaml theorycraft-form/form-data --out-dir theorycraft-form/form-data`

- Tab through and fill using latest fields + answers:
  `uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --fields-yaml latest --answers-yaml latest --out-dir theorycraft-form/form-data`

- Inspect latest fill log:

```sh
ls -1t theorycraft-form/form-data/logs/form-fill-*.yaml | head -n1 | xargs -I{} sed -n '1,200p' {}```

PowerShell 7
- Scan fields (no tabbing):
  `$out = 'theorycraft-form/form-data'; uv run theorycraft-form/main.py 'theorycraft-form/test-pages/datadog_job_7073137_app.html' --scan-only --out-dir "$out"`

- Generate LLM answers from latest fields YAML:
  `$out = 'theorycraft-form/form-data'; $fields = Get-ChildItem -Path $out -Filter 'form-fields-*.yaml' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; uv run theorycraft-form/ai-form.py --fields-yaml "$($fields.FullName)" --out-dir "$out"`

- Tab through and fill using latest fields + answers:
  `$out = 'theorycraft-form/form-data'; uv run theorycraft-form/main.py 'theorycraft-form/test-pages/datadog_job_7073137_app.html' --fields-yaml latest --answers-yaml latest --out-dir "$out"`

- Inspect latest fill log:
  `$log = Get-ChildItem -Path 'theorycraft-form/form-data/logs' -Filter 'form-fill-*.yaml' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Get-Content "$($log.FullName)"`

Notes
- `--fields-yaml` and `--answers-yaml` accept a directory (will pick latest inside) or the literal `latest` (uses `--out-dir` to resolve).
- The filler never submits the form. It fills fields, collects options, and logs actions.
