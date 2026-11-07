# Modelado de la señal — WiFi-CSI Vital Signs

> Términos acuñados en la literatura se citan en inglés sin traducir (CSI,
> RSSI, OFDM, FFT, SNR, detrend, path loss, shadowing); la prosa es en español.

Este documento describe el modelo de señal del proyecto: una ESP32-S3 captura
amplitudes CSI del WiFi, las transmite como CSV por MQTT, y un backend en
Python estima signos vitales y movimiento corporal. Todas las fórmulas de acá
son las efectivamente implementadas, en el firmware o en la cadena de
procesamiento en Python.

## 1. Panorama y alcance honesto

```
nodos ESP32-S3 (captura CSI) ──MQTT──► Mosquitto (Docker) ◄── backend Python (paho-mqtt + FFT scipy) ──► GUI PyQt5 (signos vitales + presencia/movimiento)
      (uno o más, tópico por dispositivo)                                          └──► web viewer (backend/web_viewer.py → cualquier navegador de la LAN)
```

- **CSI solo de amplitud** — el firmware descarta la fase de cada subportadora y publica solo $a_k = |H_k|$.
- **Una antena por enlace** — sin array de antenas, sin AoA (*angle of arrival*) por enlace. **Múltiples enlaces (multi-ESP32) SÍ están soportados** desde 2026-10: cada placa publica a su propio tópico y el backend fusiona por banda (ver §8).
- **Estimado hoy** — presencia (absent / still / moving) y una distancia de enlace RSSI gruesa.
- **No estimado** — coordenadas geométricas (x/y), postura, orientación corporal, ángulo de llegada.

## 2. Captura de datos (hardware → broker → backend)

**Firmware (ESP32-S3, modo STA, ESP-IDF v5.x).** El router/AP emite frames
802.11n OFDM; la ESP32 los recibe. Una sesión de ping lwIP al gateway
(`CSI_INTERVAL_MS` = 100 ms) genera tráfico constante para que los callbacks
CSI se disparen a `fs ≈ 10 Hz`.

Se usa la API CSI nativa del ESP-IDF: `esp_wifi_set_csi_config`
(`lltf_en`, `htltf_en`, `stbc_htltf2_en`, `ltf_merge_en` en `true`;
`manu_scale` en `false`; `channel_filter_en` sigue a `CSI_CHANNEL_FILTER` —
`true` en `config.h`, es el suavizado de subportadoras adyacentes del IDF para
mayor SNR) más `esp_wifi_set_csi_rx_cb`. El callback recibe un
`wifi_csi_info_t` con:

- `csi_buf` — pares de bytes I/Q con signo,
- `csi_len` — largo en bytes → `K = csi_len/2` subportadoras,
- `rx_ctrl.rssi` — potencia recibida en dBm.

**Extracción por paquete.** El coeficiente de canal complejo de cada
subportadora OFDM `k` es

```math
H_k = I_k + j Q_k
```

Físicamente, el receptor recupera cada tono recibido proyectándolo contra dos
referencias de fase: la portadora misma (**I**, *in-phase*) y la portadora
girada 90° (**Q**, *quadrature*). El par con signo $(I_k, Q_k)$ son las
coordenadas del fasor recibido de la subportadora `k`: su **longitud** es la
amplitud $a_k = \lvert H_k \rvert$ y su **ángulo** $\mathrm{atan2}(Q_k, I_k)$
es el desfasaje que el canal introdujo en ese tono (la vista desde el
firmware está en `docs/FIRMWARE-ESP32.md` §5).

El firmware conserva solo la amplitud

```math
a_k = \mathrm{round}\left(\sqrt{I_k^2 + Q_k^2}\right)
```

con $|I_k|, |Q_k| \le 127$ → $a_k \lesssim 180$, que cabe en un `uint8`.
**La fase se descarta.** El timestamp es `t_us = esp_timer_get_time()`
(µs desde el arranque).

**Transporte.** Una cola FreeRTOS (profundidad 32) desacopla el callback de la
tarea WiFi de la tarea publicadora. esp-mqtt publica el CSV ASCII

```
t_us,rssi,n,seq,a0..a(K-1)
```

al tópico `esp32/csi/raw` en un broker Mosquitto (Docker).

