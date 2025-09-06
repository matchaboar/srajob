param(
  [string]$SiteId = $env:NETLIFY_SITE_ID,
  [string]$AuthToken = $env:NETLIFY_AUTH_TOKEN
)

if (-not $SiteId -or -not $AuthToken) {
  Write-Error "NETLIFY_SITE_ID and NETLIFY_AUTH_TOKEN must be provided (arg or env)."
  exit 1
}

Push-Location "job_board_application"
try {
  # Install and build
  npm ci
  $env:VITE_CONVEX_URL = "https://affable-kiwi-46.convex.cloud"
  npm run build

  # Deploy to Netlify (prod)
  $deployCmd = "npx netlify deploy --dir dist --prod --site $SiteId --auth $AuthToken"
  Write-Host "Running: $deployCmd"
  # Run with a max timeout of 5 minutes
  $job = Start-Job -ScriptBlock { param($cmd) & cmd /c $cmd } -ArgumentList $deployCmd
  if (-not (Wait-Job $job -Timeout 300)) { Stop-Job $job -ErrorAction SilentlyContinue; throw "Netlify deploy timed out" }
  Receive-Job $job
}
finally {
  Pop-Location
}

