# Deployment Guide - ESP32-S3 WiFi-CSI Vital Signs

End-to-end setup for the pipeline:

```
ESP32-S3 ──(MQTT: esp32/csi/raw)──► Mosquitto (Docker Desktop, Windows) ◄── Python backend + PyQt5 GUI (Windows)
```

> **Disclaimer**: research/experimental. Not a medical device.

## Layer split

| Layer | Where | What runs |
|---|---|---|
| Windows | Docker Desktop | Mosquitto broker (port 1883) |
| Windows | Python 3.10+ venv in `backend/` | subscriber + FFT processor + PyQt5 GUI |
| WSL (Ubuntu) | ESP-IDF v5.3.x | firmware build, flash, monitor (via usbipd-win) |

## 1. Prerequisites

- Windows 10/11 with **WSL2** (Ubuntu 22.04+, **fish shell** — WSL commands in this guide use fish syntax)
- **Docker Desktop** for Windows (WSL2 integration enabled)
- **Python 3.10+** on Windows (python.org installer, "Add to PATH")
- ESP32-S3 dev board with a USB cable (data-capable)
- A **2.4 GHz** WiFi network (the ESP32-S3 does not see 5 GHz)

## 2. Broker (Mosquitto via Docker)

From the repo root (WSL or PowerShell - Docker Desktop handles both):

```console
docker compose up -d          # starts mosquitto on 1883
docker compose logs mosquitto # verify: "mosquitto version 2.x running"
```

Publish a test message to validate the chain:

```console
docker exec -it wifisensing_mosquitto mosquitto_pub -t esp32/csi/raw -m "0,-50,2,0,10,20"
```

### Allow the broker through Windows Firewall (admin PowerShell)

The ESP32 connects from the LAN, so inbound TCP 1883 must be allowed:

```powershell
New-NetFirewallRule -DisplayName "Mosquitto 1883 (dev)" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```

Note the **Windows host LAN IP** (`ipconfig` -> Wi-Fi adapter IPv4). That is the IP for `MQTT_BROKER_URI` in the firmware config and for every device except the Windows backend itself (which uses `localhost`).

## 3. ESP-IDF (WSL)

> WSL commands in this guide are **fish** (bash differences are noted inline — `&&`, globs and `$USER` are identical in both).

```fish
sudo apt-get update
sudo apt-get install -y git wget flex bison gperf python3 python3-pip python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
mkdir -p ~/esp && cd ~/esp
git clone -b v5.3.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32s3
source export.fish     # sets up the environment in this tab (native fish script shipped by ESP-IDF)
```

One-time fish abbreviation, so a plain `idfenv` sets up the environment in any new tab:

```fish
abbr --add idfenv 'source ~/esp/esp-idf/export.fish'
```

> In bash the only difference is `source export.fish` → `. ./export.sh`; every other line above is identical.

> Version matters: the firmware targets the ESP-IDF **v5.x** API (esp-mqtt nested broker config, `esp_wifi_set_csi_rx_cb`). The CSI API is native to ESP-IDF; no external component is required.

## 4. USB serial from WSL (usbipd-win)

WSL2 does not see USB devices natively; attach the board with usbipd (admin PowerShell):

```powershell
winget install usbipd
usbipd list                     # find your board's BUSID, e.g. 2-3
usbipd bind --busid 2-3         # once
usbipd attach --wsl --busid 2-3
```

Back in WSL:

```fish
ls /dev/ttyACM*                 # expect /dev/ttyACM0
sudo usermod -aG dialout $USER  # then close and reopen WSL
```

## 5. Configure the firmware

Edit `src/esp32/main/config.h`:

| Define | Value |
|---|---|
| `WIFI_SSID` / `WIFI_PASS` | your 2.4 GHz credentials |
| `MQTT_BROKER_URI` | `mqtt://<Windows-LAN-IP>:1883` - NOT localhost |
| `USE_TRAFFIC_PING` | `1` (auto-pings the gateway at 10 Hz to generate RX traffic) |

## 6. Build, flash, monitor

```fish
cd ~/dev/projects/c++/sensorproject/src/esp32
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash monitor
```

Expected on the monitor:

```
I (xxxx) csi_main: WiFi connected, IP: 192.168.1.42
I (xxxx) csi_main: MQTT client started -> mqtt://192.168.1.50:1883
I (xxxx) csi_main: MQTT connected
I (xxxx) csi_main: traffic ping to gateway started (every 100 ms)
I (xxxx) csi_main: csi: captured=120 qfull=0 published=120 failed=0
```

## 7. Verify the CSI stream

From WSL (the broker runs on the Windows side, so use the Windows host IP):

