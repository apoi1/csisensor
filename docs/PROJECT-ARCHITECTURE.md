# Arquitectura del Sistema: WiFi-CSI Vital Signs

## Resumen Ejecutivo
Pipeline de seguimiento vital (pulso/respiración) mediante WiFi CSI. Utiliza el ruido y desplazamiento de fase en las subportadoras (subcarriers) del protocolo WiFi 802.11n para detectar micro-movimientos torácicos.

## Pipeline de Datos
1. **Adquisición (ESP32-S3):** Captura CSI nativa (`esp_wifi_set_csi_rx_cb`). Genera tráfico constante mediante ping (~10Hz) al gateway. Publica en MQTT como CSV `t_us,rssi,n,seq,a0...aN`; cada dispositivo publica en su tópico `esp32/<id>/csi/raw` (id = últimos 3 bytes de la MAC) y el tópico plano `esp32/csi/raw` queda como caso base de un solo dispositivo.
2. **Transporte:** Mosquitto Broker (Docker).
3. **Procesamiento (Python):** 
   - **MultiLinkSubscriber (`link_manager.py`):** se suscribe a `esp32/+/csi/raw` (wildcard multi-dispositivo) más el tópico plano `esp32/csi/raw` (compatibilidad); etiqueta cada paquete con su link id (derivado del tópico) y lo enruta a pipelines aislados por link, que luego se fusionan por banda (max SNR).
   - **VitalsProcessor:** Mantiene ventana deslizante (15s). Selecciona el mejor subcarrier por SNR en banda (0.1-0.5Hz resp, 0.8-2.0Hz heart). FFT + interpolación parabólica para estimar frecuencia.
   - **MqttSubscriber:** Listener desacoplado (paho-mqtt) que vuelca a `queue.Queue`.
   - **MotionAnalyzer:** Ventana deslizante de (amplitud media CSI, RSSI); clasifica presencia (Ausente/En reposo/Movimiento) por umbral de desviación estándar y RMS de la banda de movimiento (0.5–3.0 Hz); estima la distancia de enlace RSSI vía modelo log-distance path-loss.
4. **Visualización:** PyQt5 + Matplotlib en grilla 2×3: trazas CSI/respiración/pulso + heatmap de subportadoras, espectrograma con bandas fisiológicas y traza de energía de movimiento; fila "Body" con estado y métricas en tiempo real; fórmulas con anotaciones mathtext.

## Stack Tecnológico
- **Firmware:** ESP-IDF v5.x (C++11/C++20), lwIP (ping), esp-mqtt.
- **Backend:** Python 3.10+, `numpy`, `scipy` (filtros butterworth sosfiltfilt, FFT).
- **Multi-link (backend):** `link_manager.py` (`MultiLinkSubscriber`, fusión multi-ESP32 por banda max SNR).
- **GUI:** PyQt5 (Qt5Agg backend), Matplotlib.
- **Web viewer:** aiohttp (HTTP + WebSocket, `web_viewer.py` + `web_static/`), sin Qt.
- **Entorno:** WSL2 (firmware) / Windows 10/11 (Docker/Python).

## Estado de implementación
- [x] Firmware nativo con API ESP-IDF v5.
- [x] Backend de procesamiento con FFT (suite 50/50: estimador, parser, analizador de presencia/movimiento, link manager multi-ESP32, config y web viewer).
- [x] GUI en tiempo real con 3 plots y etiquetas dinámicas.
- [x] Script simulador para dry-run.
- [x] Guía de deployment (DEPLOYMENT.md) completa.
- [x] `MotionAnalyzer` con clasificación presencia/movimiento y estimación de distancia de enlace.
- [x] Panel Body + paneles físicos en la GUI (heatmap/espectrograma/energía de movimiento).
- [x] Escenarios del simulador (resting/moving/absent).
- [x] docs/SIGNAL-MODELING.md (modelo de señal, matemática y calibración).
- [x] `link_manager.py`: MultiLinkSubscriber + fusión multi-ESP32 por banda (max SNR) con presencia conservadora.
- [x] Web viewer LAN (`web_viewer.py` + `web_static/`, aiohttp) para teléfonos.

## Funciones de la GUI y evaluación de la posición del cuerpo

La GUI añade una fila **"Body"** con el estado y métricas en tiempo real:
`Body: {estado} | RMS de movimiento | σ_ventana | RSSI dBm | distancia de enlace ~X m`.

- **Estados de presencia** (clasificados por `MotionAnalyzer` a partir de la amplitud media CSI):
  - **Ausente:** sala vacía con canal plano de ruido (σ de la amplitud media deslindada < 0.15).
  - **Movimiento:** movimiento corporal grueso (RMS de la banda 0.5–3.0 Hz > 1.5).
  - **En reposo:** persona presente en reposo.
- **Distancia de enlace:** el RSSI promedio de la ventana se convierte en una estimación de distancia vía modelo log-distance path-loss (`d_hat = d0·10^((R0−R)/(10·n_pl))`). Es la **distancia del enlace** (router ↔ dispositivo), **no coordenadas de la persona**.
- **Paneles físicos** (columna derecha de la grilla 2×3, anotados con fórmulas en mathtext):
  - Heatmap de subportadoras: `|H_k| = √(I_k² + Q_k²)` en dB.
  - Espectrograma de la amplitud media de la ventana con bandas fisiológicas sombreadas (respiración 0.1–0.5 Hz, pulso 0.8–2.0 Hz).
  - Traza de energía de movimiento de 10 minutos (`M_rms`) con la línea del umbral de movimiento.

**Limitación física explícita:** se procesan solo amplitudes `|H_k|` de un único par antena/router (sin fase ni antenas múltiples) → no se pueden calcular coordenadas, postura ni ángulo de llegada; la posición del cuerpo se evalúa como clasificación presencia/movimiento + atenuación del enlace. El detalle matemático y las técnicas de calibración están en [docs/SIGNAL-MODELING.md](SIGNAL-MODELING.md).

## Notas Técnicas para el mantenimiento
- **Punto crítico:** `vitals_processor.py` hace `sps.detrend` previo a FFT. Si cambias el `fs` (10Hz), ajusta los `band_hz`.
- **Conectividad:** En firmware, el URI MQTT no debe ser "localhost" (necesita la IP de la máquina Windows).
- **Consumo:** El main loop del ESP32 está diseñado para no bloquear (queue depth 32); no añadir lógica pesada en el callback CSI.
- **Variables de entorno de MotionAnalyzer:** `CSI_ABSENT_STD`, `CSI_MOVING_RMS`, `CSI_RSSI_REF_DBM`, `CSI_REF_DISTANCE_M` y `CSI_PATH_LOSS_N` ajustan los umbrales de presencia y la calibración RSSI. Ahora el RSSI de los paquetes sí se usa (promedio de ventana → distancia de enlace).
- **Calibración:** ver docs/SIGNAL-MODELING.md para línea base de sala vacía (umbral de ausencia), umbral de movimiento y calibración RSSI en dos puntos.
