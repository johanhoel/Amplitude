#!/usr/bin/env python3
"""A stand-in Home Assistant on 127.0.0.1:8123, for running the panels without one.

tools/staging.sh needs a real Home Assistant token, which only the owner of that
house has - so tests/smoke.py could not be run by anybody else, and it was the
one check tools/check.sh always skipped. This answers the few endpoints the
panels read at startup with made-up rooms and lights: enough to render every
page and catch a JavaScript error.

It is not a Home Assistant. Nothing is controllable and no state ever changes.
Start it through  HOMEDECK_STUB=1 tools/staging.sh.
"""
import json, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
STATES = [
    {"entity_id": f"light.l{i}", "state": "off",
     "attributes": {"friendly_name": f"Light {i}", "supported_color_modes": ["brightness"]}}
    for i in range(6)
] + [
    {"entity_id": "person.a", "state": "home", "attributes": {"friendly_name": "A"}},
    {"entity_id": "weather.home", "state": "sunny",
     "attributes": {"temperature": 12, "forecast": []}},
    {"entity_id": "media_player.m", "state": "idle", "attributes": {"friendly_name": "M"}},
]
class H(BaseHTTPRequestHandler):
    def _j(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/api/", "/api"): return self._j({"message": "API running."})
        if p == "/manifest.json": return self._j({"name": "Home Assistant"})
        if p == "/api/states": return self._j(STATES)
        m = re.fullmatch(r"/api/states/(.+)", p)
        if m:
            for s in STATES:
                if s["entity_id"] == m.group(1): return self._j(s)
            return self._j({"message": "not found"}, 404)
        if p.startswith("/api/history") or p.startswith("/api/calendars"): return self._j([])
        return self._j({}, 404)
    def do_POST(self): self._j([])
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", 8123), H).serve_forever()