**Backend (Python).** Un `MultiLinkSubscriber` de paho-mqtt (`link_manager.py`,
subclase de `CsiSubscriber`) se suscribe al wildcard `esp32/+/csi/raw` más el
tópico plano legacy `esp32/csi/raw`, y empuja los paquetes parseados (`t_us`,
`rssi`, `n`, `seq`, `amps` ndarray) a una `queue.Queue(maxsize=1024)`,
reetiquetados como pares `(link_id, packet)`; `drain_and_feed()` enruta cada
paquete a los pipelines aislados de su enlace, la GUI drena a 5 Hz, y los
enlaces se fusionan por banda (§8).

## 3. Principios físicos

**CSI OFDM.** Cada subportadora OFDM sondea el canal multipath; un cuerpo en
movimiento (dispersor) perturba $H_k$.

**Qué puede (y no puede) resolver un solo receptor.** El canal que ve el
receptor es la suma compleja de los caminos,

```math
H(f) = \sum_{p} \alpha_p\, e^{-j 2\pi f \tau_p}, \qquad \tau_p = d_p / c
```

con amplitud por camino $\alpha_p$ y retardo $\tau_p$. Dos consecuencias
acotan lo que el dato puede decir:

1. **Sin identificación por camino, sin dirección.** Una sola antena
   omnidireccional integra todas las direcciones — el ángulo de llegada exige
   un array de antenas (§6). Las muestras no traen rótulo de "qué eco vino de
   dónde": solo existe la suma compleja por tono.
2. **Sin separación de retardos por camino en este pipeline.** Resolver
   retardos de ecos exige fase a través de la frecuencia (FFT inversa de
   $H(f)$ → perfil de retardos de potencia), con resolución de rango
   $\Delta d \approx c/B \approx 15\ \mathrm{m}$ para un canal de 20 MHz —
   demasiado grueso para ecos indoor de todos modos. Y este firmware descarta
   la fase, de modo que solo existe $|H_k|$, la magnitud de la suma.

Lo que sobrevive es exactamente lo que el sensado necesita: los caminos
estáticos aportan una suma de fasores (estática) — que el `detrend` elimina —
mientras que el pecho rota su fasor lenta y periódicamente. La FFT en el eje
del tiempo (§4) lee la frecuencia de esa rotación; nunca necesita saber qué
eco era cuál.

**Modelo de zonas de Fresnel.** Las zonas de Fresnel son elipsoides alrededor
del eje TX–RX. El radio de la n-ésima zona, con `d1` y `d2` las distancias
desde TX y RX hasta el cuerpo, es

```math
r_n = \sqrt{\frac{n \lambda d_1 d_2}{d_1 + d_2}}
```

Una persona cerca del borde de la primera zona de Fresnel modula $|H_k|$
fuertemente.

**Desplazamiento por signos vitales.** El desplazamiento del pecho se modela
como

```math
x(t) \approx A_b \sin(2 \pi f_b t)
```

con respiración `f_b ∈ 0.1–0.5 Hz` y contenido cardíaco tenue en
`0.8–2.0 Hz`. Estos modulan el largo de camino en milímetros — muy por debajo
de `λ`.

**Longitud de onda.**

```math
\lambda = \frac{c}{f_c}, \qquad c = 299{,}792{,}458\ \mathrm{m/s}
```

Canal 1 (`f_c = 2.412 GHz`) → `λ ≈ 12.44 cm`. El firmware **no** publica el
canal RF ni fija uno: `CSI_CHANNEL_FILTER` (en `config.h` del firmware) es el
flag de suavizado de subportadoras del IDF, **no** un fijador de canal del AP —
por eso la longitud de onda solo se conoce en forma aproximada (asumir canal 1
salvo que se mida externamente).

**Sensado de fase Doppler — no disponible acá.** Para un rebote de ida y
vuelta,

```math
\Delta \varphi(t) = \frac{4 \pi}{\lambda} d(t)
```

Esta cantidad **no** está disponible en este pipeline porque la fase se
descarta; el sensado solo-amplitud depende de la modulación de amplitud por
multipath. (FullBreathe documenta la complementariedad fase+amplitud; ver
referencias.) Publicar `atan2(Q, I)` es el camino futuro del firmware.

**RSSI y path loss log-distance.**

```math
PL(d) = PL(d_0) + 10\, n_{pl} \log_{10}\left(\frac{d}{d_0}\right) + X_\sigma
```

Indoor `n_pl ≈ 2.7–4.3`; `X_sigma` es el shadowing (una persona cerca del camino
LOS agrega atenuación extra).

## 4. Cadena de procesamiento (fórmulas exactas implementadas)

