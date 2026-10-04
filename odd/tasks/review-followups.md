# Feature: review-followups — non-blocking findings from the body-position-gui reviews

Parent feature: `odd/tasks/body-position-gui.md` (complete; master = df6d2cd).

## Purpose

The native reviews of body-position-gui closed approved with authority burned, leaving 11
advisory (non-blocking) findings recorded as explicit follow-up work. This feature fixes
them all:

T2 backend (review-5ea1f18cd5c9bbac, informational):
1. **R3-nan-inputs** (W, `backend/motion_analyzer.py:70-79`) — `push()` accepts
   non-finite amplitudes/RSSI and poisons the whole window (NaN std/RMS breaks
   classification).
2. **R3-small-window-fallback** (W, `motion_analyzer.py:120-121`) — below 30 samples
   the motion bandpass is skipped and the full-band detrended std is compared against
   the MOVING threshold, silently misclassifying breathing content as motion.
3. **R3-low-fs-crash** (W, `motion_analyzer.py:122-125`) — with fs low enough that the
   band upper edge falls below 0.5 Hz, `scipy.butter` raises and `estimate()` crashes.
4. **R3-distance-guard-coverage** (S, `motion_analyzer.py:155-158`) — `_distance()`
   guards None but not non-finite RSSI or a non-positive reference distance.
5. **R3-ranging-defaults-unreachable** (S, `backend/config.py:41-42`) — the config
   surface can only produce floats, so the analyzer's "ranging disabled" (None) state
   is unreachable; uncalibrated ranging is always active.

T3 GUI+sim (review-169547e57921d0a4, advisory):
6. **R2-decay-rate-coupling** (S, `scripts/simulate_esp32.py:84`) — the per-packet
   `*= 0.90` decay couples the time constant to the publish rate.
7. **R2-scenario-baseline-duplication** (S, `scripts/simulate_esp32.py:96`) — the
   resting baseline formula and constants are duplicated inline across branches.
8. **R2-motion-band-unsourced** (W, `backend/gui.py:85`) — the motion-panel title
   hardcodes "band 0.5-3.0 Hz" instead of sourcing the analyzer's band definition.
9. **R2-title-escape-literal** (W, `backend/gui.py:85`) — `r"...0.5\u20133.0 Hz"`
   renders the literal characters `\u2013` (raw string defeats the escape).
10. **R2-triple-push-mirror** (W, `backend/gui.py:134-138`) — every packet is pushed
    into a hand-rolled display mirror besides the processor/analyzer, duplicating the
    window with a third drop policy.
11. **R4-gui-vstack-crash** (W, `backend/gui.py:229`) — `np.vstack` over mirrored rows
    crashes the GUI when packets with different subcarrier counts mix in one window.

## Design notes

- Single window source: the physics panels must read `VitalsProcessor` (which already
  keeps per-packet rows), not a parallel mirror; ragged windows become impossible by
  resetting the processor window when the subcarrier count changes at ingest.
- The motion band moves to a public `MOTION_BAND_HZ` constant so the GUI title sources
  the same definition the classifier uses.
- Ranging keeps its current defaults but gains a reachable disabled state via env
  (empty or "none" -> None), documented in DEPLOYMENT.md.
- Simulator decay becomes time-based (tau reproducing the historical 0.90/packet at
  the default 10 Hz rate), independent of `--rate`.

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | motion_analyzer robustness (findings 1-4) + tests | done | commit on feature/review-followups; 17/17 backend tests; MOTION_BAND_HZ now public (feeds finding 8) |
| 2 | config: reachable ranging-disable (finding 5) + test + DEPLOYMENT.md | done | empty/"none" -> None via _env_float_opt + default_factory; test_config.py; DEPLOYMENT.md note; 20/20 backend tests |
| 3 | GUI/processor: single window source, sourced band, escape fix, ragged-row policy (findings 8-11) | done | display mirror deleted; proc.current_matrix(); width-change reset; MOTION_BAND_HZ-sourced title; 22/22 backend tests; gui.py imports headless |
| 4 | simulator: time-based decay + baseline dedup (findings 6-7) | done | MOTION_DECAY_TAU_S=0.95 s (0.9001/packet @10 Hz, per-second decay rate-invariant); named constants + resting_baseline() helper |
| 5 | Verification (pytest + py_compile) | done | 22/22 backend tests; py_compile clean on all touched files; decay equivalence checked numerically |
| 6 | Native review (RDD on) + close report | pending | new commits on feature/review-followups |

## Verification evidence

(pending)
