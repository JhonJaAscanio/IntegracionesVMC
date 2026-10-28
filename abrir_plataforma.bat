@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title WPOSS Vending Integration Manager

rem Abre la plataforma en el navegador. Si el servidor no esta activo, lo inicia
rem en una ventana minimizada y espera a que responda antes de abrir el navegador.
rem Uso: abrir_plataforma.bat [--no-browser]

set "PY_VENV=.venv\Scripts\python.exe"

rem 1. Preparar el entorno la primera vez (requiere internet solo en este paso).
if not exist "%PY_VENV%" (
  set "PY="
  where py >nul 2>nul && set "PY=py -3"
  if not defined PY ( where python >nul 2>nul && set "PY=python" )
  if not defined PY (
    echo [ERROR] No se encontro Python 3. Instalelo desde https://www.python.org/downloads/
    echo         y marque la opcion "Add python.exe to PATH".
    pause
    exit /b 1
  )
  echo Preparando el entorno por primera vez...
  !PY! -m venv .venv || goto :fallo_entorno
  "%PY_VENV%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fallo_entorno
)

rem 2. Verificar el libro original.
if not exist "WPOSS_Checklist_Pruebas_Vending_5320.xlsx" (
  echo [ERROR] Falta WPOSS_Checklist_Pruebas_Vending_5320.xlsx en esta carpeta.
  echo         Copielo junto a app.py y vuelva a intentarlo.
  pause
  exit /b 1
)

rem 3. Puerto configurado en config.json (5000 por defecto).
set "PORT=5000"
if exist "config.json" (
  for /f %%P in ('"%PY_VENV%" -c "import json;print(int(json.load(open('config.json',encoding='utf-8'))['servidor']['puerto']))" 2^>nul') do set "PORT=%%P"
)
set "URL=http://127.0.0.1:%PORT%/"

rem 4. Si ya esta en ejecucion, solo abrir el navegador.
call :responde
if !errorlevel! equ 0 (
  echo La plataforma ya estaba en ejecucion.
  goto :abrir
)

rem 5. Iniciar el servidor en una ventana minimizada.
echo Iniciando la plataforma en %URL% ...
start "WPOSS servidor - cierre esta ventana para detener la plataforma" /min "%PY_VENV%" app.py --no-browser

rem 6. Esperar hasta 60 segundos a que responda.
where curl.exe >nul 2>nul
if !errorlevel! equ 0 (
  curl.exe -s -f -o nul -m 2 --retry 30 --retry-delay 2 --retry-connrefused --retry-max-time 60 "%URL%" >nul 2>nul
  if !errorlevel! equ 0 goto :abrir
) else (
  powershell -NoProfile -Command "$u='%URL%'; for($i=0;$i -lt 30;$i++){ try { Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1" >nul 2>nul
  if !errorlevel! equ 0 goto :abrir
)
echo [ERROR] La plataforma no respondio a tiempo. Revise logs\app.log
echo         o la ventana minimizada "WPOSS servidor".
pause
exit /b 1

:abrir
if /i not "%~1"=="--no-browser" start "" "%URL%"
echo Plataforma disponible en %URL%
echo Para detenerla, cierre la ventana minimizada "WPOSS servidor".
timeout /t 3 /nobreak >nul 2>nul
exit /b 0

:responde
where curl.exe >nul 2>nul
if %errorlevel% equ 0 (
  curl.exe -s -f -o nul -m 2 "%URL%" >nul 2>nul
) else (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
)
exit /b %errorlevel%

:fallo_entorno
echo.
echo [ERROR] No se pudo preparar el entorno. Revise la conexion a internet (solo se
echo         necesita la primera vez) o instale manualmente: pip install -r requirements.txt
pause
exit /b 1
