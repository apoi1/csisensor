# Arquitectura del Sistema: WiFi-CSI Vital Signs

## Resumen Ejecutivo
Pipeline de seguimiento vital (pulso/respiración) mediante WiFi CSI. Utiliza el ruido y desplazamiento de fase en las subportadoras (subcarriers) del protocolo WiFi 802.11n para detectar micro-movimientos torácicos.

## Pipeline de Datos
1. **Adquisición (ESP32-S3):** Captura CSI nativa (`esp_wifi_set_csi_rx_cb`). Genera tráfico constante mediante ping (~10Hz) al gateway. Publica en MQTT tópico `esp32/csi/raw` como CSV `t_us,rssi,n,seq,a0...aN`.
2. **Transporte:** Mosquitto Broker (Docker).
3. **Procesamiento (Python):** 
   - **VitalsProcessor:** Mantiene ventana deslizante (15s). Selecciona el mejor subcarrier por SNR en banda (0.1-0.5Hz resp, 0.8-2.0Hz heart). FFT + interpolación parabólica para estimar frecuencia.
   - **MqttSubscriber:** Listener desacoplado (paho-mqtt) que vuelca a `queue.Queue`.
4. **Visualización:** PyQt5 + Matplotlib.

## Stack Tecnológico
- **Firmware:** ESP-IDF v5.x (C++11/C++20), lwIP (ping), esp-mqtt.
- **Backend:** Python 3.10+, `numpy`, `scipy` (filtros butterworth sosfiltfilt, FFT).
- **GUI:** PyQt5 (Qt5Agg backend), Matplotlib.
- **Entorno:** WSL2 (firmware) / Windows 10/11 (Docker/Python).

## Estado de implementación
- [x] Firmware nativo con API ESP-IDF v5.
- [x] Backend de procesamiento con FFT (6 tests unitarios pasan).
- [x] GUI en tiempo real con 3 plots y etiquetas dinámicas.
- [x] Script simulador para dry-run.
- [x] Guía de deployment (DEPLOYMENT.md) completa.

## Notas Técnicas para el mantenimiento
- **Punto crítico:** `vitals_processor.py` hace `sps.detrend` previo a FFT. Si cambias el `fs` (10Hz), ajusta los `band_hz`.
- **Conectividad:** En firmware, el URI MQTT no debe ser "localhost" (necesita la IP de la máquina Windows).
- **Consumo:** El main loop del ESP32 está diseñado para no bloquear (queue depth 32); no añadir lógica pesada en el callback CSI.
