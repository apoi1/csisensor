# Guía de despliegue — ESP32-S3 WiFi-CSI Vital Signs

> Términos acuñados se citan en inglés sin traducir (CSI, RSSI, MQTT, broker,
> firewall, venv); la prosa es en español. Comandos verbatim.

Setup end-to-end del pipeline:

```
ESP32-S3 ──(MQTT: esp32/csi/raw)──► Mosquitto (Docker Desktop, Windows) ◄── backend Python + GUI PyQt5 (Windows)
```

> **Aviso**: investigación/experimental. No es un dispositivo médico.

## Reparto de capas

| Capa | Dónde | Qué corre |
|---|---|---|
| Windows | Docker Desktop | broker Mosquitto (puerto 1883) |
| Windows | venv Python 3.10+ en `backend/` | suscriptor + procesador FFT + GUI PyQt5 |
| WSL (Ubuntu) | ESP-IDF v5.3.x | build, flash y monitor del firmware (vía usbipd-win) |

## 1. Requisitos previos

- Windows 10/11 con **WSL2** (Ubuntu 22.04+, **shell fish** — los comandos WSL de esta guía usan sintaxis fish)
- **Docker Desktop** para Windows (integración WSL2 habilitada)
- **Python 3.10+** en Windows (instalador de python.org, "Add to PATH")
- Placa de desarrollo ESP32-S3 con cable USB (con datos)
- Una red WiFi de **2.4 GHz** (la ESP32-S3 no ve 5 GHz)

> **WiFi NO es internet.** El sistema necesita un **access point** WiFi
> (un router, un hotspot, cualquier cosa que cree una red local) — NO
> necesita internet. Todo el pipeline (ESP32 → MQTT → backend → GUI →
> web viewer) corre en la red local: cero bytes llegan a la WAN. Si el
> lugar no tiene WiFi, sirve el hotspot del teléfono (crea una red local
> sin gastar datos móviles — la radio del teléfono actúa de mini router;
> los dispositivos conectados se hablan localmente). La ESP32 debe unirse
> a ALGUNA red WiFi porque la CSI mide el canal de radio entre la ESP32 y
> el access point; sin enlace de radio no hay nada que medir. Para
> desplegar sin Docker, ver `docs/DEPLOYMENT-ALTERNATIVES.md`.

## 2. Broker (Mosquitto vía Docker)

Desde la raíz del repo (WSL o PowerShell — Docker Desktop maneja ambos):

```console
docker compose up -d          # levanta mosquitto en 1883
docker compose logs mosquitto # verificar: "mosquitto version 2.x running"
```

El broker también escucha en **9001 (MQTT sobre WebSockets)** — mapeado por
docker-compose y habilitado en `mosquitto.conf`. El web viewer incluido (§9)
no lo usa; está para futuros clientes de navegador que hablen directo con el
broker. La imagen del broker **bakea `mosquitto.conf` en el build** (sin bind
mount en runtime), así que `docker compose up` funciona desde PowerShell y
desde WSL; tras editar `mosquitto.conf`, aplicá el cambio con
`docker compose up -d --build mosquitto`.

Publicá un mensaje de prueba para validar la cadena:

```console
docker exec -it wifisensing_mosquitto mosquitto_pub -t esp32/csi/raw -m "0,-50,2,0,10,20"
```

### Habilitar el broker en el firewall de Windows (PowerShell admin)

La ESP32 conecta desde la LAN, así que hay que permitir el TCP 1883 entrante —
acotado a la subred local y al perfil Private, para que los puertos solo se
abran a dispositivos de la misma subred y queden callados en redes que Windows
marca Public:

```powershell
New-NetFirewallRule -DisplayName "Mosquitto 1883 (dev)" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -RemoteAddress LocalSubnet -Profile Private
```

