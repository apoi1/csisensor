# Feature: docs-sync — align maintainer docs with the multi-ESP32 branch

Parent: `odd/track-wifisensing.md`. Opened 2026-10-09 after the multi-esp32
review arc: native review unavailable (two terminally escalated lineages),
risk-gated path applied (ASSESS: writer self-verification + independent
verifier — 45/45, findings fixed in f41281a). This feature closes the
documentation debt found by the 2026-10-09 from-zero doc review plus the
verifier pass, and lands the 4 pending doc-sync edits that predate it.

## Evidence base (verified 2026-10-09)

- Tests: 45/45 (pytest 9.1.1, ~2.6-4.4 s), py_compile clean on the 5 py files.
- `backend/link_manager.py`: MAX_LINKS=16 (:47), LINK_STALE_S=20.0 (:51),
  always-admit LRU eviction (:121-131), `_prune_stale` before every fusion
  pass (:205-215, :225/:264), locked accessors n_links/primary_link
  (:154-160), always-admit ingest docstring (:182-185).
- `src/esp32/main/main.cpp:295-300`: csi_cfg.lltf_en/htltf_en/stbc_htltf2_en/
  ltf_merge_en = true, manu_scale = false, channel_filter_en =
  CSI_CHANNEL_FILTER (true, subcarrier smoothing) — SIGNAL-MODELING §2
  "all set to false" is WRONG; §3's "pin the AP channel via
  CSI_CHANNEL_FILTER" misattributes the flag (no AP-channel pin exists).
- `main.cpp:125-126`: per-device topic `esp32/<mac3>/csi/raw` from checked
  esp_read_mac (:117-123); `config.h`: MQTT_TOPIC_PREFIX "esp32",
  CSI_INTERVAL_MS 100, USE_TRAFFIC_PING 1.
- `backend/gui.py:143-145`: status bar shows "links ... (primary ...)" via
  primary_link() (f41281a).
- Branch commits: c7194cf (feature), f01f169 (hardening: multi-pattern
  subscriber state, MAX_LINKS cap, sim --topic, esp_read_mac check),
  7ef3019 + 18aaff8 (R4 corrections: always-admit LRU, stale expiry,
  lock coverage), f41281a (primary-link label + locked accessors).
- Review arc: review-d27f513bb465b0e5 (escalated: targeted_validator_rejected),
  review-2398011e737d2561 (3/4 lenses captured; escalated:
  unknown_causality over R2-MisleadingBestLink, R3-13, R3-6/7/9, R4-2);
  ASSESS risk-gated plan satisfied; independent verifier 6/6 PASS.
- Repo has NO git remote (CONTRIBUTING issue workflow is aspirational).
- Language convention: README/DEPLOYMENT/CHANGELOG/CONTRIBUTING/
  SIGNAL-MODELING in English; DEVELOPMENT-TOOLS/PROJECT-ARCHITECTURE in
  Spanish. Keep each file's language.

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | CHANGELOG: Fixed entries for the link hardening/corrections (f01f169, 7ef3019, 18aaff8) and f41281a | done | two entries under Fixed, Keep-a-Changelog shape |
| 2 | PROJECT-ARCHITECTURE: update Estado de implementación (45 tests), add MultiLinkSubscriber/LinkManager + per-band max-SNR fusion + web viewer to pipeline and stack | done | Spanish, GUI/Body and maintenance sections kept |
| 3 | DEVELOPMENT-TOOLS §4/§5.1/§5.2: flow diagram with wildcard + LinkManager + web viewer + 2x3 grid; backend inventory += link_manager.py, motion_analyzer.py, web_viewer.py, web_static/; upstream table += aiohttp | done | built on the pending count-sync hunks; verified drain_and_feed()/tagging against link_manager.py |
| 4 | SIGNAL-MODELING: fix §1 cross-ref (§11→§8), §2 csi flags (real values from main.cpp:295-300), §2 backend paragraph (MultiLinkSubscriber routing), §3 CSI_CHANNEL_FILTER correction (smoothing flag; AP channel neither pinned nor published) | done | verified against main.cpp/config.h |
| 5 | CONTRIBUTING rule 3: import-light list += link_manager | done | one word, pending 45-count hunk preserved |
| 6 | odd/tasks/multi-esp32.md: add the R4 round + review arc + f41281a rows, update task-10 note and verification evidence (45/45) | done | rows 11-12 appended, historical 40/40 lines untouched |
| 7 | Parent: verify all edits, run suite, commit the 4 pending doc-sync edits + these edits as work-unit `docs:` commit(s) | in-progress | suite 45/45 (parent run, 2.54 s); commit landing now |