```fish
sudo apt-get install -y mosquitto-clients
set BROKER (grep nameserver /etc/resolv.conf | awk '{print $2}')
mosquitto_sub -h "$BROKER" -t esp32/csi/raw -C 3
```

> Fish swaps `$( ... )` command substitution for `( ... )`; `$BROKER` expansion and quoting work the same.

Expected payload (t_us, rssi, n, seq, amplitudes):

```
1717000000123456,-52,64,42,178,176,171,169,...
```

> With WSL mirrored networking (`networkingMode=mirrored`), `localhost` also works — **Windows 11 22H2+ only**. On Windows 10 this mode is unsupported (WSL runs in NAT mode), so keep using the `BROKER` / Windows-LAN-IP path above.

## 8. Backend + GUI (Windows)

```powershell
cd \\wsl.localhost\Ubuntu\home\tilin\dev\projects\c++\sensorproject\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --host localhost
```

If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Dry-run WITHOUT hardware (recommended first)

In a second terminal (same venv), publish synthetic CSI:

```powershell
python ..\scripts\simulate_esp32.py --host localhost --scenario moving
```

Scenarios: `resting` (subject at rest, ~66 BPM / ~18 resp/min), `moving`
(adds periodic gross-movement episodes), `absent` (empty room).

The GUI should show **~66 BPM / ~18 resp/min** and both waveforms within ~15 s,
plus the **Body row** tracking the scenario: `Still` (resting), `Moving`
during episodes (moving), `Absent` (absent). The right column shows the
physics panels (subcarrier heatmap, spectrogram, motion-energy trace).

### Tune presence/motion and RSSI ranging (optional)

Body-row thresholds and the RSSI link-distance estimate are configurable
via environment variables (formulas and calibration procedures in
`docs/SIGNAL-MODELING.md`):

| Env var | Default | Meaning |
|---|---|---|
| `CSI_ABSENT_STD` | `0.15` | window std below this = empty room (`Absent`) |
| `CSI_MOVING_RMS` | `1.5` | 0.5-3.0 Hz motion-band RMS above this = `Moving` |
| `CSI_RSSI_REF_DBM` | `-52.0` | reference RSSI `R0` measured at `d0` |
| `CSI_REF_DISTANCE_M` | `1.0` | reference distance `d0` |
| `CSI_PATH_LOSS_N` | `3.0` | log-distance path-loss exponent `n` |

RSSI ranging calibration: measure `R0` at a known distance `d0` (e.g. 1 m)
and set both; see `docs/SIGNAL-MODELING.md` for a two-point fit of `n`.

## 9. Live test with the ESP32-S3

1. `python main.py --host localhost` and keep `idf.py monitor` running.
2. Subject sits still, 0.5-2 m from the ESP32, in line of sight.
3. After ~15 s the window fills and estimates appear.
4. Motion artifacts: a single movement resets the vitals estimates for a few seconds, and the **Body row** switches to `Moving` while you move.

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ls /dev/ttyACM*` empty | Re-run `usbipd attach`; check the cable is data-capable; `usbipd list` must show "Attached". |
| WiFi connects and reconnects forever | SSID is 5 GHz only - use 2.4 GHz; check credentials. |
| `MQTT connected` never appears | Broker URI uses `localhost` (only valid on Windows itself); check the firewall rule for 1883; Docker Desktop must be running. |
| MQTT connected but no data | Topic mismatch (default `esp32/csi/raw`); verify with `docker compose logs mosquitto`. |
| Data flows but GUI is empty | Backend host wrong: on Windows use `localhost`; if the backend runs inside WSL use `$BROKER` from step 7. |
| `captured` grows, `published` stays 0 | Publishes fail - broker unreachable; check the `failed` counter and broker logs. |
| `captured` stays 0 | No RX traffic: keep `USE_TRAFFIC_PING 1`, or run `ping -t <ESP32_IP>` from any machine on the network. |
| Build error inside `start_traffic_ping` | Your IDF ping API differs - set `USE_TRAFFIC_PING 0` in `config.h` and use an external ping instead. |
| BPM shows "-" | SNR below threshold: shorten distance, remove motion, try `--window 20` for a longer window. |
| Body row stuck on "waiting for data..." | Motion window (15 s) still filling, or the CSI stream is not reaching the backend; check the pkt/s rate in the status bar. |
| `idf.py: command not found` | Run `idfenv` (or `source ~/esp/esp-idf/export.fish`) in this tab — in bash: `. ~/esp/esp-idf/export.sh`. |

## 11. Security notes

- `mosquitto.conf` allows **anonymous** connections: LAN/dev use only. For anything shared, add `password_file` and `allow_anonymous false`.
- WiFi credentials live in `config.h` - never commit real ones; keep a private copy or inject them via your build system.