Alternativa one-shot, paste-safe — recrea AMBAS reglas dev (esta y la del
viewer de §9) con el mismo scoping; seguro de re-correr (idempotente):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\firewall-rules.ps1
```

Anotá la **IP LAN del host Windows** (`ipconfig` → IPv4 del adaptador Wi-Fi).
Esa es la IP para `MQTT_BROKER_URI` en la config del firmware y para todo
dispositivo excepto el propio backend Windows (que usa `localhost`).

> Las reglas de firewall exigen que la red esté marcada **Private** en
> Windows (Configuración > Red > Perfil de red); en redes Public las reglas
> quedan inactivas — que es el default seguro en Wi-Fi desconocidas.

## 3. ESP-IDF (WSL)

> Los comandos WSL de esta guía son **fish** (las diferencias con bash se
> aclaran inline — `&&`, globs y `$USER` son idénticos en ambos).

```fish
sudo apt-get update
sudo apt-get install -y git wget flex bison gperf python3 python3-pip python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
mkdir -p ~/esp && cd ~/esp
git clone -b v5.3.1 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32s3
source export.fish     # configura el entorno en esta pestaña (script fish nativo que trae ESP-IDF)
```

Abreviatura fish de una sola vez, para que un `idfenv` solo configure el
entorno en cualquier pestaña nueva:

```fish
abbr --add idfenv 'source ~/esp/esp-idf/export.fish'
```

> En bash la única diferencia es `source export.fish` → `. ./export.sh`;
> todo lo demás de arriba es idéntico.

> La versión importa: el firmware apunta a la API **v5.x** de ESP-IDF
> (config anidada de broker en esp-mqtt, `esp_wifi_set_csi_rx_cb`). La API
> CSI es nativa de ESP-IDF; no hace falta ningún componente externo. El flag
> CSI requerido ya está fijado en `src/esp32/sdkconfig.defaults`
> (`CONFIG_ESP_WIFI_CSI_ENABLED=y`) — no hace falta paso de menuconfig.

## 4. Puerto serie USB desde WSL (usbipd-win)

WSL2 no ve dispositivos USB nativamente; attach de la placa con usbipd
(PowerShell admin):

```powershell
winget install usbipd
usbipd list                     # buscar el BUSID de tu placa, p. ej. 2-3
usbipd bind --busid 2-3         # una vez
usbipd attach --wsl --busid 2-3
```

De vuelta en WSL:

```fish
ls /dev/ttyACM*                 # esperado: /dev/ttyACM0
sudo usermod -aG dialout $USER  # luego cerrar y reabrir WSL
```

## 5. Configurar el firmware

**Opción A — provisioning en runtime (recomendada, sin rebuild):** tras el
flash de una sola vez del firmware con soporte NVS (§6), cargá las
credenciales por puerto serie USB:

```bash
# Linux / WSL / Fedora (autodetecta el puerto serie):
python ../scripts/provision-esp32.py --ssid <SSID> --pass <PASS> --broker mqtt://<IP-LAN>:1883

# Ver el estado actual:
python ../scripts/provision-esp32.py --status

# Limpiar NVS (volver a los valores compilados):
python ../scripts/provision-esp32.py --clear
```

30 segundos por cambio de red — sin `idf.py build`, sin re-flash, sin WSL.
El binario queda libre de credenciales y compartible.

**Opción B — fallback compilado (la vía original):** si preferís los
#defines (p. ej. para un despliegue fijo), editá `src/esp32/main/config.h`:

| Define | Valor |
|---|---|
| `WIFI_SSID` / `WIFI_PASS` | credenciales de tu WiFi 2.4 GHz |
| `MQTT_BROKER_URI` | `mqtt://<IP-LAN-de-Windows>:1883` — NO localhost |
| `USE_TRAFFIC_PING` | `1` (auto-ping al gateway a 10 Hz para generar tráfico RX) |

## 6. Build, flash, monitor

```fish
cd ~/dev/projects/c++/sensorproject/src/esp32
idf.py set-target esp32s3
idf.py build
idf.py -p /dev/ttyACM0 flash monitor
```

Esperado en el monitor:

```
I (xxxx) csi_main: WiFi connected, IP: 192.168.1.42
I (xxxx) csi_main: MQTT client started -> mqtt://192.168.1.50:1883
I (xxxx) csi_main: MQTT connected
I (xxxx) csi_main: traffic ping to gateway started (every 100 ms)
I (xxxx) csi_main: csi: captured=120 qfull=0 published=120 failed=0
```

**Flashear desde Windows** (recomendado cuando el USB nativo del S3
re-enumera y tumba el túnel usbipd — ver §11): detach de la placa
(`usbipd detach --busid <X-X>`, PowerShell admin) y correr
`powershell -ExecutionPolicy Bypass -File .\scripts\flash-board.ps1`
(también hay un wrapper paste-safe `flash-board.cmd`). Autodetecta el COM y
acepta `-FlashSize` — default `4MB`, igual a `src/esp32/sdkconfig.defaults`;
esta placa trae 16 MB, así que subí ambos juntos si algún día necesitás el
espacio.

## 7. Verificar el stream CSI

