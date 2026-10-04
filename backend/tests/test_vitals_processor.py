"""Unit tests for the FFT-based vital-sign estimator and the payload parser."""
import numpy as np

from csi_packets import parse_csi_payload
from vitals_processor import VitalsProcessor

FS = 10.0
WINDOW_S = 15.0


def synth_matrix(bpm=60.0, resp_pm=15.0, n_sub=32, seed=7):
    """Synthetic CSI amplitudes: respiration >> heart >> noise."""
    t = np.arange(int(FS * WINDOW_S)) / FS
    rng = np.random.default_rng(seed)
    heart_phase = rng.uniform(0, 2 * np.pi, n_sub)
    resp_phase = rng.uniform(0, 2 * np.pi, n_sub)
    f_heart, f_resp = bpm / 60.0, resp_pm / 60.0
    rows = (30.0
            + 3.0 * np.sin(2 * np.pi * f_resp * t[:, None] + resp_phase[None, :])
            + 0.9 * np.sin(2 * np.pi * f_heart * t[:, None] + heart_phase[None, :])
            + rng.normal(0.0, 0.05, (t.size, n_sub)))
    return t, rows


def feed(processor, t, matrix):
    for i in range(matrix.shape[0]):
        processor.push(t[i], matrix[i])


def test_heart_rate_estimated():
    t, m = synth_matrix(bpm=60.0, resp_pm=15.0)
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    feed(p, t, m)
    est = p.estimate()
    assert est is not None
    assert est.heart_bpm is not None
    assert abs(est.heart_bpm - 60.0) <= 5.0


def test_respiration_estimated():
    t, m = synth_matrix(bpm=60.0, resp_pm=15.0)
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    feed(p, t, m)
    est = p.estimate()
    assert est is not None
    assert est.resp_pm is not None
    assert abs(est.resp_pm - 15.0) <= 3.0


def test_partial_window_returns_none():
    t, m = synth_matrix()
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    for i in range(20):
        p.push(t[i], m[i])
    assert p.ready() is False
    assert p.estimate() is None


def test_flat_signal_reports_no_vitals():
    t, m = synth_matrix()
    flat = np.full_like(m, 30.0)
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    feed(p, t, flat)
    est = p.estimate()
    assert est is not None
    assert est.heart_bpm is None
    assert est.resp_pm is None


def test_parse_csi_payload_roundtrip():
    payload = b"1717000000123456,-52,4,7,178,176,171,169"
    pkt = parse_csi_payload(payload)
    assert pkt is not None
    assert pkt.rssi == -52 and pkt.n == 4 and pkt.seq == 7
    np.testing.assert_allclose(pkt.amps, [178.0, 176.0, 171.0, 169.0])


def test_parse_csi_payload_malformed():
    assert parse_csi_payload(b"not-a-payload") is None
    assert parse_csi_payload(b"1,2,0,3") is None        # n = 0
    assert parse_csi_payload(b"1,2,3,4,5") is None       # missing subcarriers


def test_subcarrier_count_change_resets_window():
    # R4-gui-vstack-crash: a publisher restart with a different subcarrier
    # count must reset the window instead of letting ragged rows reach the
    # consumers' vstack.
    t, m = synth_matrix()
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    for i in range(20):
        p.push(t[i], m[i])
    assert p.fill() == 20
    p.push(t[20], m[20][:16])   # width 32 -> 16: window resets, no ragged rows
    assert p.fill() == 1
    assert p.ready() is False
    assert p.estimate() is None


def test_current_matrix_is_the_panels_single_source():
    # R2-triple-push-mirror: the physics panels read this exact window; the
    # GUI keeps no parallel mirror.
    t, m = synth_matrix()
    p = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    for i in range(20):
        p.push(t[i], m[i])
    window = p.current_matrix()
    assert window is not None
    t_rel, matrix = window
    assert matrix.shape == (20, 32)
    np.testing.assert_allclose(matrix, m[:20])
    assert t_rel[0] == 0.0
    q = VitalsProcessor(fs=FS, window_s=WINDOW_S)
    q.push(t[0], m[0])          # fewer than two rows: no window yet
    assert q.current_matrix() is None
