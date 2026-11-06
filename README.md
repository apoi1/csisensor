# sensorproject - WiFi-CSI Vital Signs (ESP32-S3 + Python)

Real-time experimental vital-sign tracking (heart rate and respiration
estimation) from **WiFi CSI** (Channel State Information) captured by an
ESP32-S3, streamed over MQTT to a PyQt5 desktop application with FFT-based
signal processing.

```
ESP32-S3 firmware (C++/ESP-IDF) ──MQTT──► Mosquitto (Docker) ◄── Python backend (paho-mqtt + scipy FFT) ──► PyQt5 GUI (vitals + body presence/motion)
                                                       └──► Web viewer (backend/web_viewer.py → any phone browser on the LAN)
```

> Research/educational project. **Not a medical device.**

## Layout

| Path | What |
|---|---|
| `src/esp32/` | ESP-IDF v5.x firmware: native CSI capture -> queue -> MQTT publish |
| `backend/` | Python: MQTT subscriber, FFT vitals processor + motion analyzer, multi-link manager (per-device ESP32 topics + per-band max-SNR fusion), PyQt5 GUI (real-time heart rate, respiration, body presence/motion "Body" row; physics panels: subcarrier heatmap, spectrogram, motion energy — with formula annotations), unit tests |
| `backend/web_viewer.py` + `backend/web_static/` | Standalone LAN web viewer: same DSP served to phone browsers (aiohttp + WebSocket; no app install, no CDN) |
| `scripts/simulate_esp32.py` | Synthetic CSI publisher to test the backend without hardware |
| `docker-compose.yaml` + `docker/mosquitto/` | Local Mosquitto broker |
| `DEPLOYMENT.md` | **Step-by-step deployment guide (WSL + Windows)** |
| `docs/` | Tools list and project notes |
| `docs/SIGNAL-MODELING.md` | Signal model: physics, math, variable provenance, calibration, references |
| `docs/HOW-IT-WORKS.md` | The system explained simply (physics to data cleaning to how to read every chart; in Spanish, for non-technical audiences) |
| `docs/DATA-PIPELINE.md` | End-to-end methodological framework: every stage from RF input to displayed pixel, with the exact math, the specific technology at each step, and the design rationale (in Spanish) |
| `docs/FIRMWARE-ESP32.md` | The flashed ESP32-S3 firmware as a system: boot sequence, FreeRTOS task architecture, self-ping sampling, the I/Q→amplitude→CSV→MQTT data journey, config knobs and serial provisioning (in Spanish) |
| `docs/DESKTOP-APP.md` | The desktop application as a system: thread architecture, the 7-step packet journey with each guard's rationale, process lifecycle, panel provenance, design decisions (in Spanish) |
| `docs/QUICKSTART-ZOMBIE.md` | Zombie-mode deployment guide: what's already done, one-time fix actions, daily bring-up, from-scratch and portable-kit paths (in Spanish) |
| `docs/DEPLOYMENT-ALTERNATIVES.md` | Alternative deployments: mosquitto native (no Docker) per platform, the X230/Fedora zombie guide, macOS setup, Android/iOS as viewers, multi-platform compatibility matrix |
| `odd/` | ODD feature tracking |

## Features

- **Multi-ESP32 fusion**: each board publishes to its own topic
  (`esp32/<id>/csi/raw`); the backend keeps one DSP pipeline per link and
  fuses per physiological band (best in-band SNR wins heart and respiration
  independently; presence aggregates conservatively).
- **Dead-link failover within 20 s** *(review-hardened, 2026-10-14)*: a
  silent link — including the polled primary — expires and stops winning
  fusion, so live backups take over instead of a frozen estimate winning
  forever.
- **`MQTT_TOPIC` env override restored** *(2026-10-14)*: an explicit value
  replaces the whole subscription list (baseline contract); the default
  keeps the multi-link patterns. The GUI also repaints its raw trace during
  the window-fill phase instead of freezing ~15 s until the first estimate.
