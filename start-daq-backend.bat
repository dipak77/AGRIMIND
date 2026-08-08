@echo off
setlocal EnableExtensions
title AGRIMIND DAQ Backend

REM Usage:
REM   start-daq-backend.bat
REM   start-daq-backend.bat local
REM   start-daq-backend.bat dev
REM
REM Env files: env\daq.local.env.bat | env\daq.dev.env.bat

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
echo === AGRIMIND DAQ Backend [%DAQ_ENV%] ===
echo API:  http://%DAQ_API_HOST%:%DAQ_API_PORT%
echo Docs: http://%DAQ_API_HOST%:%DAQ_API_PORT%/docs
echo Store: %OBJECT_STORE%  Lakehouse: %LAKEHOUSE_ROOT%
echo.

cd /d "%ROOT%agrimind"
if not exist "pyproject.toml" (
  echo [ERROR] agrimind monorepo not found at %ROOT%agrimind
  pause
  exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
  echo [ERROR] uv not found on PATH. Install: https://docs.astral.sh/uv/
  pause
  exit /b 1
)

echo Starting data-ingestion-service ...
uv run uvicorn data_ingestion_service.main:app --host %DAQ_API_HOST% --port %DAQ_API_PORT% --app-dir services/data-ingestion-service

echo.
echo Backend stopped.
pause
endlocal
