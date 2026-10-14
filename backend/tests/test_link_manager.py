"""Headless tests for multi-link routing, isolation and fusion."""
import time

import numpy as np

from config import Config
from csi_packets import CsiPacket, parse_csi_payload
from link_manager import (LINK_STALE_S, MAX_LINKS, LinkManager,
                          MultiLinkSubscriber, link_id_from_topic)
from motion_analyzer import PresenceState

FS = 10.0
WINDOW_S = 15.0


def synth_packets(heart_amp=0.9, resp_amp=3.0, bpm=60.0, resp_pm=15.0,
                  n_sub=32, seed=7, t0=100.0, rssi=-52.0, flat_noise=0.05):
    """Coherent-tones CSI packets (chest displacement modulates all links)."""
    n = int(FS * WINDOW_S) + 10
    t = t0 + np.arange(n) / FS
    rng = np.random.default_rng(seed)
    f_heart, f_resp = bpm / 60.0, resp_pm / 60.0
    rows = (30.0
            + resp_amp * np.sin(2 * np.pi * f_resp * t[:, None])
            + heart_amp * np.sin(2 * np.pi * f_heart * t[:, None])
            + rng.normal(0.0, flat_noise, (n, n_sub)))
    return [CsiPacket(t_us=int(t[i] * 1e6), amps=rows[i], rssi=int(rssi),
                      n=n_sub, seq=i)
            for i in range(n)]


def make_manager():
    return LinkManager(Config())


def test_topic_routing():
    assert link_id_from_topic("esp32/a1b2c3/csi/raw") == "a1b2c3"
    assert link_id_from_topic("esp32/csi/raw") == "default"
    assert link_id_from_topic("other/thing") == "other/thing"


def test_two_links_never_mix_windows():
    # The critical property vs the old single pipeline: two devices with
    # overlapping (identical) timestamps must BOTH fill their own windows.
    # On one shared window the monotonic-timestamp guard would drop every
    # other packet.
    links = make_manager()
    a = synth_packets(seed=1)
    b = synth_packets(seed=2)
    links.ingest("a1b2c3", a)
    links.ingest("d4e5f6", b)
    assert links.n_links() == 2
    assert links.link_ids() == ["a1b2c3", "d4e5f6"]
    est = links.estimate()
    assert est is not None
    assert est.n_samples == links.capacity()  # both windows kept full samples


def test_fusion_picks_best_snr_per_band():
    # Link A: strong heart, near-noise respiration. Link B: strong
    # respiration, near-noise heart. The fused estimate takes each band from
    # its best link.
    links = make_manager()
    a = synth_packets(heart_amp=3.0, resp_amp=0.02, seed=3)
    b = synth_packets(heart_amp=0.02, resp_amp=3.0, seed=4)
    links.ingest("heart-link", a)
    links.ingest("resp-link", b)
    est = links.estimate()
    assert est is not None
    assert est.heart_bpm is not None and abs(est.heart_bpm - 60.0) <= 5.0
    assert est.resp_pm is not None and abs(est.resp_pm - 15.0) <= 3.0
    assert links.primary_link() == "heart-link"  # heart SNR won the primary


def test_presence_aggregate_is_conservative():
    links = make_manager()
    # Still link: coherent breathing without motion-band energy.
    still = synth_packets(heart_amp=0.9, resp_amp=3.0, seed=5)
    # Moving link: big coherent broadband excursions (gross body movement
    # modulates ALL subcarriers together, so the mean-amplitude series keeps
    # the full amplitude — unlike per-subcarrier noise, which the mean kills).
    t = np.arange(160) / FS
    rng = np.random.default_rng(6)
    exc = rng.normal(0.0, 1.0, (t.size, 1))
    rows = 30.0 + 8.0 * exc
    moving = [CsiPacket(t_us=int(t[i] * 1e6), amps=rows[i], rssi=-52, n=1, seq=i)
              for i in range(t.size)]
    links.ingest("still-link", still)
    links.ingest("moving-link", moving)
    mot = links.motion_estimate()
    assert mot is not None
    assert mot.state == PresenceState.MOVING  # any link moving -> Moving

    only = make_manager()
    only.ingest("solo", still)
    mot = only.motion_estimate()
    assert mot.state == PresenceState.STILL


