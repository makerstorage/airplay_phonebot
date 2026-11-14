"""Keep one serial connection open and send G-code lines to it.

  .venv/bin/python scripts/serial_bot.py serve PORT BAUD     # background: opens the port (resets the board), listens on 127.0.0.1:47123, logs to /tmp/serial_bot.log
  .venv/bin/python scripts/serial_bot.py send "M119"         # sends one line, prints every reply until "ok"
"""

import os
import socket
import sys
import time

ADDR = ("127.0.0.1", 47123)
LOG = "/tmp/serial_bot.log"


def log(msg: str) -> None:
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def serve(port: str, baud: int) -> None:
    import serial

    ser = serial.Serial(port, baud, timeout=0.2)
    log(f"opened {port} @ {baud}")
    # Boot banner after the reset
    end = time.time() + 2.5
    while time.time() < end:
        line = ser.readline().decode(errors="replace").strip()
        if line:
            log(f"< {line}")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(ADDR)
    srv.listen(1)
    log("ready")
    while True:
        conn, _ = srv.accept()
        with conn:
            cmd = conn.recv(4096).decode().strip()
            ser.reset_input_buffer()
            ser.write((cmd + "\n").encode())
            log(f"> {cmd}")
            out, deadline = [], time.time() + 120  # long moves: wait up to 2 min for "ok"
            while time.time() < deadline:
                line = ser.readline().decode(errors="replace").strip()
                if not line:
                    continue
                log(f"< {line}")
                out.append(line)
                if line.startswith("ok") or line.lower().startswith("error"):
                    break
            else:
                out.append("(timeout: no ok in 120 s)")
            conn.sendall("\n".join(out).encode())


def send(cmd: str) -> None:
    c = socket.create_connection(ADDR)
    c.sendall(cmd.encode())
    c.shutdown(socket.SHUT_WR)
    data = b""
    while chunk := c.recv(4096):
        data += chunk
    print(data.decode())


if __name__ == "__main__":
    if sys.argv[1] == "serve":
        serve(sys.argv[2], int(sys.argv[3]))
    else:
        send(sys.argv[2])
