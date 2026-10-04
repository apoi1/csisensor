"""Standalone LAN web viewer: live vital-signs page for phones/tablets.

An independent MQTT consumer (like the desktop GUI): the paho subscription
feeds the same VitalsProcessor/MotionAnalyzer DSP, and an aiohttp server
serves a self-contained page plus a WebSocket that broadcasts ~1 Hz
snapshots to every connected browser.  No Qt import, so it runs headless
(WSL, server, packaged app) and keeps working while the desktop GUI is
closed.

Research/educational tool.  Not a medical device.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
import time
from collections import deque
from dataclasses import replace
from pathlib import Path

import numpy as np
from aiohttp import web

from config import Config
from link_manager import LinkManager

logger = logging.getLogger("web_viewer")

_STATIC_DIR = Path(__file__).resolve().parent / "web_static"
HISTORY_POINTS = 600  # ~10 min of 1 Hz snapshots kept for the trend plot


def _round_list(values, digits: int = 4):
    return np.round(np.asarray(values, dtype=float), digits).tolist()


class ViewerState:
    """Thread-safe latest snapshot + rolling history for the web page.

    The feed thread calls drain_and_feed()/maybe_estimate() on the
    LinkManager; the asyncio WS handlers only read latest().
    """

    def __init__(self, links: LinkManager,
                 history_points: int = HISTORY_POINTS):
        self._links = links
        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=max(2, history_points))
        self._latest = self._empty_snapshot()
        self._last_estimate = 0.0

    # ---------------------------------------------------------------- input
    def ingest(self, link_id: str, packets) -> int:
        """Passthrough: push packets into one link's pipelines."""
        return self._links.ingest(link_id, packets)

    def maybe_estimate(self, now: float, every_s: float = 1.0) -> bool:
        """Assemble a fresh snapshot at most once per `every_s` seconds."""
        if now - self._last_estimate < every_s:
            return False
        self._last_estimate = now
        est = self._links.estimate()
        mot = self._links.motion_estimate()
        self._latest = self._snapshot(now, est, mot)
        return True

    # ------------------------------------------------------------- snapshot
    def _empty_snapshot(self) -> dict:
        return {
            "ts": 0.0, "fill": 0.0, "ready": False,
            "heart_bpm": None, "resp_pm": None,
            "heart_snr_db": 0.0, "resp_snr_db": 0.0,
            "presence": "Filling", "motion_rms": 0.0,
            "rssi_dbm": None, "distance_m": None,
            "n_samples": 0, "n_subcarriers": 0, "n_links": 0,
            "wave": None,
            "history": {"t": [], "heart": [], "resp": []},
        }

    def _snapshot(self, now: float, est, mot) -> dict:
        # Record the fresh point first so the broadcast history includes it.
        self._history.append((
            now,
            None if est is None or est.heart_bpm is None else round(est.heart_bpm, 1),
            None if est is None or est.resp_pm is None else round(est.resp_pm, 1)))
        hist_t, hist_h, hist_r = [], [], []
        for ts, h, r in self._history:
            hist_t.append(round(ts, 1))
            hist_h.append(h)
            hist_r.append(r)

        snap = self._empty_snapshot()
        snap["ts"] = round(now, 3)
        snap["fill"] = round(self._links.fill() / max(1, self._links.capacity()), 3)
        snap["ready"] = (self._links.capacity() > 0
                          and self._links.fill() >= self._links.capacity())
        snap["history"] = {"t": hist_t, "heart": hist_h, "resp": hist_r}

        if est is not None:
            snap["heart_bpm"] = None if est.heart_bpm is None else round(est.heart_bpm, 1)
            snap["resp_pm"] = None if est.resp_pm is None else round(est.resp_pm, 1)
            snap["heart_snr_db"] = round(float(est.heart_snr_db), 2)
            snap["resp_snr_db"] = round(float(est.resp_snr_db), 2)
            snap["n_samples"] = est.n_samples
            snap["n_subcarriers"] = est.n_subcarriers
            idx = max(0, est.wave_times_s.size - 160)  # keep the page payload small
            snap["wave"] = {
                "t": _round_list(est.wave_times_s[idx:]),
                "heart": _round_list(est.heart_wave[idx:]),
                "resp": _round_list(est.resp_wave[idx:]),
            }
        snap["n_links"] = self._links.n_links()

        if mot is not None:
            snap["presence"] = mot.state.value
            snap["motion_rms"] = round(float(mot.motion_rms), 3)
            snap["rssi_dbm"] = None if mot.rssi_dbm is None else round(mot.rssi_dbm, 1)
            snap["distance_m"] = None if mot.distance_m is None else round(mot.distance_m, 2)

        return snap

    def latest(self) -> dict:
        with self._lock:
            return self._latest


