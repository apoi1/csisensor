"""Multi-link (multi-ESP32) CSI management: routing, isolation and fusion.

Several ESP32-S3 nodes can observe the same subject. Each publishes to its
own per-device topic ``esp32/<id>/csi/raw`` (id = last 3 bytes of the STA
MAC), so links never collide on the broker and the backend can keep one
``VitalsProcessor`` + ``MotionAnalyzer`` pipeline per device — the hardened
input guards (non-finite drop, monotonic timestamps, width reset) then apply
per link instead of fighting each other on a shared window.

Fusion (standard link-diversity practice in WiFi sensing):

- **Vitals, per band**: the link with the highest in-band SNR wins heart and
  respiration independently (they may come from different links). If the
  winning link's rate is below the SNR gate, the fused rate is None — an
  honest "no link passed the gate", never a silently mixed estimate.
- **Presence**: conservative aggregate — any link Moving -> Moving, else any
  Still -> Still, else Absent. A person visible to any link counts as
  present.
- **Panels/ranging**: the heart-winning link is the *primary* link; the GUI
  physics panels and the RSSI/distance readouts follow it.

Research/educational tool. Not a medical device.
"""
from __future__ import annotations

import logging
import queue

from motion_analyzer import MotionAnalyzer, MotionEstimate, PresenceState
from mqtt_subscriber import CsiSubscriber
from vitals_processor import VitalsEstimate, VitalsProcessor
from csi_packets import parse_csi_payload

logger = logging.getLogger(__name__)

# Wildcard for per-device topics plus the legacy flat topic, so old firmware
# keeps working without re-flashing.
DEFAULT_TOPIC_PATTERNS = ("esp32/+/csi/raw", "esp32/csi/raw")


# Hard cap on live pipelines: malformed or adversarial topics cannot grow
# the link registry (and backend memory) without bound (review finding R3-5).
MAX_LINKS = 16


def link_id_from_topic(topic: str) -> str:
    """Device id of a CSI topic: esp32/<id>/csi/raw -> <id>.

    The legacy flat topic routes to the ``default`` link; anything else uses
    the full topic string as the id so unknown layouts never collide.
    """
    parts = topic.split("/")
    if len(parts) >= 4 and parts[1] != "csi" and parts[2:4] == ["csi", "raw"]:
        return parts[1]
    if parts == ["esp32", "csi", "raw"]:
        return "default"
    return topic


class MultiLinkSubscriber(CsiSubscriber):
    """CsiSubscriber that tags every parsed packet with its link id.

    The parent subscribes every topic pattern natively (R3-1: no hidden
    single-topic state passed to the constructor); this subclass only
    re-tags the queue payload as (link_id, packet) so each device keeps
    its own pipeline.
    """

    def __init__(self, host: str, port: int, topics, max_queue: int = 1024):
        super().__init__(host, port, tuple(topics), max_queue)

    def _on_message(self, client, userdata, msg):
        packet = parse_csi_payload(msg.payload)
        if packet is None:
            return
        try:
            self._queue.put_nowait((link_id_from_topic(msg.topic), packet))
        except queue.Full:
            self._dropped += 1

    def drain_tagged(self, limit: int = 256):
        """Move up to `limit` (link_id, packet) pairs out of the queue."""
        out = []
        while len(out) < limit:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out


