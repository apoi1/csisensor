# Herramientas de Desarrollo, Metodología y Fundamentos del Proyecto

**Proyecto**: WiFi-CSI Vital Signs Tracking (ESP32-S3 + MQTT + Python/PyQt5)

Referencia única de: (1) qué herramientas usa cada capa y por qué, (2) la metodología correcta de build/flash/depuración, (3) las bases teóricas y matemáticas del procesamiento de señales —incluida la cadena **serie de Fourier → DFT → FFT**, la derivación de cada fórmula y el origen de cada variable—, (4) el flujo de datos end-to-end y (5) las tecnologías, repositorios y datasets del proyecto.

> Guía paso a paso de instalación/despliegue: **`DEPLOYMENT.md`**. Resumen de arquitectura: **`docs/PROJECT-ARCHITECTURE.md`**.

---

## 0. Correcciones respecto a la versión anterior de este archivo

| Antes (incorrecto) | Ahora (correcto) |
|---|---|
| ESP-IDF 4.4 | **ESP-IDF v5.3.x** — el firmware usa la API v5 (config anidada de esp-mqtt, `esp_wifi_set_csi_rx_cb`) y no compila contra 4.4 |
| "IDE VS Code" / flujos vía VS Code | El flujo de build/flash/monitor es **por consola en WSL** (`idf.py`). VS Code y LazyVim son **solo editores** opcionales |
| Docker instalado con `apt` dentro de WSL | El broker corre en **Docker Desktop para Windows** (integración WSL opcional) |
| VcXsrv (X server) para GUIs de Linux | Innecesario: la GUI PyQt5 corre **nativa en Windows**; no hay X-forwarding |
| Python del backend en WSL | El venv del backend/GUI vive en **Windows** |
| `gdb-multiarch`, `esptool` por pip aparte | ESP-IDF incluye su toolchain completo: `idf.py gdb`, `idf.py monitor`, `idf.py flash` |

---

## 1. Metodología de desarrollo

### Convenio de idioma

La documentación se escribe en **español**. Los términos consagrados en la
literatura se citan **en inglés, sin traducir** — CSI, RSSI, OFDM, FFT, DFT,
Hann window, spectral leakage, path loss, SNR — y se explican en español la
primera vez que aparecen. Las referencias y nombres propios (Oppenheim,
Cooley–Tukey, ESP-IDF) quedan como en la fuente, y los identificadores de
código (`np.hanning`, `esp_wifi_set_csi_rx_cb`) se escriben siempre literales.

### ¿ESP-IDF va en WSL o en Windows? ¿Se compila desde un IDE?

- **ESP-IDF se instala dentro de WSL (Ubuntu).** El toolchain de compilación (`xtensa-esp32s3-elf-gcc`, CMake/Ninja, esptool, GDB) es Linux nativo y se instala con `./install.sh esp32s3` del propio IDF.
- **Todo el ciclo build → flash → monitor → debug es por consola** (`idf.py ...`) en una terminal de WSL. No hay ningún paso que requiera un IDE.
- **El editor es irrelevante para compilar**: usá lo que prefieras —
  - **VS Code + extensión Remote-WSL** (abre la carpeta de WSL como si fuera local), o
  - **LazyVim/Neovim con clangd** (el LSP entiende el proyecto CMake de ESP-IDF: `compile_commands.json` se genera en `build/` tras el primer `idf.py build`).
- La extensión "ESP-IDF" de VS Code existe y puede invocar `idf.py` con botones, pero **no forma parte del flujo de este proyecto**: si la usás, hacé que apunte al mismo IDF de WSL para no duplicar toolchains.

### Regla de oro

| Acción | Dónde se ejecuta | Comando |
|---|---|---|
| Editar firmware | WSL (editor a gusto) | — |
| Compilar firmware | WSL, consola | `idf.py build` |
| Flashear + monitor | WSL, consola | `idf.py -p /dev/ttyACM0 flash monitor` |
| Depurar firmware | WSL, consola | `idf.py gdb` (GDB propio del IDF; no hace falta `gdb-multiarch`) |
| Broker Mosquitto | Windows (Docker Desktop) | `docker compose up -d` |
| Backend + GUI | Windows (venv) | `python main.py` |

