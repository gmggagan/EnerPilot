# One-command local start (Windows PowerShell): builds the UI if needed and serves
# everything from FastAPI at http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location "$root\backend"
python -m pip install -q -r requirements.txt
Pop-Location
if (-not (Test-Path "$root\frontend\dist\index.html")) {
    Push-Location "$root\frontend"
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
}
Push-Location "$root\backend"
Write-Host "ENERPILOT -> http://127.0.0.1:8000  (first start trains the model, ~10-30 s)"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
Pop-Location
