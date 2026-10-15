# Deployment alternativos — sin Docker, multiplataforma

> **Qué es este documento.** Las formas de correr el sistema en cada
> plataforma, ordenadas de más simple a más pesada, con el consumo real
> de cada opción. El Docker path queda documentado en `DEPLOYMENT.md`
> §2; acá están las alternativas nativas. Para la guía específica del
> ThinkPad X230 con Fedora, ver §3 de este doc.

---

## 1. El broker MQTT: Docker vs nativo (la decisión que más RAM ahorra)

Mosquitto pesa **~3 MB de RAM**. Docker Desktop en Windows corre una VM
Linux completa: **1–2 GB de RAM** constante. Estás pagando 2 GB para
correr un proceso de 3 MB.

| Opción | RAM | CPU | Dónde sirve |
|---|---|---|---|
| **Mosquitto nativo** | ~3 MB | ~0% | Windows, Linux, macOS |
| Docker Desktop (WSL2) | 1–2 GB | moderada | Windows con WSL2 |
| Docker en Linux | ~100 MB | baja | Fedora/Ubuntu nativo |
| Kit portable (mosquitto.exe) | ~3 MB | ~0% | cualquier Windows |

**Recomendación**: si el hardware es limitado (X230, netbook, etc.),
usá mosquitto nativo. Si tenés RAM de sobra y ya usás Docker para otras
cosas, el Docker path funciona igual.

### Instalar mosquitto nativo por plataforma

```bash
# Fedora / Ubuntu / Debian:
sudo dnf install mosquitto        # Fedora
sudo apt install mosquitto        # Ubuntu/Debian

# macOS:
brew install mosquitto

# Windows:
# Descargar de https://mosquitto.org/download/ → "Windows" → installer o ZIP
# Extraer en C:\mosquitto\ (o donde quieras)
```

### Arrancar el broker nativo (con la config del proyecto)

```bash
# Desde la raíz del repo — la config del Docker sirve para nativo también:
mosquitto -c docker/mosquitto/mosquitto.conf
# → "mosquitto version 2.x running" en el puerto 1883

# En background:
mosquitto -c docker/mosquitto/mosquitto.conf &
```

**Nota**: el `mosquitto.conf` del repo ya tiene `allow_anonymous true`
(uso en LAN de laboratorio). Para uso compartido, ver `DEPLOYMENT.md` §12.

---

## 2. Matriz de compatibilidad por plataforma

| Plataforma | Host (broker + backend) | GUI (PyQt5) | Web viewer (browser) | Provisionar ESP32 | Consumo total |
|---|---|---|---|---|---|
| **Windows** | ✓ Docker o mosquitto nativo | ✓ nativo | ✓ | ✓ pyserial (COM) | ~200 MB sin Docker |
| **Linux (Fedora)** | ✓ mosquitto nativo | ✓ nativo (X11) | ✓ | ✓ pyserial (`/dev/ttyACM0`) | ~200 MB |
| **macOS** | ✓ mosquitto nativo (`brew`) | ✓ nativo | ✓ | ✓ pyserial (`/dev/cu.SLAB_USBtoUART`) | ~200 MB |
| **Android** | ⚠️ Termux (experimental, sin GUI) | ✗ | ✓ browser | ⚠️ USB-OTG | ~50 MB (solo viewer) |
| **iOS** | ✗ | ✗ | ✓ browser (Safari) | ✗ | 0 MB (viewer) |

### La clave: el web viewer ya ES multiplataforma

El `web_viewer.py` sirve una página HTML pura — **cero CDN, cero app
install, cero dependencias** — a cualquier browser en la red local.
Eso significa que Android, iOS, cualquier laptop, cualquier tablet:
abren `http://<IP-del-host>:8080` y ven los signos vitales en tiempo
real. El host puede ser Windows, Linux o macOS; los viewers no
necesitan nada instalado.

---

## 3. Guía zombie: ThinkPad X230 con Fedora

> Tu X230: ~4–8 GB RAM, CPU i5 de 3ª gen. El stack completo cabe en
> ~180 MB. Sin Docker, sin WSL, sin VM. Todo nativo.

### Setup inicial (una sola vez, con internet, ~10 minutos)

```bash
# 1. Paquetes del sistema:
sudo dnf install -y git python3 python3-pip mosquitto

# 2. Clonar el repo:
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/apoi1/csisensor.git
cd csisensor

# 3. Venv del backend:
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pyserial

# 4. Firewall (una vez por máquina):
sudo firewall-cmd --add-port=1883/tcp --permanent   # broker MQTT
sudo firewall-cmd --add-port=8080/tcp --permanent   # web viewer
sudo firewall-cmd --reload

# 5. Verificar que funciona (SIN hardware):
mosquitto -c ../docker/mosquitto/mosquitto.conf &
python main.py --host localhost &
sleep 2
python ../scripts/simulate_esp32.py --host localhost --scenario resting
# → en ~15 s el GUI muestra ~66 BPM / ~18 resp/min
# Si ves esos números: la laptop está lista.

# 6. Limpiar (Ctrl+C en el simulador, luego):
kill %1 %2 2>/dev/null; true
```