- **Body presence/motion** (Absent / Still / Moving) from the mean CSI
  amplitude, plus a calibratable RSSI log-distance estimate (can be disabled
  with `CSI_RSSI_REF_DBM=none`).
- **LAN web viewer** for phones (aiohttp, zero CDN) and a **portable
  one-click kit** (`scripts/build-portable-kit.ps1`: broker + viewer exe)
  for any Windows PC — with LAN-IP detection that falls back to 10.x/172.x
  and warns instead of printing an empty URL.
- **Hardware-free dry-run**: `scripts/simulate_esp32.py` scenarios
  (resting / moving / absent; multi-node via `--device-id`).
- **Quality**: 50 automated headless tests (`pytest`) and a native 4-lens
  review process (risk / resilience / readability / reliability) whose
  findings and correction cycles are tracked in `odd/tasks/` and
  `CHANGELOG.md`.

## Quick start

1. `docker compose up -d` (broker) — and open the dev firewall once from an admin PowerShell: `powershell -ExecutionPolicy Bypass -File .\scripts\firewall-rules.ps1` (scopes ports 1883/8080 to the local subnet; the network must be marked Private — DEPLOYMENT.md §2)
2. Configure `src/esp32/main/config.h` (WiFi + broker IP)
3. Build/flash from WSL: `idf.py set-target esp32s3 && idf.py build && idf.py -p /dev/ttyACM0 flash monitor`
4. Windows (PowerShell): `cd \\wsl.localhost\Ubuntu\home\tilin\dev\projects\c++\sensorproject\backend` (the repo lives in the WSL filesystem; Windows reaches it through this share — no files are copied), then `python -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt` — full recipe: `DEPLOYMENT.md` §8
5. Dry-run: `python ..\scripts\simulate_esp32.py --scenario moving` + `python main.py` (scenario options: `resting`, `moving`, `absent`; add `--device-id <id>` per node to dry-run multi-ESP32 links)
6. Phone view: `python web_viewer.py` and open `http://<PC-LAN-IP>:8080` on any phone on the same Wi-Fi (DEPLOYMENT.md §9)
7. Live: see `DEPLOYMENT.md`

## Signal processing

- The firmware sends per-subcarrier amplitudes $\sqrt{I^2+Q^2}$ as compact CSV at ~10 Hz.
- The backend keeps a 15 s sliding window, selects the subcarrier with the
  strongest spectral peak per physiological band (respiration 0.1-0.5 Hz,
  heart 0.8-2.0 Hz), bandpass-filters it and reports the dominant frequency
  (Hann-windowed FFT + quadratic peak refinement) with an SNR quality gate.

Presence and body motion are classified from the mean CSI amplitude: an empty
room is noise-flat (window std below a threshold), gross body movement raises
the 0.5–3.0 Hz motion-band RMS; mean RSSI additionally yields a coarse
log-distance link-distance estimate (calibratable). Amplitude-only
single-antenna CSI cannot provide coordinates or angle — see
docs/SIGNAL-MODELING.md.

## GUI panels — what each graph shows

The desktop GUI (and the measures strip under the canvas) name every
magnitude and unit explicitly on its axes. Full walkthrough with
scenario-by-scenario reading: `docs/HOW-IT-WORKS.md` §5 (Spanish).

