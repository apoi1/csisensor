"""Headless tests for the web viewer's snapshot pipeline (no sockets)."""
from types import SimpleNamespace

import numpy as np

from motion_analyzer import MotionAnalyzer
from vitals_processor import VitalsProcessor
from web_viewer import ViewerState, build_app

FS = 10.0
WINDOW_S = 15.0


def synth_packets(bpm=60.0, resp_pm=15.0, n_sub=32, seed=7, t0=100.0):
    """Synthetic clean CSI packets with known vital signs.

    Breathing and heart tones are coherent across subcarriers (zero phase):
    physically, chest displacement modulates the whole channel, which is
    also what MotionAnalyzer's mean-amplitude analysis expects.
    """
    n = int(FS * WINDOW_S) + 10
    t = t0 + np.arange(n) / FS
    rng = np.random.default_rng(seed)
    f_heart, f_resp = bpm / 60.0, resp_pm / 60.0
    rows = (30.0
            + 3.0 * np.sin(2 * np.pi * f_resp * t[:, None])
            + 0.9 * np.sin(2 * np.pi * f_heart * t[:, None])
            + rng.normal(0.0, 0.05, (n, n_sub)))
    return [SimpleNamespace(t_s=float(t[i]), amps=rows[i], rssi=-52.0)
            for i in range(n)]


def make_state(history_points=8):
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    m = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    return ViewerState(p, m, history_points=history_points)


def tick(state, packets, start=200.0):
    """Feed packets then force one estimate at time `start`."""
    state.feed(packets)
    state.maybe_estimate(start, every_s=1.0)


def test_partial_window_snapshot_shape():
    state = make_state()
    tick(state, synth_packets()[:20])
    snap = state.latest()
    assert snap["ts"] == 200.0
    assert 0.0 < snap["fill"] < 1.0
    assert snap["ready"] is False
    assert snap["heart_bpm"] is None and snap["resp_pm"] is None
    assert snap["presence"] == "Filling"
    assert snap["wave"] is None
    assert snap["history"]["t"] == [200.0]


def test_full_window_reports_estimates_and_presence():
    state = make_state()
    tick(state, synth_packets())
    snap = state.latest()
    assert snap["ready"] is True
    assert snap["heart_bpm"] is not None
    assert abs(snap["heart_bpm"] - 60.0) <= 5.0
    assert snap["resp_pm"] is not None
    assert abs(snap["resp_pm"] - 15.0) <= 3.0
    assert snap["presence"] in ("Still", "Moving")
    assert snap["rssi_dbm"] == -52.0
    assert snap["distance_m"] is not None
    assert snap["wave"] is not None
    assert len(snap["wave"]["t"]) == len(snap["wave"]["heart"])
    # JSON-serializable end to end
    import json
    json.dumps(snap)


def test_estimate_cadence_respects_every_s():
    state = make_state()
    pkts = synth_packets()
    state.feed(pkts)
    assert state.maybe_estimate(300.0, every_s=1.0) is True
    assert state.maybe_estimate(300.4, every_s=1.0) is False
    assert state.maybe_estimate(301.0, every_s=1.0) is True


def test_corrupt_packets_never_break_the_stream():
    # Continuity requirement: a NaN packet must be dropped by the hardened
    # pipelines, and the next snapshot still carries finite estimates.
    state = make_state()
    good = synth_packets()
    state.feed(good)
    state.maybe_estimate(400.0, every_s=1.0)
    corrupt = SimpleNamespace(t_s=500.0,
                              amps=np.r_[good[0].amps[:3], np.nan],
                              rssi=-52.0)
    nan_time = SimpleNamespace(t_s=float("nan"),
                               amps=good[1].amps, rssi=-52.0)
    state.feed([corrupt, nan_time])
    state.maybe_estimate(401.0, every_s=1.0)
    snap = state.latest()
    assert snap["heart_bpm"] is not None
    assert abs(snap["heart_bpm"] - 60.0) <= 5.0
    assert snap["rssi_dbm"] == -52.0  # the good packets' RSSI survived


def test_history_trims_to_max_points():
    state = make_state(history_points=5)
    pkts = synth_packets()
    for i in range(9):
        state.feed(pkts)
        state.maybe_estimate(500.0 + i, every_s=1.0)
    hist = state.latest()["history"]
    assert len(hist["t"]) == 5
    assert hist["t"] == [504.0, 505.0, 506.0, 507.0, 508.0]


def test_build_app_registers_routes():
    state = make_state()
    app = build_app(state)
    paths = {r.resource.canonical for r in app.router.routes()}
    assert paths == {"/", "/ws"}
    assert app.router["index"] is not None and app.router["ws"] is not None
