@echo off
setlocal EnableExtensions
title AGRIMIND DAQ Frontend

REM Usage:
REM   start-daq-frontend.bat
REM   start-daq-frontend.bat local
REM   start-daq-frontend.bat dev

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "ENV_NAME=%~1"
if "%ENV_NAME%"=="" set "ENV_NAME=local"

set "ENV_FILE=%ROOT%env\daq.%ENV_NAME%.env.bat"
if not exist "%ENV_FILE%" (
  echo [ERROR] Env file not found: %ENV_FILE%
  echo Available: local ^| dev
  pause
  exit /b 1
)

call "%ENV_FILE%"
echo.
echo === AGRIMIND DAQ Frontend [%DAQ_ENV%] ===
echo UI:    http://127.0.0.1:%DAQ_FRONTEND_PORT%
echo Proxy: %VITE_DAQ_PROXY%
echo.

set "FE=%ROOT%frontend\data-acquisition"
if not exist "%FE%\package.json" (
  echo [ERROR] Frontend not found: %FE%
  pause
  exit /b 1
)

cd /d "%FE%"

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found on PATH. Install Node.js LTS.
  pause
  exit /b 1
)

if not exist "node_modules\" (
  echo Installing npm dependencies ...
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
  )
)

echo Starting Vite dev server ...
set "VITE_DAQ_PROXY=%VITE_DAQ_PROXY%"
call npm run dev -- --host 127.0.0.1 --port %DAQ_FRONTEND_PORT%

echo.
echo Frontend stopped.
pause
endlocal
