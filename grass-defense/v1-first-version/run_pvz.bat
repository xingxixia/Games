@echo off
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  set "PYTHON=python"
)

"%PYTHON%" "%ROOT%pvz_pygame.py"
