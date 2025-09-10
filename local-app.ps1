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
  }
  catch {
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
  $args = @('--log-level=debug', 'build', '-t', 'temporal-dev:local', '-f', $df, $ctx)
  $job = Start-Job -ScriptBlock { param($a) podman @a } -ArgumentList (, $args)
  if (-not (Wait-Job $job -Timeout 600)) { Stop-Job $job -Force; throw 'podman build timed out after 600s' }
  $out = Receive-Job $job -Keep | Out-String
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
  $args = @('run', '-d', '--replace', '--name', $name, '-p', '7233:7233', '-p', '8233:8233', 'temporal-dev:local')
  $job = Start-Job -ScriptBlock { param($a) podman @a } -ArgumentList (, $args)
  if (-not (Wait-Job $job -Timeout 60)) { Stop-Job $job -Force; throw 'podman run timed out after 60s' }
  $out = Receive-Job $job -Keep | Out-String
  if ($LASTEXITCODE -ne 0) { Write-Host $out; throw "podman run failed with exit code $LASTEXITCODE" }
}

function Stop-TemporalPodman {
  try { podman rm -f temporalite 2>$null | Out-Null } catch {}
}

function Get-PidsByPort([int]$port) {
  $pids = New-Object System.Collections.Generic.List[int]
  try {
    $lsof = Get-Command lsof -ErrorAction SilentlyContinue
    if ($lsof) {
      $out = & lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>$null
      if ($out) {
        foreach ($line in ($out -split "`n")) {
          $t = $line.Trim()
          if ($t -match '^[0-9]+$') { [void]$pids.Add([int]$t) }
        }
      }
    }
  }
  catch {}

  if ($pids.Count -eq 0) {
    try {
      $ss = Get-Command ss -ErrorAction SilentlyContinue
      if ($ss) {
        $out2 = & ss -ltnp 2>$null
        if ($out2) {
          foreach ($line in ($out2 -split "`n")) {
            if ($line -match (":$port\b")) {
              $matches = [regex]::Matches($line, 'pid=(\d+)')
              foreach ($m in $matches) { [void]$pids.Add([int]$m.Groups[1].Value) }
            }
          }
        }
      }
    }
    catch {}
  }

  if ($pids.Count -eq 0) {
    try {
      $netstat = Get-Command netstat -ErrorAction SilentlyContinue
      if ($netstat) {
        $out3 = & netstat -ano -p tcp 2>$null
        if ($out3) {
          foreach ($line in ($out3 -split "`n")) {
            if ($line -match ("`:\s*$port\s") -and $line -match 'LISTENING') {
              if ($line -match '(\d+)\s*$') { [void]$pids.Add([int]$Matches[1]) }
            }
          }
        }
      }
    }
    catch {}
  }

  return ($pids | Sort-Object -Unique)
}

function Stop-ListenersOnPort([int]$port, [int]$graceMs = 1000) {
  $pids = Get-PidsByPort $port
  if (-not $pids -or $pids.Count -eq 0) { return }
  Write-Host "Cleaning up listeners on port ${port}: $($pids -join ', ')"
  foreach ($procId in $pids) {
    try { Stop-Process -Id $procId -ErrorAction SilentlyContinue } catch {}
  }
  Start-Sleep -Milliseconds $graceMs
  $remain = Get-PidsByPort $port
  if ($remain -and $remain.Count -gt 0) {
    Write-Host "Force killing listeners on port ${port}: $($remain -join ', ')"
    foreach ($procId in $remain) { try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {} }
  }
}

function Build-TemporalDevImageSafe {
  Ensure-Command podman
  $repoRoot = (Resolve-Path ".").Path
  $df = Join-Path $repoRoot 'docker/temporal/Dockerfile.temporal-dev'
  $ctx = Join-Path $repoRoot 'docker/temporal'
  if (-not (Test-Path $df)) { throw "Dockerfile not found at $df" }
  Write-Host "Building temporal-dev image with Podman (safe)"
  $args = @('--log-level=debug', 'build', '-t', 'temporal-dev:local', '-f', $df, $ctx)

  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  $tempDir = $env:TEMP
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = $env:TMP }
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = $env:TMPDIR }
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = [System.IO.Path]::GetTempPath() }
  $logOut = Join-Path $tempDir "temporal_build_${ts}.out.log"
  $logErr = Join-Path $tempDir "temporal_build_${ts}.err.log"

  $proc = Start-Process -FilePath 'podman' -ArgumentList ($args -join ' ') -NoNewWindow -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru
  $deadline = (Get-Date).AddSeconds(600)
  while (-not $proc.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
  if (-not $proc.HasExited) {
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    Write-Host "--- podman build logs (timeout) ---"
    if (Test-Path $logOut) { Get-Content -Path $logOut | ForEach-Object { Write-Host $_ } }
    if (Test-Path $logErr) { Get-Content -Path $logErr | ForEach-Object { Write-Host $_ } }
    throw 'podman build timed out after 600s'
  }

  Write-Host "--- podman build logs begin ---"
  if (Test-Path $logOut) { Get-Content -Path $logOut | ForEach-Object { Write-Host $_ } }
  if (Test-Path $logErr) { Get-Content -Path $logErr | ForEach-Object { Write-Host $_ } }
  Write-Host "--- podman build logs end ---"

  if ($proc.ExitCode -ne 0) { throw "podman build failed with exit code $($proc.ExitCode)" }
}