> **Nota de shell (WSL)**: los comandos WSL de `DEPLOYMENT.md` están escritos en **fish**, el shell de trabajo del proyecto. Únicas diferencias reales con bash: `source export.fish` en vez de `. ./export.sh` (ESP-IDF v5.3 trae script nativo para fish — verificado en el tag del repo) y sustitución de comandos con `(...)` en vez de `$(...)`. `&&`, los globs y `$USER` valen igual en ambos shells.

---

## 2. Requisitos técnicos

### Hardware
- **ESP32-S3** con cable USB **de datos** (muchos cables solo cargan).
- Red WiFi **2.4 GHz** (el ESP32-S3 no ve 5 GHz).
- PC Windows 10/11 con **WSL2** (Ubuntu 22.04+), **Docker Desktop** y **Python 3.10+**.
- Conectividad: el ESP32, el PC (broker) y el WiFi deben estar en la **misma LAN**.

### Software, por capa

| Capa | Herramienta | Versión | Rol |
|---|---|---|---|
| WSL | Ubuntu | 22.04+ | Entorno de build del firmware |
| WSL | **ESP-IDF** | **v5.3.x** (p. ej. v5.3.1) | SDK: WiFi/CSI, esp-mqtt, ping, toolchain completo |
| WSL | git, curl, ninja, cmake | los que instala `install.sh` | Build system |
| WSL | mosquitto-clients | 2.x | Solo para *verificar* el stream desde WSL |
| WSL (opcional) | Neovim + LazyVim + clangd, o VS Code Remote-WSL | — | Editores; no compilan nada |
| Windows | Docker Desktop | — | Corre el contenedor Mosquitto |
| Windows | Python + `venv` (integrado, sin herramientas extra) | 3.10+ | Backend + GUI |
| Windows | usbipd-win | ≥ 4.x | Comparte el puerto USB con WSL (flasheo) |

### Dependencias Python (dentro del venv, `backend/requirements.txt`)

| Paquete | Versión | Por qué esa versión |
|---|---|---|
| `paho-mqtt` | `>=1.6,<2.0` | La API 2.x rompió el constructor `Client()` usado por `mqtt_subscriber.py` |
| `aiohttp` | `>=3.9` | Servidor HTTP + WebSocket del web viewer (`web_viewer.py`); mantiene el viewer sin Qt y apto para PyInstaller |
| `numpy` | `>=1.24,<3.0` | FFT (`np.fft.rfft`) y arreglos |
| `scipy` | `>=1.10` | `signal.butter/sosfiltfilt` (filtros) y `signal.detrend` |
| `PyQt5` | `>=5.15` | GUI y event loop |
| `matplotlib` | `>=3.7` | Gráficos embebidos con backend `Qt5Agg` |
| `pytest` | `>=7.4` | Tests unitarios del procesador |

Ademas del `requirements.txt`, `esptool` se instala ad hoc en el venv de Windows (`.\.venv\Scripts\python.exe -m pip install esptool`) para flashear el firmware desde `scripts/flash-board.ps1` — no es dependencia del backend y no corre en WSL.

**Gestión del venv**: no se necesita conda/poetry/pipenv — el `venv` integrado alcanza:
```powershell
# Windows, dentro de backend/ (el repo vive en el FS de WSL; entrá por \\wsl.localhost\Ubuntu\... — ver DEPLOYMENT.md §8; no se copia nada)
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # si lo bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
```
Opcional, para congelar versiones reproducibles: `pip freeze > requirements.lock`.

---

## 3. Bases teóricas y matemáticas del procesamiento

### 3.1 Principio físico

El WiFi 802.11n (OFDM) transmite en decenas de **subportadoras**. Cada paquete recibido entrega el estado del canal (**CSI**): amplitud y fase por subportadora, que reflejan cómo se sumaron los múltiples caminos (multipath) entre el TX y el RX.

Cuando una persona respira o late su corazón, el tórax se desplaza periódicamente y **modula la longitud efectiva de los caminos de radio**. Eso produce una oscilación periódica y diminuta en la amplitud/fase del CSI de ciertas subportadoras:

| Fenómeno | Frecuencia | Desplazamiento típico | Efecto en CSI |
|---|---|---|---|
| Respiración | 0.1–0.5 Hz (6–30 /min) | ~1–12 mm | Modulación **fuerte** (fácil) |
| Latido | 0.8–2.0 Hz (48–120 bpm) | ~0.1–0.5 mm | Modulación **débil** (10–30× menor) |