Desde WSL (el broker corre del lado Windows, así que usá la IP del host
Windows):

```fish
sudo apt-get install -y mosquitto-clients
set BROKER (grep nameserver /etc/resolv.conf | awk '{print $2}')
mosquitto_sub -h "$BROKER" -t esp32/csi/raw -C 3
```

> Fish cambia la sustitución de comandos `$( ... )` por `( ... )`; la
> expansión de `$BROKER` y el quoting funcionan igual.

Payload esperado (t_us, rssi, n, seq, amplitudes):

```
1717000000123456,-52,64,42,178,176,171,169,...
```

> Con networking en modo mirror de WSL (`networkingMode=mirrored`),
> `localhost` también funciona — **solo Windows 11 22H2+**. En Windows 10
> este modo no está soportado (WSL corre en NAT), así que seguí usando el
> camino `BROKER` / IP-LAN-de-Windows de arriba.

## 8. Backend + GUI (Windows)

```powershell
cd \\wsl.localhost\Ubuntu\home\tilin\dev\projects\c++\sensorproject\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --host localhost
```

> **Dónde vive el repo (sin copiar nada):** el árbol vive en el
> **filesystem de WSL** (`~/dev/projects/c++/sensorproject` en Ubuntu)
> porque ahí se compila el firmware; Windows llega a ese mismo árbol por el
> share de red `\\wsl.localhost\Ubuntu\...` — ese es el directorio que entra
> el `cd` de arriba. `requirements.txt` es `backend/requirements.txt` dentro
> de ese árbol: nada se copia a ningún lado; una vez dentro de `backend/`,
> un `pip install -r requirements.txt` normal lo lee a través del share. El
> `.venv` que se crea es un **venv de Windows** (binarios Windows,
> `Scripts\`) almacenado en el disco WSL — solo lo usa el Python de Windows,
> y el `pip install` único corre más lento por el share que en NTFS nativo
> (las lecturas en runtime son chicas y están bien). Los venvs nunca son
> portables entre OS: un **venv Linux separado** dentro de WSL solo hace
> falta para trabajo headless ahí (`pytest`, `web_viewer.py` — nunca
> importan Qt, así que PyQt5 no hace falta de ese lado).

Si `Activate.ps1` se bloquea con "is not digitally signed": Windows trata el
share `\\wsl.localhost` como zona remota, así que hasta una política
`RemoteSigned` bloquea scripts ahí. Fix más simple — **saltear la activación
por completo** y llamar al intérprete del venv directo; cada comando de esta
guía se vuelve `.\.venv\Scripts\python.exe <script>` (p. ej.
`.\.venv\Scripts\python.exe main.py --host localhost`,
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`).
Alternativa, solo para la ventana actual:
`Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force` y luego
activar normal.

### Dry-run SIN hardware (primero recomendado)

En una segunda terminal (mismo venv), publicá CSI sintético:

```powershell
python ..\scripts\simulate_esp32.py --host localhost --scenario moving
```

Escenarios: `resting` (sujeto en reposo, ~66 BPM / ~18 resp/min), `moving`
(agrega episodios periódicos de movimiento grueso), `absent` (sala vacía).

El GUI debe mostrar **~66 BPM / ~18 resp/min** y ambas ondas en ~15 s, más la
**fila Body** siguiendo el escenario: `Still` (resting), `Moving` durante los
episodios (moving), `Absent` (absent). La columna derecha muestra los paneles
físicos (heatmap de subportadoras, espectrograma, traza de energía de
movimiento).

### Ajustar presencia/movimiento y ranging RSSI (opcional)

Los umbrales de la fila Body y la estimación de distancia de enlace RSSI son
configurables por variables de entorno (fórmulas y procedimientos de
calibración en `docs/SIGNAL-MODELING.md`):

| Variable de entorno | Default | Significado |
|---|---|---|
| `CSI_ABSENT_STD` | `0.15` | std de la ventana debajo de esto = sala vacía (`Absent`) |
| `CSI_MOVING_RMS` | `1.5` | RMS de la banda de movimiento 0.5–3.0 Hz encima de esto = `Moving` |
| `CSI_RSSI_REF_DBM` | `-52.0` | RSSI de referencia `R0` medido a `d0` |
| `CSI_REF_DISTANCE_M` | `1.0` | distancia de referencia `d0` |
| `CSI_PATH_LOSS_N` | `3.0` | exponente de path loss log-distance `n` |

