param(
  [Parameter(Mandatory=$true, Position=0)]
  [ValidateSet('temporal:start','temporal:stop','hc:ephemeral','hc:real','hc:manual')]
  [string]$Task,
  [switch]$RunCheck,
  [int]$TimeoutSeconds = 300,
  [switch]$VerboseBuild,
  [switch]$SkipOpenUI
)

$ErrorActionPreference = 'Stop'

function Load-DotEnv($path) {
  if (-not (Test-Path $path)) { return }
  try {
    Get-Content -Path $path | ForEach-Object {
      if ($_ -match '^[ \t]*#') { return }
      if ($_ -notmatch '^[ \t]*([^=\s]+)[ \t]*=[ \t]*(.*)$') { return }
      $key = $Matches[1]; $val = $Matches[2]
      if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length-2) }
      Set-Item -Path "Env:$key" -Value $val
    }
  } catch { Write-Verbose "Failed to parse .env: $($_.Exception.Message)" }
}

$repoRoot = (Resolve-Path ".").Path
Load-DotEnv (Join-Path $repoRoot '.env')

function Wait-Port($hostname, $port, $retries=60, $delaySeconds=1) {
  for($i=0;$i -lt $retries;$i++){ try { if((Test-NetConnection -ComputerName $hostname -Port $port -WarningAction SilentlyContinue).TcpTestSucceeded){ return } } catch {}; Start-Sleep -Seconds $delaySeconds }
  throw ("Timeout waiting for {0}:{1}" -f $hostname, $port)
}

function Run-WithTimeout([string]$Command, [int]$Seconds) {
  $job = Start-Job -ScriptBlock { param($cmd) pwsh -NoLogo -NoProfile -Command $cmd } -ArgumentList $Command
  try {
    if (-not (Wait-Job $job -Timeout $Seconds)) {
      Stop-Job $job -Force | Out-Null
      Receive-Job $job -Keep | Out-String | Write-Host
      throw "Command timed out after $Seconds seconds: $Command"
    }
    $out = Receive-Job $job -Keep | Out-String
    Write-Host $out
  } finally {
    Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
  }
}

switch ($Task) {
  'temporal:start' {
    $args = @()
    if ($RunCheck) { $args += '-RunCheck' }
    if ($VerboseBuild) { $args += '-VerboseBuild' }
    if ($SkipOpenUI) { $args += '-SkipOpenUI' }
    $args += @('-HealthCheckTimeoutSeconds', [string]$TimeoutSeconds, '-BuildTimeoutSeconds', '600')
    & pwsh -NoLogo -NoProfile -File (Join-Path $repoRoot 'docker/temporal/start-podman.ps1') @args
    break
  }
  'temporal:stop' {
    & pwsh -NoLogo -NoProfile -File (Join-Path $repoRoot 'docker/temporal/stop-podman.ps1')
    break
  }
  'hc:ephemeral' {
    if (-not $env:CONVEX_HTTP_URL) { throw 'Set CONVEX_HTTP_URL in .env' }
    Run-WithTimeout 'uv run python -m job_scrape_application.workflows.temporal_health_check' $TimeoutSeconds
    break
  }
  'hc:real' {
    if (-not $env:TEMPORAL_ADDRESS) { $env:TEMPORAL_ADDRESS = '127.0.0.1:7233' }
    if (-not $env:TEMPORAL_NAMESPACE) { $env:TEMPORAL_NAMESPACE = 'default' }
    if (-not $env:CONVEX_HTTP_URL) { throw 'Set CONVEX_HTTP_URL in .env' }
    # Best effort wait for local dev
    try { Wait-Port '127.0.0.1' 7233 30 1 } catch {}
    Run-WithTimeout 'uv run python -m job_scrape_application.workflows.temporal_real_server_check' $TimeoutSeconds
    break
  }
  'hc:manual' {
    Run-WithTimeout 'uv run python -m job_scrape_application.workflows.manual_test' $TimeoutSeconds
    break
  }
}
