# Marco metodológico — del input en 0 al píxel en pantalla

> **Qué es este documento.** El recorrido COMPLETO de un dato: desde la
> onda de radio que llega al ESP32 hasta el píxel exacto que ves en el
> GUI, etapa por etapa, con **el tratamiento matemático exacto**, **la
> tecnología específica que ejecuta cada paso**, **por qué se hizo así y
> no de otra manera**, y **la correspondencia final dato visible ←
> origen**. Cada afirmación está verificada contra el código fuente
> (archivo y función citados). Compañeros: `docs/HOW-IT-WORKS.md`
> (versión simple) y `docs/SIGNAL-MODELING.md` (fórmulas + provenance).

---

## 0. Mapa general: las 6 etapas

| # | Etapa | Tratamiento matemático | Tecnología que lo ejecuta | Por qué esa y no otra |
|---|---|---|---|---|
| 0 | **RF/canal** | OFDM: canal `H_k` por subportadora; amplitud `a_k = √(I²+Q²)`; la física (λ≈12,44 cm, multipath, Fresnel) modula `|H_k|` con el temblor del pecho | Radio ESP32-S3 + driver WiFi de **ESP-IDF v5.x** (`esp_wifi_set_csi_rx_cb`); iluminación: **lwIP ping** cada 100 ms → `fs ≈ 10 Hz` | Sin paquetes no hay medición: el ping genera las "fotos" a ritmo fijo. API nativa del IDF (no una herramienta externa) |
| 1 | **Empaquetado** (firmware) | CSV ASCII `t_us,rssi,n,seq,a0..a(n-1)`; tópico por dispositivo `esp32/<id>/csi/raw` (id = 3 últimos bytes de la MAC STA, `esp_read_mac` verificado; buffer `snprintf` de 48 B) | **C++/ESP-IDF + esp-mqtt**; `config.h` (`CSI_INTERVAL_MS=100`, `CSI_MAX_SUBCARRIERS=128` — el S3 usa ~64, `K = csi_len/2`) | Un tópico por placa = aislamiento de links desde el transporte; CSV compacto por MQTT |
| 2 | **Transporte** | Pub/sub sin transformación (QoS 0, keepalive 60 s) | **Mosquitto** (Docker, conf bakeada en build; 1883 TCP, 9001 websockets para clientes futuros) | MQTT desacopla productor/consumidores: el GUI y el viewer son consumidores independientes del mismo broker |
| 3 | **Ingesta** | Parseo + guardias + cola + etiquetado de link + registro por link | **paho-mqtt** (`>=1.6,<2.0` — la API 2.x rompió `Client()`), `queue.Queue(1024)`, `csi_packets.parse_csi_payload`, `link_manager` (lock `threading.Lock`, LRU `MAX_LINKS=16`, expiración `LINK_STALE_S=20`) | La cola desacopla el hilo de red de paho del hilo del consumidor; el contador `dropped` da visibilidad de backpressure sin bloquear la red |
| 4 | **DSP por link** | Ventana 150×K → detrend → Hann → `rfft` → pico en banda + interpolación parabólica (dominio log) → SNR vs mediana → mejor subportadora por banda → Butterworth banda → tasas + ondas + presencia + distancia | **numpy** (`np.fft.rfft`, `np.hanning`, `deque(maxlen)`), **scipy** (`signal.detrend`, `signal.butter` orden 3 salida SOS, `signal.sosfiltfilt`) | Ver §4: cada decisión matemática con su porqué |
| 5 | **Fusión multi-link** | Por banda gana el link con mejor SNR (pueden ser links distintos para corazón y respiración); primary = ganador cardíaco; presencia conservadora; RMS = máx entre links | `link_manager.LinkManager.estimate()` / `motion_estimate()` | Dos placas = dos puntos de vista del mismo pecho; gana el que "ve mejor" CADA banda |
| 6 | **Render** | `t` relativo, dB para imágenes, `set_data`+`relim`+autoscale y-only, `draw_idle` coalescido | **PyQt5** (event loop + `QTimer` 200 ms), **Matplotlib** backend `Qt5Agg` (`FigureCanvasQTAgg`), colormaps `viridis`/`magma`; web: **aiohttp** + JS vainilla | Ver §6: cada decisión de render con su porqué |

