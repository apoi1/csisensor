# Signal Modeling — WiFi-CSI Vital-Signs Project

This document describes the signal model of the project: an ESP32-S3 captures WiFi CSI amplitudes, streams them as CSV over MQTT, and a Python backend estimates vital signs and body motion. All formulas below are the ones actually implemented in the firmware or the Python processing chain.

## 1. Overview and honest scope

```
ESP32-S3 nodes (CSI capture) ──MQTT──► Mosquitto (Docker) ◄── Python backend (paho-mqtt + scipy FFT) ──► PyQt5 GUI (vitals + body presence/motion)
      (one or more, per-device topics)                                          └──► Web viewer (backend/web_viewer.py → any phone browser on the LAN)
```

- **Amplitude-only CSI** — the firmware discards subcarrier phase and publishes only $a_k = |H_k|$.
- **Single antenna per link** — no antenna array, no per-link AoA. **Multiple links (multi-ESP32) ARE supported** since 2026-10: each device publishes to its own topic and the backend fuses per band (see §8).
- **Estimated today** — presence (absent / still / moving) and a coarse RSSI link-distance.
- **Not estimated** — geometric coordinates (x/y), posture, body orientation, angle of arrival.

## 2. Data collection (hardware → broker → backend)

**Firmware (ESP32-S3, STA mode, ESP-IDF v5.x).** The router/AP emits 802.11n OFDM frames; the ESP32 receives them. A lwIP ping session to the gateway (`CSI_INTERVAL_MS` = 100 ms) generates steady traffic so CSI callbacks fire at `fs ≈ 10 Hz`.

