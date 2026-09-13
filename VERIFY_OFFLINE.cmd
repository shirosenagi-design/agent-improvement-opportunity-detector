@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run SETUP_WINDOWS.cmd first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pytest -q tests\test_population.py tests\test_measure.py
python -m py_compile app.py core\schemas.py core\population.py core\measure.py core\trial.py
pause
