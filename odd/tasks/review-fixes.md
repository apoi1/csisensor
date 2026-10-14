# Review fixes — post-review correction cycle (v4)

Corrección de los findings de la review 4-lens (lineage `review-7d8e6420d3b9ab94`,
closed escalated, informational). Cada S# cita el finding nativo con su ubicación.

## Specs

- **S1 — MQTT_TOPIC env muerto** (R1-002, R2-MqttTopicEnvSilentlyDead, R3-002; `backend/config.py:46-49`, `backend/main.py:44-50`, `backend/web_viewer.py:214-215`): "A baseline-valid MQTT_TOPIC override is silently ignored: the process starts, logs the default patterns as subscribed, and runs a healthy GUI with no warning that the explicit option was dropped." → Restaurar el contrato baseline: `MQTT_TOPIC` explícito reemplaza la lista de suscripción; el default legacy (`esp32/csi/raw`) expande a los patrones multi-link. Precedencia: `--topic` (CLI) > `MQTT_TOPIC` (env) > default multi-link.
- **S2 — stale-expiry derrotado para el primary** (R1-001, R3-001, R4-StalePrimaryNeverExpires; `backend/link_manager.py:148,163-172,299-313`): "_pipelines() unconditionally re-stamps _last_seen on every call... The GUI status bar polls fill()/capacity() at 5 Hz... a dead primary keeps winning fusion forever." → Solo el ingest refresca staleness; los read accessors (`fill`/`capacity`/`current_matrix`/`current_window` vía `_primary_proc`) no re-stampean. Creación de pipeline cuenta como fresh.
- **S3 — GUI congelado en fase de llenado** (R2-RedrawRawNoLongerDraws, R3-005, R4-FillPhaseCanvasFrozen; `backend/gui.py:141-179`): "The trace panels paint nothing for the first ~window_seconds... cheaply fixed by one draw_idle after a successful _redraw_raw()." → `_redraw_raw()` termina en `canvas.draw_idle()` (los draw_idle coalescen por tick).
- **S4 — lecturas sin lock + trampa de deadlock** (R1-004, R2-LinkIdsLockContractTrap, R3-003; `backend/link_manager.py:151-152,174-176,281-284`): "link_ids() sorts self._links unlocked... 'fixing' link_ids() to match its siblings deadlocks fill/capacity... while calling it from another thread races." → Lock real en `link_ids()`/`evictions()` + variante interna sin lock para `_primary_proc` (que ya sostiene el lock); `motion_estimate()` captura `_primary` dentro del lock.
- **S5 — eviction no limpia _primary** (R3-004; `backend/link_manager.py:130-132`): "If the primary is ever the eviction victim, the dangling id makes the next fill()/current_window() call re-create the evicted link as an empty pipeline." → La eviction LRU limpia `_primary` si la víctima era el primary.
- **S6 — docs 45 vs 46** (R2-TestCountDocsInconsistent, R3-008; CONTRIBUTING.md:18-19, docs/DEVELOPMENT-TOOLS.md, docs/PROJECT-ARCHITECTURE.md vs CHANGELOG.md:90): "One count is stale inside the same unit of work." → Unificar al conteo real de la suite tras estas correcciones.
- **S7 — higiene de identificadores** (R1-005; `odd/tasks/2026-10-12-night-summary.md:20-26`): "the new night-summary note records the deployment's concrete broker address... and the board's full MAC address... scrub or generalize them before the repo leaves the machine." → Generalizar IP/MAC en las notas.
- **S8 — flash-size 4MB sin explicar** (R2-FlashSize4MBUnexplained; `scripts/flash-board.ps1:75`): "hardcodes --flash-size 4MB with no comment, while the project's own bring-up notes record the board as a 16 MB module." → Parámetro explícito con default documentado (16 MB según odd/tasks/2026-10-12-night-summary.md).
- **S9 — filtro LAN 192.168.* sin fallback** (R3-006; `scripts/build-portable-kit.ps1:82-85,110-112`): "on a LAN using 10.x or 172.x addressing the build prints an empty 'LAN IP'... a warning or a broader address-family fallback would close it." → Fallback a cualquier IPv4 de interfaz + warning cuando no es 192.168.*.
- **S10 — exposición del kit sin caveat** (R1-003; `scripts/firewall-rules.ps1:23-35`, kit README generado): "recommend -RemoteAddress LocalSubnet with a private-profile restriction and an auth note in the kit README." → Aplicar la recomendación del propio finding.

## Tasks

- **T1** (S1) — config.py: `topic_patterns` derivado de `MQTT_TOPIC` por `default_factory`; test RED→GREEN. Route: inline.
- **T2** (S2, S4, S5) — link_manager.py: parámetro `touch` en `_pipelines`, `_link_ids_locked`, locks en `link_ids`/`evictions`, `_primary` capturado bajo lock en `motion_estimate`, eviction limpia `_primary`; tests RED→GREEN (poll-expiry, evicted-primary, concurrent smoke). Route: inline.
- **T3** (S3) — gui.py: `draw_idle()` al final de `_redraw_raw()`. Route: inline (no testeable headless; verificación estructural).
- **T4** (S6, S7, S8, S9, S10) — docs + scripts: conteo de tests unificado, scrub IP/MAC, flash-size param, fallback LAN IP, firewall `-RemoteAddress LocalSubnet` + nota de auth en el README del kit. Route: inline.
- **T5** — suite completa en verde + conteo real para S6. Route: inline.
- **T6** — guía zombie de despliegue (entrega en chat). Route: inline.

## Log

- **L1** (2026-10-14, usuario, verbatim): "arma ciclo de conversion por favor y trabaja ese tema al final vuelve a darme guia zombie para desplegar el aplicativo" — interpretado como: ciclo de CORRECCIÓN de los findings de la review, y al final la guía de despliegue paso a paso.
- **L2** (2026-10-14): findings fuente = ledgers admitidos del linaje review-7d8e6420d3b9ab94 (store nativo). Canónicos congelados: R1-001, R1-002, R2-MqttTopicEnvSilentlyDead, R3-001, R4-StalePrimaryNeverExpires.
- **L3** (2026-10-14): ciclo de corrección commiteado en master — backend + tests: `dce3453` (fix(backend), 6 archivos, 201+/13−, suite 50/50 RED→GREEN); hygiene de scripts + docs: `96e1767` (chore(scripts,docs), 9 archivos, 81+/13−). Este commit registra las identidades como evidencia. Fuera del batch: `src/esp32/main/config.h` quedó sin commitear deliberadamente (credenciales reales de firmware del usuario, hallazgo R1-005/§12).