The native ESP-IDF CSI API is used: `esp_wifi_set_csi_config` (`lltf_en`, `htltf_en`, `stbc_htltf2_en`, `ltf_merge_en` set to `true`; `manu_scale` to `false`; `channel_filter_en` follows `CSI_CHANNEL_FILTER` — `true` in `config.h`, the IDF's adjacent-subcarrier smoothing for higher SNR) plus `esp_wifi_set_csi_rx_cb`. The callback receives a `wifi_csi_info_t` containing:

- `csi_buf` — signed I/Q byte pairs,
- `csi_len` — length in bytes → `K = csi_len/2` subcarriers,
- `rx_ctrl.rssi` — received signal strength in dBm.

**Per-packet extraction.** The complex channel coefficient per OFDM subcarrier `k` is

```math
H_k = I_k + j Q_k
```

Physically, the receiver recovers each received tone by projecting it onto two phase references: the carrier itself (**I**, *in-phase*) and the carrier shifted by 90° (**Q**, *quadrature*). The signed pair $(I_k, Q_k)$ are the coordinates of the received phasor for subcarrier `k`: its **length** is the amplitude $a_k = \lvert H_k \rvert$ and its **angle** $\mathrm{atan2}(Q_k, I_k)$ is the phase shift the channel introduced on that tone (the firmware-side view is in `docs/FIRMWARE-ESP32.md` §5).

The firmware keeps only the amplitude

```math
a_k = \mathrm{round}\left(\sqrt{I_k^2 + Q_k^2}\right)
```

with $|I_k|, |Q_k| \le 127$ → $a_k \lesssim 180$, which fits a `uint8`. **Phase is discarded.** The timestamp is `t_us = esp_timer_get_time()` (µs since boot).

**Transport.** A FreeRTOS queue (depth 32) decouples the WiFi-task callback from the publisher task. esp-mqtt publishes ASCII CSV

```
t_us,rssi,n,seq,a0..a(K-1)
```

to topic `esp32/csi/raw` on a Mosquitto broker (Docker).

**Backend (Python).** A paho-mqtt `MultiLinkSubscriber` (`link_manager.py`, subclass of `CsiSubscriber`) subscribes the wildcard `esp32/+/csi/raw` plus the legacy flat topic `esp32/csi/raw`, and pushes parsed packets (`t_us`, `rssi`, `n`, `seq`, `amps` ndarray) into `queue.Queue(maxsize=1024)`, re-tagged as `(link_id, packet)` pairs; `drain_and_feed()` routes each packet to that link's isolated pipelines, the GUI drains at 5 Hz, and links are fused per band (§8).

## 3. Physical principles

**OFDM CSI.** Each OFDM subcarrier probes the multipath channel; a moving/scattering body perturbs $H_k$.

**Fresnel-zone model.** The Fresnel zones are ellipsoids around the TX–RX axis. The radius of the n-th zone, with `d1`, `d2` the distances from TX and RX to the body, is

```math
r_n = \sqrt{\frac{n \lambda d_1 d_2}{d_1 + d_2}}
```

A person near the first Fresnel-zone boundary strongly modulates $|H_k|$.

**Vital-sign displacement.** Chest displacement is modeled as

```math
x(t) \approx A_b \sin(2 \pi f_b t)
```

with breathing `f_b ∈ 0.1–0.5 Hz` and faint heartbeat content at `0.8–2.0 Hz`. These modulate the path length by millimeters — well below `λ`.

**Wavelength.**

```math
\lambda = \frac{c}{f_c}, \qquad c = 299{,}792{,}458\ \mathrm{m/s}
```

Channel 1 (`f_c = 2.412 GHz`) → `λ ≈ 12.44 cm`. The firmware does **not** publish the RF channel, and does not pin one either: `CSI_CHANNEL_FILTER` (firmware `config.h`) is the IDF subcarrier-smoothing flag, **not** an AP-channel pin — so the wavelength is only approximately known (assume channel 1 unless the channel is measured externally).

**Doppler phase sensing — not available here.** For a reflected round trip,

```math
\Delta \varphi(t) = \frac{4 \pi}{\lambda} d(t)
```

This quantity is **not** available in this pipeline because phase is discarded; amplitude-only sensing relies on multipath amplitude modulation. (FullBreathe documents the phase+amplitude complementarity; see references.) Publishing `atan2(Q, I)` is the future firmware path.

**RSSI and log-distance path loss.**

```math
PL(d) = PL(d_0) + 10\, n_{pl} \log_{10}\left(\frac{d}{d_0}\right) + X_\sigma
```

Indoor `n_pl ≈ 2.7–4.3`; `X_sigma` is shadowing (a person near the LOS path adds excess attenuation).

## 4. Processing chain (exact implemented formulas)

**Sliding window.** $N = \mathrm{round}(f_s \cdot T_w)$ samples; defaults $f_s = 10\ \mathrm{Hz}$, $T_w = 15\ \mathrm{s}$ → $N = 150$ rows × $K$ subcarriers.

```math
N = \mathrm{round}(f_s \cdot T_w)
```

**Detrend.** Linear detrending (`scipy.signal.detrend`) removes DC/slow drift.

**Best subcarrier per band.** Per subcarrier `k`: detrend → Hann window → `np.fft.rfft` → in-band peak. The Hann window is `np.hanning`:

```math
w[n] = 0.5 \left(1 - \cos\left(\frac{2 \pi n}{N - 1}\right)\right)
```

The spectrum is

```math
X = \left| \mathrm{rfft}(x \cdot w) \right|
```

(`np.fft.rfft`). Quadratic interpolation on the log-spectrum, with `la = log(X[i-1]+eps)`, `lb = log(X[i]+eps)`, `lc = log(X[i+1]+eps)`:

```math
\delta = \frac{0.5 (l_a - l_c)}{l_a - 2 l_b + l_c}, \qquad \hat{f} = f_i + \delta \Delta f
```

In-band SNR per subcarrier:

```math
\mathrm{SNR}_k = 20 \log_{10}\left(\frac{\text{in-band peak}}{\text{in-band median}}\right)
```

The subcarrier with max $\mathrm{SNR}_k$ wins.

**Rate conversion.** $\mathrm{BPM} = 60 \cdot f_{\mathrm{heart}}$; $\mathrm{breaths/min} = 60 \cdot f_{\mathrm{resp}}$. Quality gate: the estimate is discarded if $\mathrm{SNR} < \mathrm{min\_snr\_db}$ (default 6 dB).

**Waveforms.** Zero-phase 3rd-order Butterworth bandpass (`scipy.signal.butter` with `output='sos'` + `sosfiltfilt`): respiration band `0.1–0.5 Hz`, heart band `0.8–2.0 Hz`.

**Body motion / presence (`MotionAnalyzer`).**

- Mean amplitude across subcarriers:

```math
\bar{a}[n] = \frac{1}{K} \sum_{k} a_k[n]
```

- Detrend, then `sigma_window = std(detrended a_bar)`.
- `ABSENT` if `sigma_window < 0.15` (noise-flat empty room).
- Motion band `0.5–3.0 Hz` Butterworth bandpass → `b[n]`:

```math
M_{\mathrm{rms}} = \sqrt{\mathrm{mean}(b^2)}
```

- `MOVING` if `M_rms > 1.5` (gross body movement); otherwise `STILL` (person at rest, breathing modulation only).

**RSSI link distance.** `R_bar = mean` window RSSI:

```math
\hat{d} = d_0 \cdot 10^{\frac{R_0 - \bar{R}}{10 n_{pl}}}
```

Defaults: `R0 = -52 dBm` at `d0 = 1 m`, `n_pl = 3.0`. This ranges the TX–RX link budget; the body perturbs it as shadowing (`X_sigma`), so `d_hat` is a coarse link indicator, not person coordinates.

**Visualization cadence.** A `QTimer` at 5 Hz drains the queue; estimates recompute every 1 s; heavy panels recompute only at the 1 s cadence.

## 5. Variable provenance table

| Symbol | Meaning | Unit | Where it comes from |
| --- | --- | --- | --- |
| `H_k` | Complex channel coefficient | unitless (complex) | `csi_buf` I/Q pairs |
| $a_k = \lvert H_k \rvert$ | Subcarrier amplitude | uint8 counts | CSV fields `a0..a(K-1)` |
| `I_k` / `Q_k` | Signed I/Q bytes | int8 | `csi_buf[2i]`, `csi_buf[2i+1]` |
| `K` | Subcarrier count | count | CSV field `n` = `csi_len/2` |
| `t_us` | Timestamp | µs since boot | `esp_timer_get_time()` |
| `rssi` | Received signal strength | dBm | `rx_ctrl.rssi` |
| `seq` | Packet sequence | counter | firmware counter |
| `fs` | CSI sampling rate | Hz | config `CSI_FS` (matches ping interval) |
| `T_w` | Window length | s | config `CSI_WINDOW_S` |
| $N$ | Samples per window | count | derived: $N = \mathrm{round}(f_s \cdot T_w)$ |
| `w[n]` | Hann window | unitless | `np.hanning` |
| `X[f]` | Magnitude spectrum | unitless | `abs(np.fft.rfft(x·w))` |
| `f_hat` | Estimated frequency | Hz | quadratic interpolation on log-spectrum |
| $\mathrm{SNR}_k$ | In-band SNR of subcarrier $k$ | dB | $20\cdot\log_{10}(\text{peak}/\text{median})$ |
| `BPM` | Heart rate | beats/min | `60·f_hat_heart` |
| `breaths/min` | Respiration rate | breaths/min | `60·f_hat_resp` |
| `min_snr_db` | Quality gate | dB | config `CSI_MIN_SNR_DB` |
| `a_bar[n]` | Mean subcarrier amplitude | uint8 counts | mean over `K` |
| `sigma_window` | Std of detrended `a_bar` | counts | `std(detrended a_bar)` |
| `M_rms` | Motion-band RMS | counts | `sqrt(mean(b^2))` |
| `0.15` / `1.5` | Absence / motion thresholds | counts | config `CSI_ABSENT_STD` / `CSI_MOVING_RMS` |
| `R_bar` | Mean window RSSI | dBm | mean RSSI |
| `d_hat` | Estimated link distance | m | log-distance formula |
| `R0` / `d0` / `n_pl` | Reference RSSI / distance / path-loss exponent | dBm / m / unitless | config `CSI_RSSI_REF_DBM` / `CSI_REF_DISTANCE_M` / `CSI_PATH_LOSS_N` |
| `λ`, `c`, `f_c` | Wavelength / speed of light / carrier frequency | m / m/s / Hz | constants; `f_c` depends on AP channel (not published) |
| `eps` | Numerical guard | unitless | `vitals_processor` |

## 6. Calibration techniques

- **Empty-room baseline** — record the flat channel and tune `CSI_ABSENT_STD` above the noise std.
- **Walk test** — walk near the link and tune `CSI_MOVING_RMS` below the observed episode RMS.
- **RSSI two-point ranging** — measure `R0` at a known `d0` (e.g. 1 m); at a second known distance `d`, solve `n_pl = (R0 - R(d)) / (10·log10(d/d0))`; note the shadowing variance.
- **Angle / AoA** — impossible with single-antenna amplitude-only data. Two calibration-grade paths, both future work:
  1. firmware phase export (`atan2(Q, I)`) plus an antenna array: phase difference `Δψ = (2π·s/λ)·sin(θ)` with antenna spacing `s`;
  2. multi-device geometry like Espressif esp-csi `esp-radar`.
- **Fresnel placement** — keep the body near the TX–RX first Fresnel zone for best vitals sensitivity; body location and orientation matter.

## 7. How the app evaluates body position today

- Classification pipeline absent / still / moving (window std + motion-band RMS), plus the RSSI link distance labeled **"link dist"** in the GUI.
- What it does **not** estimate: x/y coordinates, posture, angle.

## 8. Multi-device links (multi-ESP32) — implemented design

**Why multiple links help.** A single TX–RX link is hostage to geometry: the
Fresnel-zone model (§3) predicts deep amplitude nulls where the body sits at
zone boundaries, and any link loses the vital-sign modulation when the
subject turns. `N` links around the room give spatial diversity: the subject
cannot sit in the null of every link at once. This is the standard link-
diversity argument in the WiFi-sensing literature.

**Where the data comes from per link.** Each ESP32 publishes to its own
per-device topic

```
esp32/<id>/csi/raw        <id> = last 3 bytes of the STA MAC (eFuse-derived, stable)
```

so links never collide on the broker. The backend subscribes the wildcard
`esp32/+/csi/raw` **plus** the legacy flat topic `esp32/csi/raw` (old firmware
keeps working un-reflashed). Every packet is tagged with its link id taken
from the MQTT topic; each link owns an isolated `VitalsProcessor` +
`MotionAnalyzer`, so the hardened input guards (non-finite drop, monotonic
timestamps, width reset) apply **per link** — two devices with overlapping
clock domains never corrupt each other's windows (the reason a shared window
is not an option).

