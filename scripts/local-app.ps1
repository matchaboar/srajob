param(
  [int]$TimeoutSeconds = 7200,
  [switch]$SkipOpenUI
)

$ErrorActionPreference = 'Stop'

function Ensure-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

function Import-Dotenvx($repoRoot) {
  try {
    if (-not (Test-Path (Join-Path $repoRoot '.env'))) { return }
    Push-Location $repoRoot
    $code = 'const dx=require("@dotenvx/dotenvx");const out=dx.get(undefined,{all:true});process.stdout.write(JSON.stringify(out));'
    $json = & node -e $code
    Pop-Location
    if (-not $json) { return }
    $data = $json | ConvertFrom-Json
    foreach ($kv in $data.GetEnumerator()) {
      $k = [string]$kv.Key
      $v = [string]$kv.Value
      if ([string]::IsNullOrWhiteSpace($k)) { continue }
      Set-Item -Path "Env:$k" -Value $v
    }
  } catch {
    Write-Verbose "dotenvx load failed: $($_.Exception.Message)"
  }
}

function Build-TemporalDevImage {
  Ensure-Command podman
  $repoRoot = (Resolve-Path ".").Path
  $df = Join-Path $repoRoot 'docker/temporal/Dockerfile.temporal-dev'
  $ctx = Join-Path $repoRoot 'docker/temporal'
  if (-not (Test-Path $df)) { throw "Dockerfile not found at $df" }
  Write-Host "[36m=== Building temporal-dev image with Podman (verbose) ===[0m"
  $args = @('--log-level=debug','build','-t','temporal-dev:local','-f', $df, $ctx)
  $job = Start-Job -ScriptBlock { param($a) podman @a } -ArgumentList (,$args)
  if (-not (Wait-Job $job -Timeout 600)) { Stop-Job $job -Force; throw 'podman build timed out after 600s' }
  $out = Receive-Job $job -Keep | Out-String
  # Stream logs with a colored header
  Write-Host "[35m--- podman build logs begin ---[0m"
  Write-Host $out
  Write-Host "[35m--- podman build logs end ---[0m"
  if ($LASTEXITCODE -ne 0) { throw "podman build failed with exit code $LASTEXITCODE" }
}

function Start-TemporalViaPodman {
  Ensure-Command podman
  # Remove any stale container and start a fresh detached one
  $name = 'temporalite'
  try { podman rm -f $name 2>$null | Out-Null } catch {}
  $args = @('run','-d','--replace','--name',$name,'-p','7233:7233','-p','8233:8233','temporal-dev:local')
  $job = Start-Job -ScriptBlock { param($a) podman @a } -ArgumentList (,$args)
  if (-not (Wait-Job $job -Timeout 60)) { Stop-Job $job -Force; throw 'podman run timed out after 60s' }
  $out = Receive-Job $job -Keep | Out-String
  if ($LASTEXITCODE -ne 0) { Write-Host $out; throw "podman run failed with exit code $LASTEXITCODE" }
}

function Stop-TemporalPodman {
  try { podman rm -f temporalite 2>$null | Out-Null } catch {}
}

function Wait-Port($hostname, $port, $retries=60, $delaySeconds=1) {
  for($i=0;$i -lt $retries;$i++){
    try {
      $ok = (Test-NetConnection -ComputerName $hostname -Port $port -WarningAction SilentlyContinue).TcpTestSucceeded
      if ($ok) { return }
    } catch {}
    Start-Sleep -Seconds $delaySeconds
  }
  throw "Timeout waiting for $($hostname):$port to be reachable"
}

function Ensure-ConvexHttpUrl {
  if ($env:CONVEX_HTTP_URL -and ($env:CONVEX_HTTP_URL -notmatch '<your-deployment>')) { return }
  $repoRoot = (Resolve-Path ".").Path
  $appDir = Join-Path $repoRoot 'job_board_application'
  $appEnvLocal = Join-Path $appDir '.env.local'
  if (Test-Path $appEnvLocal) {
    $lines = Get-Content -Path $appEnvLocal
    $vite = ($lines | Where-Object { $_ -match '^[ ]*VITE_CONVEX_URL[ ]*=\s*(.+)$' } | Select-Object -First 1)
    if ($vite) {
      $val = ($vite -replace '^[ ]*VITE_CONVEX_URL[ ]*=\s*', '').Trim()
      if ($val.EndsWith('.convex.cloud')) { $val = $val -replace '\\.convex\\.cloud$', '.convex.site' }
      $env:CONVEX_HTTP_URL = $val
      return
    }
  }
  # try to generate .env.local
  try {
    Push-Location $appDir
    & npx --yes convex dev --once --typecheck disable --tail-logs disable | Out-Null
  } catch {}
  finally { Pop-Location }
  if (Test-Path $appEnvLocal) {
    $lines = Get-Content -Path $appEnvLocal
    $vite = ($lines | Where-Object { $_ -match '^[ ]*VITE_CONVEX_URL[ ]*=\s*(.+)$' } | Select-Object -First 1)
    if ($vite) {
      $val = ($vite -replace '^[ ]*VITE_CONVEX_URL[ ]*=\s*', '').Trim()
      if ($val.EndsWith('.convex.cloud')) { $val = $val -replace '\\.convex\\.cloud$', '.convex.site' }
      $env:CONVEX_HTTP_URL = $val
      return
    }
  }
}

