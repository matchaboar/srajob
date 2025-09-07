# Usage:
#   pwsh ./form_filler_bot/scripts/fetch_test_pages.ps1
# Downloads the Datadog job page HTML and the Greenhouse application embed for offline testing.

$ErrorActionPreference = "Stop"

$jobUrl = "https://careers.datadoghq.com/detail/7073137/?gh_jid=7073137"
$appUrl = "https://boards.greenhouse.io/embed/job_app?for=datadog&token=7073137"
$outDir = "form_filler_bot/test_pages"
$outFileJob = Join-Path $outDir "datadog_job_7073137.html"
$outFileApp = Join-Path $outDir "datadog_job_7073137_app.html"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

try {
  $progressPreference = 'SilentlyContinue'
  Invoke-WebRequest -Uri $jobUrl -TimeoutSec 20 -UseBasicParsing -OutFile $outFileJob
  Write-Host "Downloaded: $outFileJob"
  Invoke-WebRequest -Uri $appUrl -TimeoutSec 20 -UseBasicParsing -OutFile $outFileApp
  Write-Host "Downloaded: $outFileApp"
} catch {
  Write-Host "Download failed: $($_.Exception.Message)" -ForegroundColor Red
  exit 2
}
