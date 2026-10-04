"""Central configuration for the CSI backend / GUI (env-overridable)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


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


def _env_float_opt(name: str, default: float) -> float | None:
    """Like _env_float, but an empty value or "none" disables the knob.

    This is the reachable path to MotionAnalyzer's ranging-disabled state
    (None): CSI_RSSI_REF_DBM="" or CSI_REF_DISTANCE_M=none turn the distance
    estimate off until real calibration values are provided (review
    follow-up R3-ranging-defaults-unreachable).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    if raw.strip() == "" or raw.strip().lower() == "none":
        return None
    try:
        return float(raw)
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

    # Presence / motion analysis (MotionAnalyzer).  Ranging knobs parse at
    # instantiation (default_factory) so tests and tools can set the env
    # before building a Config; empty/"none" disables RSSI ranging.
    absent_std_threshold: float = _env_float("CSI_ABSENT_STD", 0.15)
    moving_rms_threshold: float = _env_float("CSI_MOVING_RMS", 1.5)
    rssi_ref_dbm: float | None = field(
        default_factory=lambda: _env_float_opt("CSI_RSSI_REF_DBM", -52.0))
    ref_distance_m: float | None = field(
        default_factory=lambda: _env_float_opt("CSI_REF_DISTANCE_M", 1.0))
    path_loss_exponent: float = _env_float("CSI_PATH_LOSS_N", 3.0)

    # GUI cadence
    gui_refresh_hz: float = 5.0
    estimate_every_s: float = 1.0
