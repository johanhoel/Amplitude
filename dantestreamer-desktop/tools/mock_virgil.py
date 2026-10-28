#!/usr/bin/env python3
"""Fake Virgil control API for trying the desktop apps without a Dante host.

Answers GET /api/status with the same JSON shape as Virgil's status_json()
(src/daemon/control.cpp) and moving meters on TX 1-2, as if AirPlay is
playing. POST /api/start, /api/stop and /api/restart change the state.

    python3 mock_virgil.py                # http://0.0.0.0:8480
    python3 mock_virgil.py --port 8481 --password secret

With --password, requests need HTTP Basic auth with that password (any
user name), like Virgil with remote access on.
"""
import argparse
import base64
import json
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"status": "running"}
TX_NAMES = ["AirPlay L", "AirPlay R", "03", "04", "05", "06", "07", "08"]
RX_NAMES = ["01", "02", "03", "04", "05", "06", "07", "08"]


def status():
    t = time.time()
    running = STATE["status"] == "running"
    # Music-like peaks between about -30 and -3 dBFS on TX 1-2, silence elsewhere.
    def peak(phase):
        db = -16 + 13 * math.sin(t * 2.3 + phase) * math.sin(t * 0.7 + phase)
        return round(10 ** (db / 20), 4)
    tx = [peak(0), peak(0.4)] + [0.0] * 6 if running else []
    rx = [0.0] * 8 if running else []
    return {
        "version": "mock",
        "status": STATE["status"],
        "error": "",
        "config_path": "/etc/virgil/virgil.conf",
        "device": {
            "name": "DanteStreamer", "interface": "eth0", "address": "192.168.1.40",
            "sample_rate": 48000, "tx_channels": 8, "rx_channels": 8,
            "latency_us": 5000, "tx_latency_us": 0, "dante": running,
            "enabled": running, "dante_ports": 4440,
        },
        "tx_names": TX_NAMES,
        "rx_names": RX_NAMES,
        "dropouts_last_hour": 0,
        "remote": {"enabled": True, "listening": True, "this_client_remote": True, "urls": []},
        "clock": {
            "state": "ptp-locked" if running else "stopped",
            "offset_us": 0.8, "grandmaster": "00-1d-c1-ff-fe-12-34-56", "source": "ptp",
        },
        "counters": {"late_ticks": 0, "clock_steps": 1},
        "clients": [{"slot": 0, "pid": 42, "name": "shairport-sync", "active": True}] if running else [],
        "meters": {"tx": tx, "rx": rx},
    }


class Handler(BaseHTTPRequestHandler):
    password = ""

    def send_json(self, code, body, extra=None):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        if not self.password:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, _, pw = base64.b64decode(auth[6:]).decode().partition(":")
                if pw == self.password:
                    return True
            except ValueError:
                pass
        self.send_json(401, {"error": "log in with the remote access password"},
                       {"WWW-Authenticate": 'Basic realm="Virgil"'})
        return False

    def do_GET(self):
        if not self.authorized():
            return
        if self.path == "/api/status":
            self.send_json(200, status())
        elif self.path in ("/", "/index.html"):
            page = b"<h1>Mock Virgil</h1><p>See <a href='/api/status'>/api/status</a>.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self.authorized():
            return
        if self.headers.get("X-Virgil-Request") != "1":
            self.send_json(403, {"error": "missing X-Virgil-Request header"})
            return
        actions = {"/api/start": "running", "/api/stop": "stopped", "/api/restart": "running"}
        if self.path not in actions:
            self.send_json(404, {"error": "not found"})
            return
        STATE["status"] = actions[self.path]
        self.send_json(200, {"ok": True})

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8480)
    ap.add_argument("--password", default="")
    a = ap.parse_args()
    Handler.password = a.password
    print(f"mock Virgil on http://{a.host}:{a.port}/" + (" (password required)" if a.password else ""))
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
