# sensorproject - WiFi-CSI Vital Signs (ESP32-S3 + Python)

Real-time experimental vital-sign tracking (heart rate and respiration
estimation) from **WiFi CSI** (Channel State Information) captured by an
ESP32-S3, streamed over MQTT to a PyQt5 desktop application with FFT-based
signal processing.

```
ESP32-S3 firmware (C++/ESP-IDF) ──MQTT──► Mosquitto (Docker) ◄── Python backend (paho-mqtt + scipy FFT) ──► PyQt5 GUI (vitals + body presence/motion)
```

> Research/educational project. **Not a medical device.**

## Layout

| Path | What |
|---|---|
| `src/esp32/` | ESP-IDF v5.x firmware: native CSI capture -> queue -> MQTT publish |
| `backend/` | Python: MQTT subscriber, FFT vitals processor + motion analyzer, PyQt5 GUI (real-time heart rate, respiration, body presence/motion "Body" row; physics panels: subcarrier heatmap, spectrogram, motion energy — with formula annotations), unit tests |
| `scripts/simulate_esp32.py` | Synthetic CSI publisher to test the backend without hardware |
| `docker-compose.yaml` + `docker/mosquitto/` | Local Mosquitto broker |
| `DEPLOYMENT.md` | **Step-by-step deployment guide (WSL + Windows)** |
| `docs/` | Tools list and project notes |
| `docs/SIGNAL-MODELING.md` | Signal model: physics, math, variable provenance, calibration, references |
| `odd/` | ODD feature tracking |

## Quick start

1. `docker compose up -d` (broker)
2. Configure `src/esp32/main/config.h` (WiFi + broker IP)
3. Build/flash from WSL: `idf.py set-target esp32s3 && idf.py build && idf.py -p /dev/ttyACM0 flash monitor`
4. Windows: `cd backend && python -m venv .venv && .\.venv\Scripts\Activate && pip install -r requirements.txt`
5. Dry-run: `python ..\scripts\simulate_esp32.py --scenario moving` + `python main.py` (scenario options: `resting`, `moving`, `absent`)
6. Live: see `DEPLOYMENT.md`

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

## License

MIT — see [LICENSE](LICENSE).
