# Cómo funciona — WiFi-CSI Vital Signs (la guía "para niños, pero técnica")

> **Para quién es esta guía.** Si tenés que explicarle este proyecto a tu
> mamá, a un compañero de trabajo o en una entrevista: cada sección acá
> tiene primero la **versión en una frase** y después la **versión
> técnica exacta** (con los números reales de ESTE proyecto). La versión
> profunda con todas las fórmulas vive en `docs/SIGNAL-MODELING.md`.
> No es un dispositivo médico: es una herramienta de investigación.

---

## 1. La idea en una frase

> **El WiFi de tu casa es una linterna invisible que rebota en todo — y
> cuando esa luz rebota en tu pecho, el rebote tiembla al ritmo de tu
> respiración y de tu corazón. Nosotros medimos ese temblor.**

Versión técnica: el ESP32 mide cómo llega cada subportadora de una señal
WiFi ($|H_k|$, la **CSI** — *Channel State Information*) a ~10
mediciones por segundo. El pecho, al moverse milímetros, cambia los
caminos de rebote de la señal (*multipath*) y eso modula la amplitud que
el ESP32 recibe. Esa modulación ES la respiración y el latido.

---

## 2. El sistema físico: de la onda invisible al dato

### 2.1 El espectro electromagnético y el WiFi

El WiFi de 2,4 GHz es una onda electromagnética que vibra 2 400 millones
de veces por segundo. Su **longitud de onda** (la distancia entre dos
crestas) es:

```math
\lambda = \frac{c}{f} = \frac{299{,}792{,}458\ \mathrm{m/s}}{2.412\ \mathrm{GHz}} \approx 12.44\ \mathrm{cm}
```

*(El firmware no fija el canal del router, así que 12,44 cm es una
aproximación razonable — el canal exacto haría variar unos mm.)*

**Por qué importa λ**: los objetos del tamaño de la longitud de onda
(decímetros) reflejan muy bien el WiFi. Las paredes, los muebles, los
cuerpos: todo es un espejo parcial.

### 2.2 Los ecos (multipath): la "sala de espejos"

El router emite; el ESP32 recibe. Pero NO recibe una sola copia de la
señal: recibe **la suma de miles de copias** — la que llegó directo, la
que rebotó en el techo, la que rebotó en la pared y en tu hombro, la que
atravesó tu cuerpo y se dispersó… Cada camino tiene una longitud
distinta, así que las copias llegan "desalineadas" y se suman mal o bien
según el punto donde estén. A eso se lo llama canal, y cambia **cada
vez que algo se mueve** en la sala.

> **Metáfora**: es una sala llena de espejos. Si un espejo se mueve un
> milímetro, la imagen compuesta cambia. Si el "espejo" es el pecho de
> una persona respirando, la imagen tiembla 12–30 veces por minuto.

### 2.3 El pecho: el "espejo" que nos interesa

- **Respiración**: el pecho se desplaza algunos milímetros a ~1 cm,
  12–30 veces por minuto (0,1–0,5 Hz).
- **Corazón**: la piel de tu pecho se mueve **fracciones de milímetro**
  con cada latido, 48–120 veces por minuto (0,8–2,0 Hz).

Modelo del proyecto (el mismo de `docs/SIGNAL-MODELING.md` §3):

```math
x(t) \approx A_b \sin(2\pi f_b t) \quad f_b \text{ respiración} \in [0.1, 0.5]\ \mathrm{Hz}
```

Esos milímetros son **muy poco** comparados con λ (12,44 cm) — y sin
embargo alcanzan: porque el pecho está cerca de las **zonas de Fresnel**
(las "cápsulas invisibles" alrededor de la línea router–ESP32 dentro de
las que viaja casi toda la energía), un cuerpo ahí perturba la suma de
caminos de forma medible.

> **Aclaración honesta**: medir el corazón es mucho más difícil que la
> respiración, porque su desplazamiento es ~10 veces más chico. Por eso
> el sistema te muestra `-` cuando la señal no supera la compuerta de
> calidad (§4, paso 6) — prefiere decir "no sé" a inventar un número.

### 2.4 Los paquetes de red: los "flashes" de la linterna

Para medir el canal hace falta que llegue una señal. El WiFi no emite
continuo como una radio: manda **paquetes** (ráfagas cortas). Cada
paquete recibido es un "flash" con el que el ESP32 puede fotografiar el
canal. ¿Y si nadie está descargando nada? El firmware **genera su
propia luz**: manda un `ping` al router cada 100 ms
(`USE_TRAFFIC_PING 1` en `config.h`), lo que produce ~10 paquetes/s
→ **fs ≈ 10 Hz**: 10 "fotos del canal" por segundo.

