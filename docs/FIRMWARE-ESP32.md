# El firmware de la ESP32 — sistema y flujo de datos

> **Qué es este documento.** La documentación de sistema y flujo de datos del
> software que se flashea en la ESP32-S3: qué hace desde que arranca hasta que
> publica cada medición por MQTT, cómo está organizado por dentro (tareas,
> colas, callbacks) y por qué cada pieza es así. Cada afirmación está
> verificada contra el código fuente (archivo y función citados; el firmware
> completo vive en `src/esp32/main/main.cpp`, ~430 líneas). Compañeros:
> [HOW-IT-WORKS.md](HOW-IT-WORKS.md) (la guía simple de la física),
> [DATA-PIPELINE.md](DATA-PIPELINE.md) (las 6 etapas del sistema completo) y
> [DESKTOP-APP.md](DESKTOP-APP.md) (el otro extremo: el aplicativo que
> consume estas mediciones). Es una herramienta de investigación; no es un
> dispositivo médico.

---

## 1. Qué es este firmware y su función en el sistema

Es el **productor de datos** del sistema: un programa C++ sobre **ESP-IDF
v5.x** que convierte una ESP32-S3 en un sensor de canal WiFi. Su función
entera cabe en una frase: *por cada paquete WiFi que recibe la placa, medir
cómo llegó cada subportadora de la señal (la CSI), reducirla a un vector de
amplitudes y publicarla como una fila CSV por MQTT*. No estima nada: ni
respiración ni presencia — esas cuentas las hace el
[aplicativo](DESKTOP-APP.md); el firmware solo mide y publica, a ~10
mediciones por segundo, para siempre.

En el mapa del sistema ocupa las etapas 0–2 de [DATA-PIPELINE.md](DATA-PIPELINE.md):
física del canal → empaquetado → transporte.

```
        ┌────────────── ESP32-S3 (este firmware) ──────────────┐
router ─┤ radio + driver WiFi → CSI (I/Q por subportadora)      │
        │        → amplitudes a_k = √(I_k²+Q_k²)                │
        │        → fila CSV → esp-mqtt                          │
        └──────────────────────┬────────────────────────────────┘
                               ▼ esp32/<id>/csi/raw
                          Mosquitto (broker)
                               ▼
                    aplicativo de escritorio / viewer web
```

---

## 2. Secuencia de arranque, paso a paso

Todo ocurre en `app_main` (`main.cpp`), en este orden exacto:

1. **Cola de muestras.** `xQueueCreate(SAMPLE_QUEUE_DEPTH=32, …)` — la cola
   FreeRTOS que desacoplará el callback de WiFi del publicador (ver §3).
   Se crea primero para que ningún evento llegue sin destino.
2. **NVS.** `nvs_flash_init()`; si la partición está llena o con otra
   versión (`ESP_ERR_NVS_NO_FREE_PAGES` /
   `ESP_ERR_NVS_NEW_VERSION_FOUND`), se borra y reintenta. La NVS es la
   memoria no volátil donde viven las credenciales provisionadas.
3. **Credenciales: NVS primero, `config.h` de respaldo.** Se copian los
   `#define` de `config.h` (`WIFI_SSID`, `WIFI_PASS`, `MQTT_BROKER_URI`)
   y después se intenta leer el namespace `"wifi_creds"` de la NVS; si
   hay SSID guardado, se usan los valores provisionados y
   `s_using_nvs = true`. *Por qué así: un binario recién flasheado con
   NVS vacía funciona out-of-the-box con la red compilada, y esa misma
   imagen ya queda lista para ser re-provisionada por serial (§7) sin
   recompilar — el binario es agnóstico de la red.*
4. **Red + WiFi STA.** `esp_netif_init` → `esp_event_loop_create_default` →
   `esp_netif_create_default_wifi_sta` → `esp_wifi_init` con la config
   default → registro de handlers (`wifi_event_handler`): al arrancar la
   STA (`WIFI_EVENT_STA_START`) conecta; si se desconecta, reconecta solo.
5. **CSI registrada.** `wifi_csi_config_t` con cada flag (abajo) y la
   terna `esp_wifi_set_csi(true)` → `esp_wifi_set_csi_config(&cfg)` →
   `esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL)`. Desde este momento,
   **cada paquete recibido** dispara el callback con su medición de canal.
6. **Tareas.** `xTaskCreate` para `publisher_task` (stack 4096, prioridad
   5), `stats_task` (2048, prioridad 4) y `provisioning_task` (4096,
   prioridad 3 — la más baja, para que jamás compita con el muestreo).