# Main
$repoRoot = (Resolve-Path ".").Path
Import-Dotenvx $repoRoot
Ensure-ConvexHttpUrl

# Start Convex dev (background)
$appDir = Join-Path $repoRoot 'job_board_application'
$convexJob = Start-Job -ScriptBlock {
  param($wd)
  Set-Location -Path $wd
  pwsh -NoLogo -NoProfile -Command 'npx --yes convex dev --typecheck disable --tail-logs disable'
} -ArgumentList $appDir

# Start Vite (background)
$viteJob = Start-Job -ScriptBlock {
  param($wd)
  Set-Location -Path $wd
  node scripts/sync-env.mjs
  npx --yes vite --port 5173 --strictPort
} -ArgumentList $appDir

# Build and start Temporal dev via Podman (detached container)
Build-TemporalDevImage
Start-TemporalViaPodman
${temporalJob} = $null

# Start worker (background)
$workerJob = Start-Job -ScriptBlock { pwsh -NoLogo -NoProfile -Command 'uv run python -m job_scrape_application.workflows.worker' }

# Wait for ports
try { Wait-Port '127.0.0.1' 7233 60 1 } catch { Write-Warning $_ }
try { Wait-Port '127.0.0.1' 8233 60 1 } catch { Write-Warning $_ }
try { Wait-Port '127.0.0.1' 5173 120 1 } catch { Write-Warning $_ }

Write-Host "Temporal UI: http://127.0.0.1:8233"
Write-Host "Frontend UI: http://127.0.0.1:5173"

function Open-InChrome([string]$url) {
  $cands = @('google-chrome','google-chrome-stable','chromium-browser','chromium','chrome')
  foreach ($c in $cands) { if (Get-Command $c -ErrorAction SilentlyContinue) { Start-Process $c $url; return } }
  try { Start-Process $url } catch { Write-Warning "Could not open $url automatically" }
}

if (-not $SkipOpenUI) {
  Open-InChrome 'http://127.0.0.1:8233'
  Open-InChrome 'http://127.0.0.1:5173'
}

Write-Host "Services started as background jobs:"
Write-Host "  Convex:  $(($convexJob.Id))"
Write-Host "  Vite:    $(($viteJob.Id))"
Write-Host "  Temporal: podman container 'temporalite'"
Write-Host "  Worker:  $(($workerJob.Id))"

function Stop-AllJobs {
  foreach ($j in @($workerJob,$temporalJob,$viteJob,$convexJob)) {
    try { if ($j -and (Get-Job -Id $j.Id -ErrorAction SilentlyContinue)) { Stop-Job $j -Force -ErrorAction SilentlyContinue } } catch {}
    try { if ($j) { Remove-Job $j -Force -ErrorAction SilentlyContinue } } catch {}
  }
  # Ensure container is stopped
  Stop-TemporalPodman
}

try {
  # Bounded wait; shows lightweight status every 30s
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 30
    $s = @{}
    foreach ($j in @{'convex'=$convexJob; 'vite'=$viteJob; 'temporal'=$temporalJob; 'worker'=$workerJob}.GetEnumerator()) {
      try { $s[$j.Key] = (Get-Job -Id $j.Value.Id).State } catch { $s[$j.Key] = 'Unknown' }
    }
    Write-Host ("[{0:HH:mm:ss}] states: {1}" -f (Get-Date), ($s.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, $_.Value } | Sort-Object | Join-String -Separator ', '))
  }
  Write-Warning "Timeout reached ($TimeoutSeconds s). Stopping services..."
} finally {
  Stop-AllJobs
}
