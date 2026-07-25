param(
    [string]$ProjectDir = "C:\Project\ADE\ade-decision-engine",
    [string]$RunnerDir = "C:\Project\ADE\ade-decision-engine\actions-runner"
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[ADE setup] $Message"
}

function Assert-Path([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path)) {
        throw "$Label not found: $Path"
    }
}

Assert-Path $ProjectDir "Project directory"
$runAdePath = Join-Path $ProjectDir "run_ade.py"
Assert-Path $runAdePath "run_ade.py"

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    throw "Python launcher 'py.exe' was not found."
}

$runnerRun = Join-Path $RunnerDir "run.cmd"
Assert-Path $runnerRun "GitHub Runner run.cmd"

$startupDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Startup)
if (-not $startupDir) {
    throw "Windows Startup folder could not be resolved."
}

Write-Step "Creating ADE startup launcher..."
$adeLauncher = Join-Path $startupDir "ADE Dashboard.cmd"
$adeLauncherContent = @"
@echo off
cd /d "$ProjectDir"
timeout /t 8 /nobreak >nul
start "ADE" /min "$($pythonLauncher.Source)" "$runAdePath"
"@
Set-Content -Path $adeLauncher -Value $adeLauncherContent -Encoding ASCII

Write-Step "Creating GitHub Runner startup launcher..."
$runnerLauncher = Join-Path $startupDir "GitHub ADE Runner.cmd"
$runnerLauncherContent = @"
@echo off
cd /d "$RunnerDir"
timeout /t 3 /nobreak >nul
start "GitHub ADE Runner" /min "$runnerRun"
"@
Set-Content -Path $runnerLauncher -Value $runnerLauncherContent -Encoding ASCII

Write-Step "Starting GitHub Runner now..."
$existingRunner = Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$RunnerDir*" }
if (-not $existingRunner) {
    Start-Process -FilePath $runnerRun -WorkingDirectory $RunnerDir -WindowStyle Minimized
}
else {
    Write-Step "GitHub Runner is already running."
}

Write-Step "Starting ADE now..."
$existingAde = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$runAdePath*" }
if (-not $existingAde) {
    Start-Process -FilePath $pythonLauncher.Source -ArgumentList @($runAdePath) -WorkingDirectory $ProjectDir -WindowStyle Minimized
}
else {
    Write-Step "ADE is already running."
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "After the next Windows sign-in:"
Write-Host "  1. GitHub Runner starts automatically from the Startup folder."
Write-Host "  2. ADE starts automatically after a short delay."
Write-Host "  3. GitHub Actions can write runtime\update.flag."
Write-Host "  4. ADE updates and restarts itself."
Write-Host ""
Write-Host "Startup files:"
Write-Host "  $runnerLauncher"
Write-Host "  $adeLauncher"
