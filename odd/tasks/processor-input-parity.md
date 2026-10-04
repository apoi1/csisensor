# Feature: processor-input-parity — harden VitalsProcessor inputs for continuous monitoring

Parent: `odd/tasks/review-followups.md` (closed approved; its review left the
advisories this feature now fixes).

## Purpose

The review-followups native review (lineage review-18150f68e8795201, approved,
authority burned) recorded two related advisories on `VitalsProcessor`:

- **R1-processor-window-nonfinite-poison** (WARNING, risk,
  `backend/vitals_processor.py:68-69`) — `push()` accepts non-finite
  amplitudes and poisons the whole window: mean/std/FFT all become NaN, the
  estimate dies, and the monitoring stream goes blank until the window
  rolls over.
- **R4-nan-inputs-processor-parity** (WARNING, resilience,
  `backend/vitals_processor.py:58`) — `MotionAnalyzer.push()` was hardened
  (R3-nan-inputs, T2 finding 1) but `VitalsProcessor.push()` kept the
  unguarded contract; the two sliding windows now disagree on input
  validity.

The user's stated priority: **continuous real-time monitoring**. A corrupt
packet must never interrupt the stream: drop it, keep the window clean.

## Design

Mirror the already-reviewed `MotionAnalyzer.push()` contract exactly, so
both windows share one input policy:

1. Drop packets whose amplitudes are empty or contain any non-finite value
   (one NaN subcarrier poisons mean/std/FFT and the heatmap/spectrogram).
2. Drop packets with non-finite timestamps (they cannot order the window).
3. Drop packets with duplicate or regressed timestamps (the FFT assumes a
   uniform sample grid; out-of-order samples corrupt the spectrum).
4. `_bandpass()`: when Nyquist cannot express the band (`hi <= lo` after
   clamping) return the input unfiltered instead of crashing in
   `scipy.butter` — the vitals twin of the already-fixed R3-low-fs-crash
   guard in `MotionAnalyzer._motion_rms()`, in the same continuity spirit.

Non-goals: sanitizing mixed packets (a corrupt CSI packet is dropped whole,
not repaired); changing the parser; touching the GUI.

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | Guard VitalsProcessor.push() + _bandpass() + tests | done | push() drops empty/non-finite amplitude packets, non-finite timestamps, duplicate/regressed timestamps (parity with MotionAnalyzer); _bandpass() returns the detrended signal when the band is unobservable at fs (vitals twin of R3-low-fs-crash guard); 4 new tests referencing the advisory IDs |
| 2 | Verification (pytest + py_compile) | done | 26/26 backend tests pass (2.16 s); py_compile clean on vitals_processor.py + test_vitals_processor.py |
| 3 | Native review (RDD on) of the committed range | done | Lineage review-c9f1784a4b88205f (tier medium, 131 lines, single review-reliability lens, budget 66): captured via child relay (kimi-k3 per standing preemptive switch, reverted after); terminal closure APPROVED with zero findings and zero corrections; acknowledge-approved executed, authority burned (revision sha256:577faf0c…, evidence gentle-ai.review-acknowledged/v1) |
| 4 | Merge to master + close report | done | fast-forward master 6470063 → c785c66 (local repo, no remote); feature doc committed with the review record |

## Verification evidence

- 26/26 backend tests pass (`python3 -m pytest tests -q`, 2.16 s); py_compile clean on `backend/vitals_processor.py` and `backend/tests/test_vitals_processor.py`.
- Native review APPROVED (2026-10-04): single-lens (review-reliability) tier-medium transaction over the committed range master (tree 40169cd8) → c785c66; the capture closed approved with **zero findings**; no correction consumed (budget 66 untouched); authority burned via acknowledge-approved (consumed revision sha256:577faf0ca4e7a0d4afeadb8ac215b4cbac3ad7bbc1fcbfa9ff657a6113bf6a3c, evidence gentle-ai.review-acknowledged/v1).
- Delivery: ordinary repository policy — fast-forward local merge to master executed (user-authorized integration step); no remote exists yet.
