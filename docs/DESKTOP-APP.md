# El aplicativo de escritorio — sistema y flujo de datos

> **Qué es este documento.** La documentación de sistema y flujo de datos del
> aplicativo de escritorio: el proceso Python que consume los paquetes CSI por
> MQTT, los procesa por enlace, los fusiona y los pinta en una ventana PyQt5 en
> tiempo real. Cada afirmación está verificada contra el código fuente (archivo
> y función citados). Compañeros: [HOW-IT-WORKS.md](HOW-IT-WORKS.md) (cómo leer
> cada panel), [DATA-PIPELINE.md](DATA-PIPELINE.md) (las matemáticas exactas de
> cada etapa) y [FIRMWARE-ESP32.md](FIRMWARE-ESP32.md) (el otro extremo del
> sistema: el software que corre en la ESP32). Es una herramienta de
> investigación; no es un dispositivo médico.

---

## 1. Qué es el aplicativo y su función en el sistema

El aplicativo es **un solo proceso Python** (`backend/main.py`, función
`main()`): se conecta al broker MQTT, se suscribe a los tópicos CSI de todas
las placas ESP32 de la red, mantiene **una cadena de procesamiento aislada por
placa** (ventana deslizante + FFT + clasificador de presencia), **fusiona** los
resultados de todas las placas y muestra el resultado en una ventana de
escritorio PyQt5 con 6 paneles de Matplotlib en tiempo real. Es el punto donde
los números crudos del firmware se convierten en lo que una persona ve: BPM,
respiraciones por minuto, estado de presencia, y las gráficas físicas del canal.

---

## 2. Arquitectura de hilos y componentes

El proceso tiene **dos hilos permanentes** y una frontera explícita entre
ambos:

- **Hilo de red (paho-mqtt).** `CsiSubscriber.start()`
  (`mqtt_subscriber.py`) llama a `connect_async()` + `loop_start()`: paho
  crea un hilo que es el único dueño del socket. Ese hilo ejecuta los
  callbacks de paho: `_on_message` parsea cada payload y lo encola con
  `put_nowait`. Este hilo nunca toca la GUI ni hace cálculo pesado.
- **Frontera: `queue.Queue(1024)`.** `CsiSubscriber.__init__` crea
  `queue.Queue(maxsize=1024)`. ¿Por qué una cola? Porque **desacopla el ritmo
  de la red del ritmo del consumidor**: el hilo de paho tiene que volver al
  socket de inmediato (keepalive, reconexión, nuevos mensajes) y no puede
  esperar a que la GUI termine de pintar; la `Queue` es thread-safe por
  construcción, así que el traspaso de paquetes entre hilos no necesita
  cerrojos propios. Como es acotada (1024), si el consumidor se atrasa la
  política es contar y descartar (`_on_message`: `queue.Full → _dropped += 1`)
  en vez de bloquear la red o crecer sin límite en memoria.
- **Hilo de la GUI (Qt).** `main()` crea `QApplication` y entra a
  `app.exec_()`, el event loop de Qt. Un `QTimer` construido en
  `VitalsWindow.__init__` dispara cada
  `refresh_ms = int(1000.0 / gui_refresh_hz)` = **200 ms (5 Hz)** y ejecuta
  `_on_tick`
  (`gui.py`), que hace tres cosas: (1) `links.drain_and_feed()` — mueve hasta
  256 paquetes de la cola hacia los pipelines; (2) la **tasa de paquetes**
  sobre una ventana móvil de **2 s** (`_pkt_window_start`/`_pkt_window_count`);
  (3) la **barra de estado**. Además, cada `cfg.estimate_every_s` = **1 s**,
  el mismo tick ejecuta la pasada de estimación, fusión y **todo el render**
  (`_apply_estimate`/`_apply_motion`).

| Componente | Archivo | Función en una línea |
|---|---|---|
| `CsiSubscriber` | `mqtt_subscriber.py` | Se suscribe por MQTT y bufferiza paquetes parseados en una cola acotada |
| `MultiLinkSubscriber` | `link_manager.py` | Subclase que etiqueta cada paquete con su link: `(link_id, packet)` (`_on_message`) |
| `LinkManager` | `link_manager.py` | Un pipeline DSP por dispositivo + fusión por banda con locks en todo accessor (`estimate`, `motion_estimate`, `ingest`, ...) |
| `VitalsProcessor` | `vitals_processor.py` | Ventana deslizante $N \times K$ + mejor subportadora por banda + tasas (matemática en DATA-PIPELINE §4) |
| `MotionAnalyzer` | `motion_analyzer.py` | Presencia (Absent/Still/Moving) desde la amplitud media + RSSI → distancia opcional |
| `VitalsWindow` | `gui.py` | Ventana PyQt5: 6 paneles Matplotlib, fila Body, barra de estado, timers |
| `web_viewer` | `web_viewer.py` | Consumidor hermano sin Qt: servidor aiohttp + WebSocket que difunde snapshots (~1 Hz) |

