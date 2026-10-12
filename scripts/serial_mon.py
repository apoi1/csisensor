#!/usr/bin/env python3
"""Print the ESP32's serial log from a COM port (UART bridge or native USB).

Usage:
    python serial_mon.py COM5             # 60 s @ 115200 baud
    python serial_mon.py COM5 -d 20       # 20 s
    python serial_mon.py /dev/ttyACM0     # from WSL too

The firmware's ESP_LOGx output goes to UART0, which is exactly what the
"COM" USB port (UART bridge) of the devkit exposes. Requires pyserial:
    .venv python -m pip install pyserial
"""
import argparse
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser(description="ESP32 serial log reader")
    p.add_argument("port", help="e.g. COM5 on Windows, /dev/ttyACM0 on WSL")
    p.add_argument("-b", "--baud", type=int, default=115200)
    p.add_argument("-d", "--duration", type=float, default=60.0,
                   help="seconds to listen (default 60)")
    args = p.parse_args()

    try:
        import serial
    except ImportError:
        print("pyserial is missing - install it first:\n"
              "  .venv python -m pip install pyserial", file=sys.stderr)
        return 1

    end = time.time() + args.duration
    print(f"listening on {args.port} @ {args.baud} for {args.duration:g}s "
          "(Ctrl+C to stop)")
    try:
        with serial.Serial(args.port, args.baud, timeout=1) as s:
            while time.time() < end:
                line = s.readline()
                if line:
                    print(line.decode("utf-8", "replace").rstrip())
    except KeyboardInterrupt:
        pass
    except Exception as e:  # serial.SerialException etc.
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
