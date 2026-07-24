@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "BRANCH=main"
set "APP_URL=http://127.0.0.1:8501"
set "LOG_DIR=logs"
set "LOG_FILE=%LOG_DIR%\update_and_run_ade.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo ========================================
echo ADE - Update, Check, Run
echo ========================================
echo.

call :log "Launcher started."

echo [1/5] Updating from GitHub...
git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo WARNING: GitHub fetch failed. Local version will be used.
    call :log "WARNING: git fetch failed."
) else (
    git status --porcelain > "%TEMP%\ade_git_status.txt"
    for %%A in ("%TEMP%\ade_git_status.txt") do set "STATUS_SIZE=%%~zA"
    if not "!STATUS_SIZE!"=="0" (
        echo WARNING: Local changes found. Pull skipped to protect your work.
        call :log "WARNING: local changes found; pull skipped."
    ) else (
        git pull --ff-only origin %BRANCH% >> "%LOG_FILE%" 2>&1
        if errorlevel 1 (
            echo WARNING: GitHub pull failed. Local version will be used.
            call :log "WARNING: git pull failed."
        ) else (
            echo GitHub update complete.
            call :log "GitHub update complete."
        )
    )
)

echo.
echo [2/5] Preparing Python packages...
py -m pip install --disable-pip-version-check -r requirements.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Package installation failed.
    echo See: %LOG_FILE%
    call :log "ERROR: requirements install failed."
    pause
    exit /b 1
)

echo.
echo [3/5] Running startup checks...
py -c "import streamlit, plotly, pandas, numpy; import dashboard.design_system; import dashboard_app" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo ERROR: ADE startup check failed.
    echo See: %LOG_FILE%
    call :log "ERROR: startup import check failed."
    pause
    exit /b 1
)

echo.
echo [4/5] Closing previous ADE window...
taskkill /FI "WINDOWTITLE eq ADE*" /T /F >> "%LOG_FILE%" 2>&1

timeout /t 1 /nobreak >nul

echo Starting ADE...
start "ADE" cmd /k "cd /d ""%~dp0"" && py run_ade.py"

echo.
echo [5/5] Waiting for web server...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$url='%APP_URL%'; for($i=0; $i -lt 60; $i++){ try { $r=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -ge 200){ exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1" >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo WARNING: ADE did not respond within 60 seconds.
    echo Check the window titled ADE and this log:
    echo %LOG_FILE%
    call :log "WARNING: web server timeout."
    pause
    exit /b 1
)

echo Opening browser...
start "" "%APP_URL%"
call :log "ADE launched successfully."

echo.
echo ADE is ready: %APP_URL%
echo Keep the ADE window open while using the app.
echo.
timeout /t 3 /nobreak >nul
exit /b 0

:log
for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%date% %time%"
echo [!STAMP!] %~1>> "%LOG_FILE%"
exit /b 0
