# Changelog

All notable changes to this project are documented here.
Format based on Keep a Changelog (https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added (2026-10-14)
- **docs/QUICKSTART-ZOMBIE.md**: the zombie-mode deployment guide — state-aware
  (what's already done and never needs repeating), the one-time actions from
  the recent fixes (scoped firewall re-run + Private profile, GUI restart,
  portable-kit rebuild), the 4-step daily bring-up, the from-scratch and
  portable-kit paths, the common-failure quick table, and the docs index.
- **docs/DATA-PIPELINE.md**: the end-to-end methodological framework — every
  stage from the RF input to the exact displayed pixel, with the precise
  math at each step (detrend/Hann/rfft/parabolic interpolation/SNR vs
  median, Butterworth SOS zero-phase, motion RMS, log-distance ranging,
  multi-link fusion), the specific technology that executes it
  (ESP-IDF CSI API, lwIP ping, esp-mqtt, paho-mqtt, queue, numpy, scipy,
  PyQt5, Matplotlib Qt5Agg, aiohttp), the design rationale for every
  decision (why median not mean, why sosfiltfilt not a one-way filter, why
  QoS 0, why draw_idle, why pinned axes, why viridis/magma), and the
  final on-screen-element to exact-source mapping table. Every claim
  verified against the source files.
- **GUI physical-measures readout**: every value axis now carries its
  physical measure and unit (mean CSI amplitude, filtered amplitude,
  motion RMS in [a.u.]), the heatmap and spectrogram titles state their
  dB scale, and a persistent strip under the canvas lists every quantity
  behind the panels (ā(t), x(t) bands, |H_k|, X(τ,f), M_rms, σ_window,
  RSSI, link distance, SNR) with units and source panel.
- **docs/HOW-IT-WORKS.md**: the "for-kids-but-technical" explainer — the
  electromagnetic spectrum and multipath physics behind the ESP32, the
  packet/OFDM/CSI measurement chain, the 9-step data-cleaning pipeline,
  what each of the 6 charts measures (with units) and how to interpret
  it, expected results and honest limits, plus three ready-made
  sentences to explain the system to non-technical audiences.

### Fixed (2026-10-14) — native-review correction cycle (lineage `review-7d8e6420d3b9ab94`)
- **`MQTT_TOPIC` honored again** (findings R1-002 / R2-MqttTopicEnvSilentlyDead
  / R3-002): `Config.topic_patterns` now derives from the `MQTT_TOPIC` env
  var — an explicit override replaces the whole subscription list (baseline
  contract), while unset/legacy-default expands to the multi-link patterns;
  the CLI `--topic` flag still wins. Previously the env value was read but
  silently ignored after the multi-link rewiring.
- **Stale-link expiry now works for the primary link** (R3-001 /
  R4-StalePrimaryNeverExpires): `_pipelines()` refreshes `_last_seen` on
  ingest and registration only — the polled read accessors
  (fill/capacity/current_matrix/current_window) no longer keep a silent
  primary alive: a dead primary expires after `LINK_STALE_S` and fusion
  fails over to live links.
- **GUI paints during the window-fill phase** (R2-RedrawRawNoLongerDraws /
  R3-005 / R4-FillPhaseCanvasFrozen): `_redraw_raw()` schedules its own
  `draw_idle()`, so the raw trace repaints from the first packet instead
  of freezing for ~window_seconds until the first full estimate.
- **Registry lock coverage completed** (R1-004 / R2-LinkIdsLockContractTrap
  / R3-003): `link_ids()` and `evictions()` take the lock; `_primary_proc()`
  uses an internal locked helper (a naive lock would deadlock
  fill()/capacity()); `motion_estimate()` captures `_primary` under the
  lock instead of reading it after release.
- **LRU eviction clears `_primary`** (R3-004): evicting the primary link can
  no longer leave a dangling id that resurrects it as an empty ghost
  pipeline on the next read.
- **Deployment hygiene** (R1-003 / R1-005 / R2-FlashSize4MBUnexplained /
  R3-006): dev firewall rules are scoped to `-RemoteAddress LocalSubnet
  -Profile Private`; the portable kit README carries the
  auth-before-exposure note; the kit's LAN-IP detection now falls back to
  10.x/172.x with an explicit warning instead of printing an empty URL;
  `flash-board.ps1` exposes `-FlashSize` (default 4MB, matching
  `sdkconfig.defaults`; the board carries 16 MB per the bring-up notes —
  raise both together); LAN IP and board MAC scrubbed from the task notes.
  Suite: 50/50.

## [0.1.0] - 2026-10-12

### Added (2026-10-12)
- **Portable web viewer**: `csi-web-viewer.exe` built with PyInstaller
  (`--onefile`, `web_static` bundled) runs the viewer on any Windows x64
  PC without Python. Only ONE web viewer can hold port 8080 at a time
  (the Python script OR the exe, never both); the desktop GUI is an
  independent MQTT consumer and does not serve the phone page. Build
  artifacts (`dist/`, `*.spec`) are gitignored.
- **GUI repaint throttling**: full-canvas repaints run at the 1 Hz
  estimate cadence instead of the 5 Hz data tick, with pinned time axes
  and y-only autoscaling — a measurably smoother interface with the same
  data path.
- **Zombie-proof .cmd wrappers** for the PowerShell tools
  (`build-portable-kit.cmd`, `flash-board.cmd`, `firewall-rules.cmd`):
  batch files are not subject to the PowerShell execution policy, and
  their invocation line is short enough never to split on paste — the
  two failure modes observed live (long UNC paths wrapping mid-paste
  and the remote-zone "not digitally signed" rejection when a split
  line ran the .ps1 under the parent session's policy).
- **Portable system kit**: `scripts/build-portable-kit.ps1` assembles the
  "whole system portable" folder — the PyInstaller viewer exe plus the
  official Mosquitto broker binaries (copied from a one-time official
  install) and a one-click `start-system.bat` — so the complete pipeline
  runs on any Windows PC with no Python and no Docker.
- **docs/VALIDATION-PROTOCOL.md**: the empirical harness to prove the
  sensor reads a body — empty-room falsification, controlled-breathing
  phase-lock, movement response, reference comparison, repeatability —
  plus the stability checklist (link geometry, SNR gate, median
  averaging).

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
- **Firmware boot loop fixed** (`a1f6950`): the Wi-Fi driver ships without
  CSI support compiled in; `sdkconfig.defaults` now pins
  `CONFIG_ESP_WIFI_CSI_ENABLED=y` (without it `esp_wifi_set_csi(true)`
  aborts in a boot loop caught live via the board's serial log).
- **Live-data fix** (`a809832`): `LinkManager.ingest()` pushed a nonexistent
  `pkt.t_s`; real `CsiPacket`s carry `t_us` (device microseconds). The first
  live packet from the board crashed the GUI; the fix converts `t_us/1e6`
  once, all test fixtures now build real `CsiPacket`s, and a regression test
  feeds the real parser output through the real queue path. Suite: 46/46.
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
  (`.\.venv\Scripts\python.exe <script>`).
- **scripts/flash-board.ps1**: one-shot Windows flasher for the ESP32-S3
  (auto-detects the COM port of the native USB-Serial-JTAG, flashes the
  WSL-built artifacts over the `\\wsl.localhost` share). Flashing the S3
  through the usbipd WSL tunnel is unreliable — the chip reset re-enumerates
  its USB and drops the tunnel mid-handshake.

### Earlier
- Initial end-to-end pipeline: ESP32-S3 firmware (native ESP-IDF CSI API,
  ~10 Hz traffic-ping sampling, CSV-over-MQTT), Mosquitto broker (Docker),
  Python backend (paho-mqtt <2.0, FFT vital-signs estimator with per-band
  best subcarrier and SNR gate), PyQt5 GUI, synthetic simulator, and the
  WSL/Windows deployment guide.
