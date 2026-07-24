@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "BRANCH=main"
set "LOG_DIR=logs"
set "LOG_FILE=%LOG_DIR%\auto_update_ade.log"
set "APP_URL=http://127.0.0.1:8501"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :log "Launching ADE updater..."
echo.
echo ================================
echo ADE update and launch
echo ================================
echo.

git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    call :log "WARNING: git fetch failed. Continuing with local files."
    echo WARNING: GitHub update check failed.
    echo Starting the local ADE version instead.
) else (
    for /f %%A in ('git rev-parse HEAD') do set "LOCAL_SHA=%%A"
    for /f %%A in ('git rev-parse origin/%BRANCH%') do set "REMOTE_SHA=%%A"

    if not "!LOCAL_SHA!"=="!REMOTE_SHA!" (
        echo New GitHub update found.
        call :log "Update found: !LOCAL_SHA! -> !REMOTE_SHA!"

        set "HAS_CHANGES="
        for /f "delims=" %%A in ('git status --porcelain') do set "HAS_CHANGES=1"

        if defined HAS_CHANGES (
            echo WARNING: Local changes exist, so git pull was skipped.
            call :log "WARNING: Local changes detected. Pull skipped."
        ) else (
            git pull --ff-only origin %BRANCH% >> "%LOG_FILE%" 2>&1
            if errorlevel 1 (
                echo WARNING: git pull failed. Starting the local version.
                call :log "WARNING: git pull failed."
            ) else (
                echo GitHub update completed.
                call :log "GitHub update completed."
            )
        )
    ) else (
        echo GitHub version is already current.
        call :log "No update."
    )
)

echo.
echo Checking Python and ADE dependencies...
call :log "Checking Python launcher..."
py --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Python launcher 'py' was not found.
    echo Install Python and enable the Python launcher.
    call :log "ERROR: Python launcher not found."
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo ERROR: requirements.txt was not found.
    call :log "ERROR: requirements.txt not found."
    pause
    exit /b 1
)

call :log "Installing/updating dependencies from requirements.txt..."
echo Installing or repairing required packages...
py -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
py -m pip install -r requirements.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed.
    echo Run this command manually:
    echo   py -m pip install -r requirements.txt
    echo See %LOG_FILE% for details.
    call :log "ERROR: requirements installation failed."
    pause
    exit /b 1
)

call :log "Verifying core imports..."
py -c "import streamlit, plotly, pandas, numpy, requests, dotenv; print('Core dependencies OK')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: One or more core packages still cannot be imported.
    echo See %LOG_FILE% for details.
    call :log "ERROR: core dependency import verification failed."
    pause
    exit /b 1
)

echo Dependencies are ready.
call :log "Dependencies ready."

echo.
echo Closing an existing ADE window...
call :log "Stopping existing ADE window..."
taskkill /FI "WINDOWTITLE eq ADE*" /T /F >> "%LOG_FILE%" 2>&1

timeout /t 1 /nobreak >nul

echo Starting ADE...
call :log "Starting ADE via py run_ade.py..."
start "ADE" cmd /k "cd /d ""%~dp0"" && py run_ade.py"

echo Waiting for startup...
timeout /t 12 /nobreak >nul

echo Opening browser...
call :log "Opening browser: %APP_URL%"
start "" "%APP_URL%"

echo.
echo ADE launch command completed.
echo Browser URL: %APP_URL%
echo.
echo Keep the separate ADE window open while using the app.
call :log "Launch command completed."

pause
exit /b 0

:log
for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%date% %time%"
echo [%STAMP%] %~1>> "%LOG_FILE%"
exit /b 0
