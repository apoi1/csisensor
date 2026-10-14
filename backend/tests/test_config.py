"""Config surface tests (review follow-up R3-ranging-defaults-unreachable).

The RSSI ranging knobs must keep their calibrated defaults while gaining a
reachable disabled state: an empty value or "none" maps to None, which is
MotionAnalyzer's "ranging not calibrated" state.
"""
import numpy as np

from config import Config
from motion_analyzer import MotionAnalyzer


def test_ranging_defaults_stay_calibrated_values(monkeypatch):
    for name in ("CSI_RSSI_REF_DBM", "CSI_REF_DISTANCE_M", "CSI_PATH_LOSS_N"):
        monkeypatch.delenv(name, raising=False)
    cfg = Config()
    assert cfg.rssi_ref_dbm == -52.0
    assert cfg.ref_distance_m == 1.0
    assert cfg.path_loss_exponent == 3.0


def test_ranging_can_be_disabled_via_empty_or_none(monkeypatch):
    monkeypatch.setenv("CSI_RSSI_REF_DBM", "")
    assert Config().rssi_ref_dbm is None
    monkeypatch.setenv("CSI_RSSI_REF_DBM", "none")
    assert Config().rssi_ref_dbm is None
    monkeypatch.setenv("CSI_RSSI_REF_DBM", "NONE")
    assert Config().rssi_ref_dbm is None
    monkeypatch.setenv("CSI_RSSI_REF_DBM", "-60.5")
    assert Config().rssi_ref_dbm == -60.5
    monkeypatch.delenv("CSI_RSSI_REF_DBM")
    monkeypatch.setenv("CSI_REF_DISTANCE_M", "none")
    assert Config().ref_distance_m is None


def test_mqtt_topic_env_restores_baseline_override(monkeypatch):
    # R1-002 / R2-MqttTopicEnvSilentlyDead / R3-002: MQTT_TOPIC is the
    # baseline configuration contract. An explicit override must replace
    # the whole subscription list (single topic/pattern); unset or the
    # legacy default value expands to the multi-link patterns (per-device
    # wildcard + legacy flat topic, so old firmware keeps working).
    monkeypatch.delenv("MQTT_TOPIC", raising=False)
    assert Config().topic_patterns == ("esp32/+/csi/raw", "esp32/csi/raw")
    monkeypatch.setenv("MQTT_TOPIC", "esp32/csi/raw")   # legacy default value
    assert Config().topic_patterns == ("esp32/+/csi/raw", "esp32/csi/raw")
    monkeypatch.setenv("MQTT_TOPIC", "")                 # empty = unset
    assert Config().topic_patterns == ("esp32/+/csi/raw", "esp32/csi/raw")
    monkeypatch.setenv("MQTT_TOPIC", "lab/room1/csi")
    assert Config().topic_patterns == ("lab/room1/csi",)


def test_disabled_ranging_config_yields_no_distance(monkeypatch):
    # End to end: Config -> MotionAnalyzer with the disabled state must
    # report no distance (None), not an uncalibrated guess.
    monkeypatch.setenv("CSI_REF_DISTANCE_M", "none")
    cfg = Config()
    analyzer = MotionAnalyzer(fs=10.0, window_s=15.0,
                              rssi_ref_dbm=cfg.rssi_ref_dbm,
                              ref_distance_m=cfg.ref_distance_m,
                              path_loss_exponent=cfg.path_loss_exponent)
    assert analyzer._distance(-52.0) is None
    # And the calibrated path still works through the same surface.
    monkeypatch.delenv("CSI_REF_DISTANCE_M")
    monkeypatch.setenv("CSI_REF_DISTANCE_M", "2.0")
    cfg = Config()
    analyzer = MotionAnalyzer(fs=10.0, window_s=15.0,
                              rssi_ref_dbm=cfg.rssi_ref_dbm,
                              ref_distance_m=cfg.ref_distance_m,
                              path_loss_exponent=cfg.path_loss_exponent)
    assert analyzer._distance(-52.0) == 2.0
