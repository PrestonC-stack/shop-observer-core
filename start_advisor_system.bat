@echo off
cd /d C:\AI-RUNTIME\shop-observer-core

start "Advisor Viewer" powershell -NoExit -Command "cd C:\AI-RUNTIME\shop-observer-core; py .\dashboard\advisor_task_viewer.py"

timeout /t 5

start "Cloudflare Tunnel" powershell -NoExit -Command "cd C:\AI-RUNTIME\shop-observer-core; .\cloudflared.exe tunnel run shop-tasks"