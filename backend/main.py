"""Entry point: MQTT CSI backend + PyQt5 real-time GUI (multi-link aware)."""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from PyQt5.QtWidgets import QApplication

from config import Config
from gui import VitalsWindow
from link_manager import DEFAULT_TOPIC_PATTERNS, LinkManager


def main() -> int:
    parser = argparse.ArgumentParser(description="WiFi-CSI vital signs backend/GUI")
    parser.add_argument("--host", default=None,
                        help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=None,
                        help="MQTT broker port (default: 1883)")
    parser.add_argument("--topic", default=None,
                        help="CSI topic or MQTT pattern (default: esp32/+/csi/raw + esp32/csi/raw for multi-ESP32)")
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
    if args.fs is not None:
        cfg = replace(cfg, sample_rate_hz=args.fs)
    if args.window is not None:
        cfg = replace(cfg, window_seconds=args.window)

    # --topic pins a single topic/pattern; default subscribes the per-device
    # wildcard plus the legacy flat topic (multi-ESP32 + backward compat).
    if args.topic is not None:
        cfg = replace(cfg, topic_patterns=(args.topic,))

    links = LinkManager(cfg)
    links.sub.start()

    app = QApplication(sys.argv)
    window = VitalsWindow(cfg, links)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
