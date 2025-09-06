param(
  [string]$Path = ".env"
)

if (Test-Path $Path) {
  Write-Host "$Path already exists. Nothing to do."
  exit 0
}
if (-not (Test-Path ".env.example")) {
  Write-Error ".env.example not found next to $Path"
  exit 1
}
Copy-Item ".env.example" $Path -Force
Write-Host "Created $Path from .env.example. Fill in your secrets."

