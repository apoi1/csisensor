# Night summary — 2026-10-12 (for tomorrow's review)

Estado al cierre de la sesión nocturna. Todo está en master (`a809832`);
nada pendiente de merge. El único paso de "repositorios" que falta es el
**push remoto**: el repo no tiene ningún `git remote` configurado —
necesito tu URL y tu auth para crearlo.

## 1. Hitos físicos — PROYECTO FUNCIONAL EN LA PARTE FÍSICA ✅

Cadena física verificada de punta a punta con evidencia en vivo:

1. **Firmware en el chip** — primer build + flasheo exitosos de la
   historia del proyecto. Flasheo por el puerto **COM** (puente UART,
   auto-descarga eléctrica) con `scripts/flash-board.ps1`; el puerto USB
   nativo no tiene circuito de auto-descarga (solo funciona con BOOT+RST
   manual, que el script también detecta).
2. **Boot limpio** — el boot loop ("CSI not enabled in menuconfig!") murió
   con el fix `a1f6950` (`CONFIG_ESP_WIFI_CSI_ENABLED=y` en
   `sdkconfig.defaults`).
3. **La cadena completa fluye** — placa → Wi-Fi (SSID 2.4 GHz) → MQTT al
   broker (`mqtt://192.168.20.30:1883`) → backend. **Prueba viviente**: el
   primer paquete real de la placa crasheó la GUI (bug `t_s`/`t_us`,
   corregido en `a809832`) — ese crash ES la prueba de que la placa
   publicaba y el backend recibía. Suite 46/46 con test de regresión que
   reproduce el camino exacto.
4. **Identidad del nodo**: link `59c0a0` (MAC 28:84:85:59:c0:a0).

Falta (cosmético, mañana): confirmación visual final de las estimativas en
pantalla tras el fix `a809832` (la GUI crasheaba al primer paquete; con el
fix el flujo continúa hasta la ventana).

## 2. GUI — cuánto se puede optimizar la fluidez

Análisis de `backend/gui.py` (280 líneas). El cuello de botella NO es el
dato (drain de 256/tick a 5 Hz, FFT a 1 Hz: milisegundos) — es **el
repaint completo de matplotlib**: cada `draw_idle()` repinta las 6 axes de
la figura (incluidos dos `imshow`), y hoy se dispara hasta ~6 veces/seg.

Propuestas en orden de impacto (necesito tu GO — Qt no se puede probar
en este WSL, se implementa y verifica con vos presente):

- **A1 — Throttle de repaints (ganancia ~3-5× CPU)**: repintar TODO a 1 Hz
  en vez de la traza cruda a 5 Hz. Cambio: mover `_redraw_raw()` al bloque
  de estimativa (1 Hz) y dejar el tick a 5 Hz solo para drenar datos +
  status bar. ~10 líneas. Diferencia visual casi nula con datos de 10 Hz.
- **A2 — Ejes de longitud fija**: reemplazar `relim()+autoscale_view()`
  (recalcular límites en cada redraw, 6 axes) por ventana x fija [0, 15 s]
  + autoscale de y solo en el tick de estimativa. ~15 líneas.
- **A3 — Figuras separadas**: partir en 2 canvases (trazas izq. / paneles
  físicos der.) para que el lado pesado repinte solo a 1 Hz. ~30 líneas,
  riesgo medio.
- **A4 — Micro**: `interpolation="nearest"` en el espectrograma (bilinear
  es más caro); blitting (opcional, más complejo, dejar para después).

Recomendación: **A1 + A2 mañana** (~30 min con verificación tuya en vivo).
A3 solo si A1+A2 no alcanzan.

## 3. Portabilidad — hasta dónde se puede avanzar

Tu objetivo declarado: **el sistema entero portable**, no solo el
environment. Camino (por costo/valor):

