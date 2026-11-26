@echo off
cd /d "%~dp0"
set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)
echo Starting VayuMitra AI Voice Assistant on http://localhost:8000 using %PYTHON_EXE% ...
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"
"%PYTHON_EXE%" app.py
pause