Cadencias (verificadas en `config.py`/`gui.py`): datos a **10 Hz** (firmware),
tick del GUI a **5 Hz** (`gui_refresh_hz` → 200 ms), estimaciones/render a
**1 Hz** (`estimate_every_s`), ventana de tasa de paquetes 2 s, historia de
movimiento 600 s.

---

## 1. Etapa 0 — la física produce el número en el chip

**Qué entra**: frames 802.11n OFDM del router (o del ping que el propio
firmware disparó). **Qué sale**: un callback con `wifi_csi_info_t`.

1. El canal de 20 MHz viaja en decenas de subportadoras (tonos OFDM).
   Cada tono sufre SU versión del canal: `H_k = Σ(caminos)` — la suma de
   ecos con distintas longitudes/fases (multipath).
2. El pecho (mm al respirar, sub-mm al latir, `x(t) ≈ A_b·sin(2πf_b·t)`,
   respiración 0,1–0,5 Hz, corazón 0,8–2,0 Hz) perturba caminos dentro
   de las zonas de Fresnel → `|H_k(t)|` queda modulado con ese ritmo.
   λ ≈ 12,44 cm (canal 1; el firmware no fija canal — aproximación
   documentada).
3. El driver entrega `I_k, Q_k` por tono; el firmware publica SOLO la
   amplitud `a_k = √(I²+Q²)` (int 0..255), **la fase se descarta a
   propósito** (limitación documentada; `atan2(Q,I)` es el camino futuro
   en `SIGNAL-MODELING.md` §3).
4. Config CSI (verificada en `config.h`/SIGNAL-MODELING §2):
   `lltf_en`, `htltf_en`, `stbc_htltf2_en`, `ltf_merge_en = true`,
   `manu_scale = false`, `channel_filter_en = CSI_CHANNEL_FILTER (true)`
   → suavizado de subportadoras adyacentes del IDF (SNR más alto).
   `K = csi_len/2` → ~64 subportadoras reales en el S3.

**Por qué así**: sin fase, la sensibilidad viene de modulación de
amplitud por multipath — funciona porque el pecho cerca de la zona de
Fresnel perturba la SUMA de caminos. El ping propio garantiza el
"flash" a `fs ≈ 10 Hz` aunque nadie más use la red.

## 2. Etapa 1–2 — firmware → MQTT → backend

Fila CSV por paquete (`csi_packets.py`, formato verificado):

| Campo | Significado | Origen físico |
|---|---|---|
| `t_us` | reloj del chip desde el arranque (µs) | `esp_timer` |
| `rssi` | potencia del paquete (dBm, int) | capa MAC |
| `n` | cantidad de subportadoras de ESTE paquete | `K = csi_len/2` |
| `seq` | nro. de secuencia del paquete | firmware |
| `a0..a(n-1)` | amplitudes `√(I²+Q²)` 0..255 | CSI del driver |

Transporte: `esp32/<id>/csi/raw` (wildcard `esp32/+/csi/raw` +
tópico plano legacy en el default del backend; `MQTT_TOPIC` explícito
reemplaza la lista — contrato restaurado 2026-10-14; `--topic` CLI gana).

## 3. Etapa 3 — ingesta: guardias, cola, links

**`parse_csi_payload`** (`csi_packets.py`): ASCII → ints → `amps` float64;
cualquier malformación → `None` (se descarta con log debug). *Por qué: un
payload corrupto jamás entra al DSP.*

