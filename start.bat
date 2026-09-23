@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "" "http://127.0.0.1:8000"
  py -3 server.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.10 or newer is required. Install Python and try again.
  ) else (
    start "" "http://127.0.0.1:8000"
    python server.py
  )
)
pause