El ESP32-S3 expone el CSI crudo (I/Q por subportadora) mediante la API nativa `esp_wifi_set_csi_rx_cb`; el callback entrega ~64 subportadoras en el S3 (límite por chip: 128, `CSI_MAX_SUBCARRIERS`). El firmware reduce cada paquete a amplitudes $a_k = \sqrt{I^2 + Q^2}$ — descartamos la fase porque sin calibración sufre saltos *wrap*; la amplitud basta para detectar la modulación.

**Problema inverso**: dado un tren de amplitudes `a_k[n]` muestreadas a ~10 Hz, contaminadas de ruido de radio y movimiento, estimar la frecuencia dominante dentro de cada banda fisiológica. Eso es un problema clásico de **detección de tonos en ruido**, resuelto con el aparato de Fourier (§3.3).

### 3.2 Modelo de señal

Para la subportadora `k`, cada muestra del CSI responde a:

```math
a_k[n] = C_k + B\cdot\sin(2\pi f_\text{resp} t_n + \varphi_k) + H\cdot\sin(2\pi f_\text{heart} t_n + \psi_k) + \varepsilon_k[n]
```

| Variable | Qué es | Valor típico | De dónde proviene |
|---|---|---|---|
| $a_k[n]$ | amplitud de la subportadora $k$ en la muestra $n$ | 0–180 (uint8) | firmware: $a_k = \sqrt{I_k^2+Q_k^2}$ con `I = csi_buf[2k]`, `Q = csi_buf[2k+1]` (int8 con signo), dentro de `wifi_csi_rx_cb()` (`main.cpp`) |
| `k` | índice de subportadora OFDM | 0–63 | `n = info->csi_len / 2` (bytes I/Q embebidos) en el callback |
| `n` | índice temporal | 0–149 | un callback CSI por paquete RX (~1 cada 100 ms, generado por el ping) |
| `t_n` | instante de la muestra `n` | segundos desde el boot | `t_us = esp_timer_get_time()` (µs); la GUI lo convierte: `t_us / 1e6` |
| `C_k` | offset estático del canal (DC) | ~30–150 | potencia media del camino de radio de esa subportadora; lo elimina `detrend` (paso 2) |
| `B`, `H` | profundidad de modulación (resp / latido) | B ≈ 1–5; H ≈ 0.1–0.5 | desplazamiento físico del tórax escalado por la respuesta del canal; H es 10–30× menor que B |
| `f_resp` | frecuencia respiratoria | 0.1–0.5 Hz | fisiología: (6–30 respiraciones/min) ÷ 60 |
| `f_heart` | frecuencia cardíaca | 0.8–2.0 Hz | fisiología: (48–120 bpm) ÷ 60 |
| `φ_k`, `ψ_k` | fase inicial por subportadora | 0–2π rad | geometría del multipath (distancias en múltiplos de λ/2 ≈ 6 cm @ 2.4 GHz) |
| `ε_k[n]` | ruido + artefactos | σ ≈ 0.05–1 | ruido de radio, AGC del receptor, movimiento del entorno |

**Cómo se llenan esas incógnitas: medido vs reconstruido vs no identificable.**
La ecuación de arriba es el modelo teórico; el sistema no mide sus variables
una a una — algunas las mide directo, otras las *reconstruye* a partir del
dato, y otras se declaran honestamente no identificables:

| Variable teórica | Estado | Cómo se obtiene del dato medido |
|---|---|---|
| `a_k[n]`, `n`, `t_n` | **medido** | directo del frame CSI (firmware: `wifi_csi_rx_cb`) |
| `C_k` (DC) | **reconstruido y descartado** | media de la ventana; lo elimina `detrend` (paso 2) |
| `f_resp`, `f_heart` | **reconstruido** | pico de la FFT por banda + interpolación parabólica δ (pasos 4–6) |
| `ε_k` (σ del ruido) | **reconstruido** | mediana del piso espectral de la banda → base del SNR (paso 7) |
| `B`, `H` (profundidades) | **parcial — solo en a.u.** | visibles como amplitud relativa de las ondas filtradas; el valor físico en mm **no es identificable** sin la ganancia del canal Γ (la fase está descartada) — por eso los ejes dicen [a.u.] y no mm |
| `φ_k`, `ψ_k` (fases) | **no identificable por diseño** | descartadas por el firmware (wrap sin calibración); `SIGNAL-MODELING.md` §3 |

