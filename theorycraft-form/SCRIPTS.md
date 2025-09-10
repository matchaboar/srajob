Handy Commands (Latest Files)

These commands auto-pick the most recent outputs so you don’t have to copy timestamps.

Prereqs
- Ensure Playwright/Chrome is available (the script prefers Chrome). Headful by default.
- Set `OPENROUTER_API_KEY` in your environment (use `dotenvx run --` if using encrypted `.env`).

Bash (Linux/macOS)
- Scan fields (no tabbing), save to default out dir:
  `uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --scan-only --out-dir theorycraft-form/form-data`

- Generate LLM answers from latest fields YAML:
  `uv run theorycraft-form/ai-form.py --fields-yaml theorycraft-form/form-data/logs --out-dir theorycraft-form/form-data`

- Tab through and fill using latest fields + answers:
  `uv run theorycraft-form/main.py theorycraft-form/test-pages/datadog_job_7073137_app.html --fields-yaml latest --answers-yaml theorycraft-form/form-data --out-dir theorycraft-form/form-data`

- Inspect latest fill log:
  `ls -1t theorycraft-form/form-data/logs/form-fill-*.yaml | head -n1 | xargs -I{} sed -n '1,200p' {}`

PowerShell 7
- Scan fields (no tabbing):
  `$out = 'theorycraft-form/form-data'; uv run theorycraft-form/main.py 'theorycraft-form/test-pages/datadog_job_7073137_app.html' --scan-only --out-dir "$out"`

- Generate LLM answers from latest fields YAML:
  `$out = 'theorycraft-form/form-data'; uv run theorycraft-form/ai-form.py --fields-yaml "$out/logs" --out-dir "$out"`

- Tab through and fill using latest fields + answers:
  `$out = 'theorycraft-form/form-data'; uv run theorycraft-form/main.py 'theorycraft-form/test-pages/datadog_job_7073137_app.html' --fields-yaml latest --answers-yaml "$out" --out-dir "$out"`

- Inspect latest fill log:
  `$log = Get-ChildItem -Path 'theorycraft-form/form-data/logs' -Filter 'form-fill-*.yaml' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; Get-Content "$($log.FullName)"`

One‑Shot Pipeline (scan → LLM → fill → screenshot)

- Bash (uses `timeout` to avoid hangs):
  ```bash
  OUT='theorycraft-form/form-data'
  TARGET='theorycraft-form/test-pages/datadog_job_7073137_app.html'
  mkdir -p "$OUT"
  timeout 180 uv run theorycraft-form/main.py "$TARGET" --scan-only --headless --out-dir "$OUT" \
  && timeout 120 uv run theorycraft-form/ai-form.py --fields-yaml "$OUT/logs" --out-dir "$OUT" \
  && timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless \
       --fields-yaml latest --answers-yaml "$OUT" --out-dir "$OUT" --screenshot-name datadog.png
  ```

  With dotenvx (wrap the whole block in a subshell):
  ```bash
  dotenvx run -- bash -lc '
    OUT="theorycraft-form/form-data"; 
    TARGET="theorycraft-form/test-pages/datadog_job_7073137_app.html";
    mkdir -p "$OUT";
    timeout 180 uv run theorycraft-form/main.py "$TARGET" --scan-only --headless --out-dir "$OUT" &&
    timeout 120 uv run theorycraft-form/ai-form.py --fields-yaml "$OUT/logs" --out-dir "$OUT" &&
    timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless --fields-yaml latest --answers-yaml "$OUT" --out-dir "$OUT" --screenshot-name datadog.png
  '
  ```

