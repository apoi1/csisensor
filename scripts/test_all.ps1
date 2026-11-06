<# 
.SYNOPSIS
    Prueba integrada: broker + simulador CSI + GUI escritorio + visor web (LAN).
.DESCRIPTION
    Levanta todo en ventanas PowerShell separadas. Detecta la raíz del repo automáticamente.
    Requiere: Docker, Python + venv en backend/.venv
#>

param(
    [string]$Scenario = "moving",
    [string]$DeviceId = "01",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

# ---- Detectar raíz del repo (donde está este script) ----
$RepoRoot = Split-Path -Parent $PSScriptRoot
Write-Host "=== TEST INTEGRADO WiFi-CSI ===" -ForegroundColor Cyan
Write-Host "Repo root: $RepoRoot" -ForegroundColor Gray

$BackendDir = Join-Path $RepoRoot "backend"
$ScriptsDir = Join-Path $RepoRoot "scripts"

# ---- 1. Broker MQTT (Docker) ----
Write-Host "`n-> Verificando/levantando broker MQTT (docker compose)..." -ForegroundColor Yellow
Push-Location $RepoRoot
try {
    $running = docker compose ps --services 2>$null | Where-Object { $_ -eq 'mosquitto' }
    if (-not $running) { docker compose up -d }
} catch {
    Write-Host "   (docker compose no respondió, intentando up de todas formas)" -ForegroundColor Gray
    docker compose up -d | Out-Null
}
Pop-Location

# ---- 2. Entorno Python (venv) ----
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Host "No se encontró .venv. Creando e instalando dependencias..." -ForegroundColor Yellow
    python -m venv "$BackendDir\.venv"
    & "$BackendDir\.venv\Scripts\Activate.ps1"
    pip install -r "$BackendDir\requirements.txt"
} else {
    & $VenvActivate
}

# ---- 3. Función para lanzar en ventana nueva con rutas ABSOLUTAS ----
function Start-RepoWindow {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$ScriptRelPath,
        [string]$Args = ""
    )
    $absScript = Join-Path $RepoRoot $ScriptRelPath
    if (-not (Test-Path $absScript)) {
        Write-Error "No existe el script: $absScript"
        return
    }
    $cmd = "cd `'$RepoRoot`'; python `'$absScript`' $Args"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd -Title $Title -WindowStyle Normal
}

# ---- 4. Lanzar componentes ----
Write-Host "`n-> Lanzando componentes..." -ForegroundColor Green

Start-RepoWindow "Simulador CSI" "scripts\simulate_esp32.py" "--scenario $Scenario --device-id $DeviceId"
Start-RepoWindow "GUI Escritorio" "backend\main.py" ""
Start-RepoWindow "Visor Web (LAN)" "backend\web_viewer.py" "--port $Port"

Write-Host "`n=== Todos los componentes lanzados ===" -ForegroundColor Green
Write-Host "Simulador:  envía CSI al tópico esp32/$DeviceId/csi/raw"
Write-Host "GUI:        ventana PyQt5 con 6 paneles + BPM / respiración / Body"
Write-Host "Visor web:  http://localhost:$Port  (se abre solo en tu navegador por defecto)"
Write-Host "`nDesde el móvil (misma Wi-Fi):  http://<IP-de-tu-PC>:$Port" -ForegroundColor Cyan
Write-Host "Cierra cada ventana PowerShell para detener ese componente." -ForegroundColor Gray