Los knobs de conexión también son overridables por entorno (`MQTT_HOST`,
`MQTT_PORT`, `MQTT_TOPIC`): un `MQTT_TOPIC` explícito **reemplaza toda la
lista de suscripción** por ese único tópico/patrón — el contrato de base,
restaurado por el ciclo de review del 2026-10-14 — mientras que sin definir
(o el default legacy) se mantienen los patrones multi-enlace
(`esp32/+/csi/raw` + el tópico plano). El flag CLI `--topic` siempre gana al
entorno.

Mientras no esté calibrado podés apagar por completo la estimación de
distancia: poné `CSI_RSSI_REF_DBM` (o `CSI_REF_DISTANCE_M`) vacío o `none` —
el GUI entonces muestra `—` en la distancia de enlace en vez de una suposición
sin calibrar.

Calibración del ranging RSSI: medí `R0` a una distancia conocida `d0`
(p. ej. 1 m) y configurá ambos; ver `docs/SIGNAL-MODELING.md` para un ajuste
a dos puntos de `n`.

## 9. Web viewer (teléfonos / tablets)

Las mismas estimaciones también se sirven a cualquier navegador de la LAN —
sin instalar nada en el teléfono. El viewer es un consumidor MQTT
independiente, así que funciona con o sin el GUI de escritorio corriendo.

