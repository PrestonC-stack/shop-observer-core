# ================================================
# Start Callahan AI Services
# ================================================
#
# Manual master launcher.
# Opens visible, labeled PowerShell windows for each local service.

$ErrorActionPreference = "Stop"

$RuntimeRoot = "C:\AI-RUNTIME\shop-observer-core"
$TunnelCommand = '.\cloudflared.exe tunnel --origincert "C:\Users\CallahanAi\.cloudflared\cert.pem" --config "C:\Users\CallahanAi\.cloudflared\config.yml" run shop-tasks'

function New-ServiceLoopCommand {
    param(
        [Parameter(Mandatory = $true)][string]$WindowTitle,
        [Parameter(Mandatory = $true)][string]$BackgroundColor,
        [Parameter(Mandatory = $true)][string]$ForegroundColor,
        [Parameter(Mandatory = $true)][string]$ServiceName,
        [Parameter(Mandatory = $true)][string]$PortLabel,
        [Parameter(Mandatory = $true)][string]$RunCommand
    )

    $escapedRoot = $RuntimeRoot.Replace("'", "''")
    $escapedWindowTitle = $WindowTitle.Replace('"', '\"')
    $escapedServiceName = $ServiceName.Replace('"', '\"')
    $escapedPortLabel = $PortLabel.Replace('"', '\"')

    return @"
`$Host.UI.RawUI.WindowTitle = "$escapedWindowTitle"
`$Host.UI.RawUI.BackgroundColor = "$BackgroundColor"
`$Host.UI.RawUI.ForegroundColor = "$ForegroundColor"
`$RunCommand = @'
$RunCommand
'@
Clear-Host
Set-Location '$escapedRoot'
while (`$true) {
    Write-Host "================================" -ForegroundColor White
    Write-Host "$escapedServiceName — Starting..." -ForegroundColor White
    Write-Host "Port: $escapedPortLabel" -ForegroundColor White
    Write-Host "Started: `$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor White
    Write-Host "================================" -ForegroundColor White
    Write-Host ""
    Invoke-Expression `$RunCommand
    Write-Host ""
    Write-Host "RESTARTING in 5 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
"@
}

function Start-CallahanServiceWindow {
    param(
        [Parameter(Mandatory = $true)][string]$WindowTitle,
        [Parameter(Mandatory = $true)][string]$BackgroundColor,
        [Parameter(Mandatory = $true)][string]$ForegroundColor,
        [Parameter(Mandatory = $true)][string]$ServiceName,
        [Parameter(Mandatory = $true)][string]$PortLabel,
        [Parameter(Mandatory = $true)][string]$RunCommand
    )

    $loopCommand = New-ServiceLoopCommand `
        -WindowTitle $WindowTitle `
        -BackgroundColor $BackgroundColor `
        -ForegroundColor $ForegroundColor `
        -ServiceName $ServiceName `
        -PortLabel $PortLabel `
        -RunCommand $RunCommand

    Start-Process powershell `
        -WorkingDirectory $RuntimeRoot `
        -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $loopCommand
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

Start-CallahanServiceWindow `
    -WindowTitle "CALLAHAN BOARD — Port 8080" `
    -BackgroundColor "DarkBlue" `
    -ForegroundColor "White" `
    -ServiceName "CALLAHAN BOARD" `
    -PortLabel "8080" `
    -RunCommand "python dashboard\advisor_task_viewer.py"

Start-Sleep -Seconds 4

Start-CallahanServiceWindow `
    -WindowTitle "CALLAHAN WEBHOOK — Port 5055" `
    -BackgroundColor "DarkGreen" `
    -ForegroundColor "White" `
    -ServiceName "CALLAHAN WEBHOOK" `
    -PortLabel "5055" `
    -RunCommand "python webhooks\autoflow_webhook_receiver.py"

Start-Sleep -Seconds 3

Start-CallahanServiceWindow `
    -WindowTitle "CALLAHAN TUNNEL — Cloudflare" `
    -BackgroundColor "DarkMagenta" `
    -ForegroundColor "White" `
    -ServiceName "CALLAHAN TUNNEL" `
    -PortLabel "Cloudflare" `
    -RunCommand $TunnelCommand

Start-Sleep -Seconds 3

Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show(
    "3 windows are now open and labeled:`n`n" +
    "🔵 BOARD (blue) — http://127.0.0.1:8080`n" +
    "🟢 WEBHOOK (green) — Port 5055`n" +
    "🟣 TUNNEL (purple) — Cloudflare active`n`n" +
    "Board: https://tasks.callahanautoaz.net`n" +
    "Drew: https://tasks.callahanautoaz.net/drew`n" +
    "Mitch: https://tasks.callahanautoaz.net/mitch`n`n" +
    "Each window auto-restarts if it crashes.`n" +
    "You can minimize them but do not close them.",
    "Callahan AI — All Systems Running",
    'OK',
    'Information'
) | Out-Null
