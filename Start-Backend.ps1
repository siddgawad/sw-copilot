# Start-Backend.ps1 — run from sw-copilot root in any PowerShell window
# Kills anything on 8001 first, then starts the Gemini-powered backend.

$p = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue |
     Select-Object -ExpandProperty OwningProcess -First 1
if ($p) { Stop-Process -Id $p -Force; Start-Sleep -Seconds 1; Write-Host "Killed old process on 8001" }

Set-Location "$PSScriptRoot\agent-backend"
Write-Host "Starting SW Copilot backend on http://127.0.0.1:8001 ..."
& ".\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8001
