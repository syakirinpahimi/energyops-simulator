# Wipe DB, re-seed, restart simulator (PowerShell).
# Usage:  pwsh -File demo/reset.ps1
$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot/..")

Write-Host "[demo/reset] resetting database"
docker compose exec -T backend python -m scripts.reset_db --seed

Write-Host "[demo/reset] restarting simulator"
docker compose restart simulator

Write-Host "[demo/reset] done"
