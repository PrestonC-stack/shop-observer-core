# 4 - Start Everything
Write-Host "🚀 Starting Full Callahan AI System..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -File C:\AI-RUNTIME\shop-observer-core\dashboard\3-Start-Ollama.ps1"
Start-Sleep -Seconds 8
Start-Process powershell -ArgumentList "-NoExit -File C:\AI-RUNTIME\shop-observer-core\dashboard\1-Start-Dashboard.ps1"
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList "-NoExit -File C:\AI-RUNTIME\shop-observer-core\dashboard\2-Start-Webhook.ps1"
Write-Host "✅ All services started" -ForegroundColor Green
