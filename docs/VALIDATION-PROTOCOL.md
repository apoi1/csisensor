# Validation Protocol — proving the sensor reads a body, not noise

Why this document exists: the displayed estimates fluctuate, rooms are
noisy, and a fair question is *"how do I make the readings more stable,
and how do I empirically justify that they come from a person and not
from ambient noise?"* This protocol is the empirical answer: a sequence
of falsifiable tests. If the system passes them, the signal is yours.

Companion docs: SIGNAL-MODELING.md (the physics and the processing
chain), DEPLOYMENT.md section 10 (live test procedure).

## 1. Setup for stability (do this before every measurement)

1. **Geometry first.** The measured radio link is **board ↔ router** —
   the subject perturbs THAT line, not the board alone. Sit 0.5–2 m from
   the board with the straight line board→router passing close to your
   torso (first Fresnel zone, SIGNAL-MODELING.md section 3), in line of
   sight, no walls or large metal objects in between.
2. **Environment.** No other people or pets moving in the room, no
   fans/oscillating devices, keep some distance from microwaves and
   other 2.4 GHz sources.
3. **Time and averaging.** Sit still for at least 60 s. Treat each
   reading as the **median of the last 5–10 displayed estimates** —
   single-second readings are samples, not the measurement.
4. **Honesty gate.** Raise the SNR gate to reject marginal windows:
   `set CSI_MIN_SNR_DB=9` before launching the GUI/viewer (default 6).
   A "-" in the display is information; a fluctuating number from a
   below-gate window is noise dressed as data.
5. **Reference floor.** If the SNR shown in the status meta line stays
   below ~9–10 dB, reposition (move the board, change the link geometry)
   instead of trusting a marginal window.

## 2. Falsification test — the empty room (noise cannot fake vitals)

Leave the room **completely empty** for 5 minutes with everything running
(board powered, broker, GUI).

- Expected: `Body: Absent`, both rates showing "-" (the window fills but
  the in-band SNR stays below the gate — an empty room's channel is
  noise-flat).
- Record the outcome. If vitals appear in an empty room, the environment
  is producing a fake tone (a fan, an oscillating device): find it or
  move the link. This test is the negative control for every other test.

## 3. Controlled-breathing test — the strongest empirical proof

You control the input; if the sensor tracks it, the signal is yours.

1. Set a metronome app to 6 breaths/min (5 s inhale, 5 s exhale) and
   breathe following it for 2 minutes.
2. Expected reading: **~6 /min** within the documented ±3 tolerance.
3. Change the metronome to 12 breaths/min and breathe for another 2 min.
4. Expected: the displayed respiration **follows the change** to ~12/min.

This is a phase-lock between a known physiological input and the
measurement — noise has no reason to follow your metronome. The ±3/min
tolerance is the same spec the synthetic unit tests enforce
(tests encode 60 bpm / 15 per min ± their gates).

## 4. Movement-response test

Walk around for a few seconds → the `Body` row must switch to `Moving`
and the vitals reset (the window is re-contaminated by gross motion);
sit still → `Still` and stabilization within ~15–20 s. A state machine
that responds to YOUR body — and resets on YOUR movement — is
sensor-driven by construction.

## 5. Reference comparison — quantitative accuracy

Run a simultaneous reference during a 5-min still period:

- Phone pulse oximeter / smartwatch / chest strap (any of them).
- Write down pairs (reference, system) once per minute for 5 minutes.
- Expected: heart within **±5 bpm** and respiration within **±3/min**
  (the tolerances the test suite encodes).

## 6. Repeatability

Repeat section 3 (or 5) **three times** in the same setup. Consistent
results within tolerance = the measurement is reproducible; drifting
results = the link geometry is unstable (back to section 1).

## 7. Reading fluctuation honestly

- Real physiology fluctuates: ±2–3 bpm beat-to-beat variation is normal.
- Ambient noise ADDS variance; it does not create sustained in-band
  tones that track your breathing (section 3) or vanish when you leave
  (section 2).
- The tools for stability are geometry, the SNR gate, and median
  averaging — in that order of impact.

## 8. What to record (the experiment log)

For each session note: date/time, room, board position (relative to
router and subject), subject distance, `CSI_MIN_SNR_DB`, the 5-min empty
room outcome, metronome readings (both paces), reference pairs if any.
With that log, any future accuracy work (second node, weighted fusion)
has a baseline to beat.
