#!/usr/bin/env python3
"""Generate documentation figures modeling the system's wave behavior.

All figures use the project's real constants (backend/config.py, docs/DATA-PIPELINE.md):
  - sample rate fs = 10 Hz (CSI_INTERVAL_MS = 100)
  - analysis window = 15 s (150 samples)
  - respiration band 0.1-0.5 Hz (12-30 /min)
  - heart band 0.8-2.0 Hz (48-120 bpm)
  - motion band 0.5-3 Hz, moving threshold RMS = 1.5 (CSI_MOVING_RMS)
  - K ~ 64 subcarriers, SNR gate 6 dB (CSI_MIN_SNR_DB)
Axis labels match the GUI exactly (t [s], [a.u.], [dB], subcarrier k, f [Hz]).

Output: docs/img/*.png (referenced by docs/HOW-IT-WORKS.md, DATA-PIPELINE.md,
VALIDATION-PROTOCOL.md). Run: python3 scripts/generate-doc-figures.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse, FancyArrowPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)

# Real system constants
FS = 10.0            # Hz, CSI_INTERVAL_MS = 100
WIN_S = 15.0         # analysis window
RESP_LO, RESP_HI = 0.1, 0.5      # Hz
HEART_LO, HEART_HI = 0.8, 2.0    # Hz
MOTION_LO, MOTION_HI = 0.5, 3.0  # Hz
RMS_THRESHOLD = 1.5  # CSI_MOVING_RMS
K = 64               # subcarriers on the S3

C_RAW, C_RESP, C_HEART, C_MOT = "#4a90d9", "#2aa876", "#c0392b", "#8e44ad"
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 8,
    "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False,
})


def save(fig, name):
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  wrote {name}")


def annot_arrow(ax, xy_from, xy_to, text, color="black", tx=0, ty=0, fs=8):
    ax.annotate("", xy=xy_to, xytext=xy_from,
                arrowprops=dict(arrowstyle="<->", color=color, lw=1.2))
    ax.text((xy_from[0] + xy_to[0]) / 2 + tx, (xy_from[1] + xy_to[1]) / 2 + ty,
            text, ha="center", va="center", fontsize=fs, color=color,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.85, lw=0.6))


# ----------------------------------------------------------------- 1. wave anatomy
def fig_wave_anatomy():
    """One clean sine with amplitude / period / frequency annotated."""
    t = np.linspace(0, 8, 800)
    f = 0.5  # Hz -> T = 2 s (a slow breath at 30 /min for the example)
    y = np.sin(2 * np.pi * f * t)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 4.6), sharex=True)

    # -- generic wave properties
    ax1.plot(t, y, color=C_RAW, lw=2)
    ax1.axhline(0, color="gray", ls="--", lw=0.8)
    pk = 0.25  # peak at t where sin=1 -> t = 0.5 (T/4)
    annot_arrow(ax1, (pk, 0), (pk, 1.0), "Amplitude A\n(a.u.)", C_RAW, tx=0.55)
    annot_arrow(ax1, (pk, 1.12), (pk + 1 / f, 1.12), "Period T = 1/f = 2 s",
                C_RAW, ty=0.32)
    ax1.set_ylim(-1.6, 1.75)
    ax1.set_ylabel("x(t)  [a.u.]")
    ax1.set_title("Anatomy of a wave: amplitude (how strong), period T (how long "
                  "per cycle), frequency $f=1/T$ (cycles per second)")
    ax1.text(4.0, -1.35, "midline (mean)", color="gray", fontsize=7, ha="center")

    # -- the same wave as the system reads it
    breaths = 30 / 60  # 0.5 Hz = 30 breaths/min (top of the band)
    y2 = np.sin(2 * np.pi * breaths * t)
    ax2.plot(t, y2, color=C_RESP, lw=2)
    ax2.axhline(0, color="gray", ls="--", lw=0.8)
    p0, p1 = 0.5, 0.5 + 60 / 30  # first two peaks
    annot_arrow(ax2, (p0, 1.12), (p1, 1.12), "one breath = T ≈ 2 s", C_RESP, ty=0.3)
    ax2.annotate("", xy=(p0, 1.0), xytext=(p0, 0),
                 arrowprops=dict(arrowstyle="->", color=C_RESP, lw=1.2))
    ax2.text(p0 + 0.15, 0.55, "chest expansion\n(millimeters)", fontsize=7,
             color=C_RESP, ha="left")
    ax2.set_ylim(-1.6, 1.75)
    ax2.set_xlabel("t [s]")
    ax2.set_ylabel("x(t)  [a.u.]")
    ax2.set_title("The same wave as vital sign: rate = 60/T = 30 breaths/min "
                  "(respiration band 0.1–0.5 Hz)")
    fig.tight_layout()
    save(fig, "wave-anatomy.png")


# --------------------------------------------------- 2. mean CSI, three scenarios
def fig_csi_mean_scenarios():
    t = np.arange(0, WIN_S, 1 / FS)  # 150 samples
    rng = np.random.default_rng(7)
    base, a_r, a_h = 45.0, 1.3, 0.13
    resp = np.sin(2 * np.pi * 0.28 * t)
    heart = np.sin(2 * np.pi * 1.25 * t)

    still = base + a_r * resp + a_h * heart + rng.normal(0, 0.06, t.size)
    moving = still.copy()
    burst = (t >= 8.0) & (t < 10.5)
    moving[burst] += rng.normal(0, 2.2, burst.sum())          # gross motion
    moving[t >= 8.0] += 2.5 * np.exp(-(t[t >= 8.0] - 8.0) / 3)  # DC jump
    absent = base + rng.normal(0, 0.08, t.size)

    fig, axes = plt.subplots(3, 1, figsize=(7.5, 5.6), sharex=True, sharey=True)
    data = [(still, C_RAW, "Resting — slow breathing wave visible (~17 /min)"),
            (moving, C_RAW, "Moving — jump + burst of noise (0.5–3 Hz)"),
            (absent, C_RAW, "Empty room — noise-flat (σ_window < 0.15)")]
    for ax, (y, c, title) in zip(axes, data):
        ax.plot(t, y, color=c, lw=0.9)
        ax.set_ylabel("mean CSI\namplitude [a.u.]")
        ax.set_title(title, loc="left", fontsize=9)
    axes[-1].set_xlabel("t [s]")
    axes[-1].set_xlim(0, WIN_S)
    fig.suptitle(r"Panel 1 — mean CSI amplitude $\bar{a}(t)=\frac{1}{K}\sum_k|H_k|$"
                 " in the three scenarios (window 15 s @ 10 Hz)", y=0.995, fontsize=10)
    fig.tight_layout()
    save(fig, "csi-mean-three-scenarios.png")


# --------------------------------------------------------- 3. respiration + heart
def fig_vitals_annotated():
    t = np.arange(0, WIN_S, 1 / FS)
    f_r, f_h = 0.28, 1.25          # 16.8 /min, 75 bpm
    a_r, a_h = 1.0, 0.10           # heart moves ~10x less
    rng = np.random.default_rng(3)
    resp = a_r * np.sin(2 * np.pi * f_r * t) + rng.normal(0, 0.02, t.size)
    heart = a_h * np.sin(2 * np.pi * f_h * t) + rng.normal(0, 0.004, t.size)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.5, 4.8), sharex=True)

    ax1.plot(t, resp, color=C_RESP, lw=1.6)
    peaks = np.where((resp[1:-1] > resp[:-2]) & (resp[1:-1] > resp[2:]))[0] + 1
    peaks = [p for p in peaks if resp[p] > 0.8 * a_r]
    ax1.plot(t[peaks], resp[peaks], "o", color=C_RESP, ms=4)
    annot_arrow(ax1, (t[peaks[1]], 1.15), (t[peaks[2]], 1.15),
                "T ≈ 3.6 s → rate = 60/T ≈ 17 /min", C_RESP, ty=0.35)
    ax1.text(0.15, -1.32, "band-pass: 0.1–0.5 Hz (12–30 /min) — shown in the "
             "panel title, not on this axis", fontsize=7, color=C_RESP)
    ax1.set_ylabel("respiration\namplitude [a.u.]")
    ax1.set_title("Panel 2 — Respiration x(t): every peak = one breath")
    ax1.set_ylim(-1.5, 1.85)

    ax2.plot(t, heart, color=C_HEART, lw=1.6)
    pk_h = np.where((heart[1:-1] > heart[:-2]) & (heart[1:-1] > heart[2:]))[0] + 1
    pk_h = [p for p in pk_h if heart[p] > 0.8 * a_h]
    ax2.plot(t[pk_h], heart[pk_h], "o", color=C_HEART, ms=4)
    annot_arrow(ax2, (t[pk_h[2]], 0.135), (t[pk_h[3]], 0.135),
                "T ≈ 0.8 s → 60/T ≈ 75 bpm", C_HEART, ty=0.035)
    # amplitude ratio: double arrow from the respiration scale to the heart scale
    annot_arrow(ax2, (0.9, 0), (0.9, a_h), "~10× smaller", C_HEART, tx=0, ty=0.0, fs=7)
    ax2.text(0.15, -0.14, "band-pass: 0.8–2.0 Hz (48–120 bpm)", fontsize=7,
             color=C_HEART)
    ax2.set_ylabel("heart\namplitude [a.u.]")
    ax2.set_xlabel("t [s]")
    ax2.set_title("Panel 3 — Heart x(t): needs stillness + short distance")
    ax2.set_xlim(0, WIN_S)
    ax2.set_ylim(-0.22, 0.22)
    fig.tight_layout()
    save(fig, "vitals-annotated.png")


# ------------------------------------------------------------------- 4. heatmap
def fig_heatmap():
    rng = np.random.default_rng(11)
    t = np.arange(0, WIN_S, 1 / FS)
    good_k = [12, 23, 40, 55]                      # subcarriers that "see" the chest
    H = rng.normal(-52, 3.0, (K, t.size))
    for k in good_k:
        H[k] += 4.0 + 2.5 * np.sin(2 * np.pi * 0.28 * t)   # coherent modulation
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    im = ax.imshow(10 * np.log10(np.abs(H)), aspect="auto", origin="lower",
                   cmap="viridis", extent=[0, WIN_S, 0, K])
    for k in good_k:
        ax.axhline(k + 0.5, color="white", ls=":", lw=0.7, alpha=0.8)
    ax.text(0.25, good_k[1] + 2.2, "bright vertical stripes = subcarriers\n"
            "that see the chest (step 3 picks the best)", fontsize=7.5,
            color="white", bbox=dict(boxstyle="round,pad=0.25", fc="black", alpha=0.55))
    ax.set_xlabel("t [s]")
    ax.set_ylabel("subcarrier k")
    ax.set_title(r"Panel 4 — Heatmap $|H_k|=\sqrt{I_k^2+Q_k^2}$ [dB], 64 subcarriers × 15 s")
    fig.colorbar(im, ax=ax, label=r"$|H_k|$ [dB]")
    fig.tight_layout()
    save(fig, "heatmap-subcarriers.png")


# -------------------------------------------------------------- 5. spectrogram
def fig_spectrogram():
    fs = FS
    dur = 60.0
    t = np.arange(0, dur, 1 / fs)
    rng = np.random.default_rng(5)
    sig = 1.0 * np.sin(2 * np.pi * 0.28 * t) + 0.1 * np.sin(2 * np.pi * 1.25 * t)
    sig += 0.12 * rng.normal(0, 1, t.size)
    burst = (t >= 25) & (t < 30)                       # person walks by
    sig[burst] += rng.normal(0, 2.0, burst.sum())

    nfft, hop = 128, 8
    win = np.hanning(nfft)
    n_frames = 1 + (t.size - nfft) // hop
    S = np.empty((nfft // 2 + 1, n_frames))
    for i in range(n_frames):
        seg = sig[i * hop: i * hop + nfft] * win
        S[:, i] = np.abs(np.fft.rfft(seg)) ** 2
    Sdb = 10 * np.log10(S + 1e-12)
    tf = np.arange(n_frames) * hop / fs
    ff = np.fft.rfftfreq(nfft, 1 / fs)

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    im = ax.pcolormesh(tf, ff, Sdb, cmap="magma", shading="auto",
                       vmin=Sdb.max() - 45, vmax=Sdb.max())
    ax.axhspan(RESP_LO, RESP_HI, color="#2aa876", alpha=0.18)
    ax.axhspan(HEART_LO, HEART_HI, color="#c0392b", alpha=0.10)
    ax.text(1.0, 0.32, "respiration band\n0.1–0.5 Hz", fontsize=7, color="#7be0c0")
    ax.text(1.0, 1.55, "heart band\n0.8–2.0 Hz", fontsize=7, color="#f0a099")
    ax.annotate("stable horizontal stripe\n= breathing in time", xy=(12, 0.28),
                xytext=(8, 1.1), fontsize=7.5, color="white",
                arrowprops=dict(arrowstyle="->", color="white", lw=1))
    ax.annotate("movement = wide blotch\nacross all frequencies", xy=(27.5, 1.8),
                xytext=(36, 2.3), fontsize=7.5, color="white",
                arrowprops=dict(arrowstyle="->", color="white", lw=1))
    ax.set_xlabel("t [s]")
    ax.set_ylabel("f [Hz]")
    ax.set_ylim(0, 3.0)
    ax.set_title("Panel 5 — Spectrogram X(τ,f) [dB] of the mean amplitude (60 s shown)")
    fig.colorbar(im, ax=ax, label="[dB]")
    fig.tight_layout()
    save(fig, "spectrogram-bands.png")


# ------------------------------------------------------------- 6. motion RMS
def fig_motion_rms():
    t = np.arange(0, 600, 1.0)                     # 10 min history at 1 Hz
    rng = np.random.default_rng(9)
    rms = np.clip(rng.normal(0.45, 0.12, t.size), 0.1, None)
    for t0, amp, dur in [(120, 2.3, 9), (300, 1.9, 6), (455, 2.6, 12)]:
        m = (t >= t0) & (t < t0 + dur)
        rms[m] += amp * np.sin(np.pi * (t[m] - t0) / dur)
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.plot(t, rms, color=C_MOT, lw=0.9)
    ax.axhline(RMS_THRESHOLD, color=C_HEART, ls="--", lw=1.2)
    ax.text(598, RMS_THRESHOLD + 0.07, f"threshold CSI_MOVING_RMS = {RMS_THRESHOLD}",
            ha="right", fontsize=7.5, color=C_HEART)
    for t0, _, dur in [(120, 0, 9), (300, 0, 6), (455, 0, 12)]:
        ax.axvspan(t0, t0 + dur, color=C_HEART, alpha=0.12)
    ax.text(124, 2.95, "each crossing = one movement\n→ Body row: Moving", fontsize=7.5)
    ax.text(60, 1.0, "below the line = Still", fontsize=7.5, color="#333")
    ax.set_xlabel("t [s]  (10 min history)")
    ax.set_ylabel("motion RMS [a.u.]")
    ax.set_ylim(0, 3.3)
    ax.set_xlim(0, 600)
    ax.set_title(f"Panel 6 — Motion energy $M_{{rms}}$ in the {MOTION_LO:g}–{MOTION_HI:g} Hz band")
    fig.tight_layout()
    save(fig, "motion-rms-threshold.png")


# ---------------------------------------------------------------- 7. multipath
def fig_multipath():
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")
    # Fresnel ellipse between router and board
    fres = Ellipse((5, 1.5), width=7.6, height=1.7, fill=False,
                   edgecolor=C_RAW, ls="--", lw=1.3)
    ax.add_patch(fres)
    ax.text(5, 0.28, "first Fresnel zone — almost all the energy travels here",
            ha="center", fontsize=8, color=C_RAW)
    # router and board
    ax.plot(1.2, 1.5, "s", ms=11, color="#333")
    ax.text(1.2, 2.0, "router", ha="center", fontsize=9)
    ax.plot(8.8, 1.5, "o", ms=11, color=C_RAW)
    ax.text(8.8, 2.0, "ESP32-S3", ha="center", fontsize=9, color=C_RAW)
    # person perturbing the zone
    ax.plot(6.7, 1.5, "o", ms=14, color=C_RESP)
    ax.text(6.7, 0.75, "chest\n(respiring)", ha="center", fontsize=8, color=C_RESP)
    # LOS ray and multipath rays
    for x2, y2, lbl, col in [
            (8.8, 1.5, "direct path", "#333"),
            (8.8, 1.5, "", "#999")]:
        pass
    ax.plot([1.2, 6.7], [1.5, 1.5], color="#333", lw=1.1)
    ax.plot([6.7, 8.8], [1.5, 1.5], color="#333", lw=1.1)
    ax.plot([1.2, 4.0, 8.8], [1.5, 4.3, 1.5], color="#999", lw=1.0, ls="-.")
    ax.plot([1.2, 3.0, 8.8], [1.5, 4.6, 1.5], color="#bbb", lw=0.9, ls=":")
    ax.text(4.6, 4.35, "echoes: ceiling, walls, furniture —\nthe \"hall of mirrors\"",
            fontsize=8, color="#555", ha="center")
    ax.annotate("the chest moving millimeters\nchanges the sum of all paths",
                xy=(6.7, 1.62), xytext=(4.6, 3.1), fontsize=8, color=C_RESP,
                arrowprops=dict(arrowstyle="->", color=C_RESP, lw=1.1))
    ax.set_title("Section 2.2 — The channel: direct path + multipath echoes, and the\n"
                 "Fresnel zone where a breathing chest is measurable", fontsize=10)
    fig.tight_layout()
    save(fig, "multipath-fresnel.png")


# ------------------------------------------------- 8. RSSI -> distance model
def fig_rssi_distance():
    d = np.linspace(0.5, 8, 200)
    ref_d, ref_dbm, n_pl = 1.0, -40.0, 3.0     # CSI_REF_DISTANCE_M / CSI_RSSI_REF_DBM / CSI_PATH_LOSS_N
    rssi = ref_dbm - 10 * n_pl * np.log10(d / ref_d)
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.plot(d, rssi, color=C_RAW, lw=2)
    ax.scatter([1.0], [ref_dbm], zorder=5, color=C_HEART)
    ax.annotate("calibration point:\n(CSI_REF_DISTANCE_M, CSI_RSSI_REF_DBM)",
                xy=(1.0, -40), xytext=(2.2, -36), fontsize=7.5,
                arrowprops=dict(arrowstyle="->", color=C_HEART, lw=1))
    ax.axhline(-52, color="gray", ls=":", lw=1)
    ax.annotate("measured RSSI = -52 dBm\n→ model inverts PL(d) → ~1.9 m",
                xy=(1.9, -52), xytext=(3.4, -56), fontsize=7.5,
                arrowprops=dict(arrowstyle="->", color="gray", lw=1))
    ax.text(5.6, -70, "$PL(d) = PL(d_0) + 10\\,n_{pl}\\,\\log_{10}(d/d_0)$\n"
            r"$n_{pl}$ indoor ≈ 2.7–4.3", fontsize=9)
    ax.set_xlabel("real distance d [m]")
    ax.set_ylabel("RSSI [dBm]")
    ax.set_title("Section 4 step 8 — RSSI → link distance: a compass, not a GPS\n"
                 "(multipath fading adds ±5–10 dB of scatter around the curve)")
    fig.tight_layout()
    save(fig, "rssi-distance-model.png")


if __name__ == "__main__":
    print("Generating documentation figures -> docs/img/")
    fig_wave_anatomy()
    fig_csi_mean_scenarios()
    fig_vitals_annotated()
    fig_heatmap()
    fig_spectrogram()
    fig_motion_rms()
    fig_multipath()
    fig_rssi_distance()
    print("Done.")