**Los flags de la CSI** (`wifi_csi_config_t`, `main.cpp: app_main`):

| Flag | Valor | Qué hace | Por qué así |
|---|---|---|---|
| `lltf_en` | `true` | estima el canal con el campo de entrenamiento **legacy** (L-LTF) | mantiene compatibilidad con la medición de subportadoras legacy |
| `htltf_en` | `true` | estima el canal con el campo **high-throughput** (HT-LTF, 802.11n) | los frames modernos traen su propio entrenamiento: es la medición completa |
| `stbc_htltf2_en` | `true` | acepta el **segundo** HT-LTF de los frames STBC | sin esto, los frames STBC se medirían a medias |
| `ltf_merge_en` | `true` | **fusiona** las estimaciones de los campos de entrenamiento | una sola estimación limpia por subportadora en vez de varias parciales |
| `channel_filter_en` | `CSI_CHANNEL_FILTER` (`true`) | suavizado de **subportadoras adyacentes** del propio IDF | menos ruido por tono → SNR más alto (el costo: menos resolución fina por tono — decisión documentada) |
| `manu_scale` | `false` | escala automática de la CSI del driver | sin factor manual: los valores que llegan son los que el chip estima |

---

## 3. Arquitectura en runtime: tareas, colas y callbacks

El firmware nunca "procesa" nada en el callback: cada pieza tiene un solo
trabajo.

- **`wifi_csi_rx_cb` — corre en la WiFi task del sistema.** Por cada paquete
  recibido: toma el buffer I/Q del driver, calcula las amplitudes (§5),
  arma un `csi_sample_t` y **solo encola**: `xQueueSend(…, 0)` con timeout
  cero. *Por qué timeout cero: este callback corre en la tarea del stack de
  WiFi; si bloqueara (ni que sea milisegundos), podría atrasar la
  recepción misma que está midiendo. Si la cola está llena, incrementa
  `s_qfull` y sigue: una muestra perdida es ruido de muestreo, no una
  catástrofe.*
- **`publisher_task` (prioridad 5).** Bloqueado en
  `xQueueReceive(…, portMAX_DELAY)` hasta que llega una muestra. Formatea
  la fila CSV en su buffer (`malloc` de `64 + CSI_MAX_SUBCARRIERS × 4`
  bytes, `main.cpp: publisher_task`) y la publica con
  `esp_mqtt_client_publish(topic, buf, len, qos=0, retain=0)`. Contadores
  `s_published` / `s_publish_failed` para observabilidad.
- **`stats_task` (prioridad 4).** Cada 10 s loguea una línea:
  `captured / qfull / published / failed` — el pulso del sensor visible
  en el monitor serial (`ESP_LOGI`, `main.cpp: stats_task`).
- **`provisioning_task` (prioridad 3, la más baja).** Lee UART0 (el USB
  serial) línea por línea buscando comandos `PROVISION:*` (§7).

**El tópico por dispositivo** (`main.cpp: publisher_task`): el publicador
arma `esp32/<id>/csi/raw` donde `<id>` son los **últimos 3 bytes de la MAC
STA** (`esp_read_mac`, derivada de eFuse: estable entre reflasheos y
reinicios). *Por qué: dos o más placas publicando al mismo tópico se
pisarían entre sí; con id por dispositivo, cada placa es un "enlace" con su
propio pipeline en el aplicativo (ver
[DESKTOP-APP.md](DESKTOP-APP.md) §3). Si `esp_read_mac` falla, se usa id
cero y se loguea el error: nunca un tópico basura.*

---

## 4. La sesión de ping: cómo se fabrica el muestreo a ~10 Hz

La CSI solo se mide **cuando llega un paquete**: sin tráfico, no hay fotos
del canal. El firmware genera su propio tráfico con una sesión **lwIP ping
endless al gateway** (`main.cpp: start_traffic_ping`): cuando la STA obtiene
IP (`IP_EVENT_STA_GOT_IP`), arranca la sesión con `count = 0` (sin fin),
`interval_ms = CSI_INTERVAL_MS = 100` y `data_size = 32`.

El mecanismo completo: el ESP32 manda un echo ICMP al router cada 100 ms →
el router responde → **cada respuesta recibida dispara el callback de CSI**
→ una medición. Resultado: $f_s \approx 10\ \mathrm{Hz}$ de muestras
perfectamente espaciadas, sin depender de que nadie más use la red.

