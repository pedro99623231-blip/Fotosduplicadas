@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Gera FotosDuplicadas.exe (nao precisa de Python para rodar o .exe depois)
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv || (echo Python nao encontrado & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt pyinstaller
".venv\Scripts\python.exe" -m pip install --quiet pillow-heif >nul 2>nul
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name FotosDuplicadas --collect-all pillow_heif iniciar.py
if errorlevel 1 (echo Falha ao gerar o executavel & pause & exit /b 1)
copy /y "dist\FotosDuplicadas.exe" "FotosDuplicadas.exe" >nul
echo.
echo Pronto: FotosDuplicadas.exe criado nesta pasta.
