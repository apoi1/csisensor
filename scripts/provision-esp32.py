#!/usr/bin/env python3
"""Provision ESP32 WiFi/broker credentials over USB serial (NVS).

The firmware (main.cpp) reads credentials from NVS at boot, falling back
to the compiled-in config.h #defines when NVS is empty. This script sends
the provisioning commands over the USB serial port — no rebuild, no
re-flash, 30 seconds. Safe to run any number of times (NVS is rewritable
with wear leveling).

Usage:
    # Provision for a new network:
    python provision-esp32.py --port /dev/ttyACM0 \
        --ssid MyWiFi --pass MyPassword \
        --broker mqtt://192.168.1.50:1883

    # On Windows (auto-detect or explicit COM port):
    python provision-esp32.py --port COM5 \
        --ssid MyWiFi --pass MyPassword \
        --broker mqtt://192.168.1.50:1883

    # Check current state without changing anything:
    python provision-esp32.py --port /dev/ttyACM0 --status

    # Clear NVS credentials (fall back to compiled-in values):
    python provision-esp32.py --port /dev/ttyACM0 --clear

    # Auto-detect the serial port:
    python provision-esp32.py --ssid MyWiFi --pass MyPassword \
        --broker mqtt://192.168.1.50:1883
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial is required:  pip install pyserial", file=sys.stderr)
    sys.exit(1)


# The firmware responds with lines prefixed by PROVISION:
OK_PREFIX = "PROVISION:OK"
ERR_PREFIX = "PROVISION:ERR"


def find_port(explicit: str | None) -> str:
    """Auto-detect the first USB serial port, or use the explicit one."""
    if explicit:
        return explicit
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("ERROR: no serial ports found. Connect the ESP32 via USB.",
              file=sys.stderr)
        sys.exit(1)
    # Prefer CP210x / CH340 / FT232 / USB-Serial-JTAG (the known bridges)
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ("cp210", "ch340", "ch9102", "ft232",
                                    "usb serial", "usb-serial", "jtag")):
            return p.device
    # Fall back to the first port
    return ports[0].device


def read_until(ser, prefix: str, timeout_s: float = 3.0) -> str:
    """Read lines until one starts with prefix, or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        line = ser.readline().decode("ascii", errors="replace").strip()
        if line.startswith(prefix):
            return line
        if line:
            print(f"  board: {line}")
    return ""


def send_and_wait(ser, command: str, timeout_s: float = 3.0) -> bool:
    """Send a command and wait for PROVISION:OK or PROVISION:ERR."""
    ser.write((command + "\n").encode("ascii"))
    ser.flush()
    response = read_until(ser, "PROVISION:", timeout_s)
    if OK_PREFIX in response:
        print(f"  OK: {response}")
        return True
    elif ERR_PREFIX in response:
        print(f"  ERROR: {response}", file=sys.stderr)
        return False
    else:
        print(f"  (no response within {timeout_s}s — the board may be "
              "booting; try again)", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision ESP32 credentials over USB serial (NVS).")
    parser.add_argument("--port", "-p", default=None,
                        help="Serial port (default: auto-detect)")
    parser.add_argument("--ssid", default=None,
                        help="WiFi network name")
    parser.add_argument("--pass", dest="password", default=None,
                        help="WiFi password")
    parser.add_argument("--broker", default=None,
                        help="MQTT broker URI (e.g. mqtt://192.168.1.50:1883)")
    parser.add_argument("--status", action="store_true",
                        help="Print current credentials (no changes)")
    parser.add_argument("--clear", action="store_true",
                        help="Erase NVS credentials (fall back to compiled-in)")
    args = parser.parse_args()

    port = find_port(args.port)
    print(f"Opening serial port: {port} (115200 baud)")
    try:
        ser = serial.Serial(port, baudrate=115200, timeout=1.0)
    except serial.SerialException as e:
        print(f"ERROR: cannot open {port}: {e}", file=sys.stderr)
        print("  On Linux: are you in the dialout group? "
              "(sudo usermod -aG dialout $USER)", file=sys.stderr)
        print("  On WSL: is the board attached? (usbipd attach --wsl --busid <X-X>)",
              file=sys.stderr)
        print("  On Windows: close any other program using the port "
              "(idf.py monitor, PuTTY, etc.)", file=sys.stderr)
        return 1

    time.sleep(0.5)  # let the serial port settle
    ser.reset_input_buffer()

    try:
        if args.status:
            print("Querying current credentials...")
            ser.write(b"PROVISION:STATUS\n")
            ser.flush()
            response = read_until(ser, "PROVISION:source=", timeout_s=3.0)
            if response:
                print(f"  {response}")
            else:
                print("  (no response — is the firmware NVS-capable?)",
                      file=sys.stderr)
                return 1
            return 0

        if args.clear:
            print("Clearing NVS credentials...")
            if not send_and_wait(ser, "PROVISION:CLEAR"):
                return 1
            print("Done. The board rebooted with the compiled-in defaults.")
            return 0

        # Provisioning mode: need all three values
        if not args.ssid or not args.password or not args.broker:
            parser.error("provisioning requires --ssid, --pass, and --broker "
                         "(or use --status / --clear)")

        print(f"Provisioning: ssid={args.ssid}, broker={args.broker}")
        ok = True
        if ok:
            ok = send_and_wait(ser, f"PROVISION:SSID={args.ssid}")
        if ok:
            ok = send_and_wait(ser, f"PROVISION:PASS={args.password}")
        if ok:
            ok = send_and_wait(ser, f"PROVISION:BROKER={args.broker}")
        if ok:
            print("All values saved. Rebooting board...")
            ser.write(b"PROVISION:SAVE\n")
            ser.flush()
            time.sleep(1.0)  # wait for the reboot message
            response = read_until(ser, "PROVISION:OK", timeout_s=2.0)
            if response:
                print(f"  {response}")
            print("Done. The board is now on the new network.")
            return 0
        else:
            return 1
    finally:
        ser.close()


if __name__ == "__main__":
    sys.exit(main())