class LinkManager:
    """One DSP pipeline per device topic + per-band max-SNR fusion."""

    def __init__(self, cfg, subscriber=None):
        self.cfg = cfg
        self._links: dict = {}          # link_id -> (VitalsProcessor, MotionAnalyzer)
        self._primary: str | None = None  # heart-winning link (panels follow it)
        self.sub = subscriber if subscriber is not None else \
            MultiLinkSubscriber(cfg.mqtt_host, cfg.mqtt_port,
                                getattr(cfg, "topic_patterns",
                                        DEFAULT_TOPIC_PATTERNS))

    # ------------------------------------------------------------------ links
    def _pipelines(self, link_id: str):
        pair = self._links.get(link_id)
        if pair is None:
            if len(self._links) >= MAX_LINKS:
                logger.warning("link registry full (%d links); dropping packets"
                               " from unknown link %r", MAX_LINKS, link_id)
                return None
            pair = (
                VitalsProcessor(fs=self.cfg.sample_rate_hz,
                                window_s=self.cfg.window_seconds,
                                heart_band_hz=self.cfg.heart_band_hz,
                                resp_band_hz=self.cfg.resp_band_hz,
                                min_snr_db=self.cfg.min_snr_db),
                MotionAnalyzer(fs=self.cfg.sample_rate_hz,
                               window_s=self.cfg.window_seconds,
                               absent_std_threshold=self.cfg.absent_std_threshold,
                               moving_rms_threshold=self.cfg.moving_rms_threshold,
                               rssi_ref_dbm=self.cfg.rssi_ref_dbm,
                               ref_distance_m=self.cfg.ref_distance_m,
                               path_loss_exponent=self.cfg.path_loss_exponent),
            )
            self._links[link_id] = pair
        return pair

    def link_ids(self):
        return sorted(self._links.keys())

    def n_links(self) -> int:
        return len(self._links)

    def primary_link(self):
        """Heart-winning link id (None until the first fused estimate)."""
        return self._primary

    def fill(self) -> int:
        """Filled samples of the primary link's vitals window."""
        proc = self._primary_proc()
        return proc.fill() if proc is not None else 0

    def capacity(self) -> int:
        proc = self._primary_proc()
        return proc.capacity if proc is not None else 0

    # ------------------------------------------------------------------ input
    def ingest(self, link_id: str, packets) -> int:
        """Push packets straight into one link's pipelines (test-friendly).

        Returns how many packets were stored; 0 when the link registry is
        full and the link is unknown (packets dropped, never mixed).
        """
        pair = self._pipelines(link_id)
        if pair is None:
            return 0
        proc, motion = pair
        for pkt in packets:
            proc.push(pkt.t_s, pkt.amps)
            motion.push(pkt.t_s, pkt.amps, pkt.rssi)
        return len(packets)

    def drain_and_feed(self, limit: int = 256) -> int:
        """Drain the subscriber and route every packet to its link."""
        count = 0
        for link_id, pkt in self.sub.drain_tagged(limit):
            count += self.ingest(link_id, (pkt,))
        return count

    # ---------------------------------------------------------------- fusion
    def estimate(self) -> VitalsEstimate | None:
        """Fused vitals: per-band max-SNR winner across ready links."""
        candidates = []
        for link_id, (proc, _motion) in self._links.items():
            est = proc.estimate()
            if est is not None:
                candidates.append((link_id, est))
        if not candidates:
            return None

        heart_id, heart_est = max(
            candidates, key=lambda c: c[1].heart_snr_db)
        resp_id, resp_est = max(
            candidates, key=lambda c: c[1].resp_snr_db)
        self._primary = heart_id  # panels and ranging follow the heart link

        return VitalsEstimate(
            heart_bpm=heart_est.heart_bpm,
            resp_pm=resp_est.resp_pm,
            heart_snr_db=heart_est.heart_snr_db,
            resp_snr_db=resp_est.resp_snr_db,
            heart_subcarrier=heart_est.heart_subcarrier,
            resp_subcarrier=resp_est.resp_subcarrier,
            heart_wave=heart_est.heart_wave,
            resp_wave=resp_est.resp_wave,
            wave_times_s=heart_est.wave_times_s,
            n_samples=heart_est.n_samples,
            n_subcarriers=heart_est.n_subcarriers,
        )

    def motion_estimate(self):
        """Conservative presence aggregate across ready links.

        Any Moving -> Moving; else any Still -> Still; else Absent. RSSI and
        distance follow the primary (heart-winning) link; motion RMS is the
        maximum across links (matches the "any link sees motion" semantics).
        """
        ready = []
        for link_id, (_proc, motion) in self._links.items():
            est = motion.estimate()
            if est is not None:
                ready.append((link_id, est))
        if not ready:
            return None

        states = [est.state for _lid, est in ready]
        if PresenceState.MOVING in states:
            state = PresenceState.MOVING
        elif PresenceState.STILL in states:
            state = PresenceState.STILL
        else:
            state = PresenceState.ABSENT

        primary = None
        for link_id, est in ready:
            if link_id == self._primary:
                primary = est
                break
        if primary is None:
            primary = ready[0][1]

        return MotionEstimate(
            state=state,
            motion_rms=max(est.motion_rms for _lid, est in ready),
            window_std=primary.window_std,
            rssi_dbm=primary.rssi_dbm,
            distance_m=primary.distance_m,
            n_samples=primary.n_samples,
        )

    # ------------------------------------------------------------- panels
    def current_matrix(self):
        proc = self._primary_proc()
        return proc.current_matrix() if proc is not None else None

    def current_window(self):
        proc = self._primary_proc()
        return proc.current_window() if proc is not None else None

    def _primary_proc(self):
        if not self._links:
            return None
        link_id = self._primary or self.link_ids()[0]
        return self._pipelines(link_id)[0]
