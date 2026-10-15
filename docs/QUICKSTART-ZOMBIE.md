# Guía zombie para desplegar el aplicativo

> **Qué es.** La guía paso a paso que no asume nada: un comando por línea,
> resultado esperado, qué hacer si falla. Y es **state-aware**: ya sabe
> qué está hecho en este proyecto y no te lo hace repetir.
> Si querés el detalle completo de cada sección, andá a `DEPLOYMENT.md`.

---

## ✅ Ya está hecho — NO lo repitas (verificado 2026-10-12)

- ESP-IDF v5.3.1 instalado en WSL + `idfenv` (abbr de fish)
- Firmware construido, flasheado y verificado en cadena completa
  (board link `59c0a0`; boot-loop y crash `t_us` ya corregidos)
- `src/esp32/main/config.h` con credenciales reales — es la config viva
- Broker mosquitto dockerizado (conf baked en la imagen, `docker compose up -d`)
- `backend/.venv` (venv de Windows sobre el share `\\wsl.localhost\...`)
  con requirements instalados
- Suite **50/50** · Fixes de la review commiteados (`dce3453`→`bdbe1b6`) ·
  Kit builder disponible (`scripts/build-portable-kit.ps1`)

## ⚡ Acciones únicas por los fixes recientes (una sola vez)

```
1. Re-corré el firewall (PowerShell como ADMIN):
   powershell -ExecutionPolicy Bypass -File .\scripts\firewall-rules.ps1
   → reemplaza las reglas por las nuevas (scoped LocalSubnet + Private).
   ⚠️ La Wi-Fi debe estar marcada "Private" (Config. de Windows > Red).
   Sin esto, la placa no llega al broker y el teléfono no ve la página.

2. Reiniciá el GUI / web viewer:
   corren directo del working tree → al reiniciar ya usan el código con
   los fixes (MQTT_TOPIC honrado, primary que expira, GUI que pinta
   durante el llenado).

3. SOLO si usás el portable kit: re-build del exe
   (.\scripts\build-portable-kit.cmd) — el exe viejo empaqueta el
   backend anterior y NO hereda los fixes.
```

**No hace falta re-flashear la placa** — el firmware no cambió.

---

## 🚀 Arranque diario (esto es todo lo que se hace)

```
1. Abrí Docker Desktop (Windows) → esperá "running".

2. Broker (PowerShell o WSL, desde la raíz del repo):
   docker compose up -d
   docker compose logs mosquitto     → "mosquitto version 2.x running"

3. Placa ya flasheada → conectala y listo. El monitor es opcional.

4. GUI (PowerShell de Windows):
   cd \\wsl.localhost\Ubuntu\home\tilin\dev\projects\c++\sensorproject\backend
   .\.venv\Scripts\python.exe main.py --host localhost
   → En ~15 s con alguien quieto a 0,5–2 m: BPM + respiración + Body row.

5. Celular (segunda terminal, misma carpeta):
   .\.venv\Scripts\python.exe web_viewer.py --broker localhost --host 0.0.0.0 --port 8080
   → En el teléfono, MISMA Wi-Fi: http://<IP-de-tu-PC>:8080
     (IP: ipconfig → adaptador Wi-Fi → IPv4. Tipeá el http:// completo
     o el navegador te fuerza HTTPS.)
```

---

## 🆕 PC nuevo / desde cero (condensado)