Si `USE_TRAFFIC_PING = 0`, el firmware loguea que hay que generar tráfico
desde afuera (por ejemplo `ping -t <IP_de_la_ESP32>` desde cualquier
máquina, o el tráfico ambiente de la red) — ver `DEPLOYMENT.md`.

---

## 5. El viaje del dato dentro del firmware

Una medición, desde la onda hasta el MQTT, paso a paso:

**Paso 1 — Llega un frame 802.11n.** Del router (o del ping propio): una
ráfaga OFDM de 20 MHz con decenas de subportadoras.

**Paso 2 — El driver demodula cada tono.** Para saber "cómo llegó" cada
subportadora `k`, la radio la compara contra dos referencias: la portadora
en fase (**I**, *in-phase*) y la portadora desfasada 90° (**Q**,
*quadrature*). El resultado son dos números con signo (int8, $-127..127$)
por tono: las coordenadas del **fasor recibido**. Juntos forman el
coeficiente de canal complejo de esa subportadora:

```math
H_k = I_k + j\,Q_k
```

La **longitud** del fasor es cuánto del tono sobrevivió al viaje (la
amplitud); su **ángulo** es cuánto se atrasó (la fase). El driver entrega
todo el vector como pares I/Q en `info->buf` (bytes con signo), más el RSSI
del paquete en `info->rx_ctrl.rssi` y `info->len` (bytes: dos por
subportadora, así que $K = \mathrm{len}/2$; el S3 entrega ~64).

**Paso 3 — El callback reduce I/Q a amplitud** (`main.cpp: wifi_csi_rx_cb`).
Para cada tono:

```math
a_k = \mathrm{round}\left(\sqrt{I_k^2 + Q_k^2}\right), \qquad \lvert I_k \rvert, \lvert Q_k \rvert \le 127 \ \Rightarrow\ a_k \le 180
```

que cabe en un `uint8`. **La fase se descarta a propósito** ($\mathrm{atan2}(Q,I)$
es el camino documentado a futuro: haría la medición ~10× más sensible —
ver `SIGNAL-MODELING.md` §3). El struct también sella el momento
(`t_us = esp_timer_get_time()`, µs desde el arranque) y el orden (`seq`,
un contador propio que arranca en 0 al booteo).

**Paso 4 — Encolado.** El struct `csi_sample_t` (t_us, rssi, n, seq, hasta
128 amplitudes) va a la cola FreeRTOS (profundidad 32) — el callback
termina acá; nunca toca la red.

**Paso 5 — El publicador arma la fila CSV.** Una línea ASCII por paquete:

```
t_us,rssi,n,seq,a0,a1,...,a(n-1)
1717000000123456,-52,64,42,178,176,171,...
```

**Paso 6 — Publicación.** `esp-mqtt` (keepalive 30 s, reconexión automática
— `main.cpp: mqtt_start`) manda la fila al broker al tópico
`esp32/<id>/csi/raw` con **QoS 0**: a 10 paquetes/s, la garantía de entrega
de QoS superior solo agregaría acks sin agregar información (un paquete
perdido = un gap de muestreo).

El extremo consumidor de cada fila está en
[DESKTOP-APP.md](DESKTOP-APP.md) §3; la matemática completa del sistema en
[DATA-PIPELINE.md](DATA-PIPELINE.md).

---

## 6. Configuración (`src/esp32/main/config.h`)

| Knob | Default | Qué hace | Cuándo tocarlo |
|---|---|---|---|
| `WIFI_SSID` / `WIFI_PASS` | `"CHANGE_ME"` | red WiFi 2,4 GHz a la que conecta (respaldo si la NVS está vacía) | solo si no vas a provisionar por serial; lo normal es dejarlo y usar §7 |
| `MQTT_BROKER_URI` | `mqtt://192.168.1.50:1883` | broker al que publica — la **IP LAN de la máquina del broker**, nunca `localhost` (la placa y el broker son máquinas distintas) | al cambiar el broker |
| `MQTT_TOPIC_PREFIX` | `esp32` | prefijo del tópico; el publicador agrega `/<id>/csi/raw` | casi nunca |
| `CSI_INTERVAL_MS` | `100` | intervalo del ping → **ritmo de muestreo** ($f_s \approx 1/\mathrm{interval}$) | si querés otra $f_s$ — ojo: el DSP del backend asume 10 Hz (`CSI_FS`) |
| `CSI_MAX_SUBCARRIERS` | `128` | tope de subportadoras por muestra (el S3 usa ~64) | nunca en la práctica |
| `CSI_CHANNEL_FILTER` | `true` | suavizado de subportadoras adyacentes del IDF (SNR más alto) | solo para experimentos |
| `USE_TRAFFIC_PING` | `1` | 1: el firmware se autoprovoca tráfico (ping al gateway); 0: tráfico externo | si la red prohíbe ICMP o preferís medir tráfico real |