function Start-TemporalViaPodmanSafe {
  Ensure-Command podman
  $name = 'temporalite'
  try { podman rm -f $name 2>$null | Out-Null } catch {}
  Write-Host "Starting Temporal dev container via Podman..."
  # Bind to 0.0.0.0 to improve Windows<->WSL accessibility
  $args = @('run', '-d', '--replace', '--name', $name,
    '--publish', '0.0.0.0:7233:7233', '--publish', '0.0.0.0:8233:8233',
    '--volume', 'temporal_dev_data:/data',
    'temporal-dev:local')

  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  $tempDir = $env:TEMP
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = $env:TMP }
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = $env:TMPDIR }
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = [System.IO.Path]::GetTempPath() }
  $logOut = Join-Path $tempDir "temporal_run_${ts}.out.log"
  $logErr = Join-Path $tempDir "temporal_run_${ts}.err.log"

  $proc = Start-Process -FilePath 'podman' -ArgumentList ($args -join ' ') -NoNewWindow -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru
  while (-not $proc.HasExited) { Start-Sleep -Seconds 1 }
  if (-not $proc.HasExited) {
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    if (Test-Path $logOut) { Get-Content -Path $logOut | ForEach-Object { Write-Host $_ } }
    if (Test-Path $logErr) { Get-Content -Path $logErr | ForEach-Object { Write-Host $_ } }
    throw 'podman run timed out after 60s'
  }
  if ($proc.ExitCode -ne 0) {
    if (Test-Path $logOut) { Get-Content -Path $logOut | ForEach-Object { Write-Host $_ } }
    if (Test-Path $logErr) { Get-Content -Path $logErr | ForEach-Object { Write-Host $_ } }
    throw "podman run failed with exit code $($proc.ExitCode)"
  }
  Write-Host "Podman container 'temporalite' started."
}

function Start-WorkerSupervised {
  param(
    [string]$WorkingDir,
    [hashtable]$EnvMap,
    [int]$MaxRestarts = 3,
    [string]$LogPath
  )
  $sb = {
    param($wd, $envMap, $maxR, $logFile)
    Set-Location -Path $wd
    foreach ($k in $envMap.Keys) {
      $v = [string]$envMap[$k]
      if ($v) { Set-Item -Path ("Env:" + $k) -Value $v }
    }
    $attempt = 0
    while ($attempt -le $maxR) {
      $attempt++
      try {
        Write-Host ("[worker] starting attempt {0}/{1}" -f $attempt, ($maxR + 1))
        & uv run python -m job_scrape_application.workflows.worker 2>&1 |
        Tee-Object -FilePath $logFile -Append | Out-Null
      }
      catch {}
      Start-Sleep -Seconds ([Math]::Min(30, [int][Math]::Pow(2, [Math]::Min(5, $attempt))))
    }
    Write-Host "[worker] reached max restarts; exiting supervisor"
  }
  return Start-Job -ScriptBlock $sb -ArgumentList @($WorkingDir, $EnvMap, $MaxRestarts, $LogPath)
}

function Test-TcpPort($hostname, $port, $timeoutMs = 1000) {
  try {
    $client = [System.Net.Sockets.TcpClient]::new()
    $iar = $client.BeginConnect($hostname, [int]$port, $null, $null)
    $completed = $iar.AsyncWaitHandle.WaitOne($timeoutMs)
    if (-not $completed) { $client.Close(); return $false }
    $client.EndConnect($iar)
    $client.Close()
    return $true
  }
  catch {
    return $false
  }
}

