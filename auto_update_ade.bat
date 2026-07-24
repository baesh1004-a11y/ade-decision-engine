@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "BRANCH=main"
set "LOG_DIR=logs"
set "LOG_FILE=%LOG_DIR%\auto_update_ade.log"
set "LOCK_DIR=runtime\auto_update_ade.lock"
set "FORCE_START=%~1"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "runtime" mkdir "runtime"

2>nul mkdir "%LOCK_DIR%"
if errorlevel 1 (
    echo ADE update is already running.
    pause
    exit /b 0
)

call :log "Checking GitHub for updates..."
echo Checking GitHub for updates...

git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "ERROR: git fetch failed."
    echo ERROR: git fetch failed.
    echo See %LOG_FILE%
    goto :cleanup_error
)

for /f %%A in ('git rev-parse HEAD') do set "LOCAL_SHA=%%A"
for /f %%A in ('git rev-parse origin/%BRANCH%') do set "REMOTE_SHA=%%A"

if not "%LOCAL_SHA%"=="%REMOTE_SHA%" (
    call :log "Update found: %LOCAL_SHA% -> %REMOTE_SHA%"
    echo Update found. Pulling latest main...

    for /f "delims=" %%A in ('git status --porcelain') do (
        call :log "ERROR: Local changes detected. Update cancelled to protect local work."
        echo ERROR: Local changes detected. Update cancelled.
        echo Commit or stash local changes first.
        goto :cleanup_error
    )

    git pull --ff-only origin %BRANCH% >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        call :log "ERROR: git pull failed."
        echo ERROR: git pull failed.
        echo See %LOG_FILE%
        goto :cleanup_error
    )
) else (
    call :log "No update."
    echo Already up to date.
)

call :log "Stopping existing run_ade.py process..."
echo Restarting ADE...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match '(^|[\\/ ])run_ade\.py([\" ]|$)' }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }" >> "%LOG_FILE%" 2>&1

timeout /t 2 /nobreak >nul

call :log "Starting ADE..."
start "ADE" /min cmd /c "cd /d ""%~dp0"" && py run_ade.py >> ""%LOG_DIR%\ade_runtime.log"" 2>&1"

call :log "ADE started successfully."
echo ADE started successfully.
echo Runtime log: %LOG_DIR%\ade_runtime.log

timeout /t 3 /nobreak >nul
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
pause
exit /b 1
