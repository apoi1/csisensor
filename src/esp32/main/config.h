#pragma once

/* ======================================================================
 *  User configuration — EDIT THIS FILE before building.
 * ==================================================================== */

/* ------------------------- WiFi (2.4 GHz only) ----------------------- */
#define WIFI_SSID   "CHANGE_ME"
#define WIFI_PASS   "CHANGE_ME"

/* ------------------------------- MQTT --------------------------------
 * The ESP32 needs the broker's LAN address, NOT "localhost".
 * Use the Windows host IP that runs Docker Desktop + Mosquitto,
 * e.g. the IPv4 shown by `ipconfig` on the Wi-Fi adapter.               */
#define MQTT_BROKER_URI  "mqtt://192.168.1.50:1883"
#define MQTT_TOPIC_CSI   "esp32/csi/raw"

/* -------------------------------- CSI -------------------------------- */
#define CSI_INTERVAL_MS      100       /* packet/ping interval ≈ sample rate (10 Hz) */
#define CSI_MAX_SUBCARRIERS  128       /* upper bound per chip (S3 uses ~64) */
#define CSI_CHANNEL_FILTER   true      /* smooth adjacent subcarriers (higher SNR) */

/* 1 = firmware pings the gateway to generate steady RX traffic (default).
 * 0 = generate traffic externally: `ping -t <ESP32_IP>` from any machine,
 *     or rely on ambient traffic (see DEPLOYMENT.md).                   */
#define USE_TRAFFIC_PING     1
