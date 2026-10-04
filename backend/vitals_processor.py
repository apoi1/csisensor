"""Vital-sign estimation from WiFi CSI amplitude streams.

Method (classic FFT-based WiFi sensing):
 1. Keep a sliding window of CSI amplitude vectors (one per received packet).
 2. For each physiological band (respiration 0.1-0.5 Hz, heart 0.8-2.0 Hz)
    select the subcarrier whose Hann-windowed spectrum has the strongest
    peak inside the band - chest displacement modulates a few subcarriers
    much more than the rest.
 3. Bandpass-filter the selected subcarrier and refine the dominant peak
    with quadratic interpolation.
 4. Report a rate only when the in-band peak SNR exceeds a threshold.

This is a research/experimental pipeline, not a medical device.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import signal as sps

_EPS = 1e-12


@dataclass(frozen=True)
class VitalsEstimate:
    heart_bpm: float | None
    resp_pm: float | None
    heart_snr_db: float
    resp_snr_db: float
    heart_subcarrier: int
    resp_subcarrier: int
    heart_wave: np.ndarray
    resp_wave: np.ndarray
    wave_times_s: np.ndarray
    n_samples: int
    n_subcarriers: int


class VitalsProcessor:
    """Sliding-window CSI buffer + band-peak vital-sign estimator."""

    def __init__(self, fs: float = 10.0, window_s: float = 15.0,
                 heart_band_hz=(0.8, 2.0), resp_band_hz=(0.1, 0.5),
                 min_snr_db: float = 6.0):
        self.fs = float(fs)
        self.window_s = float(window_s)
        self.heart_band_hz = tuple(heart_band_hz)
        self.resp_band_hz = tuple(resp_band_hz)
        self.min_snr_db = float(min_snr_db)
        self.capacity = max(16, int(round(self.fs * self.window_s)))
        self._times: deque = deque(maxlen=self.capacity)
        self._rows: deque = deque(maxlen=self.capacity)

    # ------------------------------------------------------------------ input
    def push(self, t_s: float, amplitudes) -> None:
        amps = np.asarray(amplitudes, dtype=float).ravel()
        if amps.size == 0:
            return
        if self._rows and amps.size != self._rows[-1].size:
            # Subcarrier count changed (e.g. a publisher restart with a
            # different n): a mixed-width window cannot be vstacked and is
            # physically a different link, so start a fresh window instead
            # of crashing the consumers (review follow-up R4-gui-vstack-crash).
            self._times.clear()
            self._rows.clear()
        self._times.append(float(t_s))
        self._rows.append(amps)

    def fill(self) -> int:
        return len(self._times)

    def ready(self) -> bool:
        return len(self._times) >= self.capacity

    def current_window(self):
        """Live (t_relative_s, mean_amplitude) series for the raw plot."""
        if len(self._rows) < 2:
            return None
        matrix = np.vstack(self._rows)
        t = np.asarray(self._times, dtype=float)
        return t - t[0], matrix.mean(axis=1)

    def current_matrix(self):
        """Live (t_relative_s, per_subcarrier_amplitudes) window.

        Single source for the raw panel and the physics panels (heatmap,
        spectrogram): the GUI keeps no parallel mirror of this state
        (review follow-up R2-triple-push-mirror).  Rows are width-locked
        by push(), so the vstack can never be ragged.
        """
        if len(self._rows) < 2:
            return None
        t = np.asarray(self._times, dtype=float)
        return t - t[0], np.vstack(self._rows)

    # -------------------------------------------------------------- estimation
    def estimate(self) -> "VitalsEstimate | None":
        if not self.ready():
            return None
        matrix = np.vstack(self._rows)          # (samples, subcarriers)
        n_samples, n_sub = matrix.shape
        t = np.asarray(self._times, dtype=float)
        t_rel = t - t[0]

        h_k, h_hz, h_db = self._best_subcarrier(matrix, self.heart_band_hz)
        r_k, r_hz, r_db = self._best_subcarrier(matrix, self.resp_band_hz)

        heart_ok = np.isfinite(h_db) and h_db >= self.min_snr_db
        resp_ok = np.isfinite(r_db) and r_db >= self.min_snr_db

        heart_wave = self._bandpass(sps.detrend(matrix[:, h_k]), self.heart_band_hz)
        resp_wave = self._bandpass(sps.detrend(matrix[:, r_k]), self.resp_band_hz)

        return VitalsEstimate(
            heart_bpm=h_hz * 60.0 if heart_ok else None,
            resp_pm=r_hz * 60.0 if resp_ok else None,
            heart_snr_db=h_db if np.isfinite(h_db) else 0.0,
            resp_snr_db=r_db if np.isfinite(r_db) else 0.0,
            heart_subcarrier=h_k,
            resp_subcarrier=r_k,
            heart_wave=heart_wave,
            resp_wave=resp_wave,
            wave_times_s=t_rel,
            n_samples=n_samples,
            n_subcarriers=n_sub,
        )

    # ---------------------------------------------------------------- internals
    def _best_subcarrier(self, matrix, band):
        best_k, best_hz, best_db = 0, 0.0, -np.inf
        for k in range(matrix.shape[1]):
            hz, db = self._band_peak(sps.detrend(matrix[:, k]), band)
            if db > best_db:
                best_k, best_hz, best_db = k, hz, db
        return best_k, best_hz, best_db

    def _band_peak(self, x, band):
        """Return (dominant_hz_in_band, peak_snr_db) for one detrended signal."""
        n = x.size
        windowed = x * np.hanning(n)
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(n, d=1.0 / self.fs)
        lo, hi = band
        band_idx = np.nonzero((freqs >= lo) & (freqs <= hi))[0]
        if band_idx.size == 0:
            return 0.0, -np.inf
        local = spectrum[band_idx]
        peak_i = int(band_idx[int(np.argmax(local))])
        peak = spectrum[peak_i]
        if peak <= _EPS:
            return 0.0, -np.inf

        hz = freqs[peak_i]
        if 0 < peak_i < spectrum.size - 1:
            la = np.log(spectrum[peak_i - 1] + _EPS)
            lb = np.log(spectrum[peak_i] + _EPS)
            lc = np.log(spectrum[peak_i + 1] + _EPS)
            denom = la - 2.0 * lb + lc
            if abs(denom) > 1e-15:
                delta = 0.5 * (la - lc) / denom
                if abs(delta) <= 1.0:
                    hz = freqs[peak_i] + delta * (freqs[1] - freqs[0])

        noise_floor = np.median(local)
        snr_db = 20.0 * np.log10((peak + _EPS) / (noise_floor + _EPS))
        return hz, snr_db

    def _bandpass(self, x, band):
        lo, hi = float(band[0]), float(band[1])
        hi = min(hi, self.fs / 2.0 - 0.01)
        lo = max(lo, 0.01)
        if x.size < 30:
            return x
        sos = sps.butter(3, [lo, hi], btype="bandpass", fs=self.fs, output="sos")
        return sps.sosfiltfilt(sos, x)
