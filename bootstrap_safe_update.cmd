@echo off
setlocal
cd /d "%~dp0"

echo Fetching latest ADE maintenance tools...
git fetch origin main
if errorlevel 1 goto :error

echo Extracting run_safe_git_update.py from origin/main...
git show origin/main:run_safe_git_update.py > run_safe_git_update.py
if errorlevel 1 goto :error

echo Running safe ADE source update...
python run_safe_git_update.py
if errorlevel 1 goto :error

echo.
echo Safe update completed.
exit /b 0

:error
echo.
echo Safe update failed. Review the message above.
exit /b 1
