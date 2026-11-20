@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Preparando o programa pela primeira vez, aguarde...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
  rem opcional: suporte a fotos .heic do iPhone
  ".venv\Scripts\python.exe" -m pip install --quiet pillow-heif >nul 2>nul
)
start "" ".venv\Scripts\pythonw.exe" -m fotosduplicadas