**Ventana deslizante.** $N = \mathrm{round}(f_s \cdot T_w)$ muestras; defaults
$f_s = 10\ \mathrm{Hz}$, $T_w = 15\ \mathrm{s}$ → $N = 150$ filas × $K$
subportadoras.

```math
N = \mathrm{round}(f_s \cdot T_w)
```

**Detrend.** Detrend lineal (`scipy.signal.detrend`) elimina el DC y la
deriva lenta.

**Mejor subportadora por banda.** Por cada subportadora `k`: detrend →
ventana de Hann → `np.fft.rfft` → pico en banda. La ventana de Hann es
`np.hanning`:

```math
w[n] = 0.5 \left(1 - \cos\left(\frac{2 \pi n}{N - 1}\right)\right)
```

El espectro es

```math
X = \left| \mathrm{rfft}(x \cdot w) \right|
```

(`np.fft.rfft`). Interpolación cuadrática sobre el espectro logarítmico, con
`la = log(X[i-1]+eps)`, `lb = log(X[i]+eps)`, `lc = log(X[i+1]+eps)`:

```math
\delta = \frac{0.5 (l_a - l_c)}{l_a - 2 l_b + l_c}, \qquad \hat{f} = f_i + \delta \Delta f
```

SNR en banda por subportadora:

```math
\mathrm{SNR}_k = 20 \log_{10}\left(\frac{\text{pico en banda}}{\text{mediana en banda}}\right)
```

Gana la subportadora con máximo $\mathrm{SNR}_k$.

**Conversión a tasas.** $\mathrm{BPM} = 60 \cdot f_{\mathrm{heart}}$;
$\mathrm{resp/min} = 60 \cdot f_{\mathrm{resp}}$. Compuerta de calidad: la
estimación se descarta si $\mathrm{SNR} < \mathrm{min\_snr\_db}$
(default 6 dB).

**Ondas.** Butterworth pasa-banda de orden 3 sin desfase
(`scipy.signal.butter` con `output='sos'` + `sosfiltfilt`): banda respiratoria
`0.1–0.5 Hz`, banda cardíaca `0.8–2.0 Hz`.

**Movimiento corporal / presencia (`MotionAnalyzer`).**

- Amplitud media entre subportadoras:

```math
\bar{a}[n] = \frac{1}{K} \sum_{k} a_k[n]
```

- Detrend, luego `sigma_window = std(detrended a_bar)`.
- `ABSENT` si `sigma_window < 0.15` (sala vacía, ruido plano).
- Banda de movimiento `0.5–3.0 Hz` pasa-banda Butterworth → `b[n]`:

```math
M_{\mathrm{rms}} = \sqrt{\mathrm{mean}(b^2)}
```

- `MOVING` si `M_rms > 1.5` (movimiento corporal grueso); si no, `STILL`
  (persona en reposo, solo modulación respiratoria).

**Distancia de enlace por RSSI.** `R_bar = mean` del RSSI de la ventana:

```math
\hat{d} = d_0 \cdot 10^{\frac{R_0 - \bar{R}}{10 n_{pl}}}
```

Defaults: `R0 = -52 dBm` a `d0 = 1 m`, `n_pl = 3.0`. Esto mide el presupuesto
del enlace TX–RX; el cuerpo lo perturba como shadowing (`X_sigma`), así que
`d_hat` es un indicador grueso del enlace, no coordenadas de la persona.

**Cadencia de visualización.** Un `QTimer` a 5 Hz drena la cola; las
estimaciones se recalculan cada 1 s; los paneles pesados se recalculan solo a
la cadencia de 1 s.

## 5. Tabla de procedencia de variables

