# One-shot firmware flasher for sensorproject, run from Windows PowerShell.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\flash-board.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\flash-board.ps1 -Port COM5
#
# Auto-detection priority:
#   1. UART bridge (CP210x / CH340 / FT232) - the "UART"/"COM" USB port of
#      dual-port ESP32-S3 devkits. The most reliable path: the bridge's
#      DTR/RTS lines drive the board's auto-download circuit, so esptool
#      enters download mode electrically - no button dance needed.
#   2. Native USB-Serial-JTAG in ROM download mode (VID_303A&PID_1001) -
#      entered manually with BOOT held + RST tap on boards without the
#      auto-download circuit. Flashed with --before no-reset so the waiting
#      ROM loader is not disturbed.
#   3. Native USB-Serial-JTAG in normal mode (VID_303A&PID_4001) - tried
#      with --before default-reset (only works with auto-download circuit).
#
# Requirements:
#   - The board must NOT be attached to WSL (if it is: usbipd detach --busid <X-X>)
#   - esptool installed in the backend venv:
#     .\.venv\Scripts\python.exe -m pip install esptool
#   - The firmware built (idf.py build in WSL produces src/esp32/build/*.bin)

param(
    [string]$Port = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot   # scripts\ -> repo root
$build = Join-Path $repo "src/esp32/build"

$resetMode = "default-reset"
if (-not $Port) {
    $candidates = Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.Name -match '\(COM\d+\)' }

    # 1) UART bridges - the flashing royal road on dual-port devkits
    $dev = $candidates | Where-Object { $_.DeviceID -match 'VID_10C4&PID_EA60' } | Select-Object -First 1   # CP210x
    if (-not $dev) { $dev = $candidates | Where-Object { $_.DeviceID -match 'VID_1A86' } | Select-Object -First 1 }        # CH340/CH9102
    if (-not $dev) { $dev = $candidates | Where-Object { $_.DeviceID -match 'VID_0403&PID_6001' } | Select-Object -First 1 } # FT232

    # 2) Native USB already in ROM download mode (manual BOOT+RST entry)
    if (-not $dev) {
        $dev = $candidates | Where-Object { $_.DeviceID -match 'VID_303A&PID_1001' } | Select-Object -First 1
        if ($dev) { $resetMode = "no-reset" }
    }

    # 3) Native USB in normal mode (auto-download may work)
    if (-not $dev) {
        $dev = $candidates | Where-Object { $_.DeviceID -match 'VID_303A&PID_4001' } | Select-Object -First 1
    }

    if ($dev -and $dev.Name -match '\((COM\d+)\)') {
        $Port = $Matches[1]
    } else {
        Write-Error "ESP32-S3 (or its UART bridge) not found on any COM port. If it is attached to WSL, detach it first from an admin PowerShell: usbipd detach --busid <X-X> (find the BUSID of the board with 'usbipd list')."
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

Write-Host "Flashing sensorproject firmware on $Port (reset mode: $resetMode) (build: $build)"
& $py -m esptool --chip esp32s3 -p $Port -b 460800 --before $resetMode --after hard-reset write-flash `
    --flash-mode dio --flash-freq 80m --flash-size 4MB `
    0x0 (Join-Path $build "bootloader/bootloader.bin") `
    0x8000 (Join-Path $build "partition_table/partition-table.bin") `
    0x10000 $appBin

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Flash OK - the board rebooted with the new firmware."
    Write-Host "It will join WIFI_SSID from src/esp32/main/config.h and publish to MQTT_BROKER_URI."
    Write-Host "Watch it live: backend GUI (python main.py) or the phone viewer (web_viewer.py)."
    Write-Host "If no link appears in the GUI after ~20 seconds, tap the RST button on the board"
    Write-Host "(boards without the auto-download circuit may not reboot via the USB reset line)."
}
