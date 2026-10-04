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


def test_nonfinite_amplitudes_are_dropped():
    # R3-nan-inputs: one NaN/Inf subcarrier (or timestamp) must be dropped,
    # never allowed to poison the whole window.
    t, rows, rssi = synth_matrix("vitals")
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    feed(a, t, rows, rssi)
    n_before = len(a._times)
    a.push(t[-1] + 1.0, np.r_[rows[0, :3], np.nan], -52.0)  # NaN subcarrier
    a.push(t[-1] + 2.0, rows[1] + np.inf, -52.0)            # Inf subcarrier
    a.push(float("nan"), rows[2], -52.0)                    # NaN timestamp
    assert len(a._times) == n_before
    est = a.estimate()
    assert est is not None
    assert np.isfinite(est.window_std) and np.isfinite(est.motion_rms)


def test_nonfinite_rssi_reading_is_dropped_not_the_packet():
    # The amplitude sample survives; only the broken RSSI reading is lost.
    t, rows, _ = synth_matrix("vitals")
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    feed(a, t, rows, np.full(t.size, np.nan))
    est = a.estimate()
    assert est is not None
    assert est.n_samples == int(FS * WINDOW_S)
    assert est.rssi_dbm is None and est.distance_m is None


def test_low_sample_rate_does_not_crash():
    # R3-low-fs-crash: Nyquist (0.5 Hz) cannot express the motion band; the
    # analyzer must degrade to the std fallback instead of raising.
    a = MotionAnalyzer(fs=1.0, window_s=16.0)
    t = np.arange(16) / 1.0
    rng = np.random.default_rng(3)
    rows = 30.0 + rng.normal(0.0, 0.05, (t.size, 4))
    feed(a, t, rows, np.full(t.size, -52.0))
    est = a.estimate()
    assert est is not None
    assert np.isfinite(est.motion_rms)


def test_small_window_breathing_is_still_not_moving():
    # R3-small-window-fallback: 16 samples (< 30) -> 2nd-order bandpass, so
    # 0.3 Hz breathing stays out of the motion band instead of tripping the
    # MOVING threshold through the full-band fallback.
    a = MotionAnalyzer(fs=2.0, window_s=8.0)   # capacity floor: 16 samples
    t = np.arange(a.capacity) / 2.0
    rng = np.random.default_rng(5)
    rows = (30.0 + 3.0 * np.sin(2 * np.pi * 0.3 * t)[:, None]
            + rng.normal(0.0, 0.05, (t.size, 4)))
    feed(a, t, rows)
    est = a.estimate()
    assert est is not None
    assert est.state is PresenceState.STILL


def test_distance_guards_nonfinite_and_bad_reference():
    # R3-distance-guard-coverage: non-finite RSSI and non-positive reference
    # distance must yield None instead of NaN / nonsense distances.
    a = MotionAnalyzer(fs=FS, window_s=WINDOW_S)
    assert a._distance(float("nan")) is None
    assert a._distance(float("-inf")) is None
    b = MotionAnalyzer(fs=FS, window_s=WINDOW_S, ref_distance_m=0.0)
    assert b._distance(-52.0) is None
