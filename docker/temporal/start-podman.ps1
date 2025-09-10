param(
  [switch]$RunCheck,
  [int]$HealthCheckTimeoutSeconds = 120,
  [int]$BuildTimeoutSeconds = 300,
  [switch]$VerboseBuild,
  [switch]$SkipOpenUI
)

$ErrorActionPreference = 'Stop'

function Ensure-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

function Ensure-PodmanRunning() {
  # On Linux, podman runs natively and "podman machine" is unnecessary/unsupported.
  if ($IsLinux) { return }
  # Ensure a machine exists and is running on macOS/Windows
  try {
    podman machine inspect | Out-Null
  } catch {
    try {
      podman machine init --now | Out-Null
      return
    } catch {
      Write-Warning "podman machine init not supported or failed; continuing"
      return
    }
  }
  try {
    $listJson = podman machine list --format json
    $machines = $listJson | ConvertFrom-Json
    $default = $machines | Where-Object { $_.Default -eq $true }
    if (-not $default) { $default = $machines | Select-Object -First 1 }
    if ($default -and $default.Running -ne $true) {
      podman machine start | Out-Null
    }
  } catch {
    try { podman machine start | Out-Null } catch {}
  }
}

function Ensure-Network($netName) {
  podman network inspect $netName -f '{{.Name}}' 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { podman network create $netName | Out-Null }
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
  } catch {
    return $false
  }
}

function Wait-Port($hostname, $port, $retries=60, $delaySeconds=1) {
  for($i=0;$i -lt $retries;$i++){
    if (Test-TcpPort $hostname $port 1000) { return }
    Start-Sleep -Seconds $delaySeconds
  }
  throw "Timeout waiting for $($hostname):$port to be reachable"
}

Ensure-Command podman
Ensure-PodmanRunning

$net = 'tempnet'
Ensure-Network $net

function Import-Dotenvx($repoRoot) {
  # Load and decrypt .env into current process env via dotenvx
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

# Load .env from repo root to supply envs
$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
Import-Dotenvx $repoRoot

function Invoke-WithTimeout([scriptblock]$Script, [int]$TimeoutSeconds) {
  $job = Start-Job -ScriptBlock $Script
  try {
    if (-not (Wait-Job $job -Timeout $TimeoutSeconds)) {
      Stop-Job $job -Force | Out-Null
      Receive-Job $job -Keep | Out-String | Write-Output
      throw "Operation timed out after $TimeoutSeconds seconds"
    }
    $out = Receive-Job $job -Keep | Out-String
    return $out
  } finally {
    Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
  }
}

function Build-TemporalDevImage {
  $df = Join-Path $scriptDir 'Dockerfile.temporal-dev'
  $ctx = $scriptDir
  Write-Host "Building temporal-dev image..."
  $enableVerbose = $VerboseBuild -or ($env:TEMPORAL_DEV_BUILD_VERBOSE -eq '1')
  $args = @('build')
  if ($enableVerbose) { $args = @('--log-level=debug') + $args }
  $args += @('-t','temporal-dev:local','-f', $df, $ctx)

  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  # Cross-platform temp directory resolution
  $tempDir = $env:TEMP
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = $env:TMP }
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = $env:TMPDIR }
  if (-not $tempDir -or [string]::IsNullOrWhiteSpace($tempDir)) { $tempDir = [System.IO.Path]::GetTempPath() }
  $logOut = Join-Path $tempDir "temporal_build_${ts}.out.log"
  $logErr = Join-Path $tempDir "temporal_build_${ts}.err.log"
  $proc = Start-Process -FilePath 'podman' -ArgumentList ($args -join ' ') -NoNewWindow -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru
  $deadline = (Get-Date).AddSeconds($BuildTimeoutSeconds)
  while (-not $proc.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
  if (-not $proc.HasExited) {
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    Write-Host "--- podman build logs (timeout) ---"
    if (Test-Path $logOut) { Get-Content -Path $logOut | ForEach-Object { Write-Host $_ } }
    if (Test-Path $logErr) { Get-Content -Path $logErr | ForEach-Object { Write-Host $_ } }
    throw "Image build timed out after $BuildTimeoutSeconds seconds"
  }

  Write-Host "--- podman build logs begin ---"
  if (Test-Path $logOut) { Get-Content -Path $logOut | ForEach-Object { Write-Host $_ } }
  if (Test-Path $logErr) { Get-Content -Path $logErr | ForEach-Object { Write-Host $_ } }
  Write-Host "--- podman build logs end ---"

  if ($proc.ExitCode -ne 0) { throw "podman build failed with exit code $($proc.ExitCode)" }
}