### 2.5 OFDM: los 64 "colores" del flash

Un paquete WiFi moderno (802.11n, OFDM) no es un solo tono: viaja en
decenas de **subportadoras** — tonos equiespaciados dentro del canal de
20 MHz. El ESP32 reporta cómo llegó **cada tono por separado**: el
chip entrega hasta 128 subportadoras (el S3 usa **~64** en la práctica,
`K = csi_len/2`).

Eso es la **CSI**: un vector de ~64 amplitudes por paquete,
$a_k = |H_k|$ — *el firmware descarta la fase* (un diseño honesto y
documentado; ver `docs/SIGNAL-MODELING.md` §1). Cada subportadora es un
"punto de vista" distinto del mismo canal: alguna mira el pecho mejor,
otra está tapada por la heladera, otra solo ve ruido.

**Comportamiento esperado** (y es lo que aprovecha el procesamiento):

- La respiración/el latido **mueven todas las subportadoras juntas y al
  mismo ritmo** (el pecho perturba caminos compartidos → señal
  *coherente*).
- El ruido de cada subportadora es **independiente** (cada tono sufre
  su propio ruido) → al promediar, el ruido se cancela y la señal queda.

---

## 3. La cadena de medición (los números que viajan)

```
ESP32-S3 ──MQTT (esp32/<id>/csi/raw)──► Mosquitto ──► Backend Python ──► GUI / teléfono
```

Cada medición es un CSV chiquito, ~10 veces por segundo:

```
t_us, rssi, n, seq, a0, a1, a2, ... a(n-1)
1717000000123456,-52,64,42,178,176,171,169,...
```

| Campo | Qué es | Unidad física |
|---|---|---|
| `t_us` | reloj del chip (desde el arranque) | microsegundos |
| `rssi` | potencia con la que llegó TODO el paquete | dBm |
| `n` | cuántas subportadoras trae | — |
| `seq` | número de secuencia del paquete | — |
| `a0..a(n-1)` | amplitud de cada subportadora: $a_k = \sqrt{I^2+Q^2}$ | adimensional ("a.u.") |

**Unidades, de una vez** (las mismas que ahora ves en los ejes del GUI):
las amplitudes CSI son **adimensionales** (un número que el chip
entrega, sin watts ni voltios); el heatmap y el espectrograma las
convierten a **dB** para que quepa todo en pantalla; RSSI va en
**dBm**; las frecuencias en **Hz**; el tiempo en **s**.

---

## 4. El "lavado" de datos: de 64 números ruidosos a 1 número legible

Esta es la guía práctica de cada paso. `ENTRA → SE HACE → SALE → POR QUÉ`.

**Paso 0 — Los guardias de la puerta.**
ENTRA un paquete → se descarta si tiene NaN/inf, timestamps que
retroceden o cambio de ancho (n) a mitad de ventana → SALE solo lo
íntegro. *POR QUÉ: una sola fila corrupta envenena la FFT.*

**Paso 1 — Promediar las ~64 subportadoras: $\bar{a}(t) = \frac{1}{K}\sum|H_k|$.**
ENTRA la fila de 64 amplitudes → SALE el promedio (1 número por
instante). *POR QUÉ: el pecho mueve todos los tonos juntos (coherente)
pero el ruido de cada tono es independiente → el promedio conserva la
respiración y degrada el ruido $\sqrt{64} = 8$ veces.* Esa $\bar{a}(t)$ es la **gráfica
cruda** del panel superior izquierdo.

**Paso 2 — La ventana de 15 s.**
ENTRA el chorro continuo → SALE una ventana deslizante de
`N = 10 Hz × 15 s = 150` filas. *POR QUÉ: para que la FFT tenga con qué
trabajar hacen falta varios ciclos: 15 s contienen ~4 respiraciones y
~15 latidos.*

**Paso 3 — Elegir la MEJOR subportadora por banda.**
ENTRA la ventana completa (150 × 64) → por cada subportadora se le quita
la tendencia (`detrend`), se le aplica Hann (alisa los bordes para que
la FFT no "sangrar"), se calcula su espectro y su pico dentro de la
banda; se elige la de mejor SNR → SALE 1 subportadora por banda.
*POR QUÉ: alguna subportadora "ve" el pecho con claridad y otra solo ve
la heladera; usamos la mejor vista y reportamos cuál fue (sc# en
pantalla).*

