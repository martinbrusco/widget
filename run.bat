@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
    echo.
    echo No se encontro Python en el PATH.
    echo Instala Python 3.11+ desde https://www.python.org/downloads/
    echo Marca "Add python.exe to PATH" al instalar, o ejecuta:
    echo   winget install Python.Python.3.12
    echo.
    pause
    exit /b 1
)

set "MISS="
if not exist "vendor\PyQt6\" set "MISS=1"
if not exist "vendor\pyqtgraph\" set "MISS=1"
if not exist "vendor\psutil\__init__.py" set "MISS=1"
if not exist "vendor\yt_dlp\__init__.py" set "MISS=1"
if not exist "vendor\deep_translator\__init__.py" set "MISS=1"
if defined MISS (
    echo Instalando dependencias en .\vendor ...
    "%PYEXE%" -m pip install --target "%CD%\vendor" -r requirements.txt
    if errorlevel 1 (
        echo Fallo pip install.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%\vendor;%PYTHONPATH%"
"%PYEXE%" widget.py
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" pause
exit /b %EXITCODE%
