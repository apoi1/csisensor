# One-shot firmware flasher for sensorproject, run from Windows PowerShell.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\flash-board.ps1
#
# Why: flashing the ESP32-S3 (native USB-Serial-JTAG) through the usbipd
# WSL tunnel is unreliable - the chip reset during flashing re-enumerates
# its USB and drops the tunnel mid-handshake ("No serial data received",
# then /dev/ttyACM0 vanishes). From Windows the board's COM port is native
# and the reset handshake works normally.
#
# Requirements:
#   - The board must NOT be attached to WSL (if it is: usbipd detach --busid 1-6)
#   - esptool installed in the backend venv:
#     .\.venv\Scripts\python.exe -m pip install esptool
#   - The firmware built (idf.py build in WSL produces src/esp32/build/*.bin)

param(
    [string]$Port = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot   # scripts\ -> repo root
$build = Join-Path $repo "src/esp32/build"

if (-not $Port) {
    # Auto-detect the ESP32-S3 native USB-Serial-JTAG (VID_303A & PID_4001)
    $dev = Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.DeviceID -match 'VID_303A&PID_4001' } |
        Select-Object -First 1
    if ($dev -and $dev.Name -match '\((COM\d+)\)') {
        $Port = $Matches[1]
    } else {
        Write-Error "ESP32-S3 not found on any COM port. If it is attached to WSL, detach it first from an admin PowerShell: usbipd detach --busid <X-X> (find the BUSID of the board with 'usbipd list')."
        exit 1
    }
}

$py = Join-Path $repo "backend/.venv/Scripts/python.exe"
if (-not (Test-Path $py)) {
    Write-Error "venv python not found at $py - create the backend venv first (DEPLOYMENT.md section 8)."
    exit 1
}

$appBin = Join-Path $build "wifi_csi_vitals.bin"
if (-not (Test-Path $appBin)) {
    Write-Error "Firmware not built yet: $appBin missing. Run 'idf.py build' in WSL first."
    exit 1
}

Write-Host "Flashing sensorproject firmware on $Port (build: $build)"
& $py -m esptool --chip esp32s3 -p $Port -b 460800 --before default_reset --after hard_reset write_flash `
    --flash_mode dio --flash_freq 80m --flash_size 4MB `
    0x0 (Join-Path $build "bootloader/bootloader.bin") `
    0x8000 (Join-Path $build "partition_table/partition-table.bin") `
    0x10000 $appBin

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Flash OK - the board rebooted with the new firmware."
    Write-Host "It will join WIFI_SSID from src/esp32/main/config.h and publish to MQTT_BROKER_URI."
    Write-Host "Watch it live: backend GUI (python main.py) or the phone viewer (web_viewer.py)."
}