# ------------------------------------------------------------------ aiohttp
def _ws_handler_factory(state: ViewerState):
    async def ws_handler(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        logger.info("browser connected from %s", request.remote)
        last_ts = None
        try:
            while True:
                snap = state.latest()
                if snap["ts"] != last_ts:
                    last_ts = snap["ts"]
                    await ws.send_str(json.dumps(snap))
                await asyncio.sleep(0.5)
        except ConnectionResetError:
            pass
        finally:
            logger.info("browser disconnected from %s", request.remote)
        return ws

    return ws_handler


def build_app(state: ViewerState) -> web.Application:
    app = web.Application()

    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(_STATIC_DIR / "index.html")

    app.router.add_get("/", index, name="index")
    app.router.add_get("/ws", _ws_handler_factory(state), name="ws")
    return app


# ----------------------------------------------------------------- feed loop
def _feed_loop(state: ViewerState, links: LinkManager,
               every_s: float, stop: threading.Event) -> None:
    """Drain the MQTT queue into the link pipelines; assemble ~1 Hz snapshots.

    An exception in one iteration must never kill the feed thread silently
    and leave the page showing stale data (review finding R4-3): log and
    continue.
    """
    while not stop.is_set():
        try:
            links.drain_and_feed(256)
            state.maybe_estimate(time.time(), every_s)
        except Exception:
            logger.exception("web viewer feed iteration failed; continuing")
        stop.wait(0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description="WiFi-CSI web viewer (LAN)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="web bind address (default: 0.0.0.0 = LAN reachable)")
    parser.add_argument("--port", type=int, default=8080,
                        help="web port (default: 8080)")
    parser.add_argument("--broker", default=None,
                        help="MQTT broker host (default: localhost)")
    parser.add_argument("--mqtt-port", type=int, default=None,
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
    if args.broker is not None:
        cfg = replace(cfg, mqtt_host=args.broker)
    if args.mqtt_port is not None:
        cfg = replace(cfg, mqtt_port=args.mqtt_port)
    if args.topic is not None:
        cfg = replace(cfg, topic_raw=args.topic)
    if args.fs is not None:
        cfg = replace(cfg, sample_rate_hz=args.fs)
    if args.window is not None:
        cfg = replace(cfg, window_seconds=args.window)
    if args.topic is not None:
        cfg = replace(cfg, topic_patterns=(args.topic,))

    links = LinkManager(cfg)
    state = ViewerState(links)
    links.sub.start()

    stop = threading.Event()
    feed = threading.Thread(target=_feed_loop,
                            args=(state, links, cfg.estimate_every_s, stop),
                            daemon=True, name="web-viewer-feed")
    feed.start()

    app = build_app(state)
    logger.info("web viewer listening on http://%s:%d (broker %s:%d, topics %s)",
                args.host, args.port, cfg.mqtt_host, cfg.mqtt_port,
                ", ".join(cfg.topic_patterns))
    try:
        web.run_app(app, host=args.host, port=args.port, print=None)
    finally:
        stop.set()
        links.sub.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
