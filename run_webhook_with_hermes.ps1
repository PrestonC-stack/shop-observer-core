# ================================================
# Callahan AI - Webhook + Hermes Launcher
# ================================================

$host.UI.RawUI.WindowTitle = "Callahan AI - AutoFlow Webhook + Hermes"

Write-Host "🚀 Starting Callahan AI Webhook Receiver with Hermes Memory..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Yellow

cd C:\AI-RUNTIME\shop-observer-core\webhooks

try {
    python autoflow_webhook_receiver.py
}
catch {
    Write-Host "❌ Error occurred: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host "Press Enter to close..."
}