- PowerShell 7 (quotes handled; includes timeout wrapper):
  ```powershell
  function Invoke-WithTimeout {
    param([string]$Command, [int]$TimeoutSec = 600)
    $job = Start-Job -ScriptBlock { param($c) powershell -NoProfile -Command $c } -ArgumentList $Command
    if (Wait-Job $job -Timeout $TimeoutSec) { Receive-Job $job } else { Stop-Job $job; Remove-Job $job; throw "Timed out: $Command" }
  }

  $out = 'theorycraft-form/form-data'
  $target = 'theorycraft-form/test-pages/datadog_job_7073137_app.html'
  Invoke-WithTimeout -Command ("uv run theorycraft-form/main.py `"$target`" --scan-only --headless --out-dir `"$out`"") -TimeoutSec 180
  Invoke-WithTimeout -Command ("uv run theorycraft-form/ai-form.py --fields-yaml `"$out/logs`" --out-dir `"$out`"") -TimeoutSec 120
  Invoke-WithTimeout -Command ("uv run theorycraft-form/main.py `"$target`" --headless --fields-yaml latest --answers-yaml `"$out`" --out-dir `"$out`" --screenshot-name `"datadog.png`"") -TimeoutSec 240
  ```

Notes
- `--fields-yaml` and `--answers-yaml` accept a directory (will pick latest inside) or the literal `latest` (uses `--out-dir` to resolve).
- The filler never submits the form. It fills fields, collects options, and logs actions.
- The scanner always writes fields YAML to `<out_dir>/logs`; the LLM step reads from there.
- To use the LLM step, set `OPENROUTER_API_KEY` and optionally `OPENROUTER_MODEL`.

Screenshots
- Locations:
  - Regular runs with `--out-dir "$OUT"`: `<OUT>/logs/screenshots/<name>.png`.
  - Test runs under `tests/test-artifacts/*`: `tests/test-artifacts/screenshots/<name>.png` (centralized).
- Quick checks:
  - `ls -1 "$OUT"/logs/screenshots/*.png 2>/dev/null || echo "No screenshots found in $OUT/logs/screenshots"`
  - `find . -type f -name '*.png' | sed -n '1,50p'`
- Re-run only the fill step (to create a screenshot):
  - Bash: `timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless --fields-yaml latest --answers-yaml "$OUT" --out-dir "$OUT" --screenshot-name datadog.png`
- With dotenvx: `dotenvx run -- bash -lc 'timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless --fields-yaml latest --answers-yaml "$OUT" --out-dir "$OUT" --screenshot-name datadog.png'`

LLM From Resume (no prior answers.yaml)

- Bash (uses OpenRouter, requires OPENROUTER_API_KEY):
  ```bash
  OUT='theorycraft-form/output'
  TARGET='theorycraft-form/test-pages/datadog_job_7073137_app.html'
  RESUME='theorycraft-form/example_resume/priya_desi.yml'
  mkdir -p "$OUT"
  # 1) Scan fields → writes to $OUT/logs
  timeout 180 uv run theorycraft-form/main.py "$TARGET" --scan-only --headless --out-dir "$OUT" \
  # 2) Ask LLM for answers based on resume → writes $OUT/llm-answers-*.yaml
  && timeout 120 uv run theorycraft-form/ai-form.py --fields-yaml "$OUT/logs" --resume-yaml "$RESUME" --out-dir "$OUT" \
  # 3) Fill using latest fields + the generated LLM answers
  && timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless --fields-yaml latest --answers-yaml "$OUT" --out-dir "$OUT" --screenshot-name datadog.png
  ```

- With dotenvx:
  ```bash
  dotenvx run -- bash -lc '
    OUT="theorycraft-form/output"; TARGET="theorycraft-form/test-pages/datadog_job_7073137_app.html"; RESUME="theorycraft-form/example_resume/priya_desi.yml";
    mkdir -p "$OUT";
    timeout 180 uv run theorycraft-form/main.py "$TARGET" --scan-only --headless --out-dir "$OUT" &&
    timeout 120 uv run theorycraft-form/ai-form.py --fields-yaml "$OUT/logs" --resume-yaml "$RESUME" --out-dir "$OUT" &&
    timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless --fields-yaml latest --answers-yaml "$OUT" --out-dir "$OUT" --screenshot-name datadog.png
  '
  ```

- PowerShell 7:
  ```powershell
  function Invoke-WithTimeout {
    param([string]$Command, [int]$TimeoutSec = 600)
    $job = Start-Job -ScriptBlock { param($c) powershell -NoProfile -Command $c } -ArgumentList $Command
    if (Wait-Job $job -Timeout $TimeoutSec) { Receive-Job $job } else { Stop-Job $job; Remove-Job $job; throw "Timed out: $Command" }
  }
  $out = 'theorycraft-form/output'
  $target = 'theorycraft-form/test-pages/datadog_job_7073137_app.html'
  $resume = 'theorycraft-form/example_resume/priya_desi.yml'
  Invoke-WithTimeout -Command ("uv run theorycraft-form/main.py `"$target`" --scan-only --headless --out-dir `"$out`"") -TimeoutSec 180
  Invoke-WithTimeout -Command ("uv run theorycraft-form/ai-form.py --fields-yaml `"$out/logs`" --resume-yaml `"$resume`" --out-dir `"$out`"") -TimeoutSec 120
  Invoke-WithTimeout -Command ("uv run theorycraft-form/main.py `"$target`" --headless --fields-yaml latest --answers-yaml `"$out`" --out-dir `"$out`" --screenshot-name `"datadog.png`"") -TimeoutSec 240
  ```

Resume‑Only Pipeline (no answers.yaml)

- Bash:
  ```bash
  OUT='theorycraft-form/output'
  TARGET='theorycraft-form/test-pages/datadog_job_7073137_app.html'
  RESUME='theorycraft-form/example_resume/priya_desi.yml'
  mkdir -p "$OUT"
  timeout 180 uv run theorycraft-form/main.py "$TARGET" --scan-only --headless --out-dir "$OUT" \
  && timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless \
       --fields-yaml latest --resume-yaml "$RESUME" --out-dir "$OUT" --screenshot-name datadog.png
  ```

- With dotenvx:
  ```bash
  dotenvx run -- bash -lc '
    OUT="theorycraft-form/output"; TARGET="theorycraft-form/test-pages/datadog_job_7073137_app.html"; RESUME="theorycraft-form/example_resume/priya_desi.yml";
    mkdir -p "$OUT";
    timeout 180 uv run theorycraft-form/main.py "$TARGET" --scan-only --headless --out-dir "$OUT" &&
    timeout 240 uv run theorycraft-form/main.py "$TARGET" --headless --fields-yaml latest --resume-yaml "$RESUME" --out-dir "$OUT" --screenshot-name datadog.png
  '
  ```

- PowerShell 7:
  ```powershell
  function Invoke-WithTimeout {
    param([string]$Command, [int]$TimeoutSec = 600)
    $job = Start-Job -ScriptBlock { param($c) powershell -NoProfile -Command $c } -ArgumentList $Command
    if (Wait-Job $job -Timeout $TimeoutSec) { Receive-Job $job } else { Stop-Job $job; Remove-Job $job; throw "Timed out: $Command" }
  }
  $out = 'theorycraft-form/output'
  $target = 'theorycraft-form/test-pages/datadog_job_7073137_app.html'
  $resume = 'theorycraft-form/example_resume/priya_desi.yml'
  Invoke-WithTimeout -Command ("uv run theorycraft-form/main.py `"$target`" --scan-only --headless --out-dir `"$out`"") -TimeoutSec 180
  Invoke-WithTimeout -Command ("uv run theorycraft-form/main.py `"$target`" --headless --fields-yaml latest --resume-yaml `"$resume`" --out-dir `"$out`" --screenshot-name `"datadog.png`"") -TimeoutSec 240
  ```
