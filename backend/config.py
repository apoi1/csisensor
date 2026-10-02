"""Central configuration for the CSI backend / GUI (env-overridable)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # MQTT
    mqtt_host: str = os.environ.get("MQTT_HOST", "localhost")
    mqtt_port: int = _env_int("MQTT_PORT", 1883)
    topic_raw: str = os.environ.get("MQTT_TOPIC", "esp32/csi/raw")

    # Sampling / processing
    sample_rate_hz: float = _env_float("CSI_FS", 10.0)
    window_seconds: float = _env_float("CSI_WINDOW_S", 15.0)

    # Physiological bands (Hz): respiration 6-30/min, heart 48-120 bpm
    heart_band_hz: tuple = (0.8, 2.0)
    resp_band_hz: tuple = (0.1, 0.5)
    min_snr_db: float = _env_float("CSI_MIN_SNR_DB", 6.0)

    # GUI cadence
    gui_refresh_hz: float = 5.0
    estimate_every_s: float = 1.0
