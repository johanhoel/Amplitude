"""Tiny fake Home Assistant for testing Home Deck."""
import json, sys, time, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
TOKEN = "testtoken"
now = datetime.datetime.now(datetime.timezone.utc)
iso = lambda d: d.isoformat()
S = [
 {"entity_id": "light.kitchen_ceiling", "state": "on", "attributes": {"friendly_name": "Kitchen Ceiling", "brightness": 200, "supported_color_modes": ["brightness"]}},
 {"entity_id": "light.kitchen_island", "state": "off", "attributes": {"friendly_name": "Kitchen Island", "supported_color_modes": ["onoff"]}},
 {"entity_id": "light.sofa_lamp", "state": "off", "attributes": {"friendly_name": "Sofa lamp", "supported_color_modes": ["brightness"]}},
 {"entity_id": "light.hallway", "state": "on", "attributes": {"friendly_name": "Hallway", "supported_color_modes": ["onoff"]}},
 {"entity_id": "light.all_downstairs", "state": "on", "attributes": {"friendly_name": "All downstairs", "entity_id": ["light.kitchen_ceiling"]}},
 {"entity_id": "person.anna", "state": "home", "attributes": {"friendly_name": "Anna"}},
 {"entity_id": "person.erik", "state": "not_home", "attributes": {"friendly_name": "Erik"}},
 {"entity_id": "lock.front_door", "state": "unlocked", "attributes": {"friendly_name": "Front door"}},
 {"entity_id": "media_player.living_room", "state": "playing", "attributes": {"friendly_name": "Living room", "media_title": "Song", "media_artist": "Band"}},
 {"entity_id": "media_player.spotify_anna", "state": "paused", "attributes": {"friendly_name": "Spotify Anna"}},
 {"entity_id": "weather.forecast_home", "state": "rainy", "attributes": {"temperature": 7.5, "humidity": 80, "wind_speed": 14.4, "wind_speed_unit": "km/h", "temperature_unit": "°C"}},
 {"entity_id": "sensor.office_temp", "state": "21.4", "attributes": {"friendly_name": "Office temperature", "device_class": "temperature"}},
 {"entity_id": "vacuum.robo", "state": "docked", "attributes": {"battery_level": 90}},
 {"entity_id": "sun.sun", "state": "below_horizon", "attributes": {"next_rising": iso(now)}},
]
AREA = {"light.kitchen_ceiling": "Kitchen", "light.kitchen_island": "Kitchen", "light.sofa_lamp": "Living room", "light.hallway": ""}
CALLS = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def j(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def ok(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.j({"message": "401"}, 401); return False
        return True
    def do_GET(self):
        if self.path == "/manifest.json": return self.j({"name": "HA"})
        if not self.ok(): return
        if self.path == "/api/": return self.j({"message": "API running."})
        if self.path == "/api/states": return self.j(S)
        if self.path.startswith("/api/states/"): return self.j(next(s for s in S if s["entity_id"] == self.path[12:]))
        if self.path.startswith("/api/history/period/"):
            out = []
            for e in ("person.anna", "person.erik"):
                out.append([{"entity_id": e, "state": "home", "last_changed": iso(now - datetime.timedelta(hours=9))},
                            {"state": "not_home", "last_changed": iso(now - datetime.timedelta(hours=5))},
                            {"state": "home" if e == "person.anna" else "not_home", "last_changed": iso(now - datetime.timedelta(hours=1))}])
            return self.j(out)
        if self.path == "/_calls": return self.j(CALLS)
        self.j({"message": "not found"}, 404)
    def do_POST(self):
        if not self.ok(): return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/template":
            t = body["template"]
            assert "area_name" in t
            res = json.dumps({"areas": ["Living room", "Kitchen"], "lights": AREA})
            b = res.encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); return self.wfile.write(b)
        if self.path.startswith("/api/services/weather/get_forecasts"):
            return self.j({"service_response": {body["entity_id"]: {"forecast": [{"datetime": iso(now + datetime.timedelta(hours=i)), "condition": "rainy", "temperature": 7 + i % 3, "precipitation": 0.3} for i in range(30)]}}})
        if self.path.startswith("/api/services/"):
            CALLS.append({"svc": self.path[14:], "data": body}); return self.j([])
        self.j({"message": "not found"}, 404)
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
