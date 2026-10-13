# One-shot builder of the PORTABLE SYSTEM kit for sensorproject.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\build-portable-kit.ps1
#
# What the kit is (your "sistema entero portable" goal):
#   portable-kit/
#   +-- csi-web-viewer.exe   the LAN web viewer (PyInstaller exe, no Python needed)
#   +-- mosquitto/           the official Eclipse Mosquitto broker binaries + our conf
#   +-- start-system.bat     double-click: starts broker + viewer, prints the URL
#   +-- README.txt           usage + the ESP32 broker-IP reminder
#
# Requirements (one time):
#   - The viewer exe built in WSL/Windows (DEPLOYMENT.md section 9):
#     .\.venv\Scripts\python.exe -m PyInstaller --onefile --name csi-web-viewer `
#         --add-data "web_static;web_static" web_viewer.py
#   - Eclipse Mosquitto installed ONCE with the official installer:
#     https://mosquitto.org/files/binary/win64/mosquitto-2.1.2-install-windows-x64.exe
#     (the script copies the binaries out of the install dir; it never
#      needs the installer again afterwards)

param(
    [string]$KitDir = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot   # scripts\ -> repo root

if (-not $KitDir) { $KitDir = Join-Path $repo "portable-kit" }

# ---- viewer exe ------------------------------------------------------------
$viewer = Join-Path $repo "backend/dist/csi-web-viewer.exe"
if (-not (Test-Path $viewer)) {
    Write-Error "viewer exe not found: $viewer`nBuild it first (DEPLOYMENT.md section 9):`n  .\.venv\Scripts\python.exe -m PyInstaller --onefile --name csi-web-viewer --add-data `"web_static;web_static`" web_viewer.py"
    exit 1
}

# ---- mosquitto binaries ----------------------------------------------------
$mstExe = Join-Path $KitDir "mosquitto/mosquitto.exe"
$installed = Join-Path $env:ProgramFiles "mosquitto/mosquitto.exe"
if (-not (Test-Path $mstExe)) {
    if (-not (Test-Path $installed)) {
        Write-Error "Mosquitto not found. Install it ONCE with the official installer:`n  https://mosquitto.org/files/binary/win64/mosquitto-2.1.2-install-windows-x64.exe`nIMPORTANT: at the installer's components screen UNCHECK the 'Service'`ncomponent (it would listen on port 1883 and collide with the Docker`nbroker). Then re-run this script (it copies the binaries into the kit)."
        exit 1
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $KitDir "mosquitto") | Out-Null
    Copy-Item -Path (Join-Path $env:ProgramFiles "mosquitto\*") `
              -Destination (Join-Path $KitDir "mosquitto") -Recurse -Force
    Write-Host "copied mosquitto binaries from the install dir into the kit"
}

# ---- collision guard: a Windows mosquitto service fights the Docker broker ----
$svc = Get-Service mosquitto -ErrorAction SilentlyContinue
if ($svc) {
    Write-Warning "A Windows 'mosquitto' service exists (installer's Service component). It will fight the Docker broker for port 1883. Remove it from an ADMIN prompt: sc stop mosquitto; sc delete mosquitto"
}

# ---- our broker conf (matches docker/mosquitto/mosquitto.conf) -------------
@'
listener 1883
protocol mqtt
allow_anonymous true

listener 9001
protocol websockets
allow_anonymous true

persistence false
log_dest stdout
'@ | Set-Content -Path (Join-Path $KitDir "mosquitto/mosquitto.conf") -Encoding ASCII

# ---- copy the viewer --------------------------------------------------------
New-Item -ItemType Directory -Force -Path $KitDir | Out-Null
Copy-Item -Path $viewer -Destination (Join-Path $KitDir "csi-web-viewer.exe") -Force

# ---- one-click launcher ------------------------------------------------------
@'
@echo off
title CSI broker
start "CSI broker" "%~dp0mosquitto\mosquitto.exe" -c "%~dp0mosquitto\mosquitto.conf"
timeout /t 2 /nobreak >nul
start "CSI viewer" "%~dp0csi-web-viewer.exe" --broker localhost --host 0.0.0.0 --port 8080
for /f "tokens=2 delims=:" %%a in ('netsh interface ip show address ^| findstr /c:"192.168." ^| findstr /v /c:"192.168.56." /c:"192.168.192."') do set LIP=%%a
echo.
echo  System running. Open on any phone on the SAME Wi-Fi:
echo      http://%LIP:~1%:8080
echo  (the board must be flashed with THIS PC's IP as its broker - see README.txt)
echo.
pause
'@ | Set-Content -Path (Join-Path $KitDir "start-system.bat") -Encoding ASCII

# ---- kit README ---------------------------------------------------------------
@'
SENSORPROJECT - PORTABLE SYSTEM KIT
===================================

RUN:      double-click start-system.bat
VIEW:     on any phone in the same Wi-Fi, open the URL the window prints
BOARD:    the ESP32 keeps publishing to the broker address flashed in its
          src/esp32/main/config.h (MQTT_BROKER_URI). If you move this kit
          to another PC, re-flash the board with that PC's IP:
          edit config.h, idf.py build (WSL), then scripts/flash-board.ps1.
NO PYTHON, NO DOCKER required on the target PC.

Contents:
  csi-web-viewer.exe  LAN web viewer (aiohttp, self-contained)
  mosquitto/          Eclipse Mosquitto broker (official binaries)
  start-system.bat    one-click launcher (broker + viewer)
'@ | Set-Content -Path (Join-Path $KitDir "README.txt") -Encoding ASCII

$ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -like "192.168.*" -and $_.IPAddress -notlike "192.168.56.*" -and $_.IPAddress -notlike "192.168.192.*" } |
    Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "Kit ready: $KitDir"
Write-Host "This PC's LAN IP: $ip  (phones: http://$ip`:8080)"
Write-Host "Remember: the board is flashed to its own broker IP - re-flash if the kit moves."
