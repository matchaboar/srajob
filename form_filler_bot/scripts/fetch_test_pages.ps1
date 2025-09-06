# Usage:
#   pwsh ./form_filler_bot/scripts/fetch_test_pages.ps1
# Downloads the Datadog job page HTML for offline testing.

$ErrorActionPreference = "Stop"

$url = "https://careers.datadoghq.com/detail/7073137/?gh_jid=7073137"
$outDir = "form_filler_bot/test_pages"
$outFile = Join-Path $outDir "datadog_job_7073137.html"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

try {
  $progressPreference = 'SilentlyContinue'
  Invoke-WebRequest -Uri $url -TimeoutSec 20 -UseBasicParsing -OutFile $outFile
  Write-Host "Downloaded: $outFile"
} catch {
  Write-Host "Download failed: $($_.Exception.Message)" -ForegroundColor Red
  exit 2
}

