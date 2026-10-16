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

El ESP32-S3 expone el CSI crudo (I/Q por subportadora) mediante la API nativa `esp_wifi_set_csi_rx_cb`; el callback entrega ~64 subportadoras en el S3 (límite por chip: 128, `CSI_MAX_SUBCARRIERS`). El firmware reduce cada paquete a amplitudes `a_k = √(I² + Q²)` — descartamos la fase porque sin calibración sufre saltos *wrap*; la amplitud basta para detectar la modulación.

**Problema inverso**: dado un tren de amplitudes `a_k[n]` muestreadas a ~10 Hz, contaminadas de ruido de radio y movimiento, estimar la frecuencia dominante dentro de cada banda fisiológica. Eso es un problema clásico de **detección de tonos en ruido**, resuelto con el aparato de Fourier (§3.3).

### 3.2 Modelo de señal

Para la subportadora `k`, cada muestra del CSI responde a:

```math
a_k[n] = C_k + B\cdot\sin(2\pi f_\text{resp} t_n + \varphi_k) + H\cdot\sin(2\pi f_\text{heart} t_n + \psi_k) + \varepsilon_k[n]
```

| Variable | Qué es | Valor típico | De dónde proviene |
|---|---|---|---|
| `a_k[n]` | amplitud de la subportadora `k` en la muestra `n` | 0–180 (uint8) | firmware: `a_k = √(I²+Q²)` con `I = csi_buf[2k]`, `Q = csi_buf[2k+1]` (int8 con signo), dentro de `wifi_csi_rx_cb()` (`main.cpp`) |
| `k` | índice de subportadora OFDM | 0–63 | `n = info->csi_len / 2` (bytes I/Q embebidos) en el callback |
| `n` | índice temporal | 0–149 | un callback CSI por paquete RX (~1 cada 100 ms, generado por el ping) |
| `t_n` | instante de la muestra `n` | segundos desde el boot | `t_us = esp_timer_get_time()` (µs); la GUI lo convierte: `t_us / 1e6` |
| `C_k` | offset estático del canal (DC) | ~30–150 | potencia media del camino de radio de esa subportadora; lo elimina `detrend` (paso 2) |
| `B`, `H` | profundidad de modulación (resp / latido) | B ≈ 1–5; H ≈ 0.1–0.5 | desplazamiento físico del tórax escalado por la respuesta del canal; H es 10–30× menor que B |
| `f_resp` | frecuencia respiratoria | 0.1–0.5 Hz | fisiología: (6–30 respiraciones/min) ÷ 60 |
| `f_heart` | frecuencia cardíaca | 0.8–2.0 Hz | fisiología: (48–120 bpm) ÷ 60 |
| `φ_k`, `ψ_k` | fase inicial por subportadora | 0–2π rad | geometría del multipath (distancias en múltiplos de λ/2 ≈ 6 cm @ 2.4 GHz) |
| `ε_k[n]` | ruido + artefactos | σ ≈ 0.05–1 | ruido de radio, AGC del receptor, movimiento del entorno |

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
- si no lo contiene, los productos oscilan y se **cancelan** (~√N·σ) → piso de ruido.

Ese contraste pico/piso es exactamente lo que explota la compuerta de SNR (paso 7 de §3.4).

**Vínculo clave con la serie**: la DFT "asume" que tus `N` muestras son un período completo de duración `T = N/fs` y calcula, numéricamente, los coeficientes de la serie de Fourier de esa señal periódica extendida. Por eso los bins caen en múltiplos de `f₀ = 1/T = fs/N` — de esa observación sale la fórmula de resolución `Δf` del paso 4.

4. **FFT — Fast Fourier Transform**: algoritmo (Cooley–Tukey, 1965) que calcula la DFT en `O(N·log N)` en vez de `O(N²)`, separando recursivamente las muestras pares de las impares. **Mismas matemáticas, computadas más rápido.** `np.fft.rfft` es la FFT especializada en entrada real: devuelve solo `k = 0 … N/2` porque con `x[n]` real se cumple `X[N−k] = X̄[k]` (la otra mitad es redundante).

