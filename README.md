# sensorproject - WiFi-CSI Vital Signs (ESP32-S3 + Python)

Real-time experimental vital-sign tracking (heart rate and respiration
estimation) from **WiFi CSI** (Channel State Information) captured by an
ESP32-S3, streamed over MQTT to a PyQt5 desktop application with FFT-based
signal processing.

```
ESP32-S3 firmware (C++/ESP-IDF) ──MQTT──► Mosquitto (Docker) ◄── Python backend (paho-mqtt + scipy FFT) ──► PyQt5 GUI (vitals + body presence/motion)
                                                       └──► Web viewer (backend/web_viewer.py → any phone browser on the LAN)
```

> Research/educational project. **Not a medical device.**

## Layout

| Path | What |
|---|---|
| `src/esp32/` | ESP-IDF v5.x firmware: native CSI capture -> queue -> MQTT publish |
| `backend/` | Python: MQTT subscriber, FFT vitals processor + motion analyzer, multi-link manager (per-device ESP32 topics + per-band max-SNR fusion), PyQt5 GUI (real-time heart rate, respiration, body presence/motion "Body" row; physics panels: subcarrier heatmap, spectrogram, motion energy — with formula annotations), unit tests |
| `backend/web_viewer.py` + `backend/web_static/` | Standalone LAN web viewer: same DSP served to phone browsers (aiohttp + WebSocket; no app install, no CDN) |
| `scripts/simulate_esp32.py` | Synthetic CSI publisher to test the backend without hardware |
| `docker-compose.yaml` + `docker/mosquitto/` | Local Mosquitto broker |
| `DEPLOYMENT.md` | **Step-by-step deployment guide (WSL + Windows)** |
| `docs/` | Tools list and project notes |
| `docs/SIGNAL-MODELING.md` | Signal model: physics, math, variable provenance, calibration, references |
| `docs/HOW-IT-WORKS.md` | The system explained simply (physics to data cleaning to how to read every chart; in Spanish, for non-technical audiences) |
| `docs/DATA-PIPELINE.md` | End-to-end methodological framework: every stage from RF input to displayed pixel, with the exact math, the specific technology at each step, and the design rationale (in Spanish) |
| `docs/QUICKSTART-ZOMBIE.md` | Zombie-mode deployment guide: what's already done, one-time fix actions, daily bring-up, from-scratch and portable-kit paths (in Spanish) |
| `docs/DEPLOYMENT-ALTERNATIVES.md` | Alternative deployments: mosquitto native (no Docker) per platform, the X230/Fedora zombie guide, macOS setup, Android/iOS as viewers, multi-platform compatibility matrix |
| `odd/` | ODD feature tracking |

## Features

- **Multi-ESP32 fusion**: each board publishes to its own topic
  (`esp32/<id>/csi/raw`); the backend keeps one DSP pipeline per link and
  fuses per physiological band (best in-band SNR wins heart and respiration
  independently; presence aggregates conservatively).
- **Dead-link failover within 20 s** *(review-hardened, 2026-10-14)*: a
  silent link — including the polled primary — expires and stops winning
  fusion, so live backups take over instead of a frozen estimate winning
  forever.
- **`MQTT_TOPIC` env override restored** *(2026-10-14)*: an explicit value
  replaces the whole subscription list (baseline contract); the default
  keeps the multi-link patterns. The GUI also repaints its raw trace during
  the window-fill phase instead of freezing ~15 s until the first estimate.
- **Body presence/motion** (Absent / Still / Moving) from the mean CSI
  amplitude, plus a calibratable RSSI log-distance estimate (can be disabled
  with `CSI_RSSI_REF_DBM=none`).
- **LAN web viewer** for phones (aiohttp, zero CDN) and a **portable
  one-click kit** (`scripts/build-portable-kit.ps1`: broker + viewer exe)
  for any Windows PC — with LAN-IP detection that falls back to 10.x/172.x
  and warns instead of printing an empty URL.
- **Hardware-free dry-run**: `scripts/simulate_esp32.py` scenarios
  (resting / moving / absent; multi-node via `--device-id`).
- **Quality**: 50 automated headless tests (`pytest`) and a native 4-lens
  review process (risk / resilience / readability / reliability) whose
  findings and correction cycles are tracked in `odd/tasks/` and
  `CHANGELOG.md`.

## Quick start

1. `docker compose up -d` (broker) — and open the dev firewall once from an admin PowerShell: `powershell -ExecutionPolicy Bypass -File .\scripts\firewall-rules.ps1` (scopes ports 1883/8080 to the local subnet; the network must be marked Private — DEPLOYMENT.md §2)
2. Configure `src/esp32/main/config.h` (WiFi + broker IP)
3. Build/flash from WSL: `idf.py set-target esp32s3 && idf.py build && idf.py -p /dev/ttyACM0 flash monitor`
4. Windows (PowerShell): `cd \\wsl.localhost\Ubuntu\home\tilin\dev\projects\c++\sensorproject\backend` (the repo lives in the WSL filesystem; Windows reaches it through this share — no files are copied), then `python -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt` — full recipe: `DEPLOYMENT.md` §8
5. Dry-run: `python ..\scripts\simulate_esp32.py --scenario moving` + `python main.py` (scenario options: `resting`, `moving`, `absent`; add `--device-id <id>` per node to dry-run multi-ESP32 links)
6. Phone view: `python web_viewer.py` and open `http://<PC-LAN-IP>:8080` on any phone on the same Wi-Fi (DEPLOYMENT.md §9)
7. Live: see `DEPLOYMENT.md`

## Signal processing

- The firmware sends per-subcarrier amplitudes `sqrt(I^2+Q^2)` as compact CSV at ~10 Hz.
- The backend keeps a 15 s sliding window, selects the subcarrier with the
  strongest spectral peak per physiological band (respiration 0.1-0.5 Hz,
  heart 0.8-2.0 Hz), bandpass-filters it and reports the dominant frequency
  (Hann-windowed FFT + quadratic peak refinement) with an SNR quality gate.

Presence and body motion are classified from the mean CSI amplitude: an empty
room is noise-flat (window std below a threshold), gross body movement raises
the 0.5–3.0 Hz motion-band RMS; mean RSSI additionally yields a coarse
log-distance link-distance estimate (calibratable). Amplitude-only
single-antenna CSI cannot provide coordinates or angle — see
docs/SIGNAL-MODELING.md.

## Tests

```bash
cd backend
python -m pytest tests -q
```

50 automated headless tests: vitals estimator, packet parser, motion
analyzer, multi-ESP32 link manager (routing, fusion, expiry, locks),
config surface (env overrides incl. `MQTT_TOPIC`) and the web-viewer
pipeline.

## License

MIT — see [LICENSE](LICENSE).