### 3.3 De la serie de Fourier a la FFT: la teoría indirecta

Todo el estimador descansa en una idea de Fourier (1807): **toda señal periódica es una suma de senos y cosenos armónicos**. Nuestro tórax es un "péndulo" biológico: produce unas pocas componentes periódicas (`f_resp`, `f_heart`) embebidas en ruido — y la familia de herramientas de Fourier es exactamente lo que permite **medir cuánto hay de cada frecuencia**.

1. **Serie de Fourier** (señal continua y periódica, período `T`):

```math
x(t) = \frac{a_0}{2} + \sum_{n=1}^{\infty} \left[ a_n \cos(2\pi n f_0 t) + b_n \sin(2\pi n f_0 t) \right], \quad f_0 = \frac{1}{T}
```

Los coeficientes se obtienen correlacionando la señal con cada seno/coseno durante un período:

```math
a_n = \frac{2}{T}\int_0^T x(t)\cos(2\pi n f_0 t)\,dt \quad b_n = \frac{2}{T}\int_0^T x(t)\sin(2\pi n f_0 t)\,dt
```

Interpretación: `aₙ, bₙ` dicen *cuánta* componente de frecuencia `n·f₀` tiene la señal.

2. **Transformada de Fourier** (señal continua no periódica): generaliza los coeficientes a un continuo de frecuencias:

```math
X(f) = \int_{-\infty}^{\infty} x(t)\,e^{-i2\pi ft}\,dt
```

3. **DFT — Transformada Discreta de Fourier** (lo único que una computadora puede calcular, porque nuestros datos son `N` muestras): evalúa esa correlación solo en `N` frecuencias discretas:

```math
X[k] = \sum_{n=0}^{N-1} x[n]\,e^{-i2\pi kn/N}, \quad k = 0,\dots,N-1
```

Por la identidad de Euler (`e^(−iθ) = cos θ − i·sin θ`), `X[k]` es literalmente *multiplicar la señal por el seno y el coseno muestreados a la frecuencia del bin `k` y sumar todo*:

- si la señal contiene un tono exactamente en la frecuencia del bin `k`, los productos **suman coherentemente** (crecen ~N) → pico grande;
- si no lo contiene, los productos oscilan y se **cancelan** (~$\sqrt{N}\,\sigma$) → piso de ruido.

Ese contraste pico/piso es exactamente lo que explota la compuerta de SNR (paso 7 de §3.4).

**Vínculo clave con la serie**: la DFT "asume" que tus `N` muestras son un período completo de duración `T = N/fs` y calcula, numéricamente, los coeficientes de la serie de Fourier de esa señal periódica extendida. Por eso los bins caen en múltiplos de `f₀ = 1/T = fs/N` — de esa observación sale la fórmula de resolución `Δf` del paso 4.

4. **FFT — Fast Fourier Transform**: algoritmo (Cooley–Tukey, 1965) que calcula la DFT en $O(N\log N)$ en vez de $O(N^2)$, separando recursivamente las muestras pares de las impares. **Mismas matemáticas, computadas más rápido.** `np.fft.rfft` es la FFT especializada en entrada real: devuelve solo $k = 0 \ldots N/2$ porque con $x[n]$ real se cumple $X[N-k] = \bar{X}[k]$ (la otra mitad es redundante).

Nuestro pipeline usa $\lvert X[k] \rvert = \sqrt{\mathrm{Re}^2 + \mathrm{Im}^2}$ (la "energía" presente a cada frecuencia $f_k$) y descarta la fase — coherente con lo que ya hizo el firmware al reducir cada paquete a amplitudes.

Dos limitaciones concretas de esta teoría moldean el código:

- **Fuga espectral** (*spectral leakage*): si el tono no cae exacto en un bin, su energía se reparte en los bins vecinos → ventana de Hann (paso 3).
- **Resolución de bin limitada** (`Δf`) → interpolación parabólica `δ` (paso 6).

#### ¿Por qué la familia de Fourier y no otra técnica?