---

## 3. El flujo de datos dentro del aplicativo, paso a paso

**Paso 1 — Broker → suscripción.** El firmware publica en
`esp32/<id>/csi/raw` (una placa = un tópico; ver
[FIRMWARE-ESP32.md](FIRMWARE-ESP32.md)). El cliente se suscribe, en
`CsiSubscriber._on_connect`, a los patrones configurados: por defecto
`esp32/+/csi/raw` (wildcard por dispositivo) **más** `esp32/csi/raw` (el tópico
plano heredado, para firmware viejo sin reflashear) — `DEFAULT_TOPIC_PATTERNS`
en `link_manager.py`; la derivación desde `MQTT_TOPIC` está en
`config._topic_patterns_from_env` y el flag `--topic` de `main()` tiene la
última palabra. La suscripción se hace con `qos=0`.

**Paso 2 — Parseo con guardias estructurales.** El hilo de red recibe el
mensaje y llama a `parse_csi_payload` (`csi_packets.py`): un CSV ASCII
`t_us,rssi,n,seq,a0..a(n-1)` que se convierte en un `CsiPacket` (con `amps`
float64). Se descarta el paquete (devuelve `None`) si tiene menos de 4 campos,
si `n <= 0` o si el payload trae menos amplitudes que las declaradas
(`len(parts) < 4 + n`), o si algún campo no es un entero ASCII válido
(`ValueError`/`UnicodeDecodeError`). *Por qué: un payload corrupto jamás debe
llegar al DSP — el paquete malformado se loguea en debug y se pierde, sin
excepciones que maten el hilo de red.*

**Paso 3 — Etiquetado por link.** `MultiLinkSubscriber._on_message`
(`link_manager.py`) no encola el paquete pelado: encola la tupla
`(link_id, packet)`, donde `link_id_from_topic` extrae el id del tópico
(`esp32/abc123/csi/raw → "abc123"`; el tópico plano heredado → `"default"`;
cualquier layout desconocido → el tópico entero como id, para que dos
layouts raros nunca colisionen). *Por qué: la placa que publicó es la
identidad del enlace físico, y todo lo que sigue se organiza por ella.*

**Paso 4 — Ventanas aisladas por link.** En el tick de 5 Hz, `drain_and_feed`
mueve las tuplas a `LinkManager.ingest`, que busca (o crea, con LRU si el
registro de `MAX_LINKS = 16` está lleno) el par
`(VitalsProcessor, MotionAnalyzer)` de ese link y hace `push` en ambos con
`t_s = pkt.t_us / 1e6`. Los `push` (`vitals_processor.py` / `motion_analyzer.py`)
aplican las **guardias de integridad**: amplitudes con NaN/inf → descartada
(una sola fila corrupta envenenaría media, FFT, heatmap y espectrograma);
timestamp no finito o que retrocede/repite (`t_s <= último`) → descartado (la
FFT asume una grilla temporal uniforme); cambio de cantidad de subportadoras
`n` a mitad de ventana → la ventana se vacía y arranca de nuevo (físicamente
es otro enlace; una matriz de filas de anchos distintos no se puede apilar).
La ventana es un `deque(maxlen=N)` con
$N = \mathrm{round}(f_s \cdot T_w) = 150$ filas (a $f_s \approx 10\ \mathrm{Hz}$
y $T_w = 15\ \mathrm{s}$) por $K$ columnas. *Por qué aislado por link: cada
guardia (timestamps, ancho, calidad) es válido **por enlace** — mezclar dos
placas en una misma ventana haría pelear a sus guardias entre sí y mezclaría
dos canales de radio distintos.*

**Paso 5 — Estimación por link (1 Hz).** Cada pipeline puede responder dos
cosas cuando su ventana está llena: `VitalsProcessor.estimate()` (BPM,
respiraciones/min, subportadora ganadora por banda, ondas filtradas, SNR) y
`MotionAnalyzer.estimate()` (estado de presencia, RMS de movimiento, RSSI
medio, distancia estimada). Las fórmulas exactas no se repiten acá: viven en
[DATA-PIPELINE.md](DATA-PIPELINE.md) §4.