**`CsiSubscriber`** (`mqtt_subscriber.py`): `client_id = csi-backend-<pid>`,
`connect_async` + `loop_start` (hilo de red de paho), subscribe **QoS 0**
(a 10 paquetes/s no hace falta garantía de entrega: un paquete perdido es
ruido de muestreo, no pérdida de datos), `put_nowait` en `queue.Queue(1024)`
→ si llena, `_dropped += 1` (contado, nunca bloquea la red).

**`MultiLinkSubscriber`** (`link_manager.py`): re-etiqueta `(link_id, packet)`
con `link_id_from_topic` (los 3 bytes del tópico; `esp32/csi/raw` →
"default"; layout desconocido → el tópico entero como id, sin colisiones).
`drain_tagged(256)` mueve del hilo de red al consumidor.

**`LinkManager`**: un par `(VitalsProcessor, MotionAnalyzer)` por link,
`_links/_last_seen/_primary` bajo `threading.Lock` (TODOS los accessors
públicos lo toman). `_pipelines(touch=True)` — **solo el ingest refresca
staleness** (los lectores pasan `touch=False`: un primary muerto expira a
los 20 s aunque el GUI lo sondee). LRU: al llenar `MAX_LINKS=16` desaloja
al más viejo y limpia `_primary` si era la víctima.

## 4. Etapa 4 — DSP por link: las matemáticas exactas

Archivo: `vitals_processor.py` (verificado línea a línea).

**Guardias de entrada** (`push`): NaN/inf en amplitudes → descartar;
`t ≤ t_último` → descartar (la FFT asume grilla uniforme); cambio de `n`
→ ventana nueva (link físicamente distinto). *Por qué: una sola fila
corrupta envenena media/FFT/heatmap (comentario R1/R4 del propio código).*

**Ventana**: `deque(maxlen = max(16, round(fs·T_w))) = 150` filas × K
columnas (10 Hz × 15 s). *Por qué deque: ventana deslizante O(1), sin
poda manual; por qué 15 s: ~4 ciclos respiratorios y ~15 cardíacos — la
resolución de la FFT es `Δf = 1/15 s ≈ 0,0667 Hz`.*

**Mejor subportadora por banda** (`_best_subcarrier` → `_band_peak`):
```
x_k = detrend(matrix[:, k])              # scipy.signal.detrend: resta el
                                          # ajuste lineal → sin deriva DC
w   = x_k · np.hanning(n)                 # ventana Hann: sin fuga espectral
S   = |np.fft.rfft(w)|                    # FFT real: mitad de bins, sin espejo
f   = np.fft.rfftfreq(n, d = 1/fs)
pico = argmax{ S[f] : f ∈ banda }         # resp (0,1–0,5 Hz) | heart (0,8–2,0)
```
Interpolación parabólica **en dominio log** del espectro:
```
δ = ½·(ln S[i-1] − ln S[i+1]) / (ln S[i-1] − 2·ln S[i] + ln S[i+1])
f* = f[pico] + δ·Δf        (solo si |δ| ≤ 1)
```
*Por qué: sin esto, respirar a 0,2 Hz con Δf=0,067 Hz cuantiza a 12 o
18/min; la parábola recupera precisión sub-bin.*
**SNR** (compuerta de calidad):
```
SNR_k = 20·log10( (pico + ε) / (mediana{S en banda} + ε) ),  ε = 1e-12
```
*Por qué mediana y no media del piso: robusta al propio pico (una media
se inflaría con el pico). Gana el k con mayor SNR_k — y se REPORTA cuál
(`sc#` en pantalla).*

