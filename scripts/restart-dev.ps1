# Останавливает процессы на8000 и 5173, затем поднимает API и Vite в двух окнах.
$ErrorActionPreference = 'SilentlyContinue'
foreach ($port in 8000, 5173) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 1

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$uvicorn = Join-Path $backend ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path $uvicorn)) {
    Write-Host "Нет $uvicorn — сначала: cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$cmdBack = "Set-Location '$backend'; `$env:PYTHONPATH='$backend'; & '$uvicorn' app.main:app --host 127.0.0.1 --port 8000"
$cmdFront = "Set-Location '$frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

Start-Process pwsh -ArgumentList "-NoExit", "-Command", $cmdBack
Start-Process pwsh -ArgumentList "-NoExit", "-Command", $cmdFront
Write-Host "Запущено. UI http://127.0.0.1:5173/ | API http://127.0.0.1:8000/docs"
