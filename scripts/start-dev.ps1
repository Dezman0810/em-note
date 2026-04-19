# Два отдельных окна: API и Vite (для ручного запуска).
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$uvicorn = Join-Path $backend ".venv\Scripts\uvicorn.exe"

$cmdBack = "Set-Location '$backend'; `$env:PYTHONPATH='$backend'; & '$uvicorn' app.main:app --host 127.0.0.1 --port 8000"
$cmdFront = "Set-Location '$frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

Start-Process pwsh -ArgumentList "-NoExit", "-Command", $cmdBack
Start-Process pwsh -ArgumentList "-NoExit", "-Command", $cmdFront
Write-Host "API http://127.0.0.1:8000/docs | UI http://127.0.0.1:5173/"
