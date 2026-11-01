@echo off
rem Starts the app from source. The first run makes a private Python environment (needs Python 3.11 or newer).
rem   run.bat          start the app
rem   run.bat debug    start it with a console window, so errors are visible
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Setting up a private Python environment, one time only...
  python -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :fail
)
if /i "%~1"=="debug" (
  ".venv\Scripts\python.exe" src\app.py
  pause
) else (
  start "" ".venv\Scripts\pythonw.exe" src\app.py
)
exit /b 0

:fail
echo.
echo Setup failed. Install Python 3.11 or newer (winget install Python.Python.3.13) and run this again.
pause
exit /b 1
