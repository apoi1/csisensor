# Feature: multi-esp32 — per-device links with per-band max-SNR fusion

Parent: `odd/track-wifisensing.md`. User request 2026-10-04: implement the
moderate-effort multi-ESP32 feature "con el proceso técnico y teórico detrás".

## Purpose

Multiple ESP32-S3 nodes observing the same subject improve robustness against
Fresnel-zone nulls and body-orientation sensitivity (link diversity, a
standard technique in the WiFi-sensing literature). Today every device would
publish to the same flat topic `esp32/csi/raw`, and the hardened pipelines
(monotonic-timestamp guard) would drop interleaved packets from different
devices — so multi-device support is a routing/fusion feature, not just a
config change:

1. **Firmware**: publish to a per-device topic `esp32/<id>/csi/raw`, where
   `<id>` = last 3 bytes of the STA MAC (eFuse, deterministic).
2. **Backend**: new `link_manager.py` — `MultiLinkSubscriber` subscribes the
   wildcard `esp32/+/csi/raw` **and** the legacy flat topic (backward
   compatible); each packet is tagged with its link id from the topic;
   per-link `VitalsProcessor` + `MotionAnalyzer` pipelines stay fully
   isolated (width/monotonicity guards apply per link).
3. **Fusion**: per physiological band, the link with the highest in-band SNR
   wins the estimate (heart and respiration can come from different links);
   presence aggregates conservatively (any Moving → Moving, else any Still →
   Still, else Absent); GUI physics panels show the heart-winning link's
   window.
4. **Interfaces**: GUI and web viewer consume the fused `VitalsEstimate` /
   `MotionEstimate` (same dataclasses — zero interpretation changes) plus a
   link count; simulator gains `--device-id` to dry-run multi-node setups.

## Design notes

- Fusion picks max SNR even when that link's rate is None (below the 6 dB
  gate): the fused rate then reports None — honest "no link passed the gate".
- Flat-topic packets route to the `default` link; unknown shapes route to
  the full topic string as id.
- Config stays frozen; topic patterns are CLI-level (main.py / web_viewer.py
  `--topic` overrides the default pattern set).

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | link_manager.py: MultiLinkSubscriber + LinkManager + fusion | done | wildcard + flat topics, per-link pipelines, per-band max-SNR, conservative presence, primary-link panels |
| 2 | Wire GUI (main.py + gui.py) to LinkManager | done | same dataclasses; status bar shows links; py_compile OK |
| 3 | Wire web viewer + n_links in snapshot/page | done | ViewerState takes links; snapshot + page show link count |
| 4 | Simulator --device-id | done | publishes esp32/<id>/csi/raw when set |
| 5 | Firmware per-device topic (config.h + main.cpp) | done | MQTT_TOPIC_PREFIX + eFuse MAC id via esp_read_mac; compiles on user side (no idf.py in this WSL) |
| 6 | Tests: routing isolation, per-band fusion, presence aggregate, flat-topic compat | done | 8 new tests (routing, isolation, fusion, aggregate, empty/partial, flat-gate); suite 40/40 in 2.1 s |
| 7 | Docs: DEPLOYMENT multi-node subsection, README, CHANGELOG, SIGNAL-MODELING §11 | done | §8 Multi-device links (theory + design + fusion math); DEPLOYMENT §10 multi-node dry-run; README rows; CHANGELOG |
| 8 | Native review (RDD on) + merge | pending | first transaction review-4ab1b9c40a939b06 ESCALATED terminal (native_stop_required): 4 lenses + refuter captured; refuter refuted R3-3 with proof; 5 findings unknown-causality -> maintainer inspection done, graded in this doc; fresh transaction started after the hardening commit |
| 9 | Hardening follow-up (R3-1, R3-5, R3-12, R3-13) | done | commit f01f169: native multi-pattern subscriber state, MAX_LINKS=16 registry cap, simulator --topic precedence + note, firmware esp_read_mac check; 42/42 tests |
| 10 | Fresh native review of the corrected range + merge | pending | superseded — the actual arc is rows 11–12 (fresh lineage review + risk-gated closure, see below) |
| 11 | R4 resilience corrections + fresh native review | done | 7ef3019 + 18aaff8 (always-admit LRU, 20 s stale pruning, full lock); fresh lineage review-d27f513bb465b0e5 escalated terminal (targeted_validator_rejected) after the validator relay failed natively |
| 12 | Second fresh review + risk-gated closure + verifier fixes | done | review-2398011e737d2561: 3/4 lenses admitted (risk/resilience/readability), reliability slot failed native-operation-failed → escalated unknown_causality (R2-MisleadingBestLink, R3-13, R3-6/7/9, R4-2); native review unavailable → ASSESS risk-gated plan (self-verification + independent verifier, 6/6 PASS); findings fixed in f41281a; 45/45 |

## Maintainer grading of the escalated review (2026-10-04)

The reliability lens (nemotron-3-ultra-550b) produced 16 findings; the refuter refuted R3-3 with proof. Graded:
- **Fixed in f01f169**: R3-1 (BLOCKER - dead single-topic state in the subscriber chain), R3-5 (unbounded link registry), R3-12 (silent --device-id ignore), R3-13 (unchecked esp_read_mac).
- **Wrong premise (no action)**: R3-2/R3-3/R3-8/R3-9 family - VitalsProcessor.estimate() already returns None until the window is full, so partial-window estimates cannot be fused; the refuter proved R3-3.
- **Theoretical (no action)**: R3-15 (_primary is only ever set from existing links, so the claimed race cannot occur).
- **Advisory, separate later work**: R3-6/R3-7/R3-16 (test depth suggestions), R3-10/R3-11 (--topic replacing the legacy pattern is by design, documented), R3-14 (snprintf safe by construction).

## Verification evidence

- 40/40 backend tests pass (8 new: topic routing, two-links-never-mix-windows — the critical property vs a shared pipeline, per-band fusion from asymmetric links, conservative presence aggregate, empty/partial links, constant-amplitude gate honesty, snapshot link count). py_compile clean on link_manager.py, web_viewer.py, main.py, gui.py, simulate_esp32.py.
- Test-design notes: gross movement must be COHERENT across subcarriers (per-subcarrier noise averages out in the mean — physically right and it makes the Moving threshold observable); white noise is NOT flat (its in-band peak-vs-median often clears the 6 dB gate) — constant amplitudes are the correct gate-honesty fixture.
- Smoke: web viewer serves the page (HTTP 200) and accepts WS upgrades (101 in logs); the WS round-trip could not be completed in this sandbox (background-process pipes retained by the tool) — left for the user-side dry-run; serialization is unit-tested end to end (json.dumps of every snapshot shape).
- Firmware not compiled here (no ESP-IDF in this WSL — user-side task): change is minimal (topic buffer built once in publisher_task via esp_read_mac + snprintf).
- 2026-10-09: 45/45 backend tests pass after f41281a (pytest 9.1.1, ~2.6 s); independent verifier readback 6/6 PASS.
