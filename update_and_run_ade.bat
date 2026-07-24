@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "BRANCH=main"
set "APP_URL=http://127.0.0.1:8501"
set "LOG_DIR=logs"
set "LOG_FILE=%LOG_DIR%\update_and_run_ade.log"
set "STAMP_FILE=runtime\requirements.sha"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "runtime" mkdir "runtime"

echo.
echo ========================================
echo ADE - One Click Update and Run
echo ========================================
echo.
call :log "Launcher started."

rem Update directly from GitHub. No manual git pull is required.
echo [1/4] Checking GitHub...
git fetch origin %BRANCH% >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo WARNING: GitHub check failed. Starting local version.
    call :log "WARNING: git fetch failed."
) else (
    for /f %%A in ('git rev-parse HEAD') do set "LOCAL_SHA=%%A"
    for /f %%A in ('git rev-parse origin/%BRANCH%') do set "REMOTE_SHA=%%A"

    if not "!LOCAL_SHA!"=="!REMOTE_SHA!" (
        set "HAS_CHANGES="
        for /f "delims=" %%A in ('git status --porcelain') do set "HAS_CHANGES=1"

        if defined HAS_CHANGES (
            echo WARNING: Local changes exist. GitHub update skipped.
            call :log "WARNING: local changes found; update skipped."
        ) else (
            echo Applying latest GitHub version...
            git reset --hard origin/%BRANCH% >> "%LOG_FILE%" 2>&1
            if errorlevel 1 (
                echo WARNING: GitHub update failed. Starting local version.
                call :log "WARNING: git reset failed."
            ) else (
                echo GitHub update complete.
                call :log "GitHub update complete."
            )
        )
    ) else (
        echo GitHub version is current.
    )
)

rem Install packages only when requirements.txt changed or core imports are missing.
echo.
echo [2/4] Checking Python environment...
for /f %%A in ('certutil -hashfile requirements.txt SHA256 ^| findstr /R /V "hash CertUtil"') do set "REQ_SHA=%%A"
set "SAVED_SHA="
if exist "%STAMP_FILE%" set /p SAVED_SHA=<"%STAMP_FILE%"

py -c "import streamlit, plotly, pandas, numpy" >> "%LOG_FILE%" 2>&1
set "IMPORT_ERROR=!ERRORLEVEL!"

if not "!REQ_SHA!"=="!SAVED_SHA!" set "NEED_INSTALL=1"
if not "!IMPORT_ERROR!"=="0" set "NEED_INSTALL=1"

if defined NEED_INSTALL (
    echo Installing or updating required packages...
    py -m pip install --disable-pip-version-check -r requirements.txt >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo ERROR: Package installation failed.
        echo See: %LOG_FILE%
        call :log "ERROR: requirements install failed."
        pause
        exit /b 1
    )
    >"%STAMP_FILE%" echo !REQ_SHA!
) else (
    echo Python packages are already ready.
)

rem Restart ADE.
echo.
echo [3/4] Starting ADE...
taskkill /FI "WINDOWTITLE eq ADE*" /T /F >> "%LOG_FILE%" 2>&1
timeout /t 1 /nobreak >nul
start "ADE" cmd /k "cd /d ""%~dp0"" && py run_ade.py"

rem Wait briefly for Streamlit, then open the browser.
echo.
echo [4/4] Opening browser...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$url='%APP_URL%'; for($i=0; $i -lt 20; $i++){ try { $r=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1; if($r.StatusCode -ge 200){ exit 0 } } catch {}; Start-Sleep -Milliseconds 500 }; exit 1" >> "%LOG_FILE%" 2>&1
start "" "%APP_URL%"
call :log "ADE launch command completed."

echo.
echo ADE launch completed: %APP_URL%
echo No manual git pull is needed next time.
timeout /t 2 /nobreak >nul
exit /b 0

:log
for /f "tokens=1-3 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%date% %time%"
echo [!STAMP!] %~1>> "%LOG_FILE%"
exit /b 0
