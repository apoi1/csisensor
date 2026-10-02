# WiFi CSI → Vital Signs: ESP32-S3 firmware (ESP-IDF v5.x)
#
# Build/flash from WSL:
#   idf.py set-target esp32s3
#   idf.py build
#   idf.py -p /dev/ttyACM0 flash monitor
#
# Requires ESP-IDF v5.x (esp_mqtt nested broker config + CSI API).

cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(wifi_csi_vitals)
