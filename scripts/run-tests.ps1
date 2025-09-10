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

function Ensure-ConvexHttpUrl {
  # If already set and not a placeholder, keep it
  if ($env:CONVEX_HTTP_URL -and ($env:CONVEX_HTTP_URL -notmatch '<your-deployment>')) { return }

  $appDir = Join-Path $repoRoot 'job_board_application'
  $appEnvLocal = Join-Path $appDir '.env.local'

  function _Extract-And-Set($path) {
    if (-not (Test-Path $path)) { return $false }
    $lines = Get-Content -Path $path
    # Prefer VITE_CONVEX_URL if present
    $vite = ($lines | Where-Object { $_ -match '^[ ]*VITE_CONVEX_URL[ ]*=\s*(.+)$' } | Select-Object -First 1)
    if ($vite) {
      $val = ($vite -replace '^[ ]*VITE_CONVEX_URL[ ]*=\s*', '').Trim()
      if ($val.EndsWith('.convex.cloud')) { $val = $val -replace '\\.convex\\.cloud$', '.convex.site' }
      $env:CONVEX_HTTP_URL = $val
      return $true
    }
    # Fallback to CONVEX_DEPLOYMENT slug
    $dep = ($lines | Where-Object { $_ -match '^[ ]*CONVEX_DEPLOYMENT[ ]*=\s*dev:([\w-]+)' } | Select-Object -First 1)
    if ($dep) {
      $m = [regex]::Match($dep, 'dev:([\w-]+)')
      if ($m.Success) {
        $slug = $m.Groups[1].Value
        $env:CONVEX_HTTP_URL = "https://$slug.convex.site"
        return $true
      }
    }
    return $false
  }

  if (_Extract-And-Set $appEnvLocal) { return }
  # Generate .env.local if missing
  try {
    Push-Location $appDir
    & npx --yes convex dev --once --typecheck disable --tail-logs disable | Out-Null
  } catch {}
  finally { Pop-Location }
  _Extract-And-Set $appEnvLocal | Out-Null
}

switch ($Task) {
  'temporal:start' {
    Ensure-ConvexHttpUrl
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
    Ensure-ConvexHttpUrl
    if (-not $env:CONVEX_HTTP_URL) { throw 'Set CONVEX_HTTP_URL in .env' }
    Run-WithTimeout 'uv run python -m job_scrape_application.workflows.temporal_health_check' $TimeoutSeconds
    break
  }
  'hc:real' {
    Ensure-ConvexHttpUrl
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
