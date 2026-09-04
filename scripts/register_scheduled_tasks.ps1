param(
    [int]$IntervalMinutes = 15,
    [string]$TaskName = "Callahan AI Shop Observer Scheduled Rebuild",
    [int]$HermesIntervalMinutes = 35,
    [string]$HermesTaskName = "Callahan-Hermes-Scheduler"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogsDir = Join-Path $RepoRoot "logs"
$LogFile = Join-Path $LogsDir "scheduled_rebuild.log"
$HermesLogFile = Join-Path $LogsDir "hermes_scheduler.log"
$PythonExe = (Get-Command py -ErrorAction SilentlyContinue).Source

if (-not $PythonExe) {
    throw "Python launcher 'py' was not found on PATH."
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$runnerScript = @"
`$ErrorActionPreference = "Stop"
`$RepoRoot = "$RepoRoot"
`$LogFile = "$LogFile"
`$PythonExe = "$PythonExe"

function Write-RebuildLog {
    param([string]`$Message)
    `$timestamp = (Get-Date).ToString("o")
    Add-Content -Path `$LogFile -Value "`$timestamp `$Message"
}

function Run-Step {
    param(
        [string]`$Label,
        [string]`$ScriptPath
    )

    Write-RebuildLog "START `$Label"
    & `$PythonExe `$ScriptPath *>> `$LogFile
    if (`$LASTEXITCODE -ne 0) {
        Write-RebuildLog "FAILED `$Label exit_code=`$LASTEXITCODE"
        exit `$LASTEXITCODE
    }
    Write-RebuildLog "DONE `$Label"
}

Set-Location `$RepoRoot
Write-RebuildLog "SCHEDULED REBUILD START"
Run-Step "build_active_ros_state" (Join-Path `$RepoRoot "scripts\build_active_ros_state.py")
Run-Step "build_shop_state" (Join-Path `$RepoRoot "scripts\build_shop_state.py")
Run-Step "build_board_state" (Join-Path `$RepoRoot "scripts\build_board_state.py")
Write-RebuildLog "SCHEDULED REBUILD COMPLETE"
"@

$encodedRunner = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($runnerScript))
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encodedRunner"

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$description = "Runs Shop Observer rebuild scripts every $IntervalMinutes minutes: active_ros -> shop_state -> board_state. Logs to $LogFile."

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $description `
    -Force | Out-Null

$hermesRunnerScript = @"
`$ErrorActionPreference = "Stop"
`$RepoRoot = "$RepoRoot"
`$LogFile = "$HermesLogFile"
`$PythonExe = "$PythonExe"

function Write-HermesLog {
    param([string]`$Message)
    `$timestamp = (Get-Date).ToString("o")
    Add-Content -Path `$LogFile -Value "`$timestamp `$Message"
}

Set-Location `$RepoRoot
Write-HermesLog "HERMES SCHEDULER TASK START"
& `$PythonExe (Join-Path `$RepoRoot "scripts\hermes_scheduler.py") *>> `$LogFile
if (`$LASTEXITCODE -ne 0) {
    Write-HermesLog "HERMES SCHEDULER TASK FAILED exit_code=`$LASTEXITCODE"
    exit `$LASTEXITCODE
}
Write-HermesLog "HERMES SCHEDULER TASK COMPLETE"
"@

$encodedHermesRunner = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($hermesRunnerScript))
$hermesAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encodedHermesRunner"

$hermesTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $HermesIntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$hermesDescription = "Runs Hermes background recommendations every $HermesIntervalMinutes minutes. Logs to $HermesLogFile."

Register-ScheduledTask `
    -TaskName $HermesTaskName `
    -Action $hermesAction `
    -Trigger $hermesTrigger `
    -Settings $settings `
    -Description $hermesDescription `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Interval minutes: $IntervalMinutes"
Write-Host "Registered scheduled task: $HermesTaskName"
Write-Host "Hermes interval minutes: $HermesIntervalMinutes"
Write-Host "Repo root: $RepoRoot"
Write-Host "Log file: $LogFile"
Write-Host "Hermes log file: $HermesLogFile"
Write-Host "Next step: open Task Scheduler and confirm the task appears under Task Scheduler Library."
