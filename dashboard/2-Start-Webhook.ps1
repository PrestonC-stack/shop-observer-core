# 2 - Start AutoFlow Webhook
$host.UI.RawUI.WindowTitle = "2 - Webhook Receiver"
Write-Host "🚀 Starting AutoFlow Webhook..." -ForegroundColor Green
cd C:\AI-RUNTIME\shop-observer-core\webhooks
python autoflow_webhook_receiver.py
