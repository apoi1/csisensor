# Feature: body-position-gui — Real-time body-position data + physics graphs + signal-modeling docs

Parent feature: `odd/track-wifisensing.md` (WiFiCSI tracking pipeline).

## Purpose

The PyQt5 GUI today shows heart rate (BPM), respiration rate (/min), per-band
SNR, and filtered vitals waveforms — but nothing about the person's body state.
This feature adds:

1. Real-time **body position/motion data**: presence state (absent/still/moving),
   motion level, mean RSSI, and a coarse RSSI-calibrated distance estimate.
2. **Physics graphs with formal notation**: subcarrier CSI heatmap, STFT
   spectrogram with physiological bands, motion-energy trace — each panel
   annotated with the governing formula using formal symbol names
   (matplotlib mathtext).
3. **Documentation** (`docs/SIGNAL-MODELING.md` + Spanish update in
   `docs/PROJECT-ARCHITECTURE.md` + README): physical/mathematical principles,
   variable provenance (which packet field/config/constant feeds each formula),
   calibration techniques (empty-room baseline, motion thresholds, RSSI
   log-distance model, angle/AoA constraints), how the app evaluates body
   position, and reference libraries/repositories/research citations.
4. Simulator scenarios (`resting`/`moving`/`absent`) to demo the panel without
   hardware.

## Physical constraint (honesty boundary)

The firmware publishes amplitude-only CSI `|H_k| = sqrt(I_k^2 + Q_k^2)` over a
single antenna link. Therefore the app cannot compute geometric coordinates,
AoA, or phase-based displacement. "Body position" is delivered as
presence/motion/stillness classification plus a coarse RSSI-distance estimate
(log-distance path-loss model). Angle/AoA and true coordinates are documented
as calibration techniques and future work (require phase/IQ export or
multi-antenna / multi-device geometry), with references.

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | Motion/presence analysis module + config + tests | done | commit 0c0742d on feature/body-position-gui; 12/12 backend tests pass (numpy/scipy/pytest installed in WSL via --break-system-packages; PEP 668 note). MotionEstimate(state, motion_rms, window_std, rssi_dbm, distance_m, n_samples); env knobs CSI_ABSENT_STD/CSI_MOVING_RMS/CSI_RSSI_REF_DBM/CSI_REF_DISTANCE_M/CSI_PATH_LOSS_N |
| 2 | GUI body-position panel + physics graphs with mathtext formulas | done | commit fca5d8f; 2x3 figure, Body row, heatmap/spectrogram/motion panels, formulas in mathtext |
| 3 | Simulator scenarios (resting/moving/absent) | done | commit 462c4d0; functional check vs real MotionAnalyzer: resting→Still, moving→Moving during episodes, absent→Absent; py_compile OK; backend 12/12 tests pass |
| 4 | Docs: SIGNAL-MODELING.md + PROJECT-ARCHITECTURE.md + README + DEPLOYMENT.md | done | SIGNAL-MODELING.md: 10 sections, 27-row provenance table, 15 math blocks, 10 verified references; PROJECT-ARCHITECTURE.md (Spanish) new GUI/position section; README scenarios+docs row; DEPLOYMENT.md updated with scenarios, Body row and calibration env vars |
| 5 | Verification (pytest + py_compile) + work-unit commits | pending | one commit per task on feature/body-position-gui |
| 6 | Native review (RDD on) + close report | in_progress | Split per user decision. Big lineage review-ea72262693c65479 ABANDONED (quarantined, operator_disposition). DOCS transaction review-33be7090818ba8a8: APPROVED, zero lenses (non_executable_only), authority burned. T2 backend (worktree ../sensorproject-review-t2-backend, commit 0c0742d, tier medium, 1 lens reliability): slot declared unachievable_lens_slot — 22333-byte prompt still exceeded the ~919 s relay bound. T3 (GUI+simulator) not started (same wall). Continuation: restart pi with GENTLE_PI_REVIEW_RELAY_PI_TIMEOUT_MS raised (e.g. 3600000, ceiling 7200000), then run the persisted withdraw command to re-offer the reliability reviewer |

## Reference data (verified via web search)

- espressif/esp-csi — https://github.com/espressif/esp-csi (CSI apps: indoor positioning, human detection)
- StevenMHernandez/ESP32-CSI-Tool — https://github.com/StevenMHernandez/ESP32-CSI-Tool
- Zhang et al., "Human Respiration Detection with Commodity WiFi Devices: Do User Location and Body Orientation Matter?", UbiComp 2016 (Fresnel model, body location/orientation)
- Zeng et al., "FullBreathe", IMWUT 2018 — CSI phase+amplitude complementarity
- arXiv:1908.05108 — WiFi-based real-time breathing/heart monitoring during sleep
- PMC9375645 — Survey on vital-signs monitoring based on Wi-Fi CSI
- Log-distance path loss model L(d) = L(d0) + 10·n·log10(d/d0) + X_sigma

## Verification evidence

- `cd backend && python3 -m pytest tests -q` → 12 passed (6 pre-existing + 6 motion) on Python 3.14 with numpy 2.5.3 / scipy 1.18.1 / pytest 9.1.1.
- `python3 -m py_compile` OK on motion_analyzer.py, config.py, gui.py, main.py, simulate_esp32.py.
- Simulator scenarios functionally checked against real MotionAnalyzer: resting → Still, moving → Moving during episodes, absent → Absent.
- DEPLOYMENT.md verified against docker-compose.yaml (container_name wifisensing_mosquitto, port 1883), mosquitto.conf (allow_anonymous true), requirements.txt pins and main.py CLI flags.