| Alternativa | Qué haría | Por qué se descartó acá |
|---|---|---|
| Autocorrelación | estimar el período comparando la señal con ella misma retrasada | sin espectro explícito no hay "pico vs piso", y la compuerta de honestidad SNR (paso 7) se queda sin métrica |
| Wavelets (CWT/DWT) | resolución tiempo-frecuencia simultánea | respiración y latido son cuasi-estacionarios dentro de los 15 s: la resolución extra no aporta y el costo/complejidad sube |
| Paramétricos (MUSIC/ESPRIT) | super-resolución con pocas muestras | exigen fijar el orden del modelo y son frágiles al ruido de multipath; overkill para dos bandas conocidas |
| Cruces por cero / contador de picos | contar picos de la onda filtrada | un solo glitch crea o borra un latido; sin métrica de calidad asociada |
| ML (ver §3.6) | clasificador/regresor entrenado | no hay dataset con verdad de referencia; el problema es detección de tonos en bandas conocidas *a priori* |

### 3.4 El pipeline matemático: mapa conceptual y autoridad

> **Consolidación (2026-11-06)**: la derivación fórmula-por-fórmula que vivía
> acá duplicaba a `docs/DATA-PIPELINE.md` §4. **La fuente autoritativa del DSP
> es DATA-PIPELINE §4** (matemática exacta con archivo y función citados, en
> español). Acá queda el mapa conceptual; la teoría de fondo en §3.3 y las
> referencias en §3.7.

| Paso | Qué hace | Por qué esa técnica (función) | Implementación |
|---|---|---|---|
| 1 · Ventana deslizante | apila N = fs·15 s = 150 filas de amplitudes | la FFT necesita varios períodos completos del fenómeno más lento (0.1 Hz → ≥10 s); 15 s = 1.5 ciclos respiratorios con latencia asumible | `vitals_processor.py` (`deque(maxlen)`) |
| 2 · Detrend | resta la recta de mínimos cuadrados `x'[n] = x[n] − (mn+b)` | elimina el DC y la deriva lenta: sin esto el bin 0 satura a sus vecinos y degrada el piso de ruido | `scipy.signal.detrend` |
| 3 · Ventana de Hann | multiplica por `w[n] = ½(1−cos(2πn/(N−1)))` | la ventana rectangular convoluciona el espectro con un *sinc* cuyo lóbulo lateral está a −13 dB: la respiración "embadurnaría" al latido; Hann baja los lóbulos a −31 dB (18 dB/octava) a costa de ensanchar el lóbulo principal ~2× | `np.hanning(N)` |
| 4 · FFT (rfft) | `X[k] = Σ x[n]w[n]e^{−i2πkn/N}`, magnitud `\|X[k]\|` | mide cuánta energía hay en cada frecuencia; `Δf = fs/N ≈ 0.067 Hz` fija la resolución cruda | `np.fft.rfft` + `rfftfreq` |
| 5 · Mejor subportadora por banda | por banda fisiológica, gana la subportadora con mejor SNR de pico | el tórax modula fuerte solo algunos caminos; promediar todas diluye señal con ruido | `vitals_processor.py` |
| 6 · Interpolación parabólica (δ) | parábola en escala log sobre pico y vecinos; el vértice da `x*` sub-bin | el pico verdadero casi nunca cae en un bin; sin esto el corazón se mediría en escalones de ~4 bpm | `vitals_processor.py` |
| 7 · Compuerta SNR | `SNR = pico / mediana del piso`; < 6 dB → muestra `-` | honestidad: sin pico que sobresalga del ruido, el número sería una invención | `vitals_processor.py` |
| 8 · Butterworth orden 3 | pasa-banda adelante y atrás (`sosfiltfilt`) | dibuja la onda **sin desfase**; la *estimación* viene de la FFT, el filtro es para visualizar | `scipy.signal.butter` |
| 9 · Conversión final | Hz → resp/min y bpm | unidades fisiológicas para la GUI | `vitals_processor.py` |

**De qué datos exactos parte la discriminación respiración vs latido**: del
mismo input — la matriz deslizante 150×64 de amplitudes `a_k` que sale de los
frames CSV. No separa orígenes: **separa frecuencias**. Cada columna
(subportadora) se transforma con detrend→Hann→rfft y se buscan picos en la
banda 0.1–0.5 Hz (respiración) y en la 0.8–2.0 Hz (latido); gana la mejor
subportadora *de cada banda*, que pueden ser distintas (el `sc#` de pantalla).

