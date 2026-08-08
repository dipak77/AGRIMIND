@echo off
setlocal EnableExtensions
title AGRIMIND DAQ - Start All

REM Usage:
REM   start-daq-all.bat
REM   start-daq-all.bat local
REM   start-daq-all.bat dev
REM
REM Opens two windows: backend API + frontend UI

set "ROOT=%~dp0"
set "ENV_NAME=%~1"
if "%ENV_NAME%"=="" set "ENV_NAME=local"

if not exist "%ROOT%env\daq.%ENV_NAME%.env.bat" (
  echo [ERROR] Unknown env: %ENV_NAME%
  echo Use: local ^| dev
  pause
  exit /b 1
)

echo Starting DAQ [%ENV_NAME%] ...
echo   1^) Backend  -^> new window
echo   2^) Frontend -^> new window
echo.

start "AGRIMIND DAQ Backend [%ENV_NAME%]" cmd /k ""%ROOT%start-daq-backend.bat" %ENV_NAME%"
timeout /t 3 /nobreak >nul
start "AGRIMIND DAQ Frontend [%ENV_NAME%]" cmd /k ""%ROOT%start-daq-frontend.bat" %ENV_NAME%"

echo.
echo Open when ready:
echo   API  http://127.0.0.1:8017/docs
echo   UI   http://127.0.0.1:5173
echo.
echo This window can be closed.
timeout /t 5
endlocal
