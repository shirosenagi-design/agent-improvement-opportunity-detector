@echo off
setlocal
cd /d "%~dp0"
echo.
echo [PROJECT 04 Rescue Lab] Creating an isolated Python environment...
py -3.11 -m venv .venv 2>nul
if errorlevel 1 python -m venv .venv
if errorlevel 1 (
  echo Could not create a Python virtual environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
pip install -r requirements.txt
if errorlevel 1 goto :fail
echo.
echo Setup complete. No API call was made by this setup script.
echo Next: double-click RUN_WINDOWS.cmd
pause
exit /b 0
:fail
echo.
echo Setup failed. Copy the terminal text to KAI; do not paste any API key.
pause
exit /b 1
