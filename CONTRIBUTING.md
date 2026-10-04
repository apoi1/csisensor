# Contributing to sensorproject

Research/educational WiFi-CSI vital-signs project. **Not a medical device** —
keep experimental claims out of user-facing copy.

## Development setup

- Firmware (ESP32-S3): ESP-IDF v5.x on WSL — `DEPLOYMENT.md` §3–6.
- Broker: `docker compose up -d` — `DEPLOYMENT.md` §2.
- Backend/GUI: Python venv on Windows — `DEPLOYMENT.md` §8.
- Headless dry-run without hardware:
  `python scripts/simulate_esp32.py --scenario {resting,moving,absent}`.
- Phone view while developing: `python backend/web_viewer.py` — §9.

## Before every change

```console
cd backend
python -m pytest tests -q          # full suite must pass (currently 32 tests)
python -m py_compile <touched>.py
```

## Workflow

1. One branch per feature: `feature/<name>`; keep `master` always releasable.
2. Small, self-contained commits (Conventional Commits): `feat:`, `fix:`,
   `docs:`, `test:`, `chore:`. Tests and docs travel with the behavior they
   cover — never a "docs catch-up" commit after the fact.
3. Keep the DSP modules import-light: `vitals_processor`, `motion_analyzer`,
   `csi_packets` and `web_viewer` must not import Qt, so they stay testable
   headless (WSL has no PyQt5). Only `gui.py` and `main.py` touch the GUI.
4. Update `DEPLOYMENT.md` / `README.md` / `docs/` in the same unit of work
   when behavior, interfaces or commands change.
5. New runtime dependencies go into `backend/requirements.txt` with a lower
   bound (and an upper bound where the API is known-breaking, e.g.
   `paho-mqtt>=1.6,<2.0`).

## Maintenance

- **Versioning**: tag releases from `master` as `vMAJOR.MINOR.PATCH`
  (`git tag -a v0.1.0 -m "first tagged release"`); `CHANGELOG.md` records
  every released change.
- **Issues**: bugs and advisory findings live as issues, not as TODO
  comments. Findings from native reviews keep their IDs (e.g.
  `R3-viewer-lock`) so the trail survives.
- **Secrets**: never commit credentials. `src/esp32/main/config.h` ships
  `CHANGE_ME` placeholders only; API keys and broker credentials stay
  outside the repo.
- **Docs accuracy**: `docs/DEVELOPMENT-TOOLS.md` §5.3 lists the current test
  count — keep it in sync whenever tests are added.
- **Firmware conventions**: WiFi/MQTT credentials live in `config.h` as
  `CHANGE_ME` placeholders — never commit real values. CSI capture stays on
  the native ESP-IDF `esp_wifi_set_csi_rx_cb` API, and the ~10 Hz
  traffic-ping sampling stays toggleable via `USE_TRAFFIC_PING`.

## Reporting bugs

Open an issue with: the scenario (`resting`/`moving`/`absent`/live), what
the Body row and the vitals tiles showed, the broker setup, and the
`docker compose logs mosquitto` tail. Screenshots of the GUI or the phone
page help.
