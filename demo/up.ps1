# Boot the full EnergyOps stack and seed demo data (PowerShell).
# Usage:  pwsh -File demo/up.ps1
$ErrorActionPreference = "Stop"

$root = Resolve-Path "$PSScriptRoot/.."
Set-Location $root

if (-not (Test-Path ".env")) {
    Write-Host "[demo/up] copying .env.example -> .env"
    Copy-Item ".env.example" ".env"
}

Write-Host "[demo/up] building images and starting services"
docker compose up --build -d

Write-Host "[demo/up] waiting for backend /health"
for ($i = 1; $i -le 60; $i++) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/health" -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            Write-Host "[demo/up] backend up"
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Host "[demo/up] running seed (idempotent)"
docker compose exec -T backend python -m app.seed

Write-Host ""
Write-Host "[demo/up] ready"
Write-Host "  frontend:  http://localhost:3000"
Write-Host "  api docs:  http://localhost:8000/docs"
Write-Host "  health:    http://localhost:8000/health"