def test_no_links_returns_none():
    links = make_manager()
    assert links.estimate() is None
    assert links.motion_estimate() is None
    assert links.current_matrix() is None
    assert links.current_window() is None
    assert links.fill() == 0 and links.capacity() == 0
    assert links.primary_link() is None


def test_partial_window_fused_estimate_is_none():
    links = make_manager()
    links.ingest("a1b2c3", synth_packets()[:20])
    assert links.estimate() is None
    assert links.motion_estimate() is None
    assert links.fill() == 20


def test_link_registry_admits_newcomers_always():
    # R4-1 (v3): a full registry ALWAYS admits a new legitimate device by
    # evicting the least-recently-seen link (LRU). Trusted-broker tradeoff:
    # a flood of live junk links can churn the registry - document broker
    # auth before any exposure (DEPLOYMENT security notes).
    links = make_manager()
    pkts = synth_packets()[:5]
    links.ingest("first-link", pkts)               # oldest -> evicted first
    for i in range(MAX_LINKS):
        links.ingest(f"junk-{i:02d}", pkts)        # fills + churns the registry
    assert links.n_links() == MAX_LINKS
    assert "junk-%02d" % (MAX_LINKS - 1) in links.link_ids()
    assert "first-link" not in links.link_ids()    # LRU evicted the oldest
    assert links.evictions() >= 1


def test_stale_links_are_pruned_from_memory():
    # R4-3 (v3): silent links must not linger in the registry when no new
    # registrations arrive; every fusion pass prunes them.
    links = make_manager()
    pkts = synth_packets()[:5]
    links.ingest("gone-link", pkts)
    links.ingest("live-link", pkts)
    links._last_seen["gone-link"] -= (LINK_STALE_S + 5.0)
    links.estimate()                                # fusion pass prunes
    assert links.n_links() == 1
    assert links.link_ids() == ["live-link"]


def test_subscriber_holds_every_pattern():
    # R3-1: the subscriber registers exactly the patterns it will
    # subscribe - no hidden single-topic state in the parent.
    sub = MultiLinkSubscriber("localhost", 1883, ("esp32/+/csi/raw", "esp32/csi/raw"))
    assert sub._topics == ("esp32/+/csi/raw", "esp32/csi/raw")


def test_link_registry_evicts_stalest_not_new_devices():
    # R4-1: a full registry must never permanently lock out new devices.
    links = make_manager()
    pkts = synth_packets()[:5]
    links.ingest("old-link", pkts)
    links._last_seen["old-link"] -= 3600.0      # simulate an hour of silence
    for i in range(MAX_LINKS - 1):
        links.ingest(f"link-{i:02d}", pkts)
    assert links.n_links() == MAX_LINKS
    links.ingest("new-device", pkts)            # registry full -> LRU evicts
    assert links.n_links() == MAX_LINKS
    assert "new-device" in links.link_ids()
    assert "old-link" not in links.link_ids()
    assert links.evictions() == 1


def test_stale_links_stop_contributing_to_fusion():
    # R4-2: a link that stops publishing keeps a full window with a frozen
    # high-SNR estimate; it must stop winning fusion after LINK_STALE_S.
    links = make_manager()
    strong = synth_packets(heart_amp=3.0, seed=1)
    flat = synth_packets(heart_amp=0.0, resp_amp=0.0, flat_noise=0.0, seed=2)
    links.ingest("dead-strong", strong)
    links.ingest("live-flat", flat)
    est = links.estimate()
    assert est.heart_bpm is not None
    assert links.primary_link() == "dead-strong"
    links._last_seen["dead-strong"] -= (LINK_STALE_S + 5.0)  # link went silent
    est = links.estimate()
    assert est is not None
    # Only the live flat link remains -> honest None rates (constant signal
    # carries no tone; white noise would clear the 6 dB gate spuriously)
    assert est.heart_bpm is None and est.resp_pm is None


def test_fusion_reports_none_when_best_link_fails_gate():
    # Constant-amplitude links carry no in-band tone at all: the in-band
    # peak is the numerical eps floor, SNR is -inf on every link, and the
    # fused rates honestly report None. (White noise is NOT flat: its
    # in-band peak-vs-median ratio often clears the 6 dB gate.)
    links = make_manager()
    links.ingest("flat", synth_packets(heart_amp=0.0, resp_amp=0.0,
                                       flat_noise=0.0))
    links.ingest("flatter", synth_packets(heart_amp=0.0, resp_amp=0.0,
                                          flat_noise=0.0, seed=8))
    est = links.estimate()
    assert est is not None
    assert est.heart_bpm is None and est.resp_pm is None


