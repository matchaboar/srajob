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

$repoRoot = (Resolve-Path ".").Path
Import-Dotenvx $repoRoot

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