**Paso 6 — Fusión multi-link.** `LinkManager.estimate()` / `motion_estimate()`
(`link_manager.py`) combinan solo los links **vivos** (ingest en los últimos
`LINK_STALE_S = 20` s; `_prune_stale` elimina los mudos antes de cada pasada):

```math
\ell^*(\text{banda}) = \mathrm{argmax}\,\{\mathrm{SNR}_{\text{banda}}(\ell) : \ell \in \text{links vivos}\}
```

- **Por banda**: el link con mayor SNR en la banda cardíaca gana el corazón, y
  (posiblemente otro) el de mayor SNR respiratoria gana la respiración — el
  pecho es el mismo, pero cada placa lo "ve" mejor en una banda distinta.
  Si el SNR del ganador no supera la compuerta (`min_snr_db`), la tasa
  fusionada es `None`: un "nadie pasó la compuerta" honesto, nunca una mezcla
  silenciosa.
- **Primary**: el ganador cardíaco queda registrado (`_primary`); los paneles
  físicos y el ranging siguen **ese** enlace (`current_matrix`,
  `current_window`, `fill`, `capacity` leen del primary).
- **Presencia conservadora**: cualquier link en `Moving` → `Moving`; si no,
  cualquier link en `Still` → `Still`; si no, `Absent` (una persona visible
  por cualquier placa cuenta como presente). El RMS de movimiento es el
  máximo entre links; σ, RSSI y distancia son los del primary.

**Paso 7 — Render.** La GUI (`gui.py`) no guarda copias de los datos: lee
directo del `LinkManager` con locks (`current_window` para la traza cruda,
`current_matrix` para heatmap y espectrograma, `estimate`/`motion_estimate`
para números y ondas) y actualiza los artistas existentes con `set_data` +
`relim` + `autoscale_view` — con el eje x pineado en
$[0, T_w]$, el reescalado es **solo en y** (`scalex=False`), mucho más barato
por repintado. Las imágenes van en **dB**
(heatmap: `20*log10(...+1e-9)`; espectrograma: `10*log10(...+1e-12)`) para
comprimir el rango dinámico. Todos los `canvas.draw_idle()` de un mismo tick
**coalescen** en un único repintado del canvas (comentario "Repaint throttle"
en `_on_tick`).

---

## 4. Ciclo de vida del proceso

- **Arranque** (`main()` en `main.py`): `Config()` lee entorno → overrides de
  CLI (`--host/--port/--fs/--window/--topic`) → `LinkManager(cfg)` construye
  el suscriptor multi-link → `links.sub.start()` conecta (la suscripción real
  ocurre en el callback `_on_connect`) → recién entonces se crea
  `VitalsWindow` y arranca `app.exec_()`. Como el suscriptor arranca antes que
  la ventana, los primeros paquetes ya se bufferizan en la cola mientras la
  GUI construye sus paneles.
- **Fase de llenado (~15 s)**: con la ventana a medio llenar,
  `estimate()` devuelve `None` y la etiqueta central muestra
  `"filling window... N%"` (`_apply_estimate`). La traza cruda **sí se pinta
  desde el primer tick** de estimación: `_redraw_raw` no depende del estimate,
  y su `draw_idle` es incondicional justamente para que el canvas no quede
  congelado durante el llenado.
- **Estado estable**: ventana llena (150/150 en la barra de estado), tasa
  cardíaca y respiratoria con su `sc#`/SNR, fila Body y los 6 paneles
  refrescándose a 1 Hz.
- **Pérdida de un link**: el staleness solo se refresca con **ingesta**
  (`_pipelines(touch=True)`; los lectores usan `touch=False`), así que un link
  que el GUI sondea pero que no recibe paquetes expira igual. A los 20 s sin
  datos, `_prune_stale` lo elimina antes de la siguiente fusión; si era el
  primary, `_primary` vuelve a `None` y los paneles caen al primer link vivo.
  Un link nuevo siempre es admitido: si el registro está lleno, se desaloja al
  menos-recientemente-visto (LRU, `_pipelines`).
- **Apagado**: cerrar la ventana dispara `closeEvent` (`gui.py`), que llama a
  `links.sub.stop()` — `disconnect()` + `loop_stop()` de paho — y acepta el
  evento; el event loop de Qt termina y el proceso se apaga.

---

