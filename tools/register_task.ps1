param(
    [string]$TaskName = "DailyPaperDigest",
    [string]$RunAt = "08:47",
    [string]$ProjectDir = (Get-Location).Path,
    [string]$PythonExe = "python",
    [switch]$UseExe
)

$ErrorActionPreference = "Stop"

if ($UseExe) {
    $exePath = Join-Path $ProjectDir "dist\PaperDigest.exe"
    if (-not (Test-Path $exePath)) {
        throw "Executable not found: $exePath"
    }
    $action = New-ScheduledTaskAction -Execute $exePath -Argument "--run-once" -WorkingDirectory $ProjectDir
} else {
    $scriptPath = Join-Path $ProjectDir "app\paper_digest_app.py"
    if (-not (Test-Path $scriptPath)) {
        throw "Script not found: $scriptPath"
    }
    $args = "`"$scriptPath`" --run-once"
    $action = New-ScheduledTaskAction -Execute $PythonExe -Argument $args -WorkingDirectory $ProjectDir
}

$trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$description = "Send daily medical-AI paper digest email."

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Description $description `
    -Force | Out-Null

Write-Host "Task registered: $TaskName (daily at $RunAt)"