---

## 7. Provisioning por serial (cambiar de red SIN reflashear)

La misma imagen binaria sirve para cualquier red: las credenciales viven en
la **NVS** y se cargan por el puerto USB (`provisioning_task`, UART0). El
protocolo es human-readable a propósito — funciona igual con el script
`scripts/provision-esp32.py` (detecta el puerto solo, ~30 s) o tecleado a
mano en cualquier terminal serial (`idf.py monitor`, `screen`, PuTTY):

| Comando | Qué hace |
|---|---|
| `PROVISION:SSID=<valor>` | guarda el SSID en la NVS |
| `PROVISION:PASS=<valor>` | guarda la contraseña en la NVS |
| `PROVISION:BROKER=<valor>` | guarda el URI del broker en la NVS |
| `PROVISION:SAVE` | aplica los cambios **reiniciando** la placa |
| `PROVISION:STATUS` | imprime origen de credenciales + SSID + broker (nunca la contraseña) |
| `PROVISION:CLEAR` | borra la NVS y reinicia (vuelve al `config.h` compilado) |

Flasheás **una vez**; a partir de ahí, mover la placa a otra red o broker es
un provisioning de 30 segundos, sin IDE ni cable de compilación
(`main.cpp: provisioning_task`, `provision_save`).

---

## 8. Decisiones de diseño y límites honestos

| Decisión | Por qué / límite |
|---|---|
| Amplitud sin fase | descartar $\mathrm{atan2}(Q,I)$ simplifica todo el pipeline y es honesto respecto de lo que puede; el costo es ~10× menos sensibilidad (el camino futuro está documentado) |
| QoS 0 en el publish | a $10\ \mathrm{Hz}$ un paquete perdido es ruido de muestreo; QoS ≥ 1 agrega acks y duplica la carga sin información nueva |
| Cola de 32 y timeout 0 | la medición nunca puede atrasar la recepción; el costo es que una ráfaga > 32 paquetes sin consumir descarta (y lo cuenta `qfull`) |
| Tópico por MAC | habilita multi-placa sin configuración: cada una nace con identidad propia |
| Canal RF no pineado | la longitud de onda usada en la física (λ ≈ 12,44 cm, canal 1) es una aproximación documentada: el firmware no fija el canal del router |
| Buffer CSV acotado (`64 + 128·4`) | snprintf con presupuesto de bytes fijo: jamás puede desbordar por una muestra larga |

---

## 9. Cómo se compila y flashea

Receta completa (ESP-IDF v5.x, `idf.py set-target esp32s3 && idf.py build &&
idf.py -p <puerto> flash monitor`): `DEPLOYMENT.md` §3. Provisioning
posterior: `DEPLOYMENT.md` §5 (Opción A). Sin hardware para probar:
`scripts/simulate_esp32.py` publica CSI sintética.

---

## 10. Diagrama del flujo interno

```
        ┌───────────────────────── ESP32-S3 ─────────────────────────┐
        │                                                              │
        │  lwIP ping al gateway cada 100 ms (USE_TRAFFIC_PING)        │
        │        │ echo ICMP                                           │
        │        ▼                                                     │
 router ┼─► radio WiFi + driver ESP-IDF                                │
 802.11n│   demodula cada subportadora → (I_k, Q_k) con signo, int8    │
        │        │ esp_wifi_set_csi_rx_cb → wifi_csi_rx_cb             │
        │        │   a_k = round(√(I_k²+Q_k²))  [fase: descartada]     │
        │        │   + t_us, rssi, seq  → csi_sample_t                 │
        │        ▼ xQueueSend (timeout 0)         [llena → s_qfull++] │
        │  cola FreeRTOS (profundidad 32)                             │
        │        │ xQueueReceive                                       │
        │        ▼                                                     │
        │  publisher_task (prio 5):                                    │
        │   CSV "t_us,rssi,n,seq,a0..a(n-1)" en buffer acotado         │
        │        │ esp_mqtt_client_publish (QoS 0)                     │
        │        ▼                                                     │
        │   esp32/<últimos 3 bytes MAC>/csi/raw ──────────► Mosquitto  │
        │                                                              │
        │  stats_task (prio 4): captured/qfull/published/failed 10 s   │
        │  provisioning_task (prio 3, UART0): PROVISION:* → NVS         │
        └──────────────────────────────────────────────────────────────┘
```
