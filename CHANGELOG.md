# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog (https://keepachangelog.com/en/1.1.0/).
No tagged releases yet; recent history lives under Unreleased.

## [Unreleased]

### Added (2026-10-04, later)
- **Multi-ESP32 links**: firmware publishes per-device topics
  (`esp32/<id>/csi/raw`, id = last 3 MAC bytes); backend gains
  `link_manager.py` (wildcard subscription + per-link DSP pipelines),
  per-band max-SNR fusion, conservative presence aggregate, `--device-id`
  simulator flag for multi-node dry-runs. Legacy flat topic still works.

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
- **Multi-ESP32 link hardening and resilience corrections** from the
  native-review rounds: subscriber registers exactly the patterns it
  subscribes (no hidden single-topic state), `MAX_LINKS=16` registry cap
  with always-admit LRU eviction of the stalest link, 20 s stale-link
  expiry pruned before every fusion pass, full registry lock coverage,
  simulator `--topic` precedence, checked `esp_read_mac` in the firmware
  (commits `f01f169`, `7ef3019`, `18aaff8`).
- **GUI status bar** now shows the fused primary (heart-winning) link
  instead of the alphabetically-first link; `n_links()`/`primary_link()`
  accessor reads are locked; always-admit ingest docstring and dead
  rejection branch removed (commit `f41281a`).
- **Docker broker image bakes `mosquitto.conf` in at build time** (`build:`
  instead of a runtime bind mount): `docker compose up` now works from
  PowerShell over the `\wsl.localhost` share even when WSL's distro-mount
  services are unavailable (Windows 10 + WSL 3.x); editing the config
  requires `docker compose up -d --build mosquitto`. The obsolete compose
  `version:` key was removed. Also adds `scripts/firewall-rules.ps1`, a
  paste-safe one-shot admin script that (re)creates both dev firewall
  rules correctly scoped — long console pastes had silently produced an
  over-broad all-TCP rule.
- **DEPLOYMENT §8 documents the UNC execution-policy trap**: scripts on the
  `\\wsl.localhost` share are a remote zone for PowerShell, so
  `Activate.ps1` fails as "not digitally signed" even under `RemoteSigned`;
  the guide now shows the activation-free path
  (`..\.venv\Scripts\python.exe <script>`).

### Earlier
- Initial end-to-end pipeline: ESP32-S3 firmware (native ESP-IDF CSI API,
  ~10 Hz traffic-ping sampling, CSV-over-MQTT), Mosquitto broker (Docker),
  Python backend (paho-mqtt <2.0, FFT vital-signs estimator with per-band
  best subcarrier and SNR gate), PyQt5 GUI, synthetic simulator, and the
  WSL/Windows deployment guide.