**Fusion (per band, max SNR).** For each physiological band independently,
the link whose in-band SNR ($\mathrm{SNR}_k$, §4) is highest wins the estimate:

```math
\hat{f}_{heart} = \hat{f}\left( \arg\max_{\ell \in L} \mathrm{SNR}_{heart}(\ell) \right), \qquad
\hat{f}_{resp} = \hat{f}\left( \arg\max_{\ell \in L} \mathrm{SNR}_{resp}(\ell) \right)
```

Heart and respiration may therefore come from different links — each band
follows the link that observes it best. The heart-winning link becomes the
*primary* link: the GUI physics panels and the RSSI/distance readout follow
it. If the best link still sits below the 6 dB gate, the fused rate is
`None` — an honest "no link passed the gate", never a mixed estimate.

**Presence aggregate (conservative).** Any link reports `Moving` → `Moving`;
else any link `Still` → `Still`; else `Absent`. A person visible to any link
counts as present; the aggregated motion RMS is the maximum across links.

**Practical notes.** Flash each node once with the per-device firmware; the
id is derived from its MAC, so no per-node configuration is needed. Dry-run
without hardware: run two simulators with `--device-id a1b2c3` and
`--device-id d4e5f6` (DEPLOYMENT.md §10). The backend GUI status bar and the
web page's meta line show the active link count; `--topic` still pins a
single explicit topic/pattern when needed.

