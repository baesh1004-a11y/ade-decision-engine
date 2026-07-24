@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "BRANCH=main"
set "LOG_DIR=logs"
set "LOG_FILE=%LOG_DIR%\auto_update_ade.log"
set "LOCK_DIR=runtime\auto_update_ade.lock"
set "APP_URL=http://127.0.0.1:8501"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "runtime" mkdir "runtime"

2>nul mkdir "%LOCK_DIR%"
if errorlevel 1 (
    echo ADE update is already running.
    echo Delete runtime\auto_update_ade.lock if no updater is actually running.
    pause
    exit /b 0
)

call :log "Checking GitHub for updates..."
echo Checking GitHub for updates...

git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "WARNING: git fetch failed. Continuing with local copy."
    echo WARNING: git fetch failed. Starting local ADE anyway.
) else (
    for /f %%A in ('git rev-parse HEAD') do set "LOCAL_SHA=%%A"
    for /f %%A in ('git rev-parse origin/%BRANCH%') do set "REMOTE_SHA=%%A"

    if not "!LOCAL_SHA!"=="!REMOTE_SHA!" (
        call :log "Update found: !LOCAL_SHA! -> !REMOTE_SHA!"
        echo Update found. Pulling latest main...

        set "HAS_CHANGES="
        for /f "delims=" %%A in ('git status --porcelain') do set "HAS_CHANGES=1"

        if defined HAS_CHANGES (
            call :log "WARNING: Local changes detected. Skipping git pull and starting local ADE."
            echo WARNING: Local changes detected. Update skipped.
        ) else (
            git pull --ff-only origin %BRANCH% >> "%LOG_FILE%" 2>&1
            if errorlevel 1 (
                call :log "WARNING: git pull failed. Starting local ADE anyway."
                echo WARNING: git pull failed. Starting local ADE anyway.
            )
        )
    ) else (
        call :log "No update."
        echo Already up to date.
    )
)

call :log "Stopping existing ADE-related Python processes..."
echo Stopping existing ADE process...

powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe' OR Name='py.exe'\" | Where-Object { $_.CommandLine -like '*run_ade.py*' } | ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }; exit 0" >> "%LOG_FILE%" 2>&1

call :log "Process stop command completed."
timeout /t 2 /nobreak >nul

call :log "Starting ADE..."
echo Starting ADE...
start "ADE" cmd /k "cd /d ""%~dp0"" && py run_ade.py"

call :log "Waiting briefly before opening browser..."
echo Opening browser in 8 seconds...
timeout /t 8 /nobreak >nul

call :log "Opening browser: %APP_URL%"
start "" "%APP_URL%"

call :log "ADE launch sequence completed."
echo ADE launch sequence completed.
echo URL: %APP_URL%
echo Keep the ADE window open while using the app.
echo Update log: %LOG_FILE%

timeout /t 5 /nobreak >nul
goto :cleanup_ok

:log
for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%date% %time%"
echo [%STAMP%] %~1>> "%LOG_FILE%"
exit /b 0

:cleanup_ok
rmdir "%LOCK_DIR%" 2>nul
exit /b 0
