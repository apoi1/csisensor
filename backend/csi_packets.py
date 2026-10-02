"""Parsing of the CSV CSI payload published by the ESP32-S3 firmware.

Payload format (ASCII, comma-separated):
    t_us,rssi,n,seq,a0,a1,...,a<n-1>
where a* are per-subcarrier amplitudes (sqrt(I^2 + Q^2), 0..255).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CsiPacket:
    t_us: int          # device timestamp, microseconds
    rssi: int          # dBm
    n: int             # number of subcarriers
    seq: int           # device-side sequence number
    amps: np.ndarray   # shape (n,) float64


def parse_csi_payload(payload) -> "CsiPacket | None":
    """Parse one MQTT payload into a CsiPacket. Returns None if malformed."""
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("ascii")
        parts = payload.strip().split(",")
        if len(parts) < 4:
            return None
        t_us = int(parts[0])
        rssi = int(parts[1])
        n = int(parts[2])
        seq = int(parts[3])
        if n <= 0 or len(parts) < 4 + n:
            return None
        amps = np.asarray(parts[4:4 + n], dtype=float)
        return CsiPacket(t_us=t_us, rssi=rssi, n=n, seq=seq, amps=amps)
    except (ValueError, UnicodeDecodeError) as exc:
        logger.debug("dropping malformed CSI payload: %r (%s)", str(payload)[:48], exc)
        return None