def test_real_parser_packets_flow_end_to_end():
    """Regression: ingest() once used pkt.t_s, but the real parser produces
    CsiPacket.t_us (device microseconds). The first live packet from the
    board crashed the GUI with AttributeError; the synthetic fixtures used
    SimpleNamespace(t_s=...) and never caught it. This feeds the REAL
    parser's output through the REAL queue path (drain_and_feed)."""
    links = make_manager()
    payload = "1717000000123456,-52,4,42,178,176,171,169".encode("ascii")
    pkt = parse_csi_payload(payload)
    assert pkt is not None
    links.sub._queue.put_nowait(("real", pkt))
    assert links.drain_and_feed() == 1
    assert links.n_links() == 1
    assert links._links["real"][0].fill() == 1


def test_polled_primary_still_expires():
    """R3-001 / R4-StalePrimaryNeverExpires: the shipped consumers poll
    fill()/capacity()/current_matrix()/current_window() (GUI at 5 Hz, web
    viewer ~1 Hz). Those read paths must NOT refresh staleness: a silent
    primary has to expire after LINK_STALE_S exactly like any other link
    instead of keeping its frozen full-window estimate winning fusion
    forever. The older stale tests missed this because they edited
    _last_seen directly and never exercised the polled accessors."""
    links = make_manager()
    links.ingest("primary-link", synth_packets(heart_amp=3.0, seed=1))
    est = links.estimate()
    assert est is not None
    assert links.primary_link() == "primary-link"
    links.ingest("backup-link", synth_packets(heart_amp=3.0, seed=2))
    # The primary goes silent; the consumers keep polling it hard.
    links._last_seen["primary-link"] -= (LINK_STALE_S + 5.0)
    for _ in range(5):
        assert links.fill() > 0
        assert links.capacity() > 0
        assert links.current_window() is not None
        assert links.current_matrix() is not None
    # Despite the polling, the fusion pass must prune the silent link and
    # the live backup takes over the primary.
    est = links.estimate()
    assert est is not None
    assert "primary-link" not in links.link_ids()
    assert links.primary_link() == "backup-link"


def test_evicted_primary_is_not_resurrected():
    """R3-004: LRU eviction of the primary link must clear _primary so the
    dangling id cannot re-create an empty ghost pipeline on the next read
    (churning live links out of the registry and flipping the status bar
    to 0%)."""
    links = make_manager()
    links.ingest("primary-link", synth_packets(heart_amp=3.0, seed=1))
    links.estimate()
    assert links.primary_link() == "primary-link"
    links._last_seen["primary-link"] -= 3600.0    # becomes the stalest link
    pkts = synth_packets()[:5]
    for i in range(MAX_LINKS):
        links.ingest(f"filler-{i:02d}", pkts)      # registry full -> LRU evicts
    assert "primary-link" not in links.link_ids()
    assert links.primary_link() is None           # no dangling primary id
    assert links.fill() >= 0                       # reads stay safe (no ghost)


def test_concurrent_reads_do_not_race_with_ingest():
    """R1-004 / R2-LinkIdsLockContractTrap / R3-003: link_ids() and
    evictions() read shared registry state and must take the lock like
    their siblings - while _primary_proc(), which already holds the lock,
    uses an internal locked helper (a naive lock on link_ids() would
    deadlock fill()/capacity()). Stress smoke: concurrent reader threads
    must never observe a torn registry (RuntimeError: dictionary changed
    size during iteration)."""
    import threading

    links = make_manager()
    pkts = synth_packets()[:5]
    links.ingest("seed-link", pkts)
    errors = []
    stop = threading.Event()

    def reader():
        try:
            while not stop.is_set():
                links.link_ids()
                links.evictions()
                links.fill()
                links.capacity()
        except Exception as exc:  # only reachable on a regression
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    try:
        for i in range(200):
            links.ingest(f"churn-{i % MAX_LINKS:02d}", pkts)
            links.estimate()
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=5.0)
    assert not errors
    assert not any(t.is_alive() for t in threads)