```
1. Requisitos: Windows 10/11 + WSL2 Ubuntu + Docker Desktop (integración
   WSL2 ON) + Python 3.10+ en Windows + placa ESP32-S3 + Wi-Fi 2,4 GHz.

2. Broker:         docker compose up -d
3. Firewall:       .\scripts\firewall-rules.cmd   (admin; red marcada Private)
4. Venv:           cd \\wsl.localhost\Ubuntu\home\tilin\dev\projects\c++\sensorproject\backend
                   python -m venv .venv
                   .\.venv\Scripts\python.exe -m pip install -r requirements.txt

5. PRUEBA SIN HARDWARE primero (dos terminales, mismo venv):
   .\.venv\Scripts\python.exe ..\scripts\simulate_esp32.py --host localhost --scenario resting
   → GUI: ~66 BPM / ~18 resp/min en ~15 s.
   Multi-nodo seco: dos sims con --device-id a1b2c3 y d4e5f6 → status bar "links 2".

6. Con la placa:
   a. Editá src/esp32/main/config.h:
      WIFI_SSID / WIFI_PASS  = tu Wi-Fi 2,4 GHz
      MQTT_BROKER_URI        = mqtt://<IP-de-Windows>:1883   (NUNCA localhost)
      USE_TRAFFIC_PING       = 1
   b. Build en WSL:
      idfenv
      cd ~/dev/projects/c++/sensorproject/src/esp32
      idf.py set-target esp32s3
      idf.py build
   c. Flasheo — DESDE WINDOWS (si usbipd tira "No serial data", es lo esperado):
      usbipd detach --busid <X-X>   (si estaba attached)
      .\scripts\flash-board.cmd      (auto-detecta el COM)
      → Sin auto-download en el board: BOOT + RST + soltá BOOT;
        el script lo detecta solo. Al final, tocá RST si no arranca solo.
   d. Verificá: docker exec -it wifisensing_mosquitto mosquitto_sub -t "esp32/+/csi/raw" -C 3
      → tienen que llegar CSVs. Si no: troubleshooting.

7. Otra PC sin nada (portable kit):
   .\scripts\build-portable-kit.cmd
   → genera la carpeta del kit (viewer .exe + mosquitto + launcher + README).
   Copiás la carpeta a la PC destino → doble click start-system.bat
   → imprime la URL para el teléfono. (Si no detecta la IP: ipconfig —
     ahora avisa con warning en vez de imprimir una URL vacía.)
   ⚠️ Seguridad: el broker del kit acepta MQTT anónimo — solo Wi-Fi de lab.
     Antes de exponerlo más: auth en mosquitto.conf (DEPLOYMENT.md §12).
```

---

## 🔧 Si algo falla

`DEPLOYMENT.md` §11 tiene los 14 síntomas típicos con su fix. Los más comunes:

| Síntoma | Primera mirada |
|---|---|
| Placa no llega al broker | `MQTT_BROKER_URI` con `localhost` en el firmware (va la IP de Windows); firewall 1883 abierto y red marcada **Private** |
| Teléfono no abre la página | Misma Wi-Fi; `http://` completo; firewall 8080; el viewer sigue corriendo |
| GUI vacía | pkt/s en la barra de estado — si es 0, el stream no llega (tópico o broker) |
| BPM muestra `-` | SNR bajo el umbral: acercate, quietud, o probá `--window 20` |
| `idf.py: command not found` | Corré `idfenv` en esa pestaña |
| Flash falla con `No serial data` | Desattach usbipd y flasheá desde Windows (§6c); BOOT+RST si el board no tiene auto-download |

---

## 📖 Documentación del repo (qué leer y para qué)

| Doc | Para |
|---|---|
| `DEPLOYMENT.md` | El deployment completo, sección por sección (12 secciones) |
| `docs/HOW-IT-WORKS.md` | Cómo funciona el sistema explicado fácil (física → datos → cómo leer cada gráfica) |
| `docs/DATA-PIPELINE.md` | El marco metodológico input-0-al-píxel con cada matemática y cada porqué |
| `docs/SIGNAL-MODELING.md` | Las fórmulas exactas, calibración, provenance |
| `docs/VALIDATION-PROTOCOL.md` | El protocolo de validación empírica |
| `odd/tasks/review-fixes.md` | Los hallazgos de la review y cómo se corrigieron (con hashes de commit) |

*Suite: `cd backend && python3 -m pytest tests -q` → 50/50. Research tool, not a medical device.*
