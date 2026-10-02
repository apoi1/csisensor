# WiFiCSI Tracking Feature

This feature implements a real‑time Wi‑Fi CSI data pipeline from an ESP32‑S3 to a desktop Python application that infers vital‑signs (heart rate, breathing rate). It consists of:

1. ESP32 firmware (ESP‑IDF + WiFiCSI) that captures CSI and publishes it via MQTT.
2. A local MQTT broker (Mosquitto) to relay messages.
3. A Python backend that subscribes to the broker, processes the CSI streams, detects vital‑sign rates, and exposes a simple API.
4. A PyQt5 GUI that visualises the inferred vital‑signs in real time.

All source and support scripts are located under `src` and `backend` directories.