### 3.5 Por qué 10 Hz de muestreo

Nyquist para la banda cardíaca máxima (2 Hz) exige ≥ 4 Hz; 10 Hz da margen para el filtrado digital y el ping de tráfico. El firmware genera tráfico con un **ping al gateway cada 100 ms** (`esp_ping`, `CSI_INTERVAL_MS`), porque el callback CSI solo dispara con paquetes RX entrantes: sin tráfico artificial no hay muestreo uniforme.

### 3.6 ¿Hay aprendizaje automático? No — el sistema es DSP determinista

**Respuesta directa**: este proyecto no usa ML. No hay modelo, no hay pesos, no hay entrenamiento, no hay pre-entrenamiento, no hay fine-tuning. Todo lo que el sistema "sabe" viene de (a) la física del canal (§3.1), (b) la fisiología de las bandas (§3.2) y (c) el análisis espectral determinista (§3.3–3.4). Cada número que muestra la GUI se puede trazar hasta una fórmula cerrada.

El único "entrenamiento" que existe es trivial y no usa datos: son **parámetros de diseño fijados por fórmulas** (tabla de abajo). Cambiarlos es editar `config.py` o `config.h` — nunca re-entrenar nada.

**Por qué se decidió DSP puro (y no un modelo)**

1. **No existe un dataset público de signos vitales con CSI.** Los datasets públicos del área (UT-HAR, NTU-Fi, SignFi, Wiar, FallAF — §5.3) son de reconocimiento de actividad/gestos, no de BPM/respiración con verdad de referencia. Entrenar un modelo propio exigiría montar un laboratorio con ECG o correa pectoral sincronizado con las capturas.
2. **El problema es detección de tonos, no clasificación de patrones.** Respiración y latido son componentes cuasi-periódicas en bandas conocidas *a priori*; el aparato de Fourier (§3.3) es la herramienta natural para tonos embebidos en ruido y funciona el día cero, sin ningún dato de entrenamiento.
3. **Interpretabilidad y costo**: cualquier número raro en la GUI se audita contra una fórmula (§3.4); corre en cualquier laptop sin GPU; los tests unitarios verifican el comportamiento de forma determinista (inyecto 60 bpm sintéticos → debe leer ~60 bpm).

**La tabla que juega el rol de "hiperparámetros"**

En ML los hiperparámetros se ajustan con datos de validación; acá los equivalentes se *derivan*:

| Parámetro | Análogo en ML | De dónde sale su valor |
|---|---|---|
| `heart_band_hz` = (0.8, 2.0) Hz | rango de salida del modelo | fisiología: (48–120 bpm) ÷ 60 |
| `resp_band_hz` = (0.1, 0.5) Hz | ídem | fisiología: (6–30 /min) ÷ 60 |
| `min_snr_db` = 6 dB | umbral de decisión / calibración | empírico ⇔ pico ≥ 2× el piso de ruido (10^(6/20) ≈ 2) |
| `window_s` = 15 s | contexto / ventana temporal | ≥ 1 período de la respiración más lenta (1/0.1 Hz = 10 s) + margen de latencia |
| `fs` = 10 Hz | tasa de muestreo del dataset | Nyquist (≥ 4 Hz) + margen para el filtrado digital |
| orden Butterworth = 3 | capacidad del modelo / regularización | estándar del área: pendiente suficiente sin *ringing* |

**Aclaración importante — datos sintéticos ≠ datos de entrenamiento**: el simulador (`scripts/simulate_esp32.py`) y las señales de los tests unitarios *verifican* que el algoritmo determinista recupera frecuencias conocidas; no *ajustan* parámetros con datos. Si mañana probás con 30 bpm, cambiás la señal de entrada y el algoritmo sigue siendo exactamente el mismo: nada se "acostumbra" a nada.

**Camino de evolución hacia ML (futuro, no implementado)**

Si algún día hace falta robustez que el DSP puro no da (mucho movimiento, ambientes hostiles, varias personas en la sala), la progresión típica del área sería:

1. **Nivel 1 — ML clásico sobre features del DSP**: mantener §3.4 como extractor de features (SNR por banda, varianza, coherencia inter-subportadoras, mejor `k`, …) y entrenar un clasificador o regresor (SVM, Random Forest, gradient boosting) sobre ventanas etiquetadas. Requiere decenas de sesiones con verdad de referencia (correa pectoral + ECG) y validación **cruzada por sujeto** para medir generalización real.
2. **Nivel 2 — Deep learning**: espectrogramas (subportadora × tiempo × potencia) → CNN o CNN+LSTM, las arquitecturas típicas de CSI sensing. Exige miles de ventanas etiquetadas, GPU, y validación cruzada por *sujeto y ambiente* — el *overfitting* al ambiente es el error clásico del área.
3. **El cuello de botella es el dataset, no la red**: capturar la verdad de referencia sincronizada con el CSI es la parte cara; los datasets públicos de HAR no trasladan directo a signos vitales.
4. En cualquier variante, el DSP actual queda como extractor de features o como *fallback* (el híbrido es el patrón dominante en la literatura), y el umbral de SNR se convierte en la política de "cuándo el modelo no sabe".

### 3.7 Referencias de la teoría (verificadas)

**Fundamentos de Fourier / DSP:**

- A. V. Oppenheim y R. W. Schafer, *Discrete-Time Signal Processing*, 3.ª ed., Pearson — el canon de Fourier/DFT/ventaneo.
- S. W. Smith, *The Scientist and Engineer's Guide to Digital Signal Processing* — introductoria y gratuita: <https://www.dspguide.com/>
- J. O. Smith III, *Spectral Audio Signal Processing*, W3K Publishing / CCRMA, Stanford: <https://ccrma.stanford.edu/~jos/sasp/> — en particular *Quadratic Interpolation of Spectral Peaks* (<https://ccrma.stanford.edu/~jos/sasp/Quadratic_Peak_Interpolation.html>), la derivación del `δ` del paso 6 y su justificación en dominio logarítmico.
- Cooley, J. W. y Tukey, J. W. (1965), "An algorithm for the machine calculation of complex Fourier series", *Mathematics of Computation* 19(90), 297–301 — el artículo original de la FFT.
- NumPy FFT (documentación de `rfft`/`rfftfreq`): <https://numpy.org/doc/stable/reference/routines.fft.html>
- SciPy `signal` (`butter`, `sosfiltfilt`, `detrend`): <https://docs.scipy.org/doc/scipy/reference/signal.html>
- aiohttp (servidor HTTP + WebSocket del web viewer): <https://docs.aiohttp.org/> — licencia Apache 2.0

**WiFi sensing / CSI:**

- Halperin, D., Hu, W., Sheth, A. y Wetherall, D. (2011), "Tool Release: Gathering 802.11 Traces with Channel State Information", *ACM SIGCOMM CCR* 41(1) — origen de la captura CSI con Intel 5300 y del campo entero.
- Ma, Y., Zhou, G. y Wang, S. (2019), "WiFi Sensing with Channel State Information: A Survey", *ACM Computing Surveys* 52(3), art. 46: <https://dl.acm.org/doi/10.1145/3310194>
- Adib, F., Mao, H., Kabelac, Z., Katabi, D. y Miller, R. C. (2015), "Smart Homes that Monitor Breathing and Heart Rate", *ACM CHI 2015* — el principio físico de signos vitales sin contacto con RF.
- ESP32-CSI-Tool (Steven M. Hernandez): <https://github.com/StevenMHernandez/ESP32-CSI-Tool> — herramienta de referencia para capturar CSI en ESP32. **No es una dependencia de este proyecto** (nuestro firmware habla directo con la API nativa del IDF); se lista como trabajo relacionado.

---

## 4. Flujo de datos end-to-end

> **Consolidado**: el flujo etapa por etapa — física → firmware → MQTT →
> ingesta → DSP → fusión multi-link → render, con el código exacto de cada
> paso — vive en **`docs/DATA-PIPELINE.md`** (fuente autoritativa). El esquema
> visual Mermaid está en `docs/HOW-IT-WORKS.md` §0 y el resumen
> arquitectónico en `docs/PROJECT-ARCHITECTURE.md`.

## 5. Tecnologías, repositorios y datasets

### 5.1 Componentes de este repositorio