### Cada vez que llegás a presentar (~2 minutos)

```bash
cd ~/dev/csisensor/backend
source .venv/bin/activate

# 1. Saber tu IP en esta red:
ip addr show wlan0 | grep "inet "
# → ej: inet 192.168.1.42/24 … esa es tu IP (192.168.1.42)

# 2. Provisionar la ESP32 para esta red (30 s):
python ../scripts/provision-esp32.py \
    --ssid WIFI_DEL_LUGAR --pass CLAVE \
    --broker mqtt://192.168.1.42:1883

# 3. Broker (nativo, ~3 MB):
mosquitto -c ../docker/mosquitto/mosquitto.conf &

# 4. GUI (datos reales de la placa):
python main.py --host localhost

# 5. (Opcional) Viewer para celulares/tablets:
python web_viewer.py --broker localhost --host 0.0.0.0 --port 8080
# → cualquier dispositivo en la misma Wi-Fi: http://192.168.1.42:8080
```

### Al volver a casa

```bash
# Mismo paso 2 con tu red de casa (30 s). Nada más.
python ../scripts/provision-esp32.py \
    --ssid TU_WIFI --pass TU_CLAVE \
    --broker mqtt://<IP-casa>:1883
```

### Consumo real en el X230

| Proceso | RAM | CPU |
|---|---|---|
| mosquitto nativo | ~3 MB | ~0% |
| Python backend + PyQt5 GUI | ~150 MB | 1 Hz (la FFT es trivial) |
| Web viewer (aiohttp) | ~20 MB | ~0% |
| **Total** | **~180 MB** | **el X230 lo maneja sobrado** |

### Lo que NO necesitas en el X230

| No necesitas | Por qué | Ahorro |
|---|---|---|
| Docker | mosquitto nativo = 3 MB | 1–2 GB RAM |
| ESP-IDF / idf.py | el firmware ya está flasheado desde el PC | ~2 GB disco |
| WSL | Fedora ES Linux — USB serial nativo (`/dev/ttyACM0`) | toda la VM |
| Windows venv | el venv Linux es directo | complejidad |

### Troubleshooting rápido (X230/Fedora)

| Problema | Solución |
|---|---|
| `mosquitto: command not found` | `sudo dnf install mosquitto` |
| `Permission denied: /dev/ttyACM0` | `sudo usermod -aG dialout $USER` + cerrar y reabrir sesión |
| GUI no aparece | `echo $DISPLAY` debe mostrar algo; si está vacío: X11, no Wayland en la sesión |
| `pip install` falla | `pip install --upgrade pip` primero |
| Firewall bloquea | `sudo firewall-cmd --list-ports` para ver qué está abierto |

---

## 4. macOS (resumen — 5 minutos)

```bash
brew install mosquitto python git
git clone https://github.com/apoi1/csisensor.git
cd csisensor/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pyserial

# Broker:
mosquitto -c ../docker/mosquitto/mosquitto.conf &

# Provisionar (puerto serial es distinto en Mac):
python ../scripts/provision-esp32.py \
    --port /dev/cu.SLAB_USBtoUART \
    --ssid TU_WIFI --pass CLAVE \
    --broker mqtt://<IP-Mac>:1883

# GUI + viewer:
python main.py --host localhost
python web_viewer.py --broker localhost --host 0.0.0.0 --port 8080
```

## 5. Android/iOS como viewer (cero instalación)

Si ya hay un host corriendo el web viewer en la red:

```
1. En el celular/tablet: misma Wi-Fi que el host
2. Abrí el browser (Chrome, Safari, Firefox)
3. Andá a: http://<IP-del-host>:8080
4. Ves BPM, respiración, Body row, tendencia — en tiempo real
5. No hay paso 5 — no hay nada que instalar
```

---

## Referencias

| Doc | Qué cubre |
|---|---|
| `DEPLOYMENT.md` | El deployment completo con Docker (12 secciones) |
| `docs/QUICKSTART-ZOMBIE.md` | Guía state-aware para la máquina principal |
| `docs/HOW-IT-WORKS.md` | Cómo funciona el sistema (física → datos → gráficas) |
| `docs/DATA-PIPELINE.md` | Marco metodológico input→píxel |
