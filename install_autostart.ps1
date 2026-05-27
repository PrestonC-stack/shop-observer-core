# ================================================
# Install Callahan AI Autostart Tasks
# ================================================
#
# Run once as Administrator from:
#   C:\AI-RUNTIME\shop-observer-core
#
# This registers hidden Windows Task Scheduler tasks that start the local
# dashboard, webhook receiver, and Cloudflare tunnel when the user logs in.

$ErrorActionPreference = "Stop"

$RuntimeRoot = "C:\AI-RUNTIME\shop-observer-core"
$DashboardRoot = Join-Path $RuntimeRoot "dashboard"

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description not found: $Path"
    }
}

function New-RestartLoopCommand {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$RunCommand,
        [Parameter(Mandatory = $true)][int]$DelaySeconds
    )

    $escapedWorkingDirectory = $WorkingDirectory.Replace("'", "''")
    $escapedRunCommand = $RunCommand.Replace('"', '\"')

    return "Start-Sleep -Seconds $DelaySeconds; Set-Location '$escapedWorkingDirectory'; while (`$true) { Write-Output '[CallahanAI] starting: $escapedRunCommand'; & powershell -NoProfile -ExecutionPolicy Bypass -Command `"$escapedRunCommand`"; Write-Output '[CallahanAI] process exited; restarting in 60 seconds'; Start-Sleep -Seconds 60 }"
}

function Register-CallahanTask {
    param(
        [Parameter(Mandatory = $true)][string]$TaskName,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$RunCommand,
        [Parameter(Mandatory = $true)][int]$DelaySeconds
    )

    $loopCommand = New-RestartLoopCommand `
        -WorkingDirectory $WorkingDirectory `
        -RunCommand $RunCommand `
        -DelaySeconds $DelaySeconds

    $argument = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$loopCommand`""
    $action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument $argument `
        -WorkingDirectory $WorkingDirectory

    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $trigger.Delay = "PT${DelaySeconds}S"

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
        -Hidden `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable

    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Highest

    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Callahan AI local runtime service: $TaskName"

    Register-ScheduledTask `
        -TaskName $TaskName `
        -InputObject $task `
        -Force | Out-Null

    Write-Host "Registered $TaskName" -ForegroundColor Green
}

Write-Host "Installing Callahan AI autostart tasks..." -ForegroundColor Cyan

if (-not (Test-Administrator)) {
    Write-Host ""
    Write-Host "ERROR: This script must be run once as Administrator." -ForegroundColor Red
    Write-Host "Right-click PowerShell, choose Run as administrator, then run:" -ForegroundColor Yellow
    Write-Host "  cd C:\AI-RUNTIME\shop-observer-core"
    Write-Host "  .\install_autostart.ps1"
    exit 1
}

Assert-PathExists -Path $RuntimeRoot -Description "Runtime root"
Assert-PathExists -Path $DashboardRoot -Description "Dashboard directory"
Assert-PathExists -Path (Join-Path $DashboardRoot "app.py") -Description "Dashboard app"
Assert-PathExists -Path (Join-Path $RuntimeRoot "webhooks\autoflow_webhook_receiver.py") -Description "Webhook receiver"
Assert-PathExists -Path (Join-Path $RuntimeRoot "cloudflared.exe") -Description "Cloudflare tunnel binary"

Register-CallahanTask `
    -TaskName "CallahanAI-Board" `
    -WorkingDirectory $RuntimeRoot `
    -RunCommand "python dashboard\app.py" `
    -DelaySeconds 10

Register-CallahanTask `
    -TaskName "CallahanAI-Webhook" `
    -WorkingDirectory $RuntimeRoot `
    -RunCommand "python webhooks\autoflow_webhook_receiver.py" `
    -DelaySeconds 15

Register-CallahanTask `
    -TaskName "CallahanAI-Tunnel" `
    -WorkingDirectory $RuntimeRoot `
    -RunCommand '.\cloudflared.exe tunnel --origincert "C:\Users\CallahanAi\.cloudflared\cert.pem" --config "C:\Users\CallahanAi\.cloudflared\config.yml" run shop-tasks' `
    -DelaySeconds 25

Write-Host ""
Write-Host "Callahan AI autostart is installed." -ForegroundColor Green
Write-Host ""
Write-Host "Installed tasks:"
Write-Host "  - CallahanAI-Board    starts 10 seconds after login"
Write-Host "  - CallahanAI-Webhook  starts 15 seconds after login"
Write-Host "  - CallahanAI-Tunnel   starts 25 seconds after login"
Write-Host ""
Write-Host "Instructions:" -ForegroundColor Cyan
Write-Host "  Run this script once as Administrator from C:\AI-RUNTIME\shop-observer-core."
Write-Host "  After that, you should not need to touch it again."
Write-Host "  On each login, Windows will silently start the board, webhook receiver, and tunnel."
