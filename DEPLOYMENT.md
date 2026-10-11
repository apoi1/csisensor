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

The broker also listens on **9001 (MQTT over WebSockets)** — mapped by
docker-compose and enabled in `mosquitto.conf`. The bundled web viewer
(§9) does not use it; it is there for future browser clients that talk to
the broker directly. The broker image **bakes `mosquitto.conf` in at build
time** (no runtime bind mount), so `docker compose up` works from both
PowerShell and WSL; after editing `mosquitto.conf`, apply the change with
`docker compose up -d --build mosquitto`.

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

> **Where the repo lives (no copy needed):** the tree lives in the **WSL
> filesystem** (`~/dev/projects/c++/sensorproject` on Ubuntu) because the
> firmware builds there; Windows reaches that same tree through the
> `\\wsl.localhost\Ubuntu\...` network share — that is the directory the `cd`
> above enters. `requirements.txt` is `backend/requirements.txt` inside that
> tree: nothing gets copied anywhere; once inside `backend/`, plain
> `pip install -r requirements.txt` reads it through the share. The `.venv`
> it creates is a **Windows** venv (Windows binaries, `Scripts\`) stored on
> the WSL disk — only Windows Python uses it, and the one-time `pip install`
> runs slower over the share than on native NTFS (runtime reads are small
> and fine). Venvs are never portable across OSes: a **separate Linux venv**
> inside WSL is only needed for headless work there (`pytest`,
> `web_viewer.py` — they never import Qt, so PyQt5 is not needed on that
> side).

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

Until it is calibrated you can turn the distance estimate off entirely: set
`CSI_RSSI_REF_DBM` (or `CSI_REF_DISTANCE_M`) to an empty value or `none` — the
GUI then shows `—` for the link distance instead of an uncalibrated guess.

RSSI ranging calibration: measure `R0` at a known distance `d0` (e.g. 1 m)
and set both; see `docs/SIGNAL-MODELING.md` for a two-point fit of `n`.

## 9. Web viewer (phones / tablets)

The same estimates are also served to any browser on the LAN — no app
install on the phone. The viewer is an independent MQTT consumer, so it
works with or without the desktop GUI running.

Its one new dependency is **aiohttp** (HTTP + WebSocket server, Apache 2.0;
<https://docs.aiohttp.org/>) — already covered by `pip install -r
requirements.txt`, nothing extra to install. The page itself ships zero
external assets (no CDN), so it works on LANs without internet.

On the machine that reaches the broker (same venv as §8):

```powershell
python web_viewer.py --broker <BROKER_IP> --host 0.0.0.0 --port 8080
```

- `--broker`: where MQTT lives (`localhost` if this machine runs Docker).
- `--host 0.0.0.0` binds the page to the LAN (default); `--port 8080`.
- Open `http://<PC-LAN-IP>:8080` on the phone, same Wi-Fi.

Allow the port through Windows Firewall once (admin PowerShell):

```powershell
New-NetFirewallRule -DisplayName "CSI Web Viewer 8080 (dev)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

The page needs no internet (no CDN): tiles for heart/respiration/body
state/link distance, a 10-minute trend plot and the latest filtered
waves, with automatic reconnect. Like everything here: research tool,
not a medical device.

## 10. Live test with the ESP32-S3

1. `python main.py --host localhost` and keep `idf.py monitor` running.
2. Subject sits still, 0.5-2 m from the ESP32, in line of sight.
3. After ~15 s the window fills and estimates appear.
4. Motion artifacts: a single movement resets the vitals estimates for a few seconds, and the **Body row** switches to `Moving` while you move.

### Multi-node (multi-ESP32) setup

Each node publishes to its own per-device topic (`esp32/<id>/csi/raw`, id =
last 3 bytes of its MAC), so flash as many ESP32s as you like — no per-node
configuration. The backend subscribes `esp32/+/csi/raw` plus the legacy
flat topic and fuses the links per band (best SNR wins; see
`docs/SIGNAL-MODELING.md` §8).

Dry-run two links without hardware — two terminals (same venv):

```powershell
python ..\scripts\simulate_esp32.py --host localhost --device-id a1b2c3 --scenario resting
python ..\scripts\simulate_esp32.py --host localhost --device-id d4e5f6 --scenario resting
```

The GUI status bar then shows `links a1b2c3, d4e5f6` and the estimates fuse
automatically; the web page's meta line shows `links 2`.

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Phone cannot open the viewer page | same Wi-Fi? `http://<PC-LAN-IP>:8080` correct? Windows Firewall rule for 8080 (§9)? `web_viewer.py` still running? |
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

## 12. Security notes

- `mosquitto.conf` allows **anonymous** connections: LAN/dev use only. For anything shared, add `password_file` and `allow_anonymous false`.
- WiFi credentials live in `config.h` - never commit real ones; keep a private copy or inject them via your build system.