**Paso 4 — Filtro por banda (el "colador").**
ENTRA la mejor serie → SALE la misma serie filtrada con un
pasa-banda Butterworth: **respiración 0,1–0,5 Hz** (6–30/min) y
**corazón 0,8–2,0 Hz** (48–120 bpm), filtradas hacia adelante Y hacia
atrás (`sosfiltfilt`) para no desfasar nada. *POR QUÉ: el cuerpo solo
puede respirar/latir en esos rangos — todo lo demás es ruido y se
descarta por construcción.*

**Paso 5 — La FFT: contar las oscilaciones.**
ENTRA la ventana filtrada → SALE el pico espectral (con interpolación
parabólica para no quedarse en la frecuencia de la rejilla) →
f_respiración y f_corazón en Hz. *POR QUÉ: la FFT separa "cuántas veces
por segundo tiembla" — que es, literalmente, la definición de frecuencia.
18/min de respiración = 0,3 Hz.*

**Paso 6 — La compuerta de honestidad (SNR ≥ 6 dB).**
ENTRA el pico de la banda y el piso espectral de esa subportadora →
`SNR = pico / mediana del piso` → si SNR < 6 dB (`CSI_MIN_SNR_DB`), el
sistema muestra **`-`**. *POR QUÉ: si el pico no sobresale del ruido, el
número sería una invención. Sin señal suficiente: no hay número. Eso es
diseño, no un bug.*

**Paso 7 — Presencia y movimiento (la fila "Body").**
ENTRA la ventana cruda → SALE: **σ de la ventana** (sala vacía = señal
plana, σ < 0,15 → `Absent`); **RMS de la banda 0,5–3 Hz** (> 1,5 →
`Moving`; si no, `Still`). *POR QUÉ: el cuerpo quieto es ruido lento
plano; moverse agita toda la banda de movimiento.*

**Paso 8 — RSSI → distancia de enlace.**
ENTRA el RSSI promedio (dBm) → SALE una distancia estimada (m) vía
modelo log-distance `PL(d)` calibrable (`CSI_RSSI_REF_DBM`,
`CSI_REF_DISTANCE_M`, `CSI_PATH_LOSS_N`; indoor `n_pl ≈ 2,7–4,3`). Sin
calibrar se apaga con `CSI_RSSI_REF_DBM=none` → el GUI muestra `—`.
*POR QUÉ: la señal se atenúa con la distancia; con dos puntos de
referencia medidos, se puede interpolar. Es una brújula, no un GPS.*

**Paso 9 — Multi-ESP32 (varias placas = varios puntos de vista).**
Cada placa publica en su propio tópico (`esp32/<id>/csi/raw`); el
backend mantiene un pipeline aislado por placa y fusiona: para
respiración y para corazón gana **la placa con mejor SNR de esa banda**
(pueden ser distintas); presencia = conservadora (cualquier placa que
ve movimiento → `Moving`). Un link silencioso **expira a los 20 s**
(`LINK_STALE_S`), el registro guarda 16 links con desalojo LRU.
*POR QUÉ: dos vistas del mismo pecho; la que "ve mejor" gana cada
medición, y una placa apagada no gana nada para siempre.*

---

## 5. Las gráficas: qué mide cada una y cómo leerla

El GUI de escritorio tiene 6 paneles + una franja de medidas bajo el
canvas que lista todas las cantidades con sus unidades. Ejecutá el
simulador (`python ..\scripts\simulate_esp32.py --scenario resting`) y
vas a ver cada escenario sin hardware.

### Izquierda — las 3 trazas temporales (eje x: `t [s]`, 0–15 s)

**1. CSI medio $\bar{a}(t)$ — "materia prima" [a.u.]**
La amplitud promedio cruda. *Cómo leerla*: a simple vista ya se ve la
respiración como una onda lenta y suave; un movimiento corporal es un
salto brusco; la sala vacía es casi una línea con ruido fino. Si esta
gráfica está muerta-planilla, nada de lo que sigue va a funcionar —
mirá el pkt/s en la barra de estado.

**2. Respiración `x(t)` — banda 0,1–0,5 Hz [a.u.]**
La misma señal, ya filtrada a la banda respiratoria. *Cómo leerla*:
contá los picos — cada pico es una respiración (una cada 2–10 s es
normal: 12–30/min). El título dice qué subportadora ganó (`sc#`) y con
qué calidad (`SNR` en dB). Onda pareja = persona quieta respirando.