**Ondas mostradas** (`_bandpass`): Butterworth orden 3, salida SOS,
`sosfiltfilt` (ida y vuelta → **fase cero**):
```
resp_wave  = sosfiltfilt(butter(3, [0.1, 0.5], bandpass, fs=10), detrend(x_r*))
heart_wave = sosfiltfilt(butter(3, [0.8, 2.0], bandpass, fs=10), detrend(x_h*))
```
*Por qué `sosfiltfilt` y no un filtro común: sin filtrar hacia atrás, el
filtro IIR DESFASA la onda en el tiempo — las ondas que mostrás quedarían
desplazadas respecto al raw. Por qué SOS: cascada de biquads,
numéricamente estable. Por qué orden 3: Butterworth = máximamente plano
(sin ripple en la banda); con <30 muestras no se filtra (padding).* El
fallback documentado: banda no observable a este `fs` (`hi ≤ lo`) o
ventana corta → devuelve la señal detrended tal cual.

**Tasas**: `bpm = f*_heart · 60` y `resp/min = f*_resp · 60` — **solo si
`SNR ≥ 6 dB`** (`CSI_MIN_SNR_DB`); si no, `None` → el GUI muestra `-`.
*Por qué: sin calidad no hay número — honestidad por diseño.*

**Presencia/movimiento** (`motion_analyzer.py`, verificado):

```math
x = \text{media de amplitudes por paquete} \quad x_d = \operatorname{detrend}(x) \quad \sigma_\text{ventana} = \operatorname{std}(x_d)
```

```math
\mathrm{RMS}_\text{mov} = \sqrt{\operatorname{mean}(\operatorname{sosfiltfilt}(\operatorname{butter}(\mathrm{ord},[0.5,3.0]),x_d)^2)} \quad \mathrm{ord} = \begin{cases}3 & n\ge 30\\2 & \text{si no}\end{cases}
```

```math
\text{estado: } \sigma < 0.15 \to \text{Absent} \;|\; \mathrm{RMS} > 1.5 \to \text{Moving} \;|\; \text{si no} \to \text{Still}
```
**Distancia RSSI** (log-distance path loss, calibrable/apagable):

```math
\hat{d} = d_0 \cdot 10^{\frac{R_0 - \bar{R}}{10\,n_{pl}}} \quad \bar{R} = \text{media del RSSI de la ventana}
```

```math
R_0 = \texttt{CSI\_RSSI\_REF\_DBM}\;(-52) \quad d_0 = \texttt{CSI\_REF\_DISTANCE\_M}\;(1.0) \quad n_{pl} = \texttt{CSI\_PATH\_LOSS\_N}\;(3.0)
```
*Por qué: modelo estándar indoor (`n_pl ≈ 2,7–4,3`); sin calibración real
es mejor `—` que un número inventado.*

**Fusión multi-link** (`link_manager.estimate`, verificado):