| Símbolo | Significado | Unidad | De dónde sale |
| --- | --- | --- | --- |
| `H_k` | Coeficiente de canal complejo | adimensional (complejo) | pares I/Q de `csi_buf` |
| $a_k = \lvert H_k \rvert$ | Amplitud de la subportadora | cuentas uint8 | campos CSV `a0..a(K-1)` |
| `I_k` / `Q_k` | Bytes I/Q con signo | int8 | `csi_buf[2i]`, `csi_buf[2i+1]` |
| `K` | Cantidad de subportadoras | conteo | campo CSV `n` = `csi_len/2` |
| `t_us` | Timestamp | µs desde el arranque | `esp_timer_get_time()` |
| `rssi` | Potencia recibida | dBm | `rx_ctrl.rssi` |
| `seq` | Secuencia del paquete | contador | contador del firmware |
| `fs` | Tasa de muestreo CSI | Hz | config `CSI_FS` (coincide con el intervalo de ping) |
| `T_w` | Largo de la ventana | s | config `CSI_WINDOW_S` |
| $N$ | Muestras por ventana | conteo | derivado: $N = \mathrm{round}(f_s \cdot T_w)$ |
| `w[n]` | Ventana de Hann | adimensional | `np.hanning` |
| `X[f]` | Espectro de magnitud | adimensional | `abs(np.fft.rfft(x·w))` |
| `f_hat` | Frecuencia estimada | Hz | interpolación cuadrática del espectro log |
| $\mathrm{SNR}_k$ | SNR en banda de la subportadora $k$ | dB | $20\cdot\log_{10}(\text{pico}/\text{mediana})$ |
| `BPM` | Frecuencia cardíaca | latidos/min | `60·f_hat_heart` |
| `resp/min` | Frecuencia respiratoria | respiraciones/min | `60·f_hat_resp` |
| `min_snr_db` | Compuerta de calidad | dB | config `CSI_MIN_SNR_DB` |
| `a_bar[n]` | Amplitud media de subportadoras | cuentas uint8 | media sobre `K` |
| `sigma_window` | Desvío estándar del `a_bar` detrendeado | cuentas | `std(detrended a_bar)` |
| `M_rms` | RMS de la banda de movimiento | cuentas | `sqrt(mean(b^2))` |
| `0.15` / `1.5` | Umbrales de ausencia / movimiento | cuentas | config `CSI_ABSENT_STD` / `CSI_MOVING_RMS` |
| `R_bar` | RSSI medio de la ventana | dBm | media del RSSI |
| `d_hat` | Distancia de enlace estimada | m | fórmula log-distance |
| `R0` / `d0` / `n_pl` | RSSI de referencia / distancia / exponente de path loss | dBm / m / adimensional | config `CSI_RSSI_REF_DBM` / `CSI_REF_DISTANCE_M` / `CSI_PATH_LOSS_N` |
| `λ`, `c`, `f_c` | Longitud de onda / velocidad de la luz / frecuencia portadora | m / m/s / Hz | constantes; `f_c` depende del canal del AP (no publicado) |
| `eps` | Guardia numérica | adimensional | `vitals_processor` |

## 6. Técnicas de calibración

- **Línea base de sala vacía** — registrar el canal plano y ajustar `CSI_ABSENT_STD` por encima del desvío estándar del ruido.
- **Test de caminata** — caminar cerca del enlace y ajustar `CSI_MOVING_RMS` por debajo del RMS observado en el episodio.
- **Ranging RSSI a dos puntos** — medir `R0` a una `d0` conocida (p. ej. 1 m); a una segunda distancia conocida `d`, resolver `n_pl = (R0 - R(d)) / (10·log10(d/d0))`; anotar la varianza del shadowing.
- **Ángulo / AoA** — imposible con datos solo-amplitud de una sola antena. Dos caminos con calidad de calibración, ambos trabajo futuro:
  1. exportar fase desde el firmware (`atan2(Q, I)`) más un array de antenas: diferencia de fase `Δψ = (2π·s/λ)·sin(θ)` con separación de antenas `s`;
  2. geometría multi-dispositivo como `esp-radar` de Espressif esp-csi.
- **Ubicación en la zona de Fresnel** — mantener el cuerpo cerca de la primera zona de Fresnel TX–RX para máxima sensibilidad de signos vitales; la ubicación y orientación del cuerpo importan.

## 7. Cómo evalúa hoy el aplicativo la posición del cuerpo

**Técnica efectivamente implementada** (`motion_analyzer.py`, exacta):

1. Por ventana, promediar el RSSI por paquete → $\bar{R}$ [dBm].
2. Si está calibrado (`CSI_RSSI_REF_DBM`, `CSI_REF_DISTANCE_M`, `CSI_PATH_LOSS_N` definidos; defaults −52 dBm @ 1.0 m, `n_pl = 3.0`), invertir el modelo log-distance:

```math
\hat{d} = d_0 \cdot 10^{(R_0 - \bar{R}) / (10\, n_{pl})}
```

   → el valor **"link dist ~…"** que muestra la fila Body del GUI y el web viewer.
3. Si no está calibrado (`CSI_RSSI_REF_DBM=none`), el ranging se deshabilita y se muestra como `—` — el sistema se niega a inventar metros.

**Rango vs posición.** Ese valor es un *rango* al enlace de radio, no una
posición: con un solo enlace no hay geometría para triangular, y con una
única antena omnidireccional no hay ángulo (§6). El GUI nunca muestra x/y.

