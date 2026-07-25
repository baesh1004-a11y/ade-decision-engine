param(
    [string]$ProjectDir = "C:\Project\ADE\ade-decision-engine",
    [string]$RunnerDir = "C:\Project\ADE\ade-decision-engine\actions-runner"
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[ADE setup] $Message"
}

if (-not (Test-Path $ProjectDir)) {
    throw "Project directory not found: $ProjectDir"
}

$runAdePath = Join-Path $ProjectDir "run_ade.py"
if (-not (Test-Path $runAdePath)) {
    throw "run_ade.py not found in: $ProjectDir"
}

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    throw "Python launcher 'py.exe' was not found."
}

Write-Step "Creating ADE startup task..."
$adeAction = New-ScheduledTaskAction -Execute $pythonLauncher.Source -Argument "`"$runAdePath`"" -WorkingDirectory $ProjectDir
$adeTrigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$adePrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
$adeSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "ADE Dashboard" -Action $adeAction -Trigger $adeTrigger -Principal $adePrincipal -Settings $adeSettings -Force | Out-Null

if (Test-Path (Join-Path $RunnerDir "svc.cmd")) {
    Write-Step "Configuring GitHub Runner service..."
    Push-Location $RunnerDir
    try {
        $serviceMarker = Join-Path $RunnerDir ".service"
        if (-not (Test-Path $serviceMarker)) {
            & .\svc.cmd install
        }
        & .\svc.cmd start
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Warning "GitHub Runner service helper not found: $RunnerDir\svc.cmd"
}

Write-Step "Starting ADE task now..."
Start-ScheduledTask -TaskName "ADE Dashboard"

Write-Host ""
Write-Host "Setup complete."
Write-Host "After reboot:"
Write-Host "  1. GitHub Runner starts as a Windows service."
Write-Host "  2. ADE starts automatically after sign-in."
Write-Host "  3. GitHub Actions can write runtime\update.flag."
Write-Host "  4. ADE updates and restarts itself."
