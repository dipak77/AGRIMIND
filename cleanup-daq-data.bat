@echo off
setlocal EnableExtensions
title AGRIMIND DAQ Cleanup

REM Usage:
REM   cleanup-daq-data.bat              - dry-run preview (real mode)
REM   cleanup-daq-data.bat preview demo
REM   cleanup-daq-data.bat delete real
REM   cleanup-daq-data.bat delete all

set "ROOT=%~dp0"
set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=preview"
set "MODE=%~2"
if "%MODE%"=="" set "MODE=real"

set "API=http://127.0.0.1:8017"

if /I "%ACTION%"=="preview" (
  set "DRY=true"
  set "CONFIRM=false"
) else if /I "%ACTION%"=="delete" (
  set "DRY=false"
  set "CONFIRM=true"
) else (
  echo Usage: cleanup-daq-data.bat [preview^|delete] [demo^|real^|all]
  exit /b 1
)

if /I "%MODE%"=="all" (
  set "BODY={\"dry_run\":%DRY%,\"confirm\":%CONFIRM%,\"mode\":null,\"keep_latest\":0,\"include_legacy_lakehouse\":true}"
) else (
  set "BODY={\"dry_run\":%DRY%,\"confirm\":%CONFIRM%,\"mode\":\"%MODE%\",\"keep_latest\":0,\"include_legacy_lakehouse\":true}"
)

echo === DAQ cleanup action=%ACTION% mode=%MODE% ===
echo API %API%/v1/admin/cleanup
echo Body %BODY%
echo.

curl -s -X POST "%API%/v1/admin/cleanup" -H "Content-Type: application/json" -d "%BODY%"
echo.
if /I "%ACTION%"=="delete" (
  echo.
  echo Done. Restart backend if needed.
)
pause
endlocal
