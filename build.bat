@echo off
rem Builds the Windows app with PyInstaller:
rem   dist\Media MultiTool Desktop\Media MultiTool Desktop.exe     (the app, with everything it needs next to it)
rem yt-dlp, ffmpeg and Deno are NOT bundled: the app offers to download them on first run, so the build stays small
rem and always gets the current yt-dlp.
rem   build.bat            build, then wait for a key press
rem   build.bat nopause    build and close (for scripts)
setlocal
cd /d "%~dp0"
set "NAME=Media MultiTool Desktop"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv || goto :fail
)
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt -r requirements-build.txt || goto :fail
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name "%NAME%" ^
  --icon "%~dp0logo\final\mmd-app-icon.ico" --add-data "%~dp0ui;ui" --collect-all webview ^
  --distpath "%~dp0dist" --workpath "%~dp0build" --specpath "%~dp0build" "%~dp0src\app.py" || goto :fail
if exist "%~dp0build" rmdir /s /q "%~dp0build"
echo.
echo Done:
echo   dist\%NAME%\%NAME%.exe
if /i not "%~1"=="nopause" pause
exit /b 0

:fail
echo.
echo Build failed.
if /i not "%~1"=="nopause" pause
exit /b 1