Nuestro pipeline usa `|X[k]| = √(Re² + Im²)` (la "energía" presente a cada frecuencia `f_k`) y descarta la fase — coherente con lo que ya hizo el firmware al reducir cada paquete a amplitudes.

Dos limitaciones concretas de esta teoría moldean el código:

- **Fuga espectral** (*spectral leakage*): si el tono no cae exacto en un bin, su energía se reparte en los bins vecinos → ventana de Hann (paso 3).
- **Resolución de bin limitada** (`Δf`) → interpolación parabólica `δ` (paso 6).

### 3.4 El pipeline matemático, fórmula por fórmula

#### Paso 1 — Ventana deslizante

```
N = fs · window_s = 10 Hz · 15 s = 150 muestras
```

| Variable | Valor | Origen |
|---|---|---|
| `fs` | 10 Hz | `fs = 1000 / CSI_INTERVAL_MS`, con `CSI_INTERVAL_MS = 100` (`src/esp32/main/config.h`): cada ping/respuesta genera un callback CSI |
| `window_s` | 15 s | `Config.window_seconds` (`backend/config.py`, env `CSI_WINDOW_S`) |
| `N` | 150 | producto de los dos anteriores; `VitalsProcessor.capacity = round(fs · window_s)` |

Por qué 15 s: el fenómeno más lento a detectar es la respiración a 0.1 Hz → período de 10 s. La ventana debe contener **al menos un período completo** → mínimo 10 s; 15 s dan 1.5 períodos respiratorios y 12–30 períodos cardíacos. Trade-off: ventana más larga → `Δf` más fina, pero la GUI tarda más en reflejar cambios.

#### Paso 2 — Detrend (eliminación de DC y deriva)

```math
x'[n] = x[n] - (m n + b)
```

| Variable | Qué es | Origen |
|---|---|---|
| `m`, `b` | pendiente e intercepto de la recta de mínimos cuadrados ajustada a la ventana | `scipy.signal.detrend(x)` (ajuste lineal interno) |

Elimina `C_k` (el DC del modelo de §3.2) y la deriva lenta del canal. Sin esto, la energía del DC satura el bin 0 y sus vecinos, y degrada el piso de ruido de las bandas.

#### Paso 3 — Ventana de Hann

```math
w[n] = \tfrac{1}{2}\left(1 - \cos\frac{2\pi n}{N-1}\right), \quad n = 0,\dots,N-1
```

| Variable | Valor | Origen |
|---|---|---|
| `w[n]` | 0 … 1 (0 en los bordes, 1 al centro) | `np.hanning(N)` implementa exactamente esta fórmula |

Por qué: cortar la señal de punta a punta (ventana rectangular) equivale, en frecuencia, a convolucionar el espectro con un *sinc* cuyo primer lóbulo lateral está solo **−13 dB** abajo — la respiración (fuerte) "embadurnaría" al latido (débil), que está apenas una octava arriba. Hann baja los lóbulos laterales a **−31 dB** con caída de 18 dB/octava, al precio de ensanchar el lóbulo principal ~2× (costo asumible porque las bandas fisiológicas están bien separadas).

#### Paso 4 — FFT (la DFT aplicada)

```math
X[k] = \sum_n x[n]\,w[n]\,e^{-i2\pi kn/N} \quad |X[k]| = \sqrt{\operatorname{Re}^2 + \operatorname{Im}^2}
```

```math
f_k = \frac{k\cdot f_s}{N} \quad \Delta f = \frac{f_s}{N} = \frac{10}{150} \approx 0.067\ \mathrm{Hz}
```

| Variable | Valor | Origen |
|---|---|---|
| `k` | 0–75 (rfft de N = 150) | índice del bin; `np.fft.rfftfreq(N, d=1/fs)` devuelve los `f_k` |
| `X[k]` | magnitud espectral | `np.abs(np.fft.rfft(x·w))` |
| `Δf` | ≈ 0.067 Hz ⇔ ≈ 4 bpm @ 60 bpm | DFT asume `T = N/fs` como período → bins = armónicos de `f₀ = 1/T` (§3.3) |