## 9. GUI function inventory

| Panel | Quantity | Formula shown (mathtext) |
| --- | --- | --- |
| Body row label | presence state, `M_rms`, `sigma_window`, `R_bar`, `d_hat` | text summary |
| CSI mean amplitude plot | `a_bar(t)` over window | `$\bar{a}(t)=\frac{1}{K}\sum_{k}\lvert H_k(t)\rvert$` |
| Respiration plot | Butterworth-filtered `x(t)`, 0.1–0.5 Hz | `$x(t)$`, band |
| Heart plot | filtered `x(t)`, 0.8–2.0 Hz | `$x(t)$`, band |
| Subcarrier heatmap | $20\,\log_{10}(\lvert H_k\rvert + \epsilon)$, subcarrier $k$ vs $t$ | `$\lvert H_k\rvert=\sqrt{I_k^2+Q_k^2}$` |
| Spectrogram | `scipy.signal.spectrogram` of `a_bar(t)` with shaded bands | `$X(\tau,f)=\sum_n x[n]\,w[n-\tau]\,e^{-j2\pi fn/N}$` |
| Motion-energy trace | 10-min `M_rms` history with threshold line | `$M_\mathrm{rms}=\sqrt{\langle b^2(t)\rangle}$`, band 0.5–3.0 Hz |