| Ruta | Contenido |
|---|---|
| `src/esp32/` | Firmware ESP-IDF v5.x: `main/main.cpp` (CSI→cola→MQTT), `main/config.h` (SSID, broker, `USE_TRAFFIC_PING`, `CSI_INTERVAL_MS`), `CMakeLists.txt`, `sdkconfig.defaults` |
| `backend/` | `config.py`, `csi_packets.py`, `mqtt_subscriber.py`, `vitals_processor.py`, `link_manager.py`, `motion_analyzer.py`, `web_viewer.py`, `web_static/`, `gui.py`, `main.py`, `tests/` |
| `scripts/simulate_esp32.py` | Simulador de CSI sintético (integración sin hardware) |
| `docker-compose.yaml` + `docker/mosquitto/` | Broker local (imagen `eclipse-mosquitto:2`) |
| `DEPLOYMENT.md`, `docs/` | Guía de despliegue y esta referencia |

### 5.2 Tecnologías upstream (URLs verificadas)

| Tecnología | Repo / sitio |
|---|---|
| ESP-IDF v5.3.x (SDK, API CSI nativa) | https://github.com/espressif/esp-idf |
| Documentación ESP-IDF (ESP32-S3) | https://docs.espressif.com/projects/esp-idf/en/v5.3.1/esp32s3/ |
| Eclipse Mosquitto (broker MQTT; imagen `eclipse-mosquitto:2`) | https://github.com/eclipse/mosquitto |
| paho-mqtt (cliente Python) | https://github.com/eclipse/paho.mqtt.python |
| aiohttp (servidor HTTP + WebSocket del web viewer) | https://github.com/aio-libs/aiohttp |
| numpy | https://github.com/numpy/numpy |
| scipy (procesamiento de señales) | https://github.com/scipy/scipy |
| PyQt5 (Riverbank Computing) | https://pypi.org/project/PyQt5/ |
| matplotlib | https://github.com/matplotlib/matplotlib |
| pytest | https://github.com/pytest-dev/pytest |
| usbipd-win (USB en WSL) | https://github.com/dorssel/usbipd-win |
| Docker Desktop (motor del broker) | https://www.docker.com/products/docker-desktop/ |
| WSL2 (documentación oficial de Microsoft) | https://learn.microsoft.com/en-us/windows/wsl/ |

### 5.3 Datasets

- **No se usa ningún dataset externo.** La validación es de dos niveles:
  1. **Unit tests** (`backend/tests/`): señales CSI sintéticas con verdad conocida (60 bpm / 15 resp·min⁻¹) → 50/50 pasando; el estimador debe recuperar la frecuencia inyectada ±5 bpm y ±3 /min, y una señal plana debe dar `"-"`. La suite cubre: estimador de signos vitales, parser de paquetes, analizador de presencia/movimiento, fusionador multi-ESP32 (`link_manager`: ruteo por tópico, fusión por banda con mejor SNR, agregado conservador de presencia, expiración de enlaces, incluida la del primary sondeado por los lectores), config por env (incluido el sentinel `none` y el override de `MQTT_TOPIC`), endurecimiento de entradas del procesador, y el pipeline del web viewer.
  2. **Simulador en vivo** (`scripts/simulate_esp32.py`) → GUI.
- Para validación futura contra datos de terceros, los datasets públicos conocidos de WiFi sensing son: **UT-HAR** (reconocimiento de actividad, Yousefi et al. 2017), **NTU-Fi** (HAR y lenguaje de señas), **SignFi**, **Wiar** y **FallAF**. Ninguno está orientado a signos vitales (los papers de esa área usan capturas propias de laboratorio), así que la estrategia de este proyecto es generar los datos con el propio ESP32 y el simulador.
- Lecturas académicas del área: §3.7.

---

## 6. Referencias rápidas

- **Guía de instalación y despliegue completa (12 secciones + troubleshooting):** `DEPLOYMENT.md`
- **Resumen de arquitectura:** `docs/PROJECT-ARCHITECTURE.md`
- API de WiFi/CSI del IDF: sección *WiFi CSI* de `esp_wifi.h` (docs ESP-IDF v5.3.x, ESP32-S3)
- Filtros y espectro: documentación de `scipy.signal` (butter, sosfiltfilt, detrend)
- **Licencia del proyecto:** MIT — ver `LICENSE`

---

*Mantener este archivo sincronizado con el stack real. Última revisión: alineado con el firmware ESP-IDF v5.3.x y el backend verificado (50/50 tests, incluye web viewer).*
