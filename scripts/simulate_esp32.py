#!/usr/bin/env python3
"""Synthetic ESP32 CSI publisher: test the backend/GUI without hardware.

Publishes the exact same CSV format as the firmware:
    t_us,rssi,n,seq,a0,...,a<n-1>
Defaults simulate ~66 BPM heart and 18/min respiration on 64 subcarriers.

Usage (inside the backend venv):
    python scripts/simulate_esp32.py --host localhost
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import paho.mqtt.client as mqtt


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish synthetic CSI packets")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--topic", default="esp32/csi/raw")
    ap.add_argument("--subcarriers", type=int, default=64)
    ap.add_argument("--rate", type=float, default=10.0, help="packets per second")
    ap.add_argument("--heart-hz", type=float, default=1.1, help="~66 BPM")
    ap.add_argument("--resp-hz", type=float, default=0.3, help="~18/min")
    args = ap.parse_args()

    rng = np.random.default_rng(42)
    heart_phase = rng.uniform(0, 2 * np.pi, args.subcarriers)
    resp_phase = rng.uniform(0, 2 * np.pi, args.subcarriers)

    client = mqtt.Client(client_id="csi-simulator")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    print(f"publishing synthetic CSI to {args.host}:{args.port}/{args.topic} "
          f"({args.rate} Hz, {args.subcarriers} subcarriers) - Ctrl+C to stop")

    seq = 0
    t0 = time.monotonic()
    next_t = t0
    period = 1.0 / args.rate
    try:
        while True:
            t = time.monotonic() - t0
            amps = (30.0
                    + 3.0 * np.sin(2 * np.pi * args.resp_hz * t + resp_phase)
                    + 0.9 * np.sin(2 * np.pi * args.heart_hz * t + heart_phase)
                    + rng.normal(0.0, 0.05, args.subcarriers))
            payload = ",".join([f"{int(time.time() * 1e6)}", "-52",
                                str(args.subcarriers), str(seq)]
                               + [f"{a:.0f}" for a in amps])
            client.publish(args.topic, payload, qos=0)
            seq += 1
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()
        print(f"\nstopped after {seq} packets")


if __name__ == "__main__":
    main()