function Wait-Port($hostname, $port, $retries = 60, $delaySeconds = 1) {
  for ($i = 0; $i -lt $retries; $i++) {
    if (Test-TcpPort $hostname $port 1000) { return }
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
  }
  catch {}
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

# Clean reserved ports so the predetermined ports are always available
Stop-ListenersOnPort 5173
Stop-ListenersOnPort 8233
Stop-ListenersOnPort 7233

function Reset-StaleAIQueue {
  param([int]$MaxAgeSeconds = 10)
  try {
    if (-not $env:CONVEX_HTTP_URL -or [string]::IsNullOrWhiteSpace($env:CONVEX_HTTP_URL)) {
      Write-Warning "CONVEX_HTTP_URL not set; skip stale reset"
      return
    }
    $base = $env:CONVEX_HTTP_URL.TrimEnd('/')
    $uri = "$base/api/form-fill/reset-stale"
    $body = @{ maxAgeSeconds = [int]$MaxAgeSeconds } | ConvertTo-Json -Compress
    $res = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body -TimeoutSec 10
    $count = 0
    try { $count = [int]($res.reset) } catch {}
    Write-Host ("Reset stale running AI-apply items: {0}" -f $count)
  } catch {
    Write-Warning ("Reset-StaleAIQueue failed: {0}" -f $_)
  }
}

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
  # Bind Vite to 0.0.0.0 for Windows access through WSL
  npx --yes vite --host 0.0.0.0 --port 5173 --strictPort
} -ArgumentList $appDir

# Build and start Temporal dev via Podman (detached container)
Build-TemporalDevImageSafe
Start-TemporalViaPodmanSafe
Write-Host "Waiting for services to become ready..."
${temporalJob} = $null

# Wait for ports
try { Wait-Port '127.0.0.1' 7233 60 1 } catch { Write-Warning $_ }
try { Wait-Port '127.0.0.1' 8233 60 1 } catch { Write-Warning $_ }
try { Wait-Port '127.0.0.1' 5173 120 1 } catch { Write-Warning $_ }

Write-Host "Temporal UI: http://127.0.0.1:8233"
Write-Host "Frontend UI: http://127.0.0.1:5173"

# Reset stale 'running' AI apply items to 'pending' so worker can lease immediately
Reset-StaleAIQueue -MaxAgeSeconds 10

# Start worker with supervision (background)
$workerLog = Join-Path ([System.IO.Path]::GetTempPath()) ("temporal_worker_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$envMap = @{ 'TEMPORAL_ADDRESS' = '127.0.0.1:7233'; 'TEMPORAL_NAMESPACE' = 'default'; 'CONVEX_HTTP_URL' = $env:CONVEX_HTTP_URL }
$workerJob = Start-WorkerSupervised -WorkingDir $repoRoot -EnvMap $envMap -MaxRestarts 3 -LogPath $workerLog
Write-Host ("Worker log: {0}" -f $workerLog)

# Kick a demo workflow so the task queue page has a recent run to click
try {
  $demoCmd = 'uv run python -m job_scrape_application.workflows.run_demo'
  $demoJob = Start-Job -ScriptBlock { param($cmd, $wd) Set-Location -Path $wd; pwsh -NoLogo -NoProfile -Command $cmd } -ArgumentList @($demoCmd, $repoRoot)
  if (-not (Wait-Job $demoJob -Timeout 30)) { try { Stop-Job $demoJob -Force } catch {} }
  try { Receive-Job $demoJob -Keep | Out-String | Write-Host } catch {}
  try { Remove-Job $demoJob -Force -ErrorAction SilentlyContinue } catch {}
}
catch { Write-Verbose "Demo workflow kickoff failed: $($_.Exception.Message)" }

function Open-InChrome([string]$url) {
  $cands = @('google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium', 'chrome')
  foreach ($c in $cands) { if (Get-Command $c -ErrorAction SilentlyContinue) { Start-Process $c $url; return } }
  # If running under WSL, try to open Windows default browser
  try {
    if (Get-Command cmd.exe -ErrorAction SilentlyContinue) {
      Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', 'start', '', '"' + $url + '"') | Out-Null
      return
    }
  }
  catch {}
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
  foreach ($j in @($workerJob, $temporalJob, $viteJob, $convexJob)) {
    try { if ($j -and (Get-Job -Id $j.Id -ErrorAction SilentlyContinue)) { Stop-Job $j -Force -ErrorAction SilentlyContinue } } catch {}
    try { if ($j) { Remove-Job $j -Force -ErrorAction SilentlyContinue } } catch {}
  }
  # Intentionally do NOT stop the podman container here so it persists
}

try {
  # Bounded wait; shows lightweight status every 30s
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 30
    $s = @{}
    foreach ($j in @{'convex' = $convexJob; 'vite' = $viteJob; 'temporal' = $temporalJob; 'worker' = $workerJob }.GetEnumerator()) {
      try { $s[$j.Key] = (Get-Job -Id $j.Value.Id).State } catch { $s[$j.Key] = 'Unknown' }
    }
    $pairs = $s.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, $_.Value } | Sort-Object
    Write-Host ("[{0:HH:mm:ss}] states: {1}" -f (Get-Date), ($pairs -join ', '))
  }
  Write-Warning "Timeout reached ($TimeoutSeconds s). Stopping services..."
}
finally {
  Stop-AllJobs
}
