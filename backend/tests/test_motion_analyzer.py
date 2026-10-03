"""Unit tests for the RSSI-assisted presence / motion analyzer."""
import numpy as np

from motion_analyzer import MotionAnalyzer, PresenceState

FS = 10.0
WINDOW_S = 15.0


def synth_matrix(kind="flat", n_sub=32, seed=7):
    """Synthetic CSI amplitude matrix + per-packet RSSI for one window."""
    t = np.arange(int(FS * WINDOW_S)) / FS
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 0.05, (t.size, n_sub))
    if kind == "flat":
        rows = 30.0 + noise
    elif kind == "vitals":
        # Respiration 0.3 Hz >> heart 1.1 Hz >> noise, as in the vitals tests.
        rows = (30.0
                + 3.0 * np.sin(2 * np.pi * 0.3 * t)[:, None]
                + 0.9 * np.sin(2 * np.pi * 1.1 * t)[:, None]
                + noise)
    else:  # "motion": random-walk offset shared by all subcarriers
        # Step std 2.5 keeps the bandpassed RMS well above the 1.5 threshold
        # (empirically 1.9-2.5 across seeds) with excursions > 5 units.
        walk = np.cumsum(rng.normal(0.0, 2.5, t.size))
        rows = 30.0 + (walk - walk.mean())[:, None] + noise
    rssi = np.full(t.size, -52.0)
    return t, rows, rssi


def feed(analyzer, t, rows, rssi=None):
    for i in range(rows.shape[0]):
        analyzer.push(t[i], rows[i], None if rssi is None else rssi[i])


def test_flat_noise_only_window_is_absent():
    t, rows, _ = synth_matrix("flat")
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    feed(a, t, rows)  # no RSSI recorded
    est = a.estimate()
    assert est is not None
    assert est.state is PresenceState.ABSENT
    assert est.rssi_dbm is None and est.distance_m is None


def test_breathing_and_heart_window_is_still():
    t, rows, rssi = synth_matrix("vitals")
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    feed(a, t, rows, rssi)
    est = a.estimate()
    assert est is not None
    assert est.state is PresenceState.STILL


def test_motion_episode_is_moving():
    t, rows, rssi = synth_matrix("motion")
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    feed(a, t, rows, rssi)
    est = a.estimate()
    assert est is not None
    assert est.state is PresenceState.MOVING
    assert est.motion_rms > 1.5


def test_distance_from_constant_rssi():
    t, rows, _ = synth_matrix("flat")
    rssi = np.full(t.size, -58.0)
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S,
                       rssi_ref_dbm=-52.0, ref_distance_m=1.0,
                       path_loss_exponent=3.0)
    feed(a, t, rows, rssi)
    est = a.estimate()
    assert est is not None
    expected = 1.0 * 10.0 ** ((-52.0 - (-58.0)) / (10.0 * 3.0))
    assert est.rssi_dbm == -58.0
    assert est.distance_m is not None
    assert abs(est.distance_m - expected) <= 0.01 * expected


def test_partial_window_returns_none():
    t, rows, rssi = synth_matrix()
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    for i in range(20):
        a.push(t[i], rows[i], rssi[i])
    assert a.ready() is False
    assert 0.0 < a.fill() < 1.0
    assert a.estimate() is None


def test_duplicate_and_out_of_order_timestamps_dropped():
    t, rows, rssi = synth_matrix()
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    for i in range(20):
        a.push(t[i], rows[i], rssi[i])
    n_before = len(a._times)
    a.push(t[19], rows[19], rssi[19])   # duplicate timestamp
    a.push(t[5], rows[5], rssi[5])      # out-of-order timestamp
    assert len(a._times) == n_before