1. **Viewer .exe (PyInstaller)** — LISTO PARA EJECUTAR (~30 min):
   `pip install pyinstaller` en el venv → `pyinstaller --onefile --name
   csi-web-viewer --add-data "web_static;web_static" web_viewer.py` →
   `dist\csi-web-viewer.exe` corre en cualquier Windows x64 sin Python.
   Nota técnica: `_STATIC_DIR` usa `Path(__file__).parent` que dentro de
   onefile resuelve al `_MEIPASS` — probable funciona tal cual; si no,
   un guard de 1 línea (`getattr(sys, "_MEIPASS", ...)`).
2. **Broker portable** (~1-2 h): bundle `mosquitto.exe` (~2 MB, build
   Windows oficial) + el `mosquitto.conf` del repo + un `.bat` que lo
   levante. Con esto, "sistema entero portable" = UNA CARPETA:
   viewer.exe + mosquitto.exe + .bat (+ el ESP32 en el bolsillo).
3. **GUI .exe (opcional)**: PyQt5+matplotlib empaqueta en ~200 MB;
   recomendable SOLO después de 1 y 2 (el viewer en el celu cubre la
   mayoría del uso).
4. **Simulator portable** (~15 min): demo sin hardware en cualquier PC.
5. **Firmware**: portable por naturaleza; re-flashear en cualquier PC
   es una línea (`flash-board.ps1`).

## 4. Exactitud — hasta dónde se puede avanzar

Priorizado por física/costo (los detalles teóricos ya viven en
`docs/SIGNAL-MODELING.md`):

1. **Validación con referencia** — sin verdad de tierra, toda mejora es a
   ciegas. Arnés mínimo: pulsioxímetro/app de pulso en el celu como
   referencia simultánea + protocolo de 5 min quieto / 5 min respiración
   controlada. Es la base para TODO lo demás. (~1 sesión)
2. **Segundo nodo ESP32** — el mayor salto de exactitud disponible: la
   diversidad multi-link elimina los nulls de Fresnel (el sistema ya
   tiene la fusión max-SNR lista; SOLO flashear otra placa — hoy el
   flasheo es automático por COM). (~1 placa + 15 min)
3. **Fusión ponderada de subportadoras** — hoy gana la MEJOR
   subportadora por banda; ponderar las top-N por SNR daría ~2-3 dB
   efectivos. Cambio acotado en `vitals_processor.py` + tests. (~2 h)
4. **Export de fase en firmware** (`atan2(Q,I)`): desbloquea el sensing
   Doppler-fase (señal cardíaca mucho más fuerte que amplitud pura — el
   camino documentado en §3). Firmware + parser + backend. (~medio día)
5. **Calibración RSSI a campo** (procedimiento en §6, vars en config):
   medir R0/d0/n_pl → distancia de enlace real. (~15 min de medición)
6. **Ventana dual** (10 s respuesta / 30 s precisión, cruces) — opcional.

## 5. Pendientes para mañana (necesito de vos)

1. **GUI en pantalla**: abrí la GUI (`main.py --host localhost` desde
   `backend\`) y confirmame las estimativas — es el cierre visual del hito.
2. **Git remote**: creá el repo vacío (privado, sin README/license) y
   pasame la URL + tu auth (PAT o SSH; `gh` no está instalado en WSL).
3. **GO/NO-GO** de: A1+A2 de GUI, viewer.exe, broker portable,
   2º ESP32, y el arnés de validación (en ese orden de mi recomendación).
4. (Opcional) `wsl --shutdown` si querés que el `dialout` quede permanente.

## 6. Registro de la noche (para el arco del proyecto)

| Qué | Commit |
|---|---|
| Flasher Windows one-shot (COM/UART/dual-port) | `39b6086`, `faa7ec6`, `66fe0c5`, `9452fa4` |
| Lector de log serial (`serial_mon.py`) | `cacceda` |
| Fix CSI Kconfig (fin del boot loop) | `a1f6950` |
| Nota de doc sobre el pin CSI | `474fa46` |
| Fix timestamps reales (`t_us`) + fixtures reales + regresión | `a809832` |

Suite: **46/46** · Firmware: **wifi_csi_vitals.bin 901 KB, 41% margen**
· Placa: ESP32-S3 rev v0.2, 16 MB flash, link `59c0a0`.