Su única dependencia nueva es **aiohttp** (servidor HTTP + WebSocket,
Apache 2.0; <https://docs.aiohttp.org/>) — ya cubierta por
`pip install -r requirements.txt`, nada extra que instalar. La página misma
no trae cero assets externos (sin CDN), así que funciona en LANs sin
internet.

En la máquina que alcanza al broker (mismo venv que §8):

```powershell
python web_viewer.py --broker <IP-BROKER> --host 0.0.0.0 --port 8080
```

- `--broker`: dónde vive el MQTT (`localhost` si esta máquina corre Docker).
- `--host 0.0.0.0` publica la página a la LAN (default); `--port 8080`.
- Abrí `http://<IP-LAN-PC>:8080` en el teléfono, misma Wi-Fi.

Habilitá el puerto en el firewall de Windows una vez (PowerShell admin):

```powershell
New-NetFirewallRule -DisplayName "CSI Web Viewer 8080 (dev)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -RemoteAddress LocalSubnet -Profile Private
```

(Si corriste `scripts/firewall-rules.ps1` en §2, esta regla ya existe — ambas
están acotadas a `LocalSubnet` + perfil `Private`, así que marcá la red
Private o no se abre nada.)

**Alternativa portable (sin Python en la PC destino)**: compilá un exe
standalone con PyInstaller y corrélo en cualquier lado:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --onefile --name csi-web-viewer --add-data "web_static;web_static" web_viewer.py
dist\csi-web-viewer.exe --broker <IP-BROKER> --host 0.0.0.0 --port 8080
```

Solo UN web viewer puede sostener el puerto 8080 a la vez — el script Python
o el exe, nunca ambos. El GUI de escritorio (§8) es un consumidor
independiente y no sirve la página del teléfono. Los navegadores del teléfono
pueden forzar HTTPS en direcciones tipeadas — tipeá el `http://<IP>:8080`
completo (o deshabilitá la opción "usar siempre conexiones seguras").

La página no necesita internet (sin CDN): tiles de corazón/respiración/estado
corporal/distancia de enlace, un plot de tendencia de 10 minutos y las últimas
ondas filtradas, con reconexión automática. Como todo acá: herramienta de
investigación, no un dispositivo médico.

## 10. Test en vivo con la ESP32-S3

1. `python main.py --host localhost` y dejá `idf.py monitor` corriendo.
2. El sujeto se sienta quieto, a 0.5–2 m de la ESP32, con línea de vista.
3. Tras ~15 s la ventana se llena y aparecen las estimaciones.
4. Artefactos de movimiento: un solo movimiento resetea las estimaciones por
   unos segundos, y la **fila Body** pasa a `Moving` mientras te movés.

Para lecturas estables y el protocolo de validación empírica — falsificación
de sala vacía, phase-lock de respiración controlada contra un metrónomo,
comparación con referencia y repetibilidad — ver
**docs/VALIDATION-PROTOCOL.md**.

### Setup multi-nodo (multi-ESP32)

Cada nodo publica a su tópico por dispositivo (`esp32/<id>/csi/raw`, id =
últimos 3 bytes de su MAC), así que flasheá tantas ESP32 como quieras — sin
configuración por nodo. El backend se suscribe a `esp32/+/csi/raw` más el
tópico plano legacy y fusiona los enlaces por banda (gana el mejor SNR; ver
`docs/SIGNAL-MODELING.md` §8).

Dry-run de dos enlaces sin hardware — dos terminales (mismo venv):

```powershell
python ..\scripts\simulate_esp32.py --host localhost --device-id a1b2c3 --scenario resting
python ..\scripts\simulate_esp32.py --host localhost --device-id d4e5f6 --scenario resting
```

La barra de estado del GUI muestra entonces `links a1b2c3, d4e5f6` y las
estimaciones se fusionan solas; la línea de meta de la página web muestra
`links 2`.

## 11. Troubleshooting

| Síntoma | Causa / fix |
|---|---|
| El teléfono no abre la página del viewer | ¿misma Wi-Fi? ¿`http://<IP-LAN-PC>:8080` correcta? ¿regla de firewall de Windows para 8080 (§9)? ¿`web_viewer.py` sigue corriendo? |
| `ls /dev/ttyACM*` vacío | Re-correr `usbipd attach`; verificar que el cable sea de datos; `usbipd list` debe mostrar "Attached". |
| El WiFi conecta y reconecta para siempre | SSID solo 5 GHz — usar 2.4 GHz; verificar credenciales. |
| Nunca aparece `MQTT connected` | El URI del broker usa `localhost` (solo válido en la propia Windows); verificar la regla de firewall del 1883; Docker Desktop debe estar corriendo. |
| MQTT conectado pero no hay datos | Mismatch de tópico (default `esp32/csi/raw`); verificar con `docker compose logs mosquitto`. |
| Fluyen datos pero el GUI está vacío | Host del backend mal puesto: en Windows usar `localhost`; si el backend corre dentro de WSL usar `$BROKER` del paso 7. |
| `captured` crece, `published` queda en 0 | Los publish fallan — broker inalcanzable; verificar el contador `failed` y los logs del broker. |
| `captured` queda en 0 | No hay tráfico RX: mantener `USE_TRAFFIC_PING 1`, o correr `ping -t <IP-ESP32>` desde cualquier máquina de la red. |
| Error de build dentro de `start_traffic_ping` | Tu API de ping del IDF difiere — poner `USE_TRAFFIC_PING 0` en `config.h` y usar un ping externo. |
| BPM muestra "-" | SNR debajo del umbral: acortar distancia, eliminar movimiento, probar `--window 20` para una ventana más larga. |
| Fila Body clavada en "waiting for data..." | La ventana de movimiento (15 s) todavía se está llenando, o el stream CSI no llega al backend; verificar la tasa pkt/s en la barra de estado. |
| `idf.py: command not found` | Correr `idfenv` (o `source ~/esp/esp-idf/export.fish`) en esta pestaña — en bash: `. ~/esp/esp-idf/export.sh`. |
| El flash falla con `No serial data received` y luego `/dev/ttyACM0` desaparece | El USB nativo del S3 re-enumera en cada reset del chip, lo que tumba el túnel usbipd a mitad de flash. Flashear desde Windows (sin túnel): instalar esptool en el venv (`.\.venv\Scripts\python.exe -m pip install esptool`), `usbipd detach --busid <X-X>`, y luego `powershell -ExecutionPolicy Bypass -File .\scripts\flash-board.ps1` (autodetecta el COM). |
| esptool desde Windows también dice `No serial data received` en COM3 | La placa no tiene circuito de auto-download: nunca entra en modo descarga sola. Entrada manual: mantener **BOOT**, tocar **RST**, soltar **BOOT** — la placa re-enumera como unidad compuesta JTAG/serie con un COM nuevo, queda en modo descarga ROM esperando, y `flash-board.ps1` detecta esa enumeración y flashea con `--before no-reset`. Tras el flash, tocar **RST** si la app no arranca sola. |

## 12. Notas de seguridad

- `mosquitto.conf` permite conexiones **anónimas**: solo uso LAN/dev. Para
  cualquier uso compartido, agregar `password_file` y
  `allow_anonymous false` (el README del kit portable lo repite antes de
  cualquier exposición más amplia).
- Las reglas de firewall dev (`scripts/firewall-rules.ps1`) están acotadas a
  `-RemoteAddress LocalSubnet -Profile Private`: solo dispositivos de la
  misma subred, inactivas en redes marcadas Public.
- Las credenciales WiFi viven en `config.h` — nunca commitear las reales;
  mantener una copia privada o inyectarlas desde tu sistema de build.
