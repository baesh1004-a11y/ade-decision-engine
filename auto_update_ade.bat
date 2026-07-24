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
echo Checking Python packages...
call :log "Checking Streamlit installation..."
py -m streamlit --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo Streamlit is missing. Installing it now...
    call :log "Streamlit missing. Running py -m pip install streamlit..."
    py -m pip install streamlit >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo.
        echo ERROR: Streamlit installation failed.
        echo Run this command manually:
        echo   py -m pip install streamlit
        echo See %LOG_FILE% for details.
        call :log "ERROR: Streamlit installation failed."
        pause
        exit /b 1
    )
    echo Streamlit installation completed.
    call :log "Streamlit installation completed."
) else (
    echo Streamlit is installed.
)

echo.
echo Closing an existing ADE window...
call :log "Stopping existing ADE window..."
taskkill /FI "WINDOWTITLE eq ADE*" /T /F >> "%LOG_FILE%" 2>&1

timeout /t 1 /nobreak >nul

echo Starting ADE...
call :log "Starting ADE via py run_ade.py..."
start "ADE" cmd /k "cd /d ""%~dp0"" && py run_ade.py"

echo Waiting for startup...
timeout /t 10 /nobreak >nul

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