## 10. Libraries, frameworks, technologies

- **Firmware**: ESP-IDF v5.x C++ (esp_wifi CSI API, esp_timer, esp_event, esp_netif, nvs_flash, esp-mqtt), FreeRTOS queues/tasks, lwIP ping.
- **Transport**: Mosquitto MQTT broker (Docker + docker-compose), paho-mqtt (Python).
- **Processing**: Python 3, numpy (`ndarray`, `rfft`, `hanning`, `log10`, `std`), scipy.signal (`detrend`, `butter`/`sosfiltfilt`, `spectrogram`), dataclasses, `collections.deque` sliding windows.
- **Web viewer**: aiohttp (HTTP + WebSocket server, Apache 2.0), paho-mqtt consumer.
- **Multi-link**: `backend/link_manager.py` (wildcard subscription, per-link pipelines, per-band max-SNR fusion).
- **GUI**: PyQt5 (`QMainWindow`, `QTimer`, labels/status bar), matplotlib Qt5Agg (`Figure`/`FigureCanvasQTAgg`, gridspec, `imshow`, mathtext formula titles).
- **Config/testing**: frozen dataclass `Config` with `os.getenv` overrides; pytest unit tests; numpy-based synthetic simulator (scenarios resting/moving/absent) via paho-mqtt.

## 11. References (verified)

1. Espressif ESP-CSI — CSI applications (indoor positioning, human detection): <https://github.com/espressif/esp-csi>
2. ESP32-CSI-Tool — CSI collection tool (active/passive): <https://github.com/StevenMHernandez/ESP32-CSI-Tool>
3. Zhang et al., "Human Respiration Detection with Commodity WiFi Devices: Do User Location and Body Orientation Matter?", UbiComp 2016 (Fresnel model; location/orientation).
4. Zeng et al., "FullBreathe: Full Human Respiration Detection Exploiting Complementarity of CSI Phase and Amplitude of WiFi Signals", Proc. ACM IMWUT, 2018, DOI 10.1145/3264958.
5. "WiFi-based Real-time Breathing and Heart Rate Monitoring during Sleep", arXiv:1908.05108.
6. "A survey on vital signs monitoring based on Wi-Fi CSI data" (PMC9375645).
7. Rappaport, "Wireless Communications: Principles and Practice" — log-distance path loss; see also Wikipedia "Log-distance path loss model" (`PL(d) = PL(d0) + 10·n·log10(d/d0) + X_sigma`, indoor `n ≈ 2.7–4.3`).
8. ESP-IDF WiFi CSI API: <https://docs.espressif.com/projects/esp-idf/>
9. Mosquitto: <https://mosquitto.org/> ; paho-mqtt: <https://pypi.org/project/paho-mqtt/>
10. numpy <https://numpy.org/> ; scipy <https://scipy.org/> ; matplotlib <https://matplotlib.org/> ; PyQt5 <https://www.riverbankcomputing.com/software/pyqt/>
