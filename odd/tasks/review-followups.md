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
| 6 | Native review (RDD on) + close report | done | Lineage review-18150f68e8795201 (tier high, 375 lines): 4 lens slots + read-only refuter captured via child relay pattern; APPROVED; the single CRITICAL (R3-sosfiltfilt-padlen-crash) was refuted; 10 advisory findings recorded below as separate later work; acknowledge-approved executed, authority burned (consumed revision sha256:f2f9d150…, evidence gentle-ai.review-acknowledged/v1); no correction consumed (budget 188 untouched); delivery under ordinary repository policy |

## Verification evidence

- Review candidate: committed range df6d2cd (tree b690a447) → aa0e3b0, 10 files, 375 changed lines.
- Native review APPROVED (2026-10-03). Lens artifacts all admitted: review-risk (glm-5.3, 40311-byte prompt, 5990-byte result, rart1_c9191b41…), review-resilience (kimi-k3 per user's original routing, 40325-byte prompt, 4006-byte result), review-readability (glm-5.3, 11373-byte result, rart1_608b354d…), review-reliability (kimi-k3 per user-approved preemptive switch, 3624-byte result, rart1_49c65ccc…; ~/.pi/gentle-ai/models.json reverted to glm-5.3 after capture).
- Read-only refuter batch (glm-5.3) closed the review approved and refuted the one CRITICAL finding (R3-sosfiltfilt-padlen-crash, reliability lens).
- Acknowledge-approved executed and authority burned: consumed revision sha256:f2f9d150cc888cb4fda5169d5acc0a454212ea22f6ef1473f1e4aab57cc21419, burn evidence gentle-ai.review-acknowledged/v1.
- Regression check vs the 11 findings this feature fixed: none of them was re-raised; the reviewers found no blocker on the fixed areas.

## Advisory findings from this review (separate later work, non-blocking)

Per the closure receipt: every finding below is non-blocking; none opened a correction, none reopens this review, and no correction transition is offered for this candidate.

1. **R1-processor-window-nonfinite-poison** (WARNING, risk, `backend/vitals_processor.py:68-69`) — processor window can still be poisoned by non-finite amplitudes.
2. **R4-nan-inputs-processor-parity** (WARNING, resilience, `backend/vitals_processor.py:58`) — VitalsProcessor lacks the non-finite input guard MotionAnalyzer now has (parity gap).
3. **R2-config-env-parse-timing-split** (WARNING, readability, `backend/config.py:62-65`).
4. **R2-disable-sentinel-silent-fallback** (WARNING, readability, `backend/config.py:33-38`) — the empty/"none" disable sentinel falls back silently.
5. **R2-filter-padding-threshold** (WARNING, readability, `backend/motion_analyzer.py:137-139`).
6. **R2-single-ingest-policy-split** (WARNING, readability, `backend/gui.py:137-138`).
7. **R1-distance-guard-nonfinite-refs** (SUGGESTION, risk, `backend/motion_analyzer.py:175-176`).
8. **R2-matrix-assembly-duplication** (SUGGESTION, readability, `backend/vitals_processor.py:95-96`).
9. **R2-dead-numpy-import** (SUGGESTION, readability, `backend/tests/test_config.py:7`).
10. **R3-sosfiltfilt-padlen-crash** (CRITICAL, reliability, `backend/motion_analyzer.py:137-139`) — REFUTED by the refuter; recorded for traceability only.
