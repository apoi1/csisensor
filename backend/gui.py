"""PyQt5 real-time window: CSI waveform + estimated vital signs."""
from __future__ import annotations

import time

import matplotlib
matplotlib.use("Qt5Agg")

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                             QVBoxLayout, QWidget)

from vitals_processor import VitalsEstimate, VitalsProcessor


class VitalsWindow(QMainWindow):
    def __init__(self, cfg, subscriber, processor):
        super().__init__()
        self.cfg = cfg
        self.sub = subscriber
        self.proc = processor
        self._last_estimate = 0.0
        self._pkt_window_start = time.monotonic()
        self._pkt_window_count = 0
        self._pkt_rate = 0.0

        self.setWindowTitle("WiFi-CSI Vital Signs - experimental")
        self.resize(1000, 640)

        root = QVBoxLayout()
        numbers = QHBoxLayout()
        self.lbl_heart = self._big_label("-")
        self.lbl_resp = self._big_label("-")
        self.lbl_meta = QLabel("waiting for data...")
        self.lbl_meta.setAlignment(Qt.AlignCenter)
        self.lbl_meta.setStyleSheet("color: #666;")
        numbers.addWidget(self.lbl_heart)
        numbers.addWidget(self.lbl_resp)
        root.addLayout(numbers)
        root.addWidget(self.lbl_meta)

        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        gs = self.figure.add_gridspec(3, 1, hspace=0.7)
        self.ax_raw = self.figure.add_subplot(gs[0])
        self.ax_resp = self.figure.add_subplot(gs[1])
        self.ax_heart = self.figure.add_subplot(gs[2])
        self.ax_raw.set_title("CSI mean amplitude (window)")
        self.ax_resp.set_title("Respiration (filtered)")
        self.ax_heart.set_title("Heart (filtered)")
        for ax in (self.ax_raw, self.ax_resp, self.ax_heart):
            ax.set_xlabel("t [s]")
        self.line_raw, = self.ax_raw.plot([], [], lw=1, color="#4a90d9")
        self.line_resp, = self.ax_resp.plot([], [], lw=1, color="#2aa876")
        self.line_heart, = self.ax_heart.plot([], [], lw=1, color="#c0392b")
        root.addWidget(self.canvas)

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

    # ------------------------------------------------------------------ slots
    def _on_tick(self):
        packets = self.sub.drain()
        now = time.monotonic()
        self._pkt_window_count += len(packets)
        if now - self._pkt_window_start >= 2.0:
            self._pkt_rate = self._pkt_window_count / (now - self._pkt_window_start)
            self._pkt_window_start = now
            self._pkt_window_count = 0

        for p in packets:
            self.proc.push(p.t_us / 1e6, p.amps)

        self._redraw_raw()

        if now - self._last_estimate >= self.cfg.estimate_every_s:
            self._last_estimate = now
            self._apply_estimate(self.proc.estimate())

        self.statusBar().showMessage(
            "MQTT {} | {:.1f} pkt/s | window {}/{}".format(
                "connected" if self.sub.is_connected() else "disconnected",
                self._pkt_rate, self.proc.fill(), self.proc.capacity)
        )

    def _redraw_raw(self):
        window = self.proc.current_window()
        if window is None:
            return
        t, mean = window
        self.line_raw.set_data(t, mean)
        self.ax_raw.relim()
        self.ax_raw.autoscale_view()
        self.canvas.draw_idle()

    def _apply_estimate(self, est):
        if est is None:
            self.lbl_meta.setText("filling window... {}%".format(
                int(100 * self.proc.fill() / self.proc.capacity)))
            return

        t = est.wave_times_s
        self.line_resp.set_data(t, est.resp_wave)
        self.ax_resp.relim()
        self.ax_resp.autoscale_view()
        self.line_heart.set_data(t, est.heart_wave)
        self.ax_heart.relim()
        self.ax_heart.autoscale_view()
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

    def closeEvent(self, event):
        try:
            self.sub.stop()
        finally:
            event.accept()