**3. Corazón `x(t)` — banda 0,8–2,0 Hz [a.u.]**
La señal cardíaca filtrada. *Cómo leerla*: la amplitud es muchísimo más
chica (el latido mueve ~10 veces menos que la respiración) — por eso
necesita quietud y distancia corta (0,5–2 m). Picos regulares =
latidos; el número grande arriba es el BPM. Si hay movimiento, esta
traza se ensucia primero.

### Derecha — los 3 paneles físicos (1 Hz)

**4. Heatmap de subportadoras $|H_k|$ [dB]**
Todas las subportadoras a la vez (y = subportadora, x = tiempo, color =
amplitud). *Cómo leerla*: las franjas verticales más claras son las
subportadoras "buenas" — las que el paso 3 elige. Si todo el panel se
oscurece de golpe, algo tapó el enlace.

**5. Espectrograma `X(τ,f)` [dB]**
El contenido de frecuencia de $\bar{a}(t)$ a lo largo del tiempo. *Cómo
leerla*: buscá una **franja horizontal** — una línea brillante y
estable a la altura de la frecuencia respiratoria (~0,2–0,3 Hz) es tu
respiración dibujada en el tiempo; la franja resaltada en verde/rojo
son las bandas fisiológicas que el sistema usa. Un movimiento = mancha
ancha que sube y baja.

**6. Energía de movimiento `M_rms` [a.u.]**
La banda 0,5–3 Hz en el tiempo (10 min de historia), con la línea roja
del umbral (`CSI_MOVING_RMS`, 1.5). *Cómo leerla*: por debajo de la
línea = quieto; cada pico que la cruza = un movimiento; el Body row
cambia a `Moving` exactamente cuando la traza cruza esa línea.

### La fila "Body" y la barra de meta
`Body: Still | motion 0.42 RMS | σ_window 0.31 | RSSI -52 dBm | link dist ~1.0 m`
— presencia (estado), la energía de movimiento, el "planismo" de la
señal, la potencia del enlace y la distancia estimada. La barra de
meta agrega las subportadoras ganadoras, el SNR de cada banda y el
tamaño de la ventana; con varias placas, la barra de estado lista los
links y cuál es el primary (el que gana el corazón).

---

## 6. Resultados esperados y límites (honestos)

- **Respiración**: robusta a 0,5–4 m con línea de vista; funciona hasta
  con alguien en la misma sala sin línea directa.
- **Corazón**: el más frágil — necesita quietud, 0,5–2 m, línea de
  vista; con personas moviéndose cerca, mostrá esperanza de ver `-`.
- **Varias personas**: el sistema mide "el ambiente" — dos personas
  respirando desincronizadas se mezclan. Es una limitación conocida del
  enfoque de amplitud (sin fase es difícil separar).
- **Sin fase**: la fase (`atan2(Q,I)`) haría la medición ~10× más
  sensible; el firmware actual la descarta (futuro camino documentado
  en `SIGNAL-MODELING.md` §3).
- **No es un dispositivo médico.** Nunca lo fue. Es un experimento de
  física ingenieril sobre tu propia sala.

---

## 7. Tres frases listas para alguien no técnico

1. *"El WiFi rebota en todo, igual que un grito en un cañón. Cuando rebota
   en tu pecho, tiembla al ritmo de tu respiración y tu corazón — y esta
   cajita con antena lee ese temblor."*
2. *"La señal WiFi viaja en 64 tonitos a la vez, como un acorde. Tu
   respiración desafina el acorde entero poquito pero todos juntos, y el
   ruido desafina cada tono por su lado — entonces promediamos los 64 y
   el ruido se cancela y tu respiración queda."*
3. *"Cada paquete de datos es una foto del eco de la señal. La cajita
   manda 10 fotos por segundo, el programa las apila 15 segundos, cuenta
   cuántas veces por minuto tiembla la foto — y ese número es tu
   respiración."*

---

## 8. Para profundizar

| Querés saber… | Andá a |
|---|---|
| Las fórmulas exactas implementadas (paso a paso del §4 de acá) | `docs/SIGNAL-MODELING.md` §4 |
| Calibrar presencia/movimiento y RSSI | `docs/SIGNAL-MODELING.md` §6 |
| El protocolo de validación empírica | `docs/VALIDATION-PROTOCOL.md` |
| Cómo desplegarlo paso a paso | `DEPLOYMENT.md` |
| La arquitectura del pipeline y el stack | `docs/PROJECT-ARCHITECTURE.md` |
| El inventario de funciones del GUI | `docs/SIGNAL-MODELING.md` §9 |