function Ensure-TemporalCLI() {
  $cmd = Get-Command temporal -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Path }
  Write-Host "Installing Temporal CLI locally (user scope)..."
  try {
    bash -lc "curl -sSf https://temporal.download/cli.sh | sh" | Out-Null
  } catch {
    throw "Failed to install Temporal CLI: $($_.Exception.Message)"
  }
  # Try common install locations without requiring PATH update
  $userHome = $env:HOME
  if (-not $userHome -or [string]::IsNullOrWhiteSpace($userHome)) { $userHome = [Environment]::GetFolderPath('UserProfile') }
  $candidates = @(
    (Join-Path $userHome ".temporalio/bin/temporal"),
    (Join-Path $userHome ".local/bin/temporal")
  )
  foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
  $cmd2 = Get-Command temporal -ErrorAction SilentlyContinue
  if ($cmd2) { return $cmd2.Path }
  throw "Temporal CLI not found on PATH after install"
}

function Start-TemporalHost([switch]$RunCheck, [int]$HealthCheckTimeoutSeconds, [switch]$SkipOpenUI) {
  $temporalExe = Ensure-TemporalCLI
  Write-Host "Starting Temporal dev on host..."
  $job = Start-Job -ScriptBlock { param($exe) & $exe server start-dev --ip 127.0.0.1 } -ArgumentList $temporalExe
  try {
    Wait-Port 127.0.0.1 7233
    Write-Host "Temporal UI: http://127.0.0.1:8233"
    Write-Host "Temporal Frontend (Temporal Dev): 127.0.0.1:7233"
    if ($RunCheck) {
      # Run same real-server check with timeout
      $env:TEMPORAL_ADDRESS = $env:TEMPORAL_ADDRESS -as [string]
      if (-not $env:TEMPORAL_ADDRESS) { $env:TEMPORAL_ADDRESS = '127.0.0.1:7233' }
      if (-not $env:TEMPORAL_NAMESPACE) { $env:TEMPORAL_NAMESPACE = 'default' }
      if (-not $env:CONVEX_HTTP_URL) { throw 'Set CONVEX_HTTP_URL (.convex.site) before running the check' }
      $script = 'uv run python -m job_scrape_application.workflows.temporal_real_server_check'
      $hc = Start-Job -ScriptBlock { param($cmd) pwsh -NoLogo -NoProfile -Command $cmd } -ArgumentList $script
      if (-not (Wait-Job $hc -Timeout $HealthCheckTimeoutSeconds)) {
        Stop-Job $hc -Force | Out-Null
        Receive-Job $hc -Keep | Out-String | Write-Output
        throw "Health check timed out after $HealthCheckTimeoutSeconds seconds"
      }
      $out = Receive-Job $hc -Keep | Out-String
      Write-Output $out
      Remove-Job $hc -Force -ErrorAction SilentlyContinue | Out-Null
    }
  } finally {
    # Stop the dev server to avoid long-running process
    try { Stop-Job $job -Force | Out-Null } catch {}
    try { Receive-Job $job -Keep | Out-String | Out-Null } catch {}
    Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
  }
}

