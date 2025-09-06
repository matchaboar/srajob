$ErrorActionPreference = 'Stop'

function Load-Pat {
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
  $envPath = Join-Path $root '.env'
  if (Test-Path $envPath) {
    $line = Get-Content $envPath | Where-Object { $_ -match '^[ \t]*GHCR_PAT\s*=\s*' } | Select-Object -Last 1
    if ($line) {
      $pat = ($line -split '=',2)[1].Trim()
      if ($pat.StartsWith('"') -and $pat.EndsWith('"')) { $pat = $pat.Substring(1,$pat.Length-2) }
      return $pat
    }
  }
  return $env:GHCR_PAT
}

$pat = Load-Pat
if (-not $pat) { throw 'GHCR_PAT not found (env or .env)' }
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
