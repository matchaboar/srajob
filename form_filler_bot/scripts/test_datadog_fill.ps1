$ErrorActionPreference = "Stop"

function Invoke-WithTimeout {
  param(
    [Parameter(Mandatory=$true)][string]$Command,
    [Parameter(Mandatory=$true)][int]$TimeoutSec
  )
  $job = Start-Job -ScriptBlock { param($cmd) & $cmd } -ArgumentList $Command
  if (-not (Wait-Job -Job $job -Timeout $TimeoutSec)) {
    Stop-Job -Job $job -Force | Out-Null
    Remove-Job -Job $job -Force | Out-Null
    throw "Command timed out after $TimeoutSec sec: $Command"
  }
  Receive-Job -Job $job
  Remove-Job -Job $job -Force | Out-Null
}

Write-Host "Fetching Datadog test HTML..."
Invoke-WithTimeout -Command "pwsh ./form_filler_bot/scripts/fetch_test_pages.ps1" -TimeoutSec 60

Write-Host "Ensuring dependencies (uv + browser-use + bs4)..."
Invoke-WithTimeout -Command "uv add browser-use pyyaml beautifulsoup4" -TimeoutSec 600

Write-Host "Installing Chromium via playwright (if needed)..."
Invoke-WithTimeout -Command "uvx playwright install chromium --with-deps --no-shell" -TimeoutSec 600

Write-Host "Running form filler headfully on local SAMPLE form..."
Invoke-WithTimeout -Command "uv run python -m form_filler_bot.cli --html-file form_filler_bot/test_pages/datadog_form_sample.html --resume form_filler_bot/samples/resume.sample.yaml --execute --window-width 1100 --window-height 720 --action-delay-ms 200 --hold-seconds 5 --post-goto-wait-ms 1500" -TimeoutSec 900

Write-Host "Running form filler headfully on LIVE Greenhouse embed..."
Invoke-WithTimeout -Command "uv run python -m form_filler_bot.cli --url 'https://boards.greenhouse.io/embed/job_app?for=datadog&token=7073137' --resume form_filler_bot/samples/resume.sample.yaml --execute --window-width 1100 --window-height 720 --action-delay-ms 200 --hold-seconds 5 --post-goto-wait-ms 2500" -TimeoutSec 900

Write-Host "Done. The browser should have opened and attempted to fill fields."