function Start-TemporalViaPodman() {
  $ok = $false
  $existing = podman ps -a --format '{{.Names}}'
  if ($LASTEXITCODE -ne 0) { return $false }
  $has = $false
  foreach ($n in $existing) { if ($n -eq 'temporalite') { $has = $true; break } }
  if ($has) {
    $state = (podman inspect temporalite -f '{{.State.Status}}' 2>$null)
    if ($LASTEXITCODE -eq 0 -and $state -eq 'running') { $ok = $true }
    if (-not $ok) {
      $null = (podman start temporalite 2>&1)
      if ($LASTEXITCODE -ne 0) {
        $null = (podman rm -f temporalite 2>&1)
        $null = (podman run -d --replace --network $net --name temporalite -p 7233:7233 -p 8233:8233 temporal-dev:local 2>&1)
        if ($LASTEXITCODE -eq 0) { $ok = $true }
      } else { $ok = $true }
    }
  } else {
    $null = (podman run -d --replace --network $net --name temporalite -p 7233:7233 -p 8233:8233 temporal-dev:local 2>&1)
    if ($LASTEXITCODE -eq 0) { $ok = $true }
  }
  if ($ok) {
    Wait-Port 127.0.0.1 7233
    Write-Host "Temporal UI: http://127.0.0.1:8233"
    Write-Host "Temporal Frontend (Temporal Dev): 127.0.0.1:7233"
  }
  return $ok
}

Build-TemporalDevImage

# Try Podman first; if networking backend (netavark) is missing, fall back to host-run
$started = $false
try {
  $started = Start-TemporalViaPodman
} catch {
  $started = $false
}
if (-not $started) {
  Write-Warning "Podman start failed (likely missing netavark). Falling back to host-run."
  Start-TemporalHost -RunCheck:$RunCheck -HealthCheckTimeoutSeconds $HealthCheckTimeoutSeconds -SkipOpenUI:$SkipOpenUI
  # Host-run already performed optional health check and cleaned up; exit script here
  return
}

# Optionally open Temporal UI in default browser (skip on CI/headless)
$isHeadless = $false
if ($env:CI -in @('true','1') -or $env:GITHUB_ACTIONS -in @('true','1') -or $env:TF_BUILD -in @('true','1') -or $env:GITLAB_CI -in @('true','1')) { $isHeadless = $true }
if (-not $SkipOpenUI) {
  if (-not $isHeadless) {
    try {
      Wait-Port 127.0.0.1 8233 60 1
      Start-Process "http://127.0.0.1:8233" | Out-Null
    } catch {
      Write-Warning "Could not open Temporal UI automatically: $($_.Exception.Message)"
    }
  } else {
    Write-Host "Headless/CI environment detected; not opening browser."
  }
} else {
  Write-Host "SkipOpenUI set; not opening browser."
}

if ($RunCheck) {
  $env:TEMPORAL_ADDRESS = $env:TEMPORAL_ADDRESS -as [string]
  if (-not $env:TEMPORAL_ADDRESS) { $env:TEMPORAL_ADDRESS = '127.0.0.1:7233' }
  if (-not $env:TEMPORAL_NAMESPACE) { $env:TEMPORAL_NAMESPACE = 'default' }
  if (-not $env:CONVEX_HTTP_URL) { throw 'Set CONVEX_HTTP_URL (.convex.site) before running the check' }

  function Run-HealthCheck([int]$TimeoutSeconds) {
    $script = 'uv run python -m job_scrape_application.workflows.temporal_real_server_check'
    $job = Start-Job -ScriptBlock { param($cmd) pwsh -NoLogo -NoProfile -Command $cmd } -ArgumentList $script
    try {
      if (-not (Wait-Job $job -Timeout $TimeoutSeconds)) {
        Stop-Job $job -Force | Out-Null
        Receive-Job $job -Keep | Out-String | Write-Output
        throw "Health check timed out after $TimeoutSeconds seconds"
      }
      $out = Receive-Job $job -Keep | Out-String
      Write-Output $out
      $state = ($job | Select-Object -ExpandProperty State)
      if ($state -ne 'Completed') {
        throw "Health check job ended in state: $state"
      }
    } finally {
      Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
    }
  }

  Run-HealthCheck -TimeoutSeconds $HealthCheckTimeoutSeconds
}
