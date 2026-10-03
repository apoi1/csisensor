"""Entry point: MQTT CSI backend + PyQt5 real-time GUI."""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from PyQt5.QtWidgets import QApplication

from config import Config
from gui import VitalsWindow
from motion_analyzer import MotionAnalyzer
from mqtt_subscriber import CsiSubscriber
from vitals_processor import VitalsProcessor


def main() -> int:
    parser = argparse.ArgumentParser(description="WiFi-CSI vital signs backend/GUI")
    parser.add_argument("--host", default=None,
                        help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=None,
                        help="MQTT broker port (default: 1883)")
    parser.add_argument("--topic", default=None,
                        help="CSI topic (default: esp32/csi/raw)")
    parser.add_argument("--fs", type=float, default=None,
                        help="expected CSI sample rate in Hz (default: 10)")
    parser.add_argument("--window", type=float, default=None,
                        help="estimation window in seconds (default: 15)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    cfg = Config()
    if args.host is not None:
        cfg = replace(cfg, mqtt_host=args.host)
    if args.port is not None:
        cfg = replace(cfg, mqtt_port=args.port)
    if args.topic is not None:
        cfg = replace(cfg, topic_raw=args.topic)
    if args.fs is not None:
        cfg = replace(cfg, sample_rate_hz=args.fs)
    if args.window is not None:
        cfg = replace(cfg, window_seconds=args.window)

    processor = VitalsProcessor(fs=cfg.sample_rate_hz,
                                window_s=cfg.window_seconds,
                                heart_band_hz=cfg.heart_band_hz,
                                resp_band_hz=cfg.resp_band_hz,
                                min_snr_db=cfg.min_snr_db)
    motion = MotionAnalyzer(fs=cfg.sample_rate_hz,
                            window_s=cfg.window_seconds,
                            absent_std_threshold=cfg.absent_std_threshold,
                            moving_rms_threshold=cfg.moving_rms_threshold,
                            rssi_ref_dbm=cfg.rssi_ref_dbm,
                            ref_distance_m=cfg.ref_distance_m,
                            path_loss_exponent=cfg.path_loss_exponent)
    subscriber = CsiSubscriber(cfg.mqtt_host, cfg.mqtt_port, cfg.topic_raw)
    subscriber.start()

    app = QApplication(sys.argv)
    window = VitalsWindow(cfg, subscriber, processor, motion)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
