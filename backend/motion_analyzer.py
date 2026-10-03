"""Body-motion / presence analysis from WiFi CSI amplitude streams.

Method (RSSI-assisted, complements the FFT vital-sign estimator):
 1. Keep a sliding window of per-packet (mean subcarrier amplitude, RSSI)
    samples.  The mean amplitude across subcarriers is a robust proxy for
    whole-body channel disturbance.
 2. Classify presence from the detrended mean-amplitude series: an empty
    room shows only noise (very low window std); a person at rest adds slow
    breathing modulation (low in-band RMS); gross body movement produces
    large broadband excursions (high in-band RMS).
 3. Optionally map the mean RSSI to an estimated person-to-device distance
    with the log-distance path-loss model.

This is a research/experimental pipeline, not a medical device.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np
from scipy import signal as sps

# Gross body movement (walking, large gestures) lives at 0.5-3.0 Hz;
# slower content is breathing (0.1-0.5 Hz) and heart beats (0.8-2.0 Hz).
_MOTION_BAND_HZ = (0.5, 3.0)


class PresenceState(str, Enum):
    """Presence classification with human-readable display strings."""

    ABSENT = "Absent"
    STILL = "Still"
    MOVING = "Moving"


@dataclass(frozen=True)
class MotionEstimate:
    state: PresenceState
    motion_rms: float
    window_std: float
    rssi_dbm: float | None
    distance_m: float | None
    n_samples: int


class MotionAnalyzer:
    """Sliding-window presence/motion classifier with optional RSSI ranging."""

    def __init__(self, fs: float = 10.0, window_s: float = 15.0,
                 absent_std_threshold: float = 0.15,
                 moving_rms_threshold: float = 1.5,
                 rssi_ref_dbm: float | None = -52.0,
                 ref_distance_m: float | None = 1.0,
                 path_loss_exponent: float = 3.0):
        self.fs = float(fs)
        self.window_s = float(window_s)
        self.absent_std_threshold = float(absent_std_threshold)
        self.moving_rms_threshold = float(moving_rms_threshold)
        self.rssi_ref_dbm = None if rssi_ref_dbm is None else float(rssi_ref_dbm)
        self.ref_distance_m = None if ref_distance_m is None else float(ref_distance_m)
        self.path_loss_exponent = float(path_loss_exponent)
        self.capacity = max(16, int(round(self.fs * self.window_s)))
        self._times: deque = deque(maxlen=self.capacity)
        self._mean_amps: deque = deque(maxlen=self.capacity)
        self._rssi: deque = deque(maxlen=self.capacity)

    # ------------------------------------------------------------------ input
    def push(self, t_s: float, amplitudes, rssi_dbm: float | None = None) -> None:
        amps = np.asarray(amplitudes, dtype=float).ravel()
        if amps.size == 0:
            return
        t_s = float(t_s)
        if self._times and t_s <= self._times[-1]:
            return  # drop duplicate / out-of-order packet timestamps
        self._times.append(t_s)
        self._mean_amps.append(float(amps.mean()))
        self._rssi.append(None if rssi_dbm is None else float(rssi_dbm))

    def fill(self) -> float:
        """Fraction of the sliding window currently filled (0.0 .. 1.0)."""
        return len(self._times) / self.capacity

    def ready(self) -> bool:
        return len(self._times) >= self.capacity

    # -------------------------------------------------------------- estimation
    def estimate(self) -> "MotionEstimate | None":
        if not self.ready():
            return None
        x = np.asarray(self._mean_amps, dtype=float)
        n_samples = x.size

        x_d = sps.detrend(x)
        window_std = float(np.std(x_d))
        motion_rms = self._motion_rms(x_d, window_std)
        state = self._classify(window_std, motion_rms)

        rssi_dbm = self._mean_rssi()
        distance_m = self._distance(rssi_dbm)

        return MotionEstimate(
            state=state,
            motion_rms=motion_rms,
            window_std=window_std,
            rssi_dbm=rssi_dbm,
            distance_m=distance_m,
            n_samples=n_samples,
        )

    # ---------------------------------------------------------------- internals
    def _motion_rms(self, x_d: np.ndarray, fallback_std: float) -> float:
        """RMS of the detrended mean-amplitude series inside the motion band.

        Gross body movement lives at 0.5-3.0 Hz; slower content is breathing.
        With too few samples the bandpass is skipped and the detrended std
        (its RMS for a zero-mean series) is used as the fallback.
        """
        if x_d.size < 30:
            return fallback_std
        lo, hi = _MOTION_BAND_HZ
        hi = min(hi, self.fs / 2.0 - 0.01)
        lo = max(lo, 0.01)
        sos = sps.butter(3, [lo, hi], btype="bandpass", fs=self.fs, output="sos")
        b = sps.sosfiltfilt(sos, x_d)
        return float(np.sqrt(np.mean(b ** 2)))

    def _classify(self, window_std: float, motion_rms: float) -> PresenceState:
        # ABSENT: window_std below the threshold means the mean-amplitude
        # series is noise-level flat - no breathing or motion modulation at
        # all, i.e. an empty room.
        if window_std < self.absent_std_threshold:
            return PresenceState.ABSENT
        # MOVING: in-band RMS above the threshold means large broadband
        # excursions - gross body movement (walking, large gestures).
        if motion_rms > self.moving_rms_threshold:
            return PresenceState.MOVING
        # STILL: modulation above the noise floor but only slow, low-power
        # content - a person at rest breathing (plus faint heart beats).
        return PresenceState.STILL

    def _mean_rssi(self) -> float | None:
        values = [r for r in self._rssi if r is not None]
        if not values:
            return None
        return float(np.mean(values))

    def _distance(self, rssi_dbm: float | None) -> float | None:
        """Log-distance path-loss ranging: d_hat = d0 * 10^((R0 - R)/(10*n)).

        R0 is the RSSI measured at the reference distance d0 and n is the
        path-loss exponent.  Disabled while calibration is not configured.
        """
        if rssi_dbm is None or self.rssi_ref_dbm is None or self.ref_distance_m is None:
            return None
        if self.path_loss_exponent <= 0:
            return None
        return self.ref_distance_m * 10.0 ** (
            (self.rssi_ref_dbm - rssi_dbm) / (10.0 * self.path_loss_exponent))
