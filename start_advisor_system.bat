@echo off
cd /d C:\AI-RUNTIME\shop-observer-core

echo ========================================
echo STARTING SHOP OBSERVER SYSTEM
echo ========================================

echo Rebuilding tasks...
py .\scripts\build_advisor_game_plan.py

timeout /t 2

echo Starting Webhook Receiver...
start "Webhook Server" powershell -NoExit -Command "cd C:\AI-RUNTIME\shop-observer-core; py .\webhooks\autoflow_webhook_receiver.py"

timeout /t 3

echo Starting Advisor Viewer...
start "Advisor Viewer" powershell -NoExit -Command "cd C:\AI-RUNTIME\shop-observer-core; py .\dashboard\advisor_task_viewer.py"

timeout /t 5

echo Starting Cloudflare Tunnel...
start "Cloudflare Tunnel" powershell -NoExit -Command "cd C:\AI-RUNTIME\shop-observer-core; .\cloudflared.exe tunnel run shop-tasks"

echo ========================================
echo SYSTEM START COMPLETE
echo ========================================