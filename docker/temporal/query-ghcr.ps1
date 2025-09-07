$ErrorActionPreference = 'Stop'

function Get-GhcrPat {
  $root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
  # Try env first
  if ($env:GHCR_PAT) { return $env:GHCR_PAT }

  # Fallback to dotenvx get (decrypt from .env + .env.keys)
  try {
    Push-Location $root
    $code = 'const dx=require("@dotenvx/dotenvx");const v=dx.get("GHCR_PAT");if(v){process.stdout.write(v);}';
    $out = & node -e $code
    Pop-Location
    if ($out) { return $out.Trim() }
  } catch {
    Write-Verbose "dotenvx get GHCR_PAT failed: $($_.Exception.Message)"
  }
  return $null
}

$pat = Get-GhcrPat
if (-not $pat) { throw 'GHCR_PAT not found (env or decrypted via dotenvx)' }
$headers = @{ Authorization = ("Bearer " + $pat); 'User-Agent'='srajob2-ci' }

$pkgs = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/orgs/temporalio/packages?package_type=container" -Method Get
$names = $pkgs | Select-Object -ExpandProperty name
Write-Host ("Packages: " + ($names -join ', '))

function Get-Tags([string]$pkg) {
  $resp = Invoke-RestMethod -Headers $headers -Uri ("https://api.github.com/orgs/temporalio/packages/container/$pkg/versions?per_page=100") -Method Get
  $tags = @()
  foreach($v in $resp){ $tags += $v.metadata.container.tags }
  $tags | Where-Object { $_ } | Select-Object -Unique
}

try {
  $tTags = Get-Tags -pkg 'temporalite'
  Write-Host ("temporalite tags (first 20): " + (($tTags | Select-Object -First 20) -join ', '))
} catch {
  Write-Host "Failed to fetch temporalite tags: $($_.Exception.Message)"
}

try {
  $uiTags = Get-Tags -pkg 'ui'
  Write-Host ("ui tags (first 20): " + (($uiTags | Select-Object -First 20) -join ', '))
} catch {
  Write-Host "Failed to fetch ui tags: $($_.Exception.Message)"
}
