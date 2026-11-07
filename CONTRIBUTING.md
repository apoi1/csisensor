# Contribuir a sensorproject

Proyecto de signos vitales por WiFi-CSI, de investigación/educación. **No es
un dispositivo médico** — mantener los claims experimentales fuera del texto
de cara al usuario.

> Términos acuñados se citan en inglés sin traducir (CSI, RSSI, MQTT, broker,
> venv); la prosa es en español.

## Setup de desarrollo

- Firmware (ESP32-S3): ESP-IDF v5.x en WSL — `DEPLOYMENT.md` §3–6.
- Broker: `docker compose up -d` — `DEPLOYMENT.md` §2.
- Backend/GUI: venv de Python en Windows — `DEPLOYMENT.md` §8.
- Dry-run headless sin hardware:
  `python scripts/simulate_esp32.py --scenario {resting,moving,absent}`.
- Vista en el teléfono mientras desarrollás: `python backend/web_viewer.py` — §9.

## Antes de cada cambio

```console
cd backend
python -m pytest tests -q          # la suite completa debe pasar (hoy 50 tests)
python -m py_compile <tocado>.py
```

## Flujo de trabajo

1. Una rama por feature: `feature/<nombre>`; `master` siempre liberable.
2. Commits chicos y autocontenidos (Conventional Commits): `feat:`, `fix:`,
   `docs:`, `test:`, `chore:`. Los tests y los docs viajan con el
   comportamiento que cubren — nunca un commit de "puesta al día de docs"
   después de hecho.
3. Mantener los módulos DSP con imports livianos: `vitals_processor`,
   `motion_analyzer`, `csi_packets`, `link_manager` y `web_viewer` no deben
   importar Qt, así siguen siendo testeables headless (WSL no tiene PyQt5).
   Solo `gui.py` y `main.py` tocan la GUI.
4. Actualizar `DEPLOYMENT.md` / `README.md` / `docs/` en la misma unidad de
   trabajo cuando cambien comportamiento, interfaces o comandos.
5. Las dependencias nuevas de runtime van a `backend/requirements.txt` con
   cota inferior (y cota superior cuando la API se sabe rota, p. ej.
   `paho-mqtt>=1.6,<2.0`).

## Mantenimiento

- **Versionado**: taggear releases desde `master` como `vMAJOR.MINOR.PATCH`
  (`git tag -a v0.1.0 -m "first tagged release"`); `CHANGELOG.md` registra
  cada cambio liberado.
- **Issues**: los bugs y hallazgos de advisories viven como issues, no como
  comentarios TODO. Los hallazgos de las reviews nativas conservan su ID
  (p. ej. `R3-viewer-lock`) para que la trazabilidad sobreviva.
- **Secretos**: nunca commitear credenciales. `src/esp32/main/config.h` se
  distribuye solo con placeholders `CHANGE_ME`; las API keys y credenciales
  del broker quedan fuera del repo.
- **Exactitud de docs**: `docs/DEVELOPMENT-TOOLS.md` §5.3 lista la cantidad
  actual de tests — mantenerla en sync cada vez que se agreguen tests.
- **Convenciones del firmware**: las credenciales WiFi/MQTT viven en
  `config.h` como placeholders `CHANGE_ME` — nunca commitear valores reales.
  La captura CSI se queda en la API nativa `esp_wifi_set_csi_rx_cb` de
  ESP-IDF, y el muestreo por traffic-ping a ~10 Hz sigue siendo
  conmutable vía `USE_TRAFFIC_PING`.

## Reportar bugs

Abrir un issue con: el escenario (`resting`/`moving`/`absent`/en vivo), qué
mostraban la fila Body y los tiles de signos vitales, el setup del broker, y
el tail de `docker compose logs mosquitto`. Screenshots del GUI o de la
página del teléfono ayudan.
