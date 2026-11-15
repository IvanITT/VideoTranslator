@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar-o-verificar.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %EXITCODE%
