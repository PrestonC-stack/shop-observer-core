# ================================================
# Start Callahan AI Services
# ================================================
#
# Manual desktop launcher.
# Task Scheduler handles auto-start on reboot.

$ErrorActionPreference = "Stop"

$RuntimeRoot = "C:\AI-RUNTIME\shop-observer-core"

function Start-CallahanService {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command
    )

    Write-Host "Starting $Name..." -ForegroundColor Green
    Start-Process powershell `
        -WindowStyle Minimized `
        -WorkingDirectory $RuntimeRoot `
        -ArgumentList "-NoExit -ExecutionPolicy Bypass -Command", "cd '$RuntimeRoot'; $Command"
}

if (-not (Test-Path -LiteralPath $RuntimeRoot)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "Runtime folder not found:`n`n$RuntimeRoot",
        "Callahan AI — Start Failed",
        'OK',
        'Error'
    ) | Out-Null
    exit 1
}

Set-Location $RuntimeRoot

Start-CallahanService `
    -Name "advisor board" `
    -Command "python dashboard\advisor_task_viewer.py"

Start-Sleep -Seconds 4

Start-CallahanService `
    -Name "AutoFlow webhook receiver" `
    -Command "python webhooks\autoflow_webhook_receiver.py"

Start-Sleep -Seconds 3

Start-CallahanService `
    -Name "Cloudflare tunnel" `
    -Command '.\cloudflared.exe tunnel --origincert "C:\Users\CallahanAi\.cloudflared\cert.pem" --config "C:\Users\CallahanAi\.cloudflared\config.yml" run shop-tasks'

Start-Sleep -Seconds 8

Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show(
    "All services are running.`n`n" +
    "Board: https://tasks.callahanautoaz.net`n" +
    "Drew: https://tasks.callahanautoaz.net/drew`n" +
    "Mitch: https://tasks.callahanautoaz.net/mitch`n`n" +
    "Task Scheduler handles auto-start on reboot.`n" +
    "This launcher is for manual restarts only.",
    "Callahan AI — Ready",
    'OK',
    'Information'
) | Out-Null
