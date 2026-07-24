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
    pause
    exit /b 0
)

call :log "Checking GitHub for updates..."
echo Checking GitHub for updates...

git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "ERROR: git fetch failed. Continuing with local copy."
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
echo Restarting ADE...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$procs = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match '^python(w)?\.exe$' -or $_.Name -eq 'py.exe') -and $_.CommandLine -match 'run_ade\.py' }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }" >> "%LOG_FILE%" 2>&1

timeout /t 2 /nobreak >nul

call :log "Starting ADE..."
start "ADE" cmd /k "cd /d ""%~dp0"" && py run_ade.py"

call :log "Waiting for ADE web server..."
echo Waiting for ADE web server...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%APP_URL%'; for($i=0; $i -lt 45; $i++){ try { $r=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -ge 200){ exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    call :log "WARNING: ADE web server did not respond within 45 seconds. Opening browser anyway."
    echo WARNING: ADE did not respond within 45 seconds.
) else (
    call :log "ADE web server is ready."
    echo ADE web server is ready.
)

call :log "Opening browser: %APP_URL%"
echo Opening browser...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%APP_URL%'" >> "%LOG_FILE%" 2>&1
if errorlevel 1 start "" "%APP_URL%"

call :log "ADE launch sequence completed."
echo ADE launch sequence completed.
echo Update log: %LOG_FILE%
echo Keep the ADE window open while using the app.

timeout /t 5 /nobreak >nul
goto :cleanup_ok

:log
for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%date% %time%"
echo [%STAMP%] %~1>> "%LOG_FILE%"
exit /b 0

:cleanup_ok
rmdir "%LOCK_DIR%" 2>nul
exit /b 0