**Por qué no es exacto — cuantificado.** El término de shadowing $X_\sigma$
del modelo es de ±5–10 dB en una sala típica. Con $n_{pl} = 3$, cada 5 dB de
error de fading multiplica la distancia estimada por $10^{5/30} \approx 1.47$:
±10 dB de fading hace oscilar la distancia mostrada aproximadamente ×0.7…×2.1
alrededor del valor real, y el sistema no puede distinguir si una desviación
dada es shadowing o desplazamiento real. El bloqueo corporal, la orientación
de la antena y la varianza de RSSI del chipset agregan sesgo adicional.

**Explícitamente pendiente (trabajo futuro — sin resolver):**

- calibración automatizada a dos puntos por sala para fijar $R_0$ / $n_{pl}$ por instalación (§6);
- fusión multi-nodo para trilateración gruesa (exige ≥ 3 enlaces calibrados);
- ranging por fase/ToF (exige publicar la fase — el camino futuro documentado del firmware, §3).

Hasta que alguno de esos aterrice, "link dist" debe leerse como una brújula de
orden de magnitud, nunca como una posición medida.

## 8. Enlaces multi-dispositivo (multi-ESP32) — diseño implementado

**Por qué ayudan varios enlaces.** Un único enlace TX–RX está rehén de la
geometría: el modelo de zonas de Fresnel (§3) predice nulos profundos de
amplitud donde el cuerpo se ubica en los bordes de zona, y cualquier enlace
pierde la modulación de signos vitales cuando el sujeto gira. `N` enlaces
alrededor de la sala dan diversidad espacial: el sujeto no puede estar en el
nulo de todos los enlaces a la vez. Es el argumento estándar de diversidad de
enlaces de la literatura de WiFi sensing.

**De dónde salen los datos por enlace.** Cada ESP32 publica a su tópico
propio por dispositivo

```
esp32/<id>/csi/raw        <id> = últimos 3 bytes de la MAC STA (derivada de eFuse, estable)
```

así que los enlaces nunca colisionan en el broker. El backend se suscribe al
wildcard `esp32/+/csi/raw` **más** el tópico plano legacy `esp32/csi/raw` (el
firmware viejo sigue funcionando sin reflashear). Cada paquete se etiqueta con
su link id tomado del tópico MQTT; cada enlace posee un `VitalsProcessor` +
`MotionAnalyzer` aislados, de modo que las guardias endurecidas de entrada
(descarte de no-finitos, timestamps monotónicos, reset por ancho) aplican
**por enlace** — dos dispositivos con dominios de reloj superpuestos jamás
corrompen las ventanas del otro (la razón por la que una ventana compartida no
es opción).

**Fusión (por banda, máximo SNR).** Para cada banda fisiológica
independientemente, gana la estimación el enlace cuyo SNR en banda
($\mathrm{SNR}_k$, §4) sea el más alto:

```math
\hat{f}_{heart} = \hat{f}\left( \arg\max_{\ell \in L} \mathrm{SNR}_{heart}(\ell) \right), \qquad
\hat{f}_{resp} = \hat{f}\left( \arg\max_{\ell \in L} \mathrm{SNR}_{resp}(\ell) \right)
```

Por lo tanto corazón y respiración pueden venir de enlaces distintos — cada
banda sigue al enlace que mejor la observa. El enlace ganador de corazón pasa
a ser el *primary*: los paneles físicos del GUI y el readout de RSSI/distancia
lo siguen. Si el mejor enlace igual queda debajo de la compuerta de 6 dB, la
tasa fusionada es `None` — un "ningún enlace pasó la compuerta" honesto, jamás
una estimación mezclada.

**Presencia agregada (conservadora).** Cualquier enlace en `Moving` →
`Moving`; si no, cualquier enlace `Still` → `Still`; si no, `Absent`. Una
persona visible para cualquier enlace cuenta como presente; el RMS de
movimiento agregado es el máximo entre enlaces.

**Notas prácticas.** Flashear cada nodo una vez con el firmware
por-dispositivo; el id se deriva de su MAC, así que no hace falta
configuración por nodo. Dry-run sin hardware: correr dos simuladores con
`--device-id a1b2c3` y `--device-id d4e5f6` (DEPLOYMENT.md §10). La barra de
estado del GUI y la línea de meta de la página web muestran la cantidad de
enlaces activos; `--topic` sigue fijando un único tópico/patrón explícito
cuando hace falta.