| Panel (position) | Magnitude (y-axis / color) | x-axis | Unit | What to look for |
|---|---|---|---|---|
| 1 · CSI mean (top-left) | mean CSI amplitude ā(t) | t [s], 0–15 | a.u. | Slow breathing wave; a jump = body motion; flat line = empty room |
| 2 · Respiration (mid-left) | respiration amplitude x(t) | t [s], 0–15 | a.u. | Regular peaks at 12–30/min; title shows winning subcarrier (sc#) and SNR [dB] |
| 3 · Heart (bottom-left) | heart amplitude x(t) | t [s], 0–15 | a.u. | Small regular peaks (48–120 bpm); first trace to dirty up with motion |
| 4 · Heatmap (top-right) | y: subcarrier k · color: \|Hₖ\| | t [s] | dB | Bright vertical stripes = good subcarriers; sudden darkening = link blocked |
| 5 · Spectrogram (mid-right) | y: frequency f · color: X(τ,f) | t [s] | Hz / dB | Stable horizontal stripe at ~0.2–0.3 Hz = respiration; wide blotch = motion |
| 6 · Motion RMS (bottom-right) | motion RMS M_rms | t [s], 10 min | a.u. | Below red threshold line (1.5) = still; each crossing = one movement |

Units: CSI amplitudes are dimensionless (a.u.); heatmap/spectrogram are
shown in dB; RSSI in dBm; frequencies in Hz; time in seconds.

## Tests

```bash
cd backend
python -m pytest tests -q
```

50 automated headless tests: vitals estimator, packet parser, motion
analyzer, multi-ESP32 link manager (routing, fusion, expiry, locks),
config surface (env overrides incl. `MQTT_TOPIC`) and the web-viewer
pipeline.

## Uso en Colombia y monitoreo continuo en hogares del común

Este proyecto está pensado para ser implementado en hogares colombianos, aprovechando la infraestructura Wi‑Fi que ya existe en la mayoría de los hogares del país. El sistema se puede instalar en cualquier vivienda con acceso a una red Wi‑Fi (2.4 GHz recomendado, 5 GHz también soportado) y no requiere hardware adicional más allá del ESP32‑S3, el router y el backend Python.

**Ventajas para el uso en hogares colombianos**

- **Bajo costo:** el ESP32‑S3 y el firmware son de bajo costo y pueden adquirirse sin trámites regulatorios complejos para uso residencial.
- **Facilidad de despliegue:** la guía de despliegue (`DEPLOYMENT.md`) está escrita en español y contempla pasos prácticos para configurar el router, abrir el firewall (puertos 1883/8080) y colocar el ESP32‑S3 en una toma de corriente dentro del rango del router.
- **Monitoreo continuo:** el ESP32‑S3 captura CSI a ~10 Hz, envía los datos por MQTT y el backend mantiene una ventana deslizante de 15 s que permite estimar respiración y pulso en tiempo real, renovando la estimación cada segundo. Esto permite observar la evolución de los signos vitales a lo largo del tiempo sin intervención manual.
- **Privacidad:** el sistema solo procesa la señal de radio; no usa cámaras ni micrófonos, por lo que la privacidad de los residentes está protegida por diseño.

### Esquema de los frames CSV de CSI

Cada paquete MQTT publicado por el ESP32‑S3 contiene una línea CSV con los siguientes campos:

```
t_us,rssi,n,seq,a0,a1,...,a(n-1)
```

| Campo | Descripción | Unidad / Formato |
|-------|-------------|------------------|
| **t_us** | Timestamp del ESP32‑S3 (microsegundos desde el arranque) | entero (`uint64`) |
| **rssi** | Potencia del paquete recibida por el ESP32‑S3 | dBm (`int8`, típico -128…0) |
| **n** | Cantidad de sub‑portadoras que incluye este paquete | entero (`uint16`, ~64) |
| **seq** | Número de secuencia del paquete (monotónico) | entero (`uint32`) |
| **a0 … a(n‑1)** | Amplitud de cada sub‑portadora: `round(sqrt(I²+Q²))`, 0‑255 | entero (`uint8`) |

**Ejemplo** (8 sub‑portadoras, `n=8`):

```
12345678,-62,8,42,15,12,14,13,16,11,13,12
```

![Anatomía de un frame CSI y el destino de cada campo en el backend](img/csi-frame-anatomy.png)

**Parseo en Python** (`backend/csi_packets.py`):

```python
@dataclass(frozen=True)
class CsiPacket:
    t_us: int
    rssi: int
    n: int
    seq: int
    amps: np.ndarray   # shape (n,), float64
```

Si el payload no cumple el formato (menos de 4 campos, `n <= 0`, o faltan amplitudes), la función `parse_csi_payload` devuelve `None` y el paquete se descarta; esto evita que una muestra corrupta envenene la ventana deslizante de 15 s.

---

## License

MIT — see [LICENSE](LICENSE).
