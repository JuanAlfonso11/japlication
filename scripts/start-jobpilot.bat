@echo off
setlocal enabledelayedexpansion

REM Starts JobPilot: launches Docker Desktop if it isn't running yet, waits
REM for it to be ready, then brings up the docker compose stack.
REM Safe to double-click any time - if everything is already running,
REM "docker compose up -d" just confirms that and exits.
REM
REM Registered by scripts\install-autostart.ps1 to run at every Windows
REM login, so JobPilot is available without opening a terminal - but you
REM can also just double-click this file any time you want to start it.

set "REPO_DIR=%~dp0.."
cd /d "%REPO_DIR%"

echo [JobPilot] Checking Docker Desktop...
docker info >nul 2>&1
if not %errorlevel%==0 (
    echo [JobPilot] Docker Desktop is not running yet - starting it.
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"

    echo [JobPilot] Waiting for Docker to be ready, this can take a minute.
    set attempts=0

    :wait_loop
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel%==0 goto docker_ready

    set /a attempts=attempts+1
    if !attempts! geq 40 (
        echo [JobPilot] Docker still is not ready after 2 minutes.
        echo [JobPilot] Open Docker Desktop manually, then re-run this script.
        exit /b 1
    )
    goto wait_loop
)

:docker_ready
echo [JobPilot] Docker is ready. Starting the app.
docker compose up -d

if not %errorlevel%==0 (
    echo [JobPilot] docker compose up failed, see the error above.
    exit /b 1
)

echo [JobPilot] Up and running.
echo   Web:       http://localhost:3000
echo   Tailscale: http://radalv11.tailb3d4c1.ts.net:3000

endlocal
