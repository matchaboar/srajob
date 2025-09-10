param(
  [Parameter(Mandatory=$true)]
  [string]$UserId,
  [int]$Limit = 10,
  [switch]$All, # include already queued
  [int]$TimeoutSeconds = 60
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

function Ensure-ConvexHttpUrl {
  if ($env:CONVEX_HTTP_URL -and ($env:CONVEX_HTTP_URL -notmatch '<your-deployment>')) { return }
  $repoRoot = (Resolve-Path ".").Path
  $appEnvLocal = Join-Path (Join-Path $repoRoot 'job_board_application') '.env.local'
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
  throw 'CONVEX_HTTP_URL not set and VITE_CONVEX_URL not found; set CONVEX_HTTP_URL explicitly.'
}

# Load envs
$repoRoot = (Resolve-Path ".").Path
Import-Dotenvx $repoRoot
Ensure-ConvexHttpUrl

$base = $env:CONVEX_HTTP_URL.TrimEnd('/')
$url = "$base/api/form-fill/queue-user-jobs"
$body = @{ userId = $UserId; limit = $Limit; onlyUnqueued = (-not $All) } | ConvertTo-Json -Compress

Write-Host "POST $url"
Write-Host "Body: $body"

$job = Start-Job -ScriptBlock {
  param($u,$b)
  try {
    $resp = Invoke-WebRequest -Uri $u -Method POST -Body $b -ContentType 'application/json' -TimeoutSec 30
    return $resp.Content
  } catch {
    throw $_
  }
} -ArgumentList $url,$body

try {
  if (-not (Wait-Job $job -Timeout $TimeoutSeconds)) {
    Stop-Job $job -Force | Out-Null
    throw "Request timed out after $TimeoutSeconds seconds"
  }
  $out = Receive-Job $job -Keep | Out-String
  Write-Output $out
} finally {
  Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
}

