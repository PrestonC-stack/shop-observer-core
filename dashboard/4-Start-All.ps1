# ================================================
# 4 - Start All Callahan AI Services (Desktop Friendly)
# ================================================

$host.UI.RawUI.WindowTitle = "Callahan AI System Launcher"

Write-Host "🚀 Starting Full Callahan AI System..." -ForegroundColor Cyan

# Start Dashboard FIRST (most important for remote access)
Write-Host "Starting Dashboard..." -ForegroundColor Green
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -File C:\AI-RUNTIME\shop-observer-core\dashboard\1-Start-Dashboard.ps1"
Start-Sleep -Seconds 4

# Start Webhook
Write-Host "Starting AutoFlow Webhook Receiver..." -ForegroundColor Green
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -File C:\AI-RUNTIME\shop-observer-core\dashboard\2-Start-Webhook.ps1"
Start-Sleep -Seconds 2

# Start Ollama
Write-Host "Starting Ollama (Hermes)..." -ForegroundColor Green
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -Command", "cd 'C:\AI-RUNTIME\shop-observer-core\dashboard'; ollama run qwen2.5-coder:7b"
Start-Sleep -Seconds 5

Write-Host "✅ All services started successfully!" -ForegroundColor Green

# Show desktop popup
Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show(
    "✅ Callahan AI System is now running!`n`n" +
    "• Dashboard: http://127.0.0.1:5000`n" +
    "• Tunnel: https://countryclub-advisors.callahanautoaz.net`n`n" +
    "All windows are minimized. You can close this window.", 
    "Callahan AI System - Ready", 
    'OK', 
    'Information'
)