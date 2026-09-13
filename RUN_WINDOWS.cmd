@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run SETUP_WINDOWS.cmd first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if defined PROJECT04_OPENAI_API_KEY (
  echo PROJECT04 key: present ^(value hidden^)
) else if defined OPENAI_API_KEY (
  echo OPENAI key: present ^(value hidden^)
) else (
  echo No API key was found in PROJECT04_OPENAI_API_KEY or OPENAI_API_KEY.
  echo The app can still open, but Live Research Trial will be disabled.
)
echo Starting http://127.0.0.1:8040 ...
start "" http://127.0.0.1:8040
python -m uvicorn app:app --host 127.0.0.1 --port 8040
pause
