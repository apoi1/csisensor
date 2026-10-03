#!/usr/bin/env python3
"""Synthetic ESP32 CSI publisher: test the backend/GUI without hardware.

Publishes the exact same CSV format as the firmware:
    t_us,rssi,n,seq,a0,...,a<n-1>

Scenarios (--scenario):
    resting  person at rest: constant baseline plus slow respiration and
             heart sines on all subcarriers, constant RSSI -52 dBm
             (default, exactly the previous behaviour)
    moving   resting dynamics plus periodic motion episodes: every ~20 s a
             ~4 s episode adds a smooth random-walk common-mode offset
             (per-packet Gaussian step, std ~2.5, cumulative, decaying back
             to baseline afterwards) to all subcarriers, with the RSSI
             fluctuating by +-2 dB during episodes; between episodes the
             scene behaves like resting
    absent   empty room: noise-level amplitudes only (no sines), constant
             RSSI -52 dBm

Defaults simulate ~66 BPM heart and 18/min respiration on 64 subcarriers.

Usage (inside the backend venv):
    python scripts/simulate_esp32.py --host localhost
    python scripts/simulate_esp32.py --scenario moving
    python scripts/simulate_esp32.py --scenario absent
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
    ap.add_argument("--scenario", choices=["resting", "moving", "absent"],
                    default="resting",
                    help="synthetic scene: resting (default), moving "
                         "(motion episodes), absent (empty room)")
    args = ap.parse_args()

    rng = np.random.default_rng(42)
    heart_phase = rng.uniform(0, 2 * np.pi, args.subcarriers)
    resp_phase = rng.uniform(0, 2 * np.pi, args.subcarriers)

    # Motion-episode state (moving scenario only).  The common-mode offset
    # accumulates from small Gaussian steps during an episode and decays
    # back to the baseline afterwards, so between episodes the published
    # stream is identical to the resting scenario.
    moving = args.scenario == "moving"
    episode_period_s = 20.0
    episode_len_s = 4.0
    episode_start_s = None          # start of the running episode, None if idle
    next_episode_s = episode_period_s   # first episode ~20 s after start
    motion_offset = 0.0             # cumulative offset, decays to 0 when idle

    client = mqtt.Client(client_id="csi-simulator")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    print(f"publishing synthetic CSI to {args.host}:{args.port}/{args.topic} "
          f"({args.rate} Hz, {args.subcarriers} subcarriers, "
          f"scenario={args.scenario}) - Ctrl+C to stop")

    seq = 0
    t0 = time.monotonic()
    next_t = t0
    period = 1.0 / args.rate
    try:
        while True:
            t = time.monotonic() - t0

            in_episode = False
            if moving:
                if episode_start_s is None:
                    motion_offset *= 0.90  # decay residual offset (~10 Hz rate)
                    if t >= next_episode_s:
                        episode_start_s = t
                        next_episode_s = (t + episode_period_s
                                          + rng.uniform(-2.0, 2.0))
                elif t - episode_start_s < episode_len_s:
                    motion_offset += rng.normal(0.0, 2.5)
                    in_episode = True
                else:
                    episode_start_s = None  # episode over: offset decays

            if args.scenario == "absent":
                amps = 30.0 + rng.normal(0.0, 0.05, args.subcarriers)
            else:
                amps = (30.0
                        + 3.0 * np.sin(2 * np.pi * args.resp_hz * t + resp_phase)
                        + 0.9 * np.sin(2 * np.pi * args.heart_hz * t + heart_phase)
                        + rng.normal(0.0, 0.05, args.subcarriers))
                if moving:
                    amps = amps + motion_offset

            if in_episode:
                rssi = -52.0 + rng.uniform(-2.0, 2.0)  # small link fluctuation
            else:
                rssi = -52.0

            payload = ",".join([f"{int(time.time() * 1e6)}", f"{rssi:.0f}",
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
