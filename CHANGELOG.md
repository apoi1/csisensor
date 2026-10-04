# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog (https://keepachangelog.com/en/1.1.0/).
No tagged releases yet; recent history lives under Unreleased.

## [Unreleased]

### Added (2026-10-04)
- LAN **web viewer** for phones/tablets: `backend/web_viewer.py` serves a
  self-contained page (`backend/web_static/`) and broadcasts ~1 Hz
  snapshots over WebSocket to every browser on the LAN — no app install, no
  CDN, no firmware change; independent of the desktop GUI (aiohttp,
  requirements gained `aiohttp>=3.9`).
- Mosquitto **9001 MQTT-over-WebSocket listener** enabled
  (`docker/mosquitto/mosquitto.conf`) — the docker-compose mapping now
  serves a real listener for future browser clients.
- `VitalsProcessor` **input hardening** for continuous monitoring:
  packets with empty/non-finite amplitudes, non-finite timestamps, or
  duplicate/regressed timestamps are dropped (parity with the hardened
  `MotionAnalyzer`); the bandpass degrades to the detrended signal when
  Nyquist cannot express the band instead of crashing.
- Maintenance docs: `CONTRIBUTING.md` (workflow, maintenance policy) and
  this changelog.

### Added (2026-10-03)
- **Body-position GUI**: real-time presence/motion "Body" row and physics
  panels (subcarrier heatmap, spectrogram with physiological band markers,
  motion-energy trace) with formula annotations; simulator scenarios
  `resting|moving|absent`; `docs/SIGNAL-MODELING.md` (signal model,
  variable provenance, calibration guidance).
- RSSI **log-distance ranging**, calibratable via `CSI_RSSI_REF_DBM`,
  `CSI_REF_DISTANCE_M`, `CSI_PATH_LOSS_N`; an empty value or `none`
  disables the estimate until calibrated.

### Fixed
- Eleven advisory findings from the body-position-gui native reviews
  (`feature/review-followups`): motion-analyzer non-finite/distance guards
  and low-fs fallback, reachable ranging-disable via config, GUI
  single-window source with band-sourced title and ragged-row reset,
  simulator time-based decay (`MOTION_DECAY_TAU_S`) and deduplicated
  resting baseline.
- ESP32 simulator now publishes the decaying motion offset between episodes
  (native-review CRITICAL correction, `dafca66`).

### Earlier
- Initial end-to-end pipeline: ESP32-S3 firmware (native ESP-IDF CSI API,
  ~10 Hz traffic-ping sampling, CSV-over-MQTT), Mosquitto broker (Docker),
  Python backend (paho-mqtt <2.0, FFT vital-signs estimator with per-band
  best subcarrier and SNR gate), PyQt5 GUI, synthetic simulator, and the
  WSL/Windows deployment guide.