`Δf` cruda significa: sin refinamiento, el corazón solo se puede medir en escalones de ~4 bpm. De eso se encarga el paso 6.

#### Paso 5 — Mejor subportadora por banda

Para cada banda fisiológica se recorren las ~64 subcarriers y se retiene la de mayor SNR de pico dentro de la banda (con la métrica del paso 7). Racional: el tórax modula fuerte solo algunos caminos de radio; **promediar todas las subportadoras diluye la señal** con las que solo traen ruido.

#### Paso 6 — Interpolación parabólica del pico (el "delta" `δ`)

Problema: el pico verdadero casi nunca cae exacto en un bin; `Δf ≈ 0.067 Hz` limita la resolución.

Truco: cerca del máximo, el lóbulo en escala logarítmica es casi una parábola (el logaritmo de una campana gaussiana es *exactamente* una parábola). Se ajusta la parábola que pasa por el pico y sus dos vecinos, con `l = ln|X|`:

```math
\text{puntos: } (-1,\,l_-),\;(0,\,l_0),\;(1,\,l_+) \quad (l_0 = \ln\text{ del bin pico})
```

```math
p(x) = ax^2 + bx + c \quad a = \tfrac{1}{2}(l_- - 2l_0 + l_+) \quad b = \tfrac{1}{2}(l_+ - l_-) \quad c = l_0
```

El vértice de una parábola está en `x* = −b/(2a)`, entonces:

```math
\delta = -\frac{b}{2a} = \frac{\tfrac{1}{2}(l_- - l_+)}{l_- - 2l_0 + l_+} \quad f_\text{peak} = f[k^*] + \delta\cdot\Delta f
```

| Variable | Qué es | Origen |
|---|---|---|
| `l₀`, `l₋`, `l₊` | logaritmos de las magnitudes del bin pico y sus dos vecinos | espectro del paso 4 |
| `a`, `b` | coeficientes de la parábola (en un máximo, `a < 0`) | resolver el sistema lineal de los 3 puntos (derivación arriba) |
| `δ` | desplazamiento sub-bin del vértice, acotado a [−1, +1] | fórmula del vértice `−b/(2a)`; la cota existe porque el pico real debe caer entre los bins vecinos |
| `f_peak` | frecuencia fina del pico | `f[k*] + δ·Δf` |

Efecto: la resolución pasa de ~4 bpm a **~1 bpm** (por eso el test unitario con 60 bpm sintéticos tolera ±5 bpm con margen). Referencia de la derivación y su justificación en dominio log: J. O. Smith III, *Quadratic Interpolation of Spectral Peaks* (§3.7).

#### Paso 7 — Compuerta de calidad SNR

```math
\mathrm{SNR}_{\mathrm{dB}} = 20\cdot\log_{10}\!\left(\frac{S_\text{pico}}{S_\text{mediana}}\right)
```

| Variable | Qué es | Origen |
|---|---|---|
| `pico` | máxima magnitud espectral dentro de la banda | paso 4, máximo sobre los bins de la banda |
| `mediana` | piso de ruido robusto | mediana de las magnitudes dentro de la banda; se usa la mediana y no la media porque la media queda contaminada por el propio pico |
| el factor `20` | conversión de razón de amplitudes a dB | potencia ∝ amplitud² ⇒ 10·log₁₀(P/P₀) = 20·log₁₀(A/A₀) |
| umbral 6 dB | ⇔ pico ≥ 2× el piso de ruido | `10^(6/20) ≈ 2.0`; configurable con `CSI_MIN_SNR_DB` (`config.py`) |

Si `SNR_dB < 6`, la GUI muestra "-" en lugar de un número basura: mejor no mostrar nada que mostrar ruido.

#### Paso 8 — Filtro Butterworth para graficar (no para estimar)

```
|H(ω)| = 1 / √(1 + (ω/ω_c)^(2n))          (prototipo; n = 3)
```

