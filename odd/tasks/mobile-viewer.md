# Feature: mobile-viewer — LAN web viewer for phones + broker websocket fix

Parent: `odd/track-wifisensing.md` (WiFiCSI tracking pipeline). User decision
2026-10-04: implement option A now; also fix the dead 9001 mapping; update
deployment/requirements docs; PyInstaller+Docker chosen for final packaging
(separate follow-up).

## Purpose

All interfaces must be functional: besides the PyQt5 desktop GUI, users on
phones/tablets need a live view of the estimates. Option A (verified
feasible analysis): a **standalone backend web viewer** — an asyncio web
service (single port: static page + WebSocket) with its own MQTT
subscription feeding the same `VitalsProcessor`/`MotionAnalyzer` DSP, so
the web interface works even when the desktop GUI is not running. Zero
firmware changes.

Also fixed here: `docker-compose.yaml` publishes 9001 but
`docker/mosquitto/mosquitto.conf` has no websocket listener — add
`listener 9001` + `protocol websockets` so MQTT-over-WS (option B browsers,
future use) actually works.

## Design

- `backend/web_viewer.py`: standalone entry (`python web_viewer.py
  [--host] [--port] [--broker] [--topic]`). aiohttp serves the page and the
  WebSocket on one port; paho-mqtt subscribes on its usual thread; snapshots
  (estimates + presence + recent wave history) are broadcast ~1 Hz to all
  connected browsers via `loop.call_soon_threadsafe`.
- Static page `backend/web_static/index.html`: self-contained (no CDN — LAN
  may be offline), canvas traces + numeric tiles, auto-reconnect WS client.
- The desktop GUI keeps its own processor/analyzer (unchanged); the viewer
  is an independent broker consumer — no Qt import, PyInstaller-friendly.
- New dep: `aiohttp` (HTTP+WS in one package). Everything else reused.
- Tests focus on the viewer's snapshot serialization and pipeline wiring
  (headless, no sockets needed beyond a loop test).

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | mosquitto.conf websocket listener 9001 | done | listener 9001 + protocol websockets added; compose mapping now real; restart note in DEPLOYMENT §2 |
| 2 | backend/web_viewer.py (aiohttp + paho pipeline + WS broadcast) | done | standalone, no Qt; ViewerState thread-safe snapshots ~1 Hz; named routes; smoke-tested HTTP 200 |
| 3 | web_static/index.html self-contained page | done | canvas trend + waves, tiles, auto-reconnect, no CDN; 6.6 KB served |
| 4 | tests: snapshot serialization + pipeline wiring | done | 6 new tests (partial/full window, cadence, corrupt-packet continuity, history trim, routes); 32/32 pass |
| 5 | DEPLOYMENT.md + README + requirements.txt updates | done | new §9 web viewer (flags, firewall rule, phone URL), §10-12 renumbered (no cross-refs), §2 websockets note, README diagram/layout/quick-start, aiohttp>=3.9, Activate.ps1 fix |
| 6 | Native review (RDD on) of the committed range + merge | done | Lineage review-7716806197e13244 (tier medium, 639 lines, single review-reliability lens, budget 200): child relay capture (kimi-k3 per standing preemptive switch, reverted after); terminal closure APPROVED with 3 advisory findings recorded below; acknowledge-approved burned authority (revision sha256:c4805b4a…, evidence gentle-ai.review-acknowledged/v1); commit already on master (078c215, local repo, review covered the committed range e449ad4..078c215) |

## Verification evidence

- 32/32 backend tests pass (`python3 -m pytest tests -q`, 1.83 s); py_compile clean on web_viewer.py + tests.
- WSL env: aiohttp 3.14.3 + paho-mqtt <2.0 installed (--break-system-packages) to run the suite.
- Smoke test: `python3 web_viewer.py --port 8123` with no broker running — page served (HTTP 200, 6662 bytes, "WiFi-CSI Live" present), paho reconnects in background, clean logs.
- Test-design note: synthetic breathing/heart tones are coherent across subcarriers (chest displacement modulates the whole channel) so MotionAnalyzer's mean-amplitude path sees realistic common-mode.
- Native review APPROVED (2026-10-04): single-lens (review-reliability) tier-medium transaction over the committed range e449ad4 (tree 8c6bc4a6) → 078c215; capture closed approved; no correction consumed (budget 200 untouched); authority burned (revision c4805b4a, evidence gentle-ai.review-acknowledged/v1).

## Advisory findings from this review (separate later work, non-blocking)

Per the closure receipt: every finding below is non-blocking; none opened a correction, none reopens this review.

1. **R3-feed-plumbing-mismatch** (WARNING, reliability, `backend/web_viewer.py:200-209`) — feed loop / main wiring plumbing.
2. **R3-viewer-lock** (WARNING, reliability, `backend/web_viewer.py:63-73`) — ViewerState locking discipline.
3. **R3-ws-error-path** (WARNING, reliability, `backend/web_viewer.py:136-152`) — WebSocket error-path handling.
