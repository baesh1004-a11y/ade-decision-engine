@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "BRANCH=main"
set "LOG_DIR=logs"
set "LOG_FILE=%LOG_DIR%\auto_update_ade.log"
set "LOCK_DIR=runtime\auto_update_ade.lock"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "runtime" mkdir "runtime"

2>nul mkdir "%LOCK_DIR%"
if errorlevel 1 exit /b 0

call :log "Checking GitHub for updates..."

git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "ERROR: git fetch failed."
    goto :cleanup_error
)

for /f %%A in ('git rev-parse HEAD') do set "LOCAL_SHA=%%A"
for /f %%A in ('git rev-parse origin/%BRANCH%') do set "REMOTE_SHA=%%A"

if "%LOCAL_SHA%"=="%REMOTE_SHA%" (
    call :log "No update."
    goto :cleanup_ok
)

call :log "Update found: %LOCAL_SHA% -> %REMOTE_SHA%"

for /f "delims=" %%A in ('git status --porcelain') do (
    call :log "ERROR: Local changes detected. Update cancelled to protect local work."
    goto :cleanup_error
)

git pull --ff-only origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "ERROR: git pull failed."
    goto :cleanup_error
)

call :log "Stopping existing run_ade.py process..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match '(^|[\\/ ])run_ade\.py([\" ]|$)' }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }" >> "%LOG_FILE%" 2>&1

timeout /t 2 /nobreak >nul

call :log "Starting ADE..."
start "ADE" /min cmd /c "cd /d ""%~dp0"" && py run_ade.py >> ""%LOG_DIR%\ade_runtime.log"" 2>&1"

call :log "ADE restarted successfully."
goto :cleanup_ok

:log
for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%date% %time%"
echo [%STAMP%] %~1>> "%LOG_FILE%"
exit /b 0

:cleanup_ok
rmdir "%LOCK_DIR%" 2>nul
exit /b 0

:cleanup_error
rmdir "%LOCK_DIR%" 2>nul
exit /b 1
