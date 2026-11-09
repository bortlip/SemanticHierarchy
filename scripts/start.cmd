@echo off
setlocal
cd /d "%~dp0.."
if errorlevel 1 (
    echo Could not open the Semantic Hierarchy project folder.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Project environment is missing.
    echo Follow the installation instructions in README.md first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\start.py" %*
set "code=%errorlevel%"
if not "%code%"=="0" (
    echo.
    echo Launch failed with exit code %code%.
    pause
)
exit /b %code%
