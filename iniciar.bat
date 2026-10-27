@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title WPOSS Vending Integration Manager

rem Busca Python 3 (lanzador "py" o "python").
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] No se encontro Python 3. Instalelo desde https://www.python.org/downloads/
  echo         y marque la opcion "Add python.exe to PATH".
  pause
  exit /b 1
)

rem Entorno virtual propio de la aplicacion (solo la primera vez requiere internet).
if not exist ".venv\Scripts\python.exe" (
  echo Preparando el entorno por primera vez...
  %PY% -m venv .venv || goto :fallo
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fallo
)

".venv\Scripts\python.exe" app.py %*
if errorlevel 1 pause
exit /b

:fallo
echo.
echo [ERROR] No se pudo preparar el entorno. Revise la conexion a internet (solo se
echo         necesita la primera vez) o instale manualmente: pip install -r requirements.txt
pause
exit /b 1
