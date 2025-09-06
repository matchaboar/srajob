$ErrorActionPreference = 'Stop'

function Ensure-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

Ensure-Command podman

foreach($name in @('temporal-ui','temporalite')){
  try { podman rm -f $name | Out-Null } catch {}
}

try { podman network rm -f tempnet | Out-Null } catch {}

Write-Host 'Stopped Temporalite stack (Podman)'
