# Windows dev: backend opens in a new window, frontend runs here.
# Run: powershell -ExecutionPolicy Bypass -File .\dev.ps1
$root = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; uv run fastapi dev app/main.py"

Set-Location "$root\frontend"
npm run dev
