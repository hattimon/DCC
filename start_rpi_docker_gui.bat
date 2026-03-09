@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="--tunnel-only" goto tunnel_only

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python docker-menager.ps
goto end

:tunnel_only
if not defined DOCKER_TUNNEL_COMMAND exit /b 1
start "Docker SSH Tunnel" cmd /k %DOCKER_TUNNEL_COMMAND%
if defined DOCKER_TUNNEL_WAIT timeout /t %DOCKER_TUNNEL_WAIT% /nobreak >nul

:end
endlocal
