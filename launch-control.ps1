$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$LatestSummaryPath = Join-Path $RepoRoot "outputs\latest_summary.txt"
$HistoryFolderPath = Join-Path $RepoRoot "outputs\history"
$ObserverPath = Join-Path $RepoRoot "observer.py"

function Show-Menu {
    Write-Host ""
    Write-Host "HERMES LAUNCH CONTROL"
    Write-Host "1. Pull latest from GitHub"
    Write-Host "2. Run Shop Observer"
    Write-Host "3. View latest summary"
    Write-Host "4. View Questions for Preston"
    Write-Host "5. Open history folder"
    Write-Host "6. Exit"
    Write-Host ""
}

function Invoke-GitPull {
    Push-Location $RepoRoot
    try {
        git pull
    }
    finally {
        Pop-Location
    }
}

function Invoke-Observer {
    Push-Location $RepoRoot
    try {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py $ObserverPath
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python $ObserverPath
        }
        else {
            Write-Host "Python launcher not found. Install py or python first."
        }
    }
    finally {
        Pop-Location
    }
}

function Open-LatestSummary {
    if (Test-Path $LatestSummaryPath) {
        Start-Process $LatestSummaryPath
    }
    else {
        Write-Host "Latest summary not found: $LatestSummaryPath"
    }
}

function Show-QuestionsForPreston {
    if (-not (Test-Path $LatestSummaryPath)) {
        Write-Host "Latest summary not found: $LatestSummaryPath"
        return
    }

    $lines = Get-Content $LatestSummaryPath
    $startIndex = [Array]::IndexOf($lines, "QUESTIONS FOR PRESTON")

    if ($startIndex -lt 0) {
        Write-Host "QUESTIONS FOR PRESTON section not found."
        return
    }

    Write-Host ""
    Write-Host "QUESTIONS FOR PRESTON"

    for ($i = $startIndex + 1; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line -eq "FULL ITEM LIST") {
            break
        }

        if ($line.Trim().Length -eq 0) {
            continue
        }

        Write-Host $line
    }
}

function Open-HistoryFolder {
    if (Test-Path $HistoryFolderPath) {
        Start-Process $HistoryFolderPath
    }
    else {
        Write-Host "History folder not found: $HistoryFolderPath"
    }
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Select an option"

    switch ($choice) {
        "1" { Invoke-GitPull }
        "2" { Invoke-Observer }
        "3" { Open-LatestSummary }
        "4" { Show-QuestionsForPreston }
        "5" { Open-HistoryFolder }
        "6" { break }
        default { Write-Host "Invalid selection. Choose 1-6." }
    }
}