```math
\text{vivos} = \{\text{links}: \text{ahora} - t_\text{ingest} \le 20\text{ s}\} \quad \text{por banda: gana el mayor SNR en ESA banda} \quad \text{primary} = \text{ganador cardíaco}
```
presencia  : Moving si alguno Moving | Still si alguno Still | si no Absent
RMS        = máx entre links vivos listos
σ/RSSI/d   : los del primary (o el primero listo)
```

## 5. Etapa 5 — qué se calcula cuándo

- **5 Hz** (`QTimer` 200 ms): `drain_and_feed()` (red→DSP), tasa de
  paquetes (ventana 2 s), barra de estado.
- **1 Hz** (`estimate_every_s`): `estimate()` + `motion_estimate()` de
  cada link, fusión, TODO el render.
*Por qué: el render de 6 ejes con 2 imshows es caro — 1 Hz alcanza para
una estimación que por construcción tiene 15 s de historia.*

## 6. Etapa 6 — render: cada píxel y su porqué

Tecnología: **PyQt5** (event loop, `QTimer`, `QLabel`) +
**Matplotlib** embebido (`FigureCanvasQTAgg`, backend `Qt5Agg`) — *por
qué: plotting científico con fórmulas mathtext ($\bar{a}(t)$, $X(\tau,f)$)
dentro de la ventana Qt*.

| Decisión | Por qué esa y no otra |
|---|---|
| `set_data` + `relim` + `autoscale_view` en vez de re-plot | reusa los artistas; no reconstruye leyendas ni ejes por frame |
| `draw_idle()` (no `draw()`) | pide el repaint asíncrono; los `draw_idle` de un mismo tick **coalescen** en UN repintado |
| Eje x pineado (0–15 s) + autoscale y-only | autoscale completo por frame es caro; el tiempo estable ayuda al ojo |
| Heatmap: `20·log10(M.T + 1e-9)` en dB, `viridis`, `origin=upper` | dB comprime el rango dinámico (los tonos buenos se ven); viridis = perceptualmente uniforme (válido en escala de grises/daltonismo); subportadora 0 arriba |
| Espectrograma: `scipy.signal.spectrogram(ā, fs, nperseg=min(64,N), noverlap=nperseg//2)` → `10·log10(sxx+1e-12)`, `magma`, `origin=lower` | nperseg 64 ≈ 6,4 s → Δf≈0,156 Hz (resuelve la banda respiratoria); overlap 50% suaviza en tiempo; f crece hacia arriba como un piano |
| Franja de medidas + ylabels con unidad (2026-10-14) | "qué estoy mirando" en un vistazo; misma unidad que este doc |

**Web viewer** (`web_viewer.py`, aiohttp + `web_static/` JS vainilla):
el MISMO `LinkManager` vía accessors con lock; hilo de feed a 1 s; tiles
(BPM, resp/min, Body, distancia) + tendencia de 10 min + últimas ondas
filtradas; reconexión automática; **cero CDN** (funciona en LAN sin
internet). *Por qué aiohttp: un solo proceso sirve HTTP + WebSocket sin
Qt — apto para PyInstaller.*

## 7. Correspondencia final: dato visible ← origen exacto

| Ves en pantalla | Es exactamente | Calculado en | Con qué |
|---|---|---|---|
| Trazo "CSI mean amplitude" | `ā(t)` = media de las K amplitudes del primary, t relativo 0–15 s | `VitalsProcessor.current_window()` | numpy `mean(axis=1)` |
| Trazo "Respiration (filtered)" | señal del mejor subcarrier resp, detrended + Butterworth 0,1–0,5 Hz fase cero | `_bandpass(detrend(x_r*))` | scipy `butter`+`sosfiltfilt` |
| Trazo "Heart (filtered)" | ídem banda 0,8–2,0 Hz | `_bandpass(detrend(x_h*))` | scipy |
| Número BPM / por-min | `f*·60` de la banda (solo si SNR ≥ 6 dB) | `_band_peak` + interpolación | numpy rfft |
| `sc#` y `SNR` del meta | subportadora ganadora y su SNR por banda | `_best_subcarrier` | numpy + mediana |
| Fila "Body" | estado (σ/RMS), RMS banda 0,5–3 Hz, σ_ventana, RSSI medio, d̂ | `MotionAnalyzer.estimate()` | scipy + modelo PL |
| Heatmap | `20·log10(|H_k| + 1e-9)` de TODAS las subportadoras del primary | `current_matrix()` → `_redraw_heatmap` | matplotlib imshow |
| Espectrograma | PSD de `ā` (10·log10), bandas fisiológicas sombreadas | `_redraw_spectrogram` | scipy.spectrogram |
| Energía de movimiento | historia 600 s del RMS fusionado + umbral 1.5 | `_motion_history` deque | matplotlib |
| "links … (primary …)" | registro vivo: ids ordenados + ganador cardíaco | `link_ids()`/`primary_link()` (con lock) | — |
| Franja de medidas | unidades de TODO lo anterior, siempre visible | estática (`gui.py`) | QLabel |

## 8. Limitaciones declaradas (sin sorpresas)

Amplitud sin fase (futuro: `atan2(Q,I)`); corazón frágil (sub-mm);
personas múltiples se mezclan; fallback de RMS con ventanas cortas arrastra
respiración; λ aproximada (canal no pineado); **no es un dispositivo
médico**.
