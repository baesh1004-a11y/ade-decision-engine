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

$runnerServiceMarker = Join-Path $RunnerDir ".service"
$runnerServiceHelper = Join-Path $RunnerDir "svc.cmd"
$runnerUsesService = (Test-Path $runnerServiceMarker) -and (Test-Path $runnerServiceHelper)

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
powershell.exe -NoProfile -WindowStyle Hidden -Command "$target = '$runAdePath'; $running = Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like ('*' + $target + '*') }; if (-not $running) { Start-Process -FilePath '$($pythonLauncher.Source)' -ArgumentList @($target) -WorkingDirectory '$ProjectDir' -WindowStyle Minimized }"
"@
Set-Content -Path $adeLauncher -Value $adeLauncherContent -Encoding ASCII

$runnerLauncher = Join-Path $startupDir "GitHub ADE Runner.cmd"
if ($runnerUsesService) {
    Write-Step "Runner service detected; removing duplicate Startup launcher..."
    if (Test-Path $runnerLauncher) {
        Remove-Item $runnerLauncher -Force
    }
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
else {
    Write-Step "Creating guarded GitHub Runner startup launcher..."
    $runnerLauncherContent = @"
@echo off
cd /d "$RunnerDir"
timeout /t 3 /nobreak >nul
powershell.exe -NoProfile -WindowStyle Hidden -Command "$dir = '$RunnerDir'; $running = Get-CimInstance Win32_Process -Filter \"Name='Runner.Listener.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -like ($dir + '*') }; if (-not $running) { Start-Process -FilePath '$runnerRun' -WorkingDirectory '$RunnerDir' -WindowStyle Minimized }"
"@
    Set-Content -Path $runnerLauncher -Value $runnerLauncherContent -Encoding ASCII
}

Write-Step "Starting GitHub Runner now..."
if (-not $runnerUsesService) {
    $existingRunner = Get-CimInstance Win32_Process -Filter "Name='Runner.Listener.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like "$RunnerDir*" }
    if (-not $existingRunner) {
        Start-Process -FilePath $runnerRun -WorkingDirectory $RunnerDir -WindowStyle Minimized
    }
    else {
        Write-Step "GitHub Runner is already running."
    }
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
if ($runnerUsesService) {
    Write-Host "  1. GitHub Runner starts as a Windows service."
}
else {
    Write-Host "  1. GitHub Runner starts once from the Startup folder."
}
Write-Host "  2. ADE starts automatically after a short delay."
Write-Host "  3. Duplicate Runner sessions are prevented."
Write-Host "  4. GitHub Actions can write runtime\update.flag."
Write-Host ""
Write-Host "Startup files:"
Write-Host "  $adeLauncher"
if (-not $runnerUsesService) {
    Write-Host "  $runnerLauncher"
}
