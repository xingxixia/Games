@echo off
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  set "PYTHON=python"
)

"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --console --name "GrassDefenseAI" "%ROOT%pvz_pygame.py"

if %ERRORLEVEL% EQU 0 (
  copy /Y "%ROOT%dist\GrassDefenseAI.exe" "%ROOT%GrassDefenseAI.exe" >nul
  echo Build finished: "%ROOT%dist\GrassDefenseAI.exe"
  echo Copied to: "%ROOT%GrassDefenseAI.exe"
)
