"""PyQt5 real-time window: CSI waveform, vital signs, body position and
physics panels (subcarrier heatmap, spectrogram, motion energy)."""
from __future__ import annotations

import time
from collections import deque

import matplotlib
matplotlib.use("Qt5Agg")

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                             QVBoxLayout, QWidget)
from scipy import signal as sps

from motion_analyzer import MOTION_BAND_HZ

# Motion-energy history length in the bottom-right panel (seconds).
_MOTION_HISTORY_S = 600.0


class VitalsWindow(QMainWindow):
    """Left column: CSI/vital traces; right column: physics panels."""

    def __init__(self, cfg, links):
        super().__init__()
        self.cfg = cfg
        self.links = links
        self._last_estimate = 0.0
        self._pkt_window_start = time.monotonic()
        self._pkt_window_count = 0
        self._pkt_rate = 0.0

        self.setWindowTitle("WiFi-CSI Vital Signs - experimental")
        self.resize(1280, 800)

        root = QVBoxLayout()
        numbers = QHBoxLayout()
        self.lbl_heart = self._big_label("-")
        self.lbl_resp = self._big_label("-")
        self.lbl_body = self._body_label("waiting for data...")
        self.lbl_meta = QLabel("waiting for data...")
        self.lbl_meta.setAlignment(Qt.AlignCenter)
        self.lbl_meta.setStyleSheet("color: #666;")
        numbers.addWidget(self.lbl_heart)
        numbers.addWidget(self.lbl_resp)
        root.addLayout(numbers)
        root.addWidget(self.lbl_body)
        root.addWidget(self.lbl_meta)

        # Physics panels read VitalsProcessor.current_matrix() directly — no
        # parallel display mirror of the window (single source of truth,
        # review follow-up R2-triple-push-mirror).
        self._motion_history: deque = deque()  # (t_monotonic, motion_rms)
        self.img_heat = None
        self.img_spec = None

        self.figure = Figure(figsize=(12.8, 6.2))
        self.canvas = FigureCanvasQTAgg(self.figure)
        gs = self.figure.add_gridspec(3, 2)
        self.ax_raw = self.figure.add_subplot(gs[0, 0])
        self.ax_resp = self.figure.add_subplot(gs[1, 0])
        self.ax_heart = self.figure.add_subplot(gs[2, 0])
        self.ax_heat = self.figure.add_subplot(gs[0, 1])
        self.ax_spec = self.figure.add_subplot(gs[1, 1])
        self.ax_motion = self.figure.add_subplot(gs[2, 1])
        resp_lo, resp_hi = self.cfg.resp_band_hz
        heart_lo, heart_hi = self.cfg.heart_band_hz
        self.ax_raw.set_title("CSI mean amplitude (window)  "
                              r"$\bar{a}(t)=\frac{1}{K}\sum_{k}|H_k(t)|$")
        self.ax_resp.set_title("Respiration (filtered)  $x(t)$, "
                               f"band {resp_lo:g}\u2013{resp_hi:g} Hz")
        self.ax_heart.set_title("Heart (filtered)  $x(t)$, "
                                f"band {heart_lo:g}\u2013{heart_hi:g} Hz")
        self.ax_heat.set_title(r"$|H_k|=\sqrt{I_k^2+Q_k^2}$ in dB (per subcarrier)")
        self.ax_spec.set_title(
            r"$X(\tau,f)=\sum_n x[n]\,w[n-\tau]\,e^{-j2\pi fn/N}$ [dB]")
        motion_lo, motion_hi = MOTION_BAND_HZ
        self.ax_motion.set_title(
            r"$M_\mathrm{rms}=\sqrt{\langle b^2(t)\rangle}$"
            f", band {motion_lo:g}\u2013{motion_hi:g} Hz")
        for ax in (self.ax_raw, self.ax_resp, self.ax_heart, self.ax_heat,
                   self.ax_spec, self.ax_motion):
            ax.set_xlabel("t [s]")
        # Physical measure + unit on every value axis: what the reader is
        # looking at, at a glance (2026-10-14 request; see the measures
        # strip below the canvas and docs/HOW-IT-WORKS.md).
        self.ax_raw.set_ylabel("mean CSI amplitude [a.u.]")
        self.ax_resp.set_ylabel("filtered amplitude [a.u.]")
        self.ax_heart.set_ylabel("filtered amplitude [a.u.]")
        self.ax_motion.set_ylabel("motion RMS [a.u.]")
        # Fixed time axes: every window/wave series is expressed relative to
        # its own window start, so x is always [0, window_seconds]. Pinning
        # x lets autoscale_view run y-only (much cheaper per repaint).
        for ax in (self.ax_raw, self.ax_resp, self.ax_heart):
            ax.set_xlim(0.0, self.cfg.window_seconds)
        self.ax_heat.set_ylabel("subcarrier k")
        self.ax_spec.set_ylabel("f [Hz]")
        self.line_raw, = self.ax_raw.plot([], [], lw=1, color="#4a90d9")
        self.line_resp, = self.ax_resp.plot([], [], lw=1, color="#2aa876")
        self.line_heart, = self.ax_heart.plot([], [], lw=1, color="#c0392b")
        self.line_motion, = self.ax_motion.plot([], [], lw=1.2, color="#8e44ad")
        self.ax_motion.axhline(self.cfg.moving_rms_threshold,
                               color="#c0392b", ls="--", lw=1)
        root.addWidget(self.canvas)
        # Physical-measures strip: every quantity behind the panels, with
        # unit and source, always visible (2026-10-14). Full explainer in
        # docs/HOW-IT-WORKS.md.
        self.lbl_measures = QLabel(
            "Measures — \u0101(t): mean CSI amplitude [a.u.] (raw panel) \u00b7 "
            "x(t): band-filtered amplitude [a.u.] (respiration 0.1\u20130.5 Hz, "
            "heart 0.8\u20132.0 Hz) \u00b7 |H_k|: subcarrier amplitude [dB] "
            "(heatmap) \u00b7 X(\u03c4,f): spectral power [dB] (spectrogram) \u00b7 "
            "M_rms: motion-band RMS [a.u.] \u00b7 \u03c3_window: amplitude std "
            "[a.u.] \u00b7 RSSI [dBm] \u00b7 link distance [m] \u00b7 SNR [dB] \u00b7 "
            "f [Hz] \u00b7 t [s]. Explainer: docs/HOW-IT-WORKS.md")
        self.lbl_measures.setWordWrap(True)
        self.lbl_measures.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(self.lbl_measures)
        self.figure.tight_layout()

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

        refresh_ms = int(1000.0 / max(1.0, cfg.gui_refresh_hz))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(refresh_ms)

    @staticmethod
    def _big_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 42px; font-weight: bold; color: #222;")
        return lbl

    @staticmethod
    def _body_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #222;")
        return lbl

    # ------------------------------------------------------------------ slots
    def _on_tick(self):
        fed = self.links.drain_and_feed()
        now = time.monotonic()
        self._pkt_window_count += fed
        if now - self._pkt_window_start >= 2.0:
            self._pkt_rate = self._pkt_window_count / (now - self._pkt_window_start)
            self._pkt_window_start = now
            self._pkt_window_count = 0

        # Repaint throttle (A1): the whole canvas (6 axes incl. two imshows)
        # repaints on draw_idle, so all redraws run at the estimate cadence
        # (1 Hz) instead of every tick (5 Hz) - the data tick stays at 5 Hz
        # only for drain + status. draw_idle calls within this callback
        # coalesce into a single repaint.
        if now - self._last_estimate >= self.cfg.estimate_every_s:
            self._last_estimate = now
            self._redraw_raw()
            self._apply_estimate(self.links.estimate())
            self._apply_motion(self.links.motion_estimate(), now)

        status = "MQTT {} | {:.1f} pkt/s | window {}/{}".format(
            "connected" if self.links.sub.is_connected() else "disconnected",
            self._pkt_rate, self.links.fill(), self.links.capacity())
        if self.links.n_links() > 1:
            status += " | links {} (primary {})".format(
                ", ".join(self.links.link_ids()),
                self.links.primary_link() or "-")
        self.statusBar().showMessage(status)

    def _redraw_raw(self):
        window = self.links.current_window()
        if window is None:
            return
        t, mean = window
        self.line_raw.set_data(t, mean)
        self.ax_raw.relim()
        self.ax_raw.autoscale_view(scalex=False)   # x is pinned: y-only
        # Always schedule a repaint: during the window-fill phase the
        # estimate is None and _apply_estimate returns before its own
        # draw_idle, so without this the raw trace stays frozen for the
        # first window_seconds of every session (review findings
        # R2-RedrawRawNoLongerDraws / R3-005 / R4-FillPhaseCanvasFrozen).
        # draw_idle calls within one tick coalesce into a single repaint.
        self.canvas.draw_idle()

    def _apply_estimate(self, est):
        if est is None:
            self.lbl_meta.setText("filling window... {}%".format(
                int(100 * self.links.fill() / max(1, self.links.capacity()))))
            return

        t = est.wave_times_s
        self.line_resp.set_data(t, est.resp_wave)
        self.ax_resp.relim()
        self.ax_resp.autoscale_view(scalex=False)  # x is pinned: y-only
        self.line_heart.set_data(t, est.heart_wave)
        self.ax_heart.relim()
        self.ax_heart.autoscale_view(scalex=False)  # x is pinned: y-only
        self.canvas.draw_idle()

        if est.heart_bpm is not None:
            self.lbl_heart.setText("{:.0f} BPM".format(est.heart_bpm))
            self.lbl_heart.setStyleSheet(
                "font-size:42px;font-weight:bold;color:#c0392b;")
        else:
            self.lbl_heart.setText("-")
        if est.resp_pm is not None:
            self.lbl_resp.setText("{:.0f} /min".format(est.resp_pm))
            self.lbl_resp.setStyleSheet(
                "font-size:42px;font-weight:bold;color:#2aa876;")
        else:
            self.lbl_resp.setText("-")

        self.lbl_meta.setText(
            "heart sc#{} SNR {:.0f} dB | resp sc#{} SNR {:.0f} dB | {}x{} window".format(
                est.heart_subcarrier, est.heart_snr_db,
                est.resp_subcarrier, est.resp_snr_db,
                est.n_samples, est.n_subcarriers))

    # ------------------------------------------------------- body / physics
    def _apply_motion(self, est, now):
        """Update the body label and right-column physics panels (1 Hz)."""
        if est is None:
            self.lbl_body.setText("waiting for data...")
            return

        self._motion_history.append((now, est.motion_rms))
        cutoff = now - _MOTION_HISTORY_S
        while self._motion_history and self._motion_history[0][0] < cutoff:
            self._motion_history.popleft()

        self._update_body_label(est)
        self._redraw_heatmap()
        self._redraw_spectrogram()
        self._redraw_motion_trace()
        self.canvas.draw_idle()

    def _update_body_label(self, est):
        """One-glance body-position summary (None values shown as em-dash)."""
        rssi = "\u2014" if est.rssi_dbm is None else "{:.0f}".format(est.rssi_dbm)
        dist = ("\u2014" if est.distance_m is None
                else "~{:.1f} m".format(est.distance_m))
        self.lbl_body.setText(
            "Body: {} | motion {:.2f} RMS | \u03c3_window {:.2f} | "
            "RSSI {} dBm | link dist {}".format(
                est.state.value, est.motion_rms, est.window_std, rssi, dist))

    def _redraw_heatmap(self):
        """Subcarrier heatmap: 20*log10(|H_k| + eps) over the current window."""
        window = self.links.current_matrix()
        if window is None:
            return
        t_rel, matrix = window                   # (time, subcarrier)
        db = 20.0 * np.log10(matrix.T + 1e-9)    # (subcarrier, time) = (y, x)
        n_sub = matrix.shape[1]
        extent = (t_rel[0], t_rel[-1], n_sub - 1, 0)
        if self.img_heat is None:
            self.img_heat = self.ax_heat.imshow(
                db, aspect="auto", origin="upper", interpolation="nearest",
                cmap="viridis", extent=extent)
        else:
            self.img_heat.set_data(db)
            self.img_heat.set_extent(extent)
            self.ax_heat.set_xlim(t_rel[0], t_rel[-1])
            self.ax_heat.set_ylim(n_sub - 1, 0)

    def _redraw_spectrogram(self):
        """Spectrogram of the window's mean amplitude with physiological bands."""
        window = self.links.current_matrix()
        if window is None:
            return
        _, matrix = window
        x = matrix.mean(axis=1)                  # same series as the raw panel
        fs = self.cfg.sample_rate_hz
        nperseg = min(64, x.size)
        freqs, times, sxx = sps.spectrogram(x, fs=fs, nperseg=nperseg,
                                            noverlap=nperseg // 2)
        sxx_db = 10.0 * np.log10(sxx + 1e-12)
        extent = (times[0], times[-1], freqs[0], freqs[-1])
        if self.img_spec is None:
            self.img_spec = self.ax_spec.imshow(
                sxx_db, aspect="auto", origin="lower", interpolation="nearest",
                cmap="magma", extent=extent)
            resp_lo, resp_hi = self.cfg.resp_band_hz
            heart_lo, heart_hi = self.cfg.heart_band_hz
            self.ax_spec.axhspan(resp_lo, resp_hi, color="#2aa876", alpha=0.15)
            self.ax_spec.axhspan(heart_lo, heart_hi, color="#c0392b", alpha=0.15)
        else:
            self.img_spec.set_data(sxx_db)
            self.img_spec.set_extent(extent)
            self.ax_spec.set_xlim(times[0], times[-1])
            self.ax_spec.set_ylim(freqs[0], freqs[-1])

    def _redraw_motion_trace(self):
        """Motion-energy history (recent estimates) with moving threshold."""
        if len(self._motion_history) < 2:
            return
        t = np.array([s for s, _ in self._motion_history])
        m = np.array([v for _, v in self._motion_history])
        self.line_motion.set_data(t - t[0], m)
        self.ax_motion.relim()
        self.ax_motion.autoscale_view()

    def closeEvent(self, event):
        try:
            self.links.sub.stop()
        finally:
            event.accept()
