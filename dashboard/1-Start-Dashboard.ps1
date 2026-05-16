# 1 - Start Advisor Command Board
$host.UI.RawUI.WindowTitle = "1 - Advisor Command Board"

Write-Host "Starting Country Club Advisor Command Board..." -ForegroundColor Green

Set-Location "C:\AI-RUNTIME\shop-observer-core\dashboard"

# Restart loop for resilience.
# If the dashboard crashes or exits, it will automatically restart after 8 seconds.
while ($true) {
    Write-Host "Launching dashboard on http://127.0.0.1:5000" -ForegroundColor Cyan
    
    python advisor_task_viewer.py
    
    $exitCode = $LASTEXITCODE
    Write-Host "Dashboard exited with code $exitCode. Restarting in 8 seconds..." -ForegroundColor Yellow
    
    Start-Sleep -Seconds 8
}