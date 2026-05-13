@echo off
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  set "PYTHON=python"
)

"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "GrassDefense" "%ROOT%pvz_pygame.py"

if %ERRORLEVEL% EQU 0 (
  copy /Y "%ROOT%dist\GrassDefense.exe" "%ROOT%GrassDefense.exe" >nul
  echo Build finished: "%ROOT%dist\GrassDefense.exe"
  echo Copied to: "%ROOT%GrassDefense.exe"
)
