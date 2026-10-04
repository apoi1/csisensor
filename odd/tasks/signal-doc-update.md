# Feature: signal-doc-update — literature metrics, variable origins, multi-link and medical sections

Parent: user request 2026-10-04 — "actualizar la documentación con todos
estos hallazgos, métricas, técnicas, matemáticas, física, teoría,
referencias y antecedentes nuevos, además explicar de dónde salen estos
datos y de dónde salen las variables que tomamos para aplicar los
principios físicos".

## Purpose

Extend `docs/SIGNAL-MODELING.md` (the canonical signal-model doc) with:

1. **§5.1 Where the design values come from** — derivation of each design
   variable: physics (Fresnel, Nyquist, resolution), physiology (bands ÷60),
   hardware constraints (uint8 amplitude, ping-rate sampling), empirical
   calibration (thresholds), and literature (window length tradeoffs).
2. **§10 Expected accuracy (literature-grounded)** — VitalCSI RR numbers,
   Pulse-Fi HR numbers (same amplitude-only single-antenna class), classic
   peak-detection family positioning, window tradeoff, simulator-vs-reality
   boundary; every number cited.
3. **§11 Multi-device links (multi-ESP32)** — link-diversity physics and the
   hard architectural requirement (per-device topics; interleaved publishers
   collide with the monotonic-timestamp guard) + max-SNR fusion design.
4. **§12 Medical feasibility** — honest positioning; FDA 510(k) contactless
   analogues as evidence the regulatory path exists; what is missing.
5. References section gains the new verified sources (renumbered §13).
6. §1/§2/§9 touch-ups: web viewer in the diagram/consumers, hardened input
   contract (data-validity guards and where they come from), aiohttp row.

`docs/DEVELOPMENT-TOOLS.md` §5.3 (Spanish) gains the accuracy expectation
summary + pointer.

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | SIGNAL-MODELING.md: variable-origin derivations (§5.1) | pending | table + notes: physics/physiology/hardware/empirical/literature per value |
| 2 | SIGNAL-MODELING.md: accuracy, multi-link, medical sections + refs | pending | §10/§11/§12 + §13 renumber; all numbers cited |
| 3 | SIGNAL-MODELING.md: diagram/consumers/guards/aiohttp touch-ups | pending | §1, §2, §9 |
| 4 | DEVELOPMENT-TOOLS.md §5.3 accuracy summary + pointer | pending | Spanish |
| 5 | Verification (math fences, table pipes, cross-refs) | pending | doc invariants from the audit |
| 6 | Native review (RDD on) of the committed range | pending | expect docs-only tier |

## Verification evidence

(pending)