## 9. Inventario de funciones del GUI

| Panel | Cantidad | Fórmula mostrada (mathtext) |
| --- | --- | --- |
| Fila Body | estado de presencia, `M_rms`, `sigma_window`, `R_bar`, `d_hat` | resumen de texto |
| Gráfica de amplitud CSI media | `a_bar(t)` sobre la ventana | `$\bar{a}(t)=\frac{1}{K}\sum_{k}\lvert H_k(t)\rvert$` |
| Gráfica de respiración | `x(t)` filtrada Butterworth, 0.1–0.5 Hz | `$x(t)$`, banda |
| Gráfica de corazón | `x(t)` filtrada, 0.8–2.0 Hz | `$x(t)$`, banda |
| Heatmap de subportadoras | $20\,\log_{10}(\lvert H_k\rvert + \epsilon)$, subportadora $k$ vs $t$ | `$\lvert H_k\rvert=\sqrt{I_k^2+Q_k^2}$` |
| Espectrograma | `scipy.signal.spectrogram` de `a_bar(t)` con bandas sombreadas | `$X(\tau,f)=\sum_n x[n]\,w[n-\tau]\,e^{-j2\pi fn/N}$` |
| Traza de energía de movimiento | historia de 10 min de `M_rms` con línea de umbral | `$M_\mathrm{rms}=\sqrt{\langle b^2(t)\rangle}$`, banda 0.5–3.0 Hz |

## 10. Librerías, frameworks y tecnologías

- **Firmware**: ESP-IDF v5.x C++ (API CSI de esp_wifi, esp_timer, esp_event, esp_netif, nvs_flash, esp-mqtt), colas/tareas FreeRTOS, ping lwIP.
- **Transporte**: broker Mosquitto MQTT (Docker + docker-compose), paho-mqtt (Python).
- **Procesamiento**: Python 3, numpy (`ndarray`, `rfft`, `hanning`, `log10`, `std`), scipy.signal (`detrend`, `butter`/`sosfiltfilt`, `spectrogram`), dataclasses, ventanas deslizantes con `collections.deque`.
- **Web viewer**: aiohttp (servidor HTTP + WebSocket, Apache 2.0), consumidor paho-mqtt.
- **Multi-enlace**: `backend/link_manager.py` (suscripción wildcard, pipelines por enlace, fusión por banda con máximo SNR).
- **GUI**: PyQt5 (`QMainWindow`, `QTimer`, labels/barra de estado), matplotlib Qt5Agg (`Figure`/`FigureCanvasQTAgg`, gridspec, `imshow`, títulos de fórmulas con mathtext).
- **Config/testing**: dataclass congelada `Config` con overrides por `os.getenv`; tests unitarios pytest; simulador sintético basado en numpy (escenarios resting/moving/absent) vía paho-mqtt.

## 11. Referencias (verificadas)

1. Espressif ESP-CSI — aplicaciones CSI (posicionamiento indoor, detección humana): <https://github.com/espressif/esp-csi>
2. ESP32-CSI-Tool — herramienta de captura CSI (activa/pasiva): <https://github.com/StevenMHernandez/ESP32-CSI-Tool>
3. Zhang et al., "Human Respiration Detection with Commodity WiFi Devices: Do User Location and Body Orientation Matter?", UbiComp 2016 (modelo de Fresnel; ubicación/orientación).
4. Zeng et al., "FullBreathe: Full Human Respiration Detection Exploiting Complementarity of CSI Phase and Amplitude of WiFi Signals", Proc. ACM IMWUT, 2018, DOI 10.1145/3264958.
5. "WiFi-based Real-time Breathing and Heart Rate Monitoring during Sleep", arXiv:1908.05108.
6. "A survey on vital signs monitoring based on Wi-Fi CSI data" (PMC9375645).
7. Rappaport, "Wireless Communications: Principles and Practice" — path loss log-distance; ver también Wikipedia "Log-distance path loss model" (`PL(d) = PL(d0) + 10·n·log10(d/d0) + X_sigma`, indoor `n ≈ 2.7–4.3`).
8. API WiFi CSI del ESP-IDF: <https://docs.espressif.com/projects/esp-idf/>
9. Mosquitto: <https://mosquitto.org/> ; paho-mqtt: <https://pypi.org/project/paho-mqtt/>
10. numpy <https://numpy.org/> ; scipy <https://scipy.org/> ; matplotlib <https://matplotlib.org/> ; PyQt5 <https://www.riverbankcomputing.com/software/pyqt/>
