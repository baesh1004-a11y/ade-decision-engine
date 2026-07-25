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

$startupDir = [Environment]::GetFolderPath("Startup")
if (-not $startupDir) {
    throw "Windows Startup folder could not be resolved."
}

Write-Step "Creating ADE startup launcher..."
$adeLauncher = Join-Path $startupDir "ADE Dashboard.cmd"
$adeLauncherContent = @"
@echo off
cd /d "$ProjectDir"
start "ADE" /min "$($pythonLauncher.Source)" "$runAdePath"
"@
Set-Content -Path $adeLauncher -Value $adeLauncherContent -Encoding ASCII

$runnerRun = Join-Path $RunnerDir "run.cmd"
$runnerServiceHelper = Join-Path $RunnerDir "svc.cmd"
$runnerServiceMarker = Join-Path $RunnerDir ".service"

if (Test-Path $runnerServiceMarker) {
    Write-Step "GitHub Runner service is already configured."
    try {
        Push-Location $RunnerDir
        & $runnerServiceHelper start | Out-Host
    }
    catch {
        Write-Warning "Runner service could not be started automatically: $($_.Exception.Message)"
    }
    finally {
        Pop-Location
    }
}
elseif (Test-Path $runnerServiceHelper) {
    Write-Warning "Runner is not installed as a Windows service. Creating a Startup-folder launcher instead."
    $runnerLauncher = Join-Path $startupDir "GitHub ADE Runner.cmd"
    $runnerLauncherContent = @"
@echo off
cd /d "$RunnerDir"
start "GitHub ADE Runner" /min "$runnerRun"
"@
    Set-Content -Path $runnerLauncher -Value $runnerLauncherContent -Encoding ASCII
}
else {
    Write-Warning "GitHub Runner was not found: $RunnerDir"
}

Write-Step "Starting ADE now..."
Start-Process -FilePath $pythonLauncher.Source -ArgumentList @($runAdePath) -WorkingDirectory $ProjectDir -WindowStyle Minimized

if ((-not (Test-Path $runnerServiceMarker)) -and (Test-Path $runnerRun)) {
    Write-Step "Starting GitHub Runner now..."
    Start-Process -FilePath $runnerRun -WorkingDirectory $RunnerDir -WindowStyle Minimized
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "After the next Windows sign-in:"
Write-Host "  1. ADE starts automatically."
Write-Host "  2. GitHub Runner starts automatically, either as a service or from Startup."
Write-Host "  3. GitHub Actions can write runtime\update.flag."
Write-Host "  4. ADE updates and restarts itself."
