# Windows setup: installs deps and creates .env files.
# Run: powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Install it with:" -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js/npm not found. Install Node 22+ from https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

Push-Location "$root\backend"
uv sync
if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Pop-Location

Push-Location "$root\frontend"
npm install
if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Pop-Location

Push-Location "$root\RL"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Pop-Location

Write-Host "Setup done. Run: powershell -ExecutionPolicy Bypass -File .\dev.ps1" -ForegroundColor Green
Write-Host "Fill in RL/.env and backend/.env with the keys you have; both are gitignored." -ForegroundColor Yellow