## 5. Qué ve el usuario y de dónde sale

Los paneles son los mismos que describe la guía de lectura de
[HOW-IT-WORKS.md](HOW-IT-WORKS.md) §5 (y la correspondencia matemática exacta
está en DATA-PIPELINE §7); esta es la **vista de sistema**: qué componente
alimenta cada cosa que se ve.

| Ves | Es | Calculado en |
|---|---|---|
| Trazas cruda / respiración / corazón | $\bar{a}(t)$ y las ondas filtradas del primary | `VitalsProcessor.current_window()` / `estimate()` (gui `_redraw_raw`/`_apply_estimate`) |
| Números grandes BPM y /min | tasas de las bandas, solo si pasan la compuerta de SNR | `VitalsProcessor.estimate()` vía `LinkManager.estimate()` |
| Barra de meta (sc#, SNR, NxK) | subportadora ganadora por banda + tamaño de ventana | campos de `VitalsEstimate` (`_apply_estimate`) |
| Fila "Body" | presencia + RMS de movimiento + σ + RSSI + distancia | `MotionAnalyzer.estimate()` vía `LinkManager.motion_estimate()` (`_update_body_label`) |
| Heatmap de subportadoras | amplitud $\lvert H_k \rvert$ del primary, en dB | `VitalsProcessor.current_matrix()` (`_redraw_heatmap`) |
| Espectrograma | contenido de frecuencia de $\bar{a}(t)$, en dB, con bandas sombreadas | `scipy.spectrogram` en `_redraw_spectrogram` |
| Energía de movimiento | historia de 600 s del RMS fusionado + umbral | `motion_estimate().motion_rms` + `_motion_history` (`_redraw_motion_trace`) |
| Franja de medidas | unidades de todas las cantidades, siempre visible | texto estático (`gui.py`) |
| Barra de estado | MQTT conectado?, pkt/s (ventana 2 s), llenado N/N, y con >1 link: `links a, b (primary a)` | `is_connected`, `fill`/`capacity`, `n_links`/`primary_link` en `_on_tick` |

---

## 6. El viewer web, un consumidor hermano

`web_viewer.py` es **otro proceso** con el mismo esqueleto y cero Qt: su
`main()` construye un `LinkManager` idéntico (misma suscripción MQTT, mismos
pipelines por link, mismos locks) y lo alimenta desde un hilo de feed propio
(`_feed_loop`: `drain_and_feed(256)` + un snapshot por `estimate_every_s`).
Encima, un servidor **aiohttp** (`build_app`) sirve la página estática
`web_static/index.html` y un WebSocket `/ws` cuyo handler (`ws_handler`)
difunde el último snapshot a cada navegador apenas cambia (chequeo cada 0,5 s,
`ViewerState.latest()`). Cada snapshot (`ViewerState._snapshot`) lleva
BPM/respiración, presencia, RSSI/distancia, las últimas 160 muestras de las
ondas y una historia de 600 puntos (~10 min) para la tendencia.

*Por qué existe*: para mirar el sistema desde un **teléfono o tablet en la
LAN sin instalar nada** — el navegador es el cliente — y para funcionar en
entornos sin escritorio (WSL, servidores), donde PyQt5 no tiene pantalla.

---

## 7. Decisiones de diseño y porqués

| Decisión | Por qué |
|---|---|
| paho-mqtt 1.x (`>=1.6,<2.0` en `backend/requirements.txt`) | La API 2.x de paho rompió la construcción de `Client()`; fijar 1.x mantiene estable el punto de integración (DATA-PIPELINE §0, etapa 3) |
| Locks en todo accessor público de `LinkManager` | `threading.Lock` protege `_links/_last_seen/_primary` "across ingest and consumer threads": el que ingesta (timer Qt o hilo de feed web) y el que lee (render, handlers del WebSocket) pueden ser hilos distintos según el proceso anfitrión; con el lock, cualquier hilo puede llamar sin coordinación extra (comentario de `LinkManager.__init__`) |
| QoS 0 en la suscripción (`_on_connect`) | A $\approx 10$ paquetes/s, un paquete perdido es un gap de muestreo, no pérdida de información: no compensa el costo de retransmisión/ack de QoS mayor (DATA-PIPELINE §3) |
| Cadencias 5 Hz / 1 Hz | El tick de 5 Hz (`gui_refresh_hz`) mantiene la cola vacía y la barra de estado fresca; el render completo (6 ejes con 2 `imshow`) es caro, así que toda la pasada de estimación+render corre a 1 Hz (`estimate_every_s`) — suficiente para una estimación que por construcción ya integra 15 s de historia (DATA-PIPELINE §5) |
| Un pipeline por link, nunca uno global | Las guardias de integridad (timestamps, ancho, SNR) solo tienen sentido por enlace físico; compartir ventana entre placas mezclaría canales distintos y haría pelear a las guardias (docstring de `link_manager.py`) |
| Cola acotada + contador de descartes | Backpressure explícita: la red nunca se bloquea por un consumidor lento, y el usuario puede ver cuántos paquetes se perdieron (`dropped()`) |

---

## 8. Configuración relevante

Todas las variables se leen una sola vez en `Config` (`backend/config.py`);
las cadencias de GUI (5 Hz y 1 s) y las bandas fisiológicas son constantes de
código, no de entorno. Los flags CLI `--host/--port/--fs/--window/--topic`
(`main.py`, función `main()`) pisan los valores de entorno.

| Variable de entorno | Qué ajusta | Default |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | broker al que se conecta el backend | `localhost` / `1883` |
| `MQTT_TOPIC` | lista de suscripción: si no está, está vacía o es el legacy `esp32/csi/raw` → wildcard + legacy; si está con otro valor → ese único tópico/patrón (`_topic_patterns_from_env`) | wildcard + legacy |
| `CSI_FS` | frecuencia de muestreo esperada del DSP (`sample_rate_hz`) | `10.0` |
| `CSI_WINDOW_S` | largo de la ventana de estimación en segundos (`window_seconds`) | `15.0` |
| `CSI_MIN_SNR_DB` | compuerta de calidad para reportar tasas (`min_snr_db`) | `6.0` |
| `CSI_ABSENT_STD` | umbral de σ para clasificar sala vacía (`absent_std_threshold`) | `0.15` |
| `CSI_MOVING_RMS` | umbral de RMS en banda 0,5–3 Hz para `Moving` (`moving_rms_threshold`) | `1.5` |
| `CSI_RSSI_REF_DBM` | RSSI de referencia del modelo de distancia; vacío o `none` apaga el ranging (`rssi_ref_dbm`, `_env_float_opt`) | `-52.0` |
| `CSI_REF_DISTANCE_M` | distancia de referencia del modelo; vacío o `none` apaga el ranging | `1.0` |
| `CSI_PATH_LOSS_N` | exponente de path-loss del modelo log-distancia (`path_loss_exponent`) | `3.0` |

---

## 9. Diagrama del proceso

```
        placas ESP32 (~10 pkt/s c/u)
          │ publish esp32/<id>/csi/raw
          ▼
   ┌───────────────┐        ┌──────────────────────────────────────────────┐
   │  Broker MQTT  │        │  Proceso aplicativo  (backend/main.py)       │
   │  (Mosquitto)  │        │                                              │
   └───────────────┘        │  HILO DE RED (paho loop_start)               │
          │ subscribe       │    _on_message → parse_csi_payload           │
          │ qos=0           │      │ put_nowait  (llena → _dropped += 1)   │
          └────────────────►│      ▼                                       │
                            │  queue.Queue(1024)  ← frontera entre hilos   │
                            │      │ drain_tagged(256), cada 200 ms (5 Hz) │
                            │      ▼  QTimer._on_tick (hilo Qt)            │
                            │  LinkManager.drain_and_feed                  │
                            │   ├─ link "a" → VitalsProcessor+MotionAn.    │
                            │   └─ link "b" → VitalsProcessor+MotionAn.    │
                            │   (locks en cada accessor público)           │
                            │      │ cada 1 s (estimate_every_s)           │
                            │      ▼                                       │
                            │  estimate() + motion_estimate() → fusión     │
                            │  (SNR máx por banda, primary = ganador       │
                            │   cardíaco, presencia conservadora,          │
                            │   expiración de links mudos a los 20 s)      │
                            │      ▼                                       │
                            │  VitalsWindow: set_data + draw_idle          │
                            │  (coalescido) + fila Body + barra de estado  │
                            └──────────────────────────────────────────────┘
                                             │  mismo esquema, otro proceso
                                             ▼
                            ┌──────────────────────────────────────────────┐
                            │  web_viewer.py (sin Qt)                      │
                            │  hilo feed (100 ms) → mismo LinkManager      │
                            │  aiohttp :8080 → página + WebSocket (~1 Hz)  │
                            └──────────────────────────────────────────────┘
```
