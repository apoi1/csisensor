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
| 5 | Verification (pytest + py_compile) + work-unit commits | done | One commit per task on feature/body-position-gui: 0c0742d (motion analyzer), fca5d8f (GUI), 462c4d0 (simulator), docs commits through 3e596b6; plus fix dafca66 (native-review correction). 12/12 backend tests + py_compile re-verified after the correction |
| 6 | Native review (RDD on) + close report | done | All three transactions APPROVED + authority burned. Docs review-33be7090818ba8a8: APPROVED zero lenses, burned. T2 review-5ea1f18cd5c9bbac: APPROVED + burned; 5 informational follow-ups (R3-nan-inputs W motion_analyzer.py:70-79, R3-small-window-fallback W :120-121, R3-low-fs-crash W :122-125, R3-distance-guard-coverage S :155-158, R3-ranging-defaults-unreachable S config.py:41-42). T3 review-169547e57921d0a4: 4 lens slots captured via sequential gentle-shell children (env GENTLE_PI_REVIEW_RELAY_PI_TIMEOUT_MS=7200000, --model nvidia/z-ai/glm-5.3); review-reliability required a user-approved reviewer switch to nvidia/moonshotai/kimi-k3 (glm-5.3 died twice at ~3610 s stream cut on that prompt; ~/.pi/gentle-ai/models.json reverted afterwards). Closed in correction_required → correction plan 2 diff lines → fix commit 2df2f52 in the review worktree (detached) → targeted validation APPROVED → acknowledge-approved executed (authority burned; delivery under ordinary repository policy). Fix delivered on the branch as dafca66; 12/12 tests pass. 6 advisory findings (non-blocking, separate later work): R2-decay-rate-coupling S scripts/simulate_esp32.py:84, R2-scenario-baseline-duplication S scripts/simulate_esp32.py:96, R2-motion-band-unsourced W backend/gui.py:85, R2-title-escape-literal W backend/gui.py:85, R2-triple-push-mirror W backend/gui.py:134-138, R4-gui-vstack-crash W backend/gui.py:229. Review worktrees t2/t3 removed. Mobile work remains paused by user decision |

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
- Post-correction (2026-10-03): fix dafca66 ("if moving:" applies the decaying motion offset to the published stream) cherry-picked to feature/body-position-gui; 12/12 backend tests pass and py_compile OK on scripts/simulate_esp32.py.