| Variable | Valor | Origen |
|---|---|---|
| `n` | 3 (orden del filtro) | código: `sps.butter(3, [lo, hi], …)`; mayor n ⇒ flancos más empinados |
| `lo`, `hi` | bordes de cada banda | fisiología ÷ 60 (§3.2) |
| forma `sos` | cascada de secciones de segundo orden | estabilidad numérica (`output='sos'`) |
| `sosfiltfilt` | filtrado hacia adelante + hacia atrás | respuesta de **fase cero**: la forma de onda mostrada no se distorsiona en el tiempo |

#### Paso 9 — Conversión final

```
bpm = f_peak · 60            respiraciones/min = f_peak · 60
```

El `·60` convierte ciclos por segundo (Hz) a eventos por minuto — la misma fórmula que definió las bandas: `banda_Hz = ritmo_por_minuto / 60`.

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

## 4. Flujo de datos end-to-end (el correcto, código real)

```
┌─────────────────────── ESP32-S3 (firmware, src/esp32) ───────────────────────┐
│ esp_ping → gateway (100 ms)  ⇒  llega un frame RX                            │
│   └─ wifi_csi_rx_cb(): lee csi_buf, calcula a_k = √(I²+Q²)                   │
│        └─ xQueueSend (FreeRTOS, depth 32)  ← desacopla el callback WiFi      │
│             └─ publisher_task: arma CSV y esp_mqtt_client_publish()           │
└────────────────────────────── MQTT topic: esp32/csi/raw ───────────────────────┘
                                     │  payload: "t_us,rssi,n,seq,a0,...,aN"
                                     ▼
              Mosquitto 2.x (contenedor Docker en Windows, puerto 1883)
                                     │
                                     ├─ rama paralela (sin Qt): web_viewer.py
                                     │  (aiohttp, WebSocket) — consumidor paho
                                     │  propio; snapshot ~1 Hz a cada navegador
                                     │  (teléfonos) en la LAN
                                     │
                                     ▼
┌────────────────────── Backend Python (Windows, venv) ────────────────────────┐
│ MultiLinkSubscriber (link_manager.py, hilo de red paho)                      │
│   suscribe esp32/+/csi/raw + esp32/csi/raw (legacy)                          │
│   └─ parse_csi_payload() → CsiPacket → queue.Queue(1024), etiquetado         │
│      como (link_id, packet)  ← desacopla red/consumidores                    │
│        └─ QTimer de la GUI (5 Hz): links.drain_and_feed() drena la cola      │
│             └─ LinkManager: VitalsProcessor + MotionAnalyzer por link        │
│                (pipelines aislados; deque deslizante 150 por link)           │
│                └─ cada 1 s: estimate()  [§3.4: detrend→Hann→FFT→δ→SNR]       │
│                     └─ fusión: max SNR por banda, presencia conservadora     │
│                          └─ PyQt5: grilla 2×3 (trazas + heatmap +            │
│                             espectrograma + energía de movimiento)           │
│                             + fila Body + BPM / resp·min⁻¹ + SNR             │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Formato del payload** (CSV ASCII, ~64 subportadoras ≈ 450 bytes @ 10 Hz ≈ 4.5 kB/s — trivial para Mosquitto):
```
t_us,rssi,n,seq,a0,a1,...,aN
1717000000123456,-52,64,42,178,176,171,169,...
```

**Desacoples de threading** (los dos puntos donde el sistema protege la integridad):
1. Firmware: el callback CSI corre en el contexto de WiFi → pasa todo a una cola FreeRTOS; la publicación MQTT corre en su propia task.
2. Backend: paho corre su loop en un hilo → solo hace `put_nowait` en una `queue.Queue`; el hilo de la GUI (Qt) drena con `get_nowait`. Nunca se toca Qt desde el hilo de red.

**Verificación sin hardware**: `scripts/simulate_esp32.py` publica exactamente el mismo formato CSV con señales sintéticas (~66 bpm / 18 resp·min⁻¹), para probar toda la cadena menos el ESP32.

---

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
