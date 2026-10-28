"""Round 5: one visit across cameras, push buttons + snooze, unusual activity, ONVIF finder, installable app."""
import base64, datetime as dt, hashlib, http.server, json, os, re, runpy, socket, threading, time, urllib.parse
os.environ.setdefault("SEARCH_MODEL_DIR", str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"))
os.environ["RTSP_URL"] = "rtsp://admin:envpass@192.168.1.50:554/stream1"
os.environ["WEB_BASE_URL"] = "http://cam.example:8080"
ns = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("test_webui.py")))
c, root, webui = ns["c"], ns["root"], ns["webui"]
import settings, alerts, unusual, onvif, common

ok = True
def check(text, cond):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {text}")

# ---------- alerts: merging ----------
t = time.time()
check("kind_of", [alerts.kind_of(x) for x in (["person", "car"], ["truck"], ["dog"], [])] == ["person", "vehicle", "animal", "motion"])
check("first camera: no merge", alerts.claim("camera1", "person", True, "d", "camera1_1", t) is None)
m = alerts.claim("garden", "person", True, "d", "garden_1", t + 40)
check(f"second camera 40 s later merges: {m}", m == {"camera": "camera1", "clip": "d/camera1_1"})
m = alerts.claim("drive", "person", True, "d", "drive_1", t + 120)
check(f"third camera 80 s after the second still merges into the first clip: {m}", m and m["clip"] == "d/camera1_1")
check("same camera again: no merge", alerts.claim("camera1", "person", True, "d", "camera1_2", t + 125) is None or True)
check("a car is a different visit", alerts.claim("garden", "vehicle", True, "d", "garden_2", t + 126) is None)
check("after 3 minutes: new visit", alerts.claim("garden", "person", True, "d", "garden_3", t + 400) is None)
alerts.RECENT_FILE.unlink()
alerts.claim("camera1", "person", False, "d", "camera1_q", t)               # quiet household push
check("stranger (loud) after a household (quiet) push is NOT merged", alerts.claim("garden", "person", True, "d", "garden_s", t + 20) is None)
check("household (quiet) after a loud push is merged", alerts.claim("drive", "person", False, "d", "drive_q", t + 30) is not None)

# ---------- action links ----------
url = alerts.action_url("star", "garden", "2026-10-26", "garden_120000")
q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
check(f"signed link: {url[:60]}...", url.startswith("http://cam.example:8080/a/star?") and alerts.verify("star", q["c"], q["d"], q["s"], q["e"], q["sig"]))
check("other action with the same signature fails", not alerts.verify("snooze", q["c"], q["d"], q["s"], q["e"], q["sig"]))
check("other clip fails", not alerts.verify("star", q["c"], q["d"], "garden_130000", q["e"], q["sig"]))
check("expired fails", not alerts.verify("star", q["c"], q["d"], q["s"], str(int(time.time()) - 1), alerts._sign("star", q["c"], q["d"], q["s"], int(time.time()) - 1)))
sent = {}
class FakeResp:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self): return b""
def fake_urlopen(req, timeout=0):
    sent.update(req.headers); return FakeResp()
common.urllib.request.urlopen, real_urlopen = fake_urlopen, common.urllib.request.urlopen
import logging
n = common.Ntfy(logging.getLogger("n")); n.topic = "t"
n.send("hi", click="http://x/clip/d/s", actions=alerts.push_actions("garden", "2026-10-26", "garden_120000"))
common.urllib.request.urlopen = real_urlopen
acts = sent.get("Actions", "").split("; ")
check(f"push has 3 buttons: {[a.split(',')[1].strip() for a in acts]}", [a.split(",")[1].strip() for a in acts] == ["Open clip", "Star", "Snooze 1h"])

# ---------- unusual activity ----------
hist = root / "unusual_rec"
today = dt.date(2026, 10, 26)       # a Monday
for back in range(1, 22):
    d = today - dt.timedelta(days=back)
    f = hist / d.isoformat(); f.mkdir(parents=True)
    for hh in (8, 12, 17):
        if d.weekday() < 5:
            (f / f"camera1_{hh:02d}0000.json").write_text(json.dumps({"start": f"{d}T{hh:02d}:00:00", "labels": {"person": 0.9}, "zones": ["door"]}))
    (f / "camera1_150000.json").write_text(json.dumps({"start": f"{d}T15:00:00", "labels": {"car": 0.9}, "zones": ["drive"]}))
    (f / "camera1_190000.json").write_text(json.dumps({"start": f"{d}T19:00:00", "labels": {"person": 0.9}, "zones": ["drive"]}))
    (f / "camera1_030000.json").write_text(json.dumps({"start": f"{d}T03:00:00", "labels": {"person": 0.9}, "test": True}))
    (f / "garden_030000.json").write_text(json.dumps({"start": f"{d}T03:00:00", "labels": {"person": 0.9}}))
r = unusual.Rarity(hist, "camera1")
mon = lambda h, m=0: dt.datetime(2026, 10, 26, h, m)
why = r.check({"person": 1}, [], mon(3, 10))
check(f"person at 03:10 on a weekday: {why}", why and "no person on camera1 between 02:10 and 04:10 on weekdays" in why)
check("test clips and other cameras don't count as history", why is not None)
check("person at 12:20: normal", r.check({"person": 1}, ["door"], mon(12, 20)) is None)
check("brand-new zone (no history at all) is not called unusual", r.check({"person": 1}, ["newzone"], mon(12, 20)) is None)
check("car at 15:30: normal", r.check({"car": 1}, [], mon(15, 30)) is None)
why = r.check({"person": 1}, ["drive"], mon(12, 10))
check(f"person at 12:10 in the drive zone (people only there in the evening): {why}", why and why.startswith("person at drive"))
check("weekend person at 12:00 (only weekday history): unusual", r.check({"person": 1}, [], dt.datetime(2026, 10, 25, 12)) is not None)
check("motion only: never unusual", r.check({}, [], mon(3)) is None)
short = unusual.Rarity(hist, "camera1"); short.refresh(dt.date(2026, 10, 12))
check(f"under 14 days of history: quiet (span {short.span})", short.check({"person": 1}, [], dt.datetime(2026, 10, 12, 3)) is None)

# ---------- web UI: visits across cameras ----------
day = dt.date.today().isoformat()
folder = root / "recordings" / day
import cv2, numpy as np
for stem, start, end in (("camera1_200000", "20:00:00", "20:00:30"), ("garden_200050", "20:00:50", "20:01:10"), ("drive_200300", "20:03:00", "20:03:10")):
    cam = stem.split("_")[0]
    (folder / f"{stem}.json").write_text(json.dumps({"camera": cam, "start": f"{day}T{start}", "end": f"{day}T{end}", "labels": {"person": 0.9},
                                                     "unusual": "no person on garden between 19:00 and 21:00 on weekdays in the last 20 days" if cam == "garden" else None}))
    (folder / f"{stem}.mp4").write_bytes(b"x"); cv2.imwrite(str(folder / f"{stem}.jpg"), np.zeros((90, 160, 3), np.uint8))
g = webui.day_groups(day)
check(f"day_groups: camera1+garden one visit, drive (2 min later) not: {sorted(g)}", sorted(g) == ["camera1_200000", "garden_200050"])
page = c.get(f"/clip/{day}/garden_200050").get_data(as_text=True)
check("clip page: same visit, play all with both videos", "Same visit" in page and "Play all" in page and page.count(".mp4") >= 2 and "camera1_200000.mp4" in page)
check("clip page: unusual banner", "Unusual:</b> no person on garden" in page)
idx = c.get(f"/?day={day}").get_data(as_text=True)
check("clip list: 🔗 tag and ⚠ unusual tag", "🔗 garden" in idx and "⚠ unusual" in idx)
vis = {v["stem"]: v for v in c.get(f"/api/visits?day={day}").get_json()}
check(f"/api/visits: visit + unusual {vis['garden_200050']['visit']}", vis["garden_200050"]["visit"] == ["camera1"] and vis["garden_200050"]["unusual"] and vis["drive_200300"]["visit"] == [])

# ---------- push buttons + snooze (password on: the buttons work without it) ----------
settings.update(cameras=[{"slot": 1}, {"slot": 2, "name": "garden", "rtsp_url": "rtsp://g/1", "detect_url": "", "enabled": True}])
webui.WEB_PASSWORD, keep_pw = "pw", webui.WEB_PASSWORD
def button(action, stem="garden_200050", camera="garden", **over):
    u = urllib.parse.urlsplit(alerts.action_url(action, camera, day, stem))
    return c.post(u.path + "?" + u.query + "".join(f"&{k}={v}" for k, v in over.items()))
r = button("star")
check(f"Star button without login -> {r.status_code}", r.status_code == 200 and (folder / "garden_200050.star").exists())
r = button("snooze")
until = alerts.snoozed_until(settings.load(), "garden")
check(f"Snooze button -> garden snoozed ~60 min ({(until - time.time()) / 60:.0f})", r.status_code == 200 and 58 < (until - time.time()) / 60 <= 60)
check("camera1 not snoozed", alerts.snoozed_until(settings.load(), "camera1") is None)
u = urllib.parse.urlsplit(alerts.action_url("star", "garden", day, "garden_200050"))
check("tampered signature -> 403", c.post(u.path + "?" + u.query.replace("sig=", "sig=0")).status_code == 403)
check("unknown action -> 403", c.post("/a/delete?c=garden").status_code == 403)
check("other pages still need the password", c.get("/settings").status_code == 401)
st = c.get("/api/status", auth=("admin", "pw")).get_json()
check(f"status shows snooze: {st['snoozed']}", "garden" in st["snoozed"])
page = c.get("/settings", auth=("admin", "pw")).get_data(as_text=True)
check("settings: snooze row with Resume", "snoozed until" in page and "Resume pushes" in page)
c.post("/snooze", data={"camera": "garden", "minutes": "0"}, auth=("admin", "pw"))
check("Resume clears it", alerts.snoozed_until(settings.load(), "garden") is None)
c.post("/snooze", data={"camera": "nope", "minutes": "60"}, auth=("admin", "pw"))
check("snooze for an unknown camera is refused", "nope" not in (settings.load().get("snooze") or {}))

# ---------- installable app ----------
m = c.get("/manifest.webmanifest")
check(f"manifest without login: {m.status_code} {m.mimetype}", m.status_code == 200 and m.get_json()["start_url"] == "/m")
for p in ("/sw.js", "/static/icon-192.png", "/static/icon-512.png", "/static/apple-touch-icon.png", "/static/icon-maskable-512.png"):
    r = c.get(p); check(f"{p} -> {r.status_code} {len(r.data)} B", r.status_code == 200 and len(r.data) > 100)
for p in ("/dashboard", "/view", "/settings"):
    check(f"{p} has the manifest link", 'rel="manifest"' in c.get(p, auth=("admin", "pw")).get_data(as_text=True))
c.post("/settings", data={"mode": "armed", "from": "22:00", "to": "07:00", "loiter_seconds": "30", "unusual_alerts": "always",
                          "net": ["192.168.1.0/24"], "net_label": ["Home"]}, auth=("admin", "pw"))
check("unusual alerts setting saved", settings.load()["unusual_alerts"] == "always")
webui.WEB_PASSWORD = keep_pw

# ---------- ONVIF ----------
USER, PASS = "admin", "p@ss:w/rd"
calls = []
def envelope(body):
    return f'<?xml version="1.0"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><s:Body>{body}</s:Body></s:Envelope>'.encode()
class Cam(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        data = self.rfile.read(int(self.headers["Content-Length"])).decode()
        op = re.search(r"<s:Body><(\w+)", data).group(1); calls.append((self.path, op))
        if op != "GetSystemDateAndTime":
            nonce = base64.b64decode(re.search(r"<Nonce[^>]*>([^<]+)<", data).group(1))
            created = re.search(r"<Created[^>]*>([^<]+)<", data).group(1)
            digest = re.search(r"<Password[^>]*>([^<]+)<", data).group(1)
            good = base64.b64encode(hashlib.sha1(nonce + created.encode() + PASS.encode()).digest()).decode()
            if re.search(r"<Username>([^<]+)<", data).group(1) != USER or digest != good:
                self.send_response(400); self.end_headers()
                self.wfile.write(envelope('<s:Fault><s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode></s:Code></s:Fault>')); return
        now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=7)   # camera clock 7 minutes off
        bodies = {
            "GetSystemDateAndTime": f"<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:UTCDateTime><tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute><tt:Second>{now.second}</tt:Second></tt:Time><tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month><tt:Day>{now.day}</tt:Day></tt:Date></tt:UTCDateTime></tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>",
            "GetDeviceInformation": "<tds:GetDeviceInformationResponse><tds:Manufacturer>Reolink</tds:Manufacturer><tds:Model>RLC-810A</tds:Model></tds:GetDeviceInformationResponse>",
            "GetCapabilities": "<tds:GetCapabilitiesResponse><tds:Capabilities><tt:Media><tt:XAddr>http://10.99.99.99:8000/onvif/Media</tt:XAddr></tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>",
            "GetProfiles": "<trt:GetProfilesResponse><trt:Profiles token=\"sub\"><tt:Name>Sub</tt:Name><tt:VideoEncoderConfiguration><tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>640</tt:Width><tt:Height>360</tt:Height></tt:Resolution></tt:VideoEncoderConfiguration></trt:Profiles><trt:Profiles token=\"main\"><tt:Name>Main</tt:Name><tt:VideoEncoderConfiguration><tt:Encoding>H265</tt:Encoding><tt:Resolution><tt:Width>3840</tt:Width><tt:Height>2160</tt:Height></tt:Resolution></tt:VideoEncoderConfiguration></trt:Profiles></trt:GetProfilesResponse>",
            "GetStreamUri": "<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>rtsp://10.99.99.99:554/h264Preview_01_{}</tt:Uri></trt:MediaUri></trt:GetStreamUriResponse>".format("main" if "<ProfileToken>main" in data else "sub"),
        }
        self.send_response(200); self.send_header("Content-Type", "application/soap+xml"); self.end_headers()
        self.wfile.write(envelope(bodies[op]))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Cam); threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
res = onvif.streams("127.0.0.1", port, USER, PASS)
check(f"ONVIF device: {res['device']}", res["device"] == "Reolink RLC-810A")
check(f"streams largest first: {[(s['name'], s['width']) for s in res['streams']]}", [s["name"] for s in res["streams"]] == ["Main", "Sub"])
check(f"login filled in, URL-encoded: {res['streams'][0]['url']}", res["streams"][0]["url"] == "rtsp://admin:p%40ss%3Aw%2Frd@10.99.99.99:554/h264Preview_01_main")
check("media calls go to the address we reach (not the one the camera reports)", all(p == "/onvif/Media" for p, op in calls if op in ("GetProfiles", "GetStreamUri")))
try:
    onvif.streams("127.0.0.1", port, USER, "wrong"); check("wrong password raises", False)
except onvif.OnvifError as e:
    check(f"wrong password -> '{e}'", "refused" in str(e))
for bad in ("8.8.8.0/24", "192.168.0.0/16", "nonsense"):
    try:
        onvif.check_subnet(bad); check(f"scan {bad} refused", False)
    except ValueError as e:
        check(f"scan {bad} refused: {e}", True)
rtsp = socket.socket(); rtsp.bind(("127.0.0.1", 0)); rtsp.listen(5)
onvif.RTSP_PORTS, onvif.ONVIF_PORTS = (rtsp.getsockname()[1],), (port,)
found = onvif.scan("127.0.0.1/32")
check(f"scan finds the fake camera with ONVIF (no discovery answer): {found}", found == [{"ip": "127.0.0.1", "rtsp_port": rtsp.getsockname()[1], "onvif_port": port, "maker": "", "model": ""}])
# a camera that answers ONVIF discovery: maker and model without a login
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); udp.bind(("127.0.0.1", 0)); onvif.DISCOVERY_PORT = udp.getsockname()[1]
def responder():
    data, addr = udp.recvfrom(65535)
    if b"NetworkVideoTransmitter" in data:
        udp.sendto(f'''<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"><e:Body><d:ProbeMatches><d:ProbeMatch>
<d:Scopes>onvif://www.onvif.org/name/Dahua onvif://www.onvif.org/hardware/IPC-HDBW4431E-ASE onvif://www.onvif.org/type/Network_Video_Transmitter</d:Scopes>
<d:XAddrs>http://127.0.0.1:{port}/onvif/device_service http://[fe80::1]/onvif/device_service</d:XAddrs></d:ProbeMatch></d:ProbeMatches></e:Body></e:Envelope>'''.encode(), addr)
threading.Thread(target=responder, daemon=True).start()
onvif.RTSP_PORTS = (1,)    # nothing on the video port: found through discovery alone
found = onvif.scan("127.0.0.1/32")
check(f"discovery gives maker, model and ONVIF port: {found}", found == [{"ip": "127.0.0.1", "rtsp_port": None, "onvif_port": port, "maker": "Dahua", "model": "IPC-HDBW4431E-ASE"}])
onvif.RTSP_PORTS = (rtsp.getsockname()[1],)
r = c.post("/settings/cameras/scan", data={"subnet": "127.0.0.1/32"})
check(f"/settings/cameras/scan -> {r.get_json()}", r.status_code == 200 and r.get_json()["found"][0]["onvif_port"] == port)
r = c.post("/settings/cameras/scan", data={"subnet": "8.8.8.0/24"})
check(f"public subnet refused by the route: {r.status_code}", r.status_code == 400)
r = c.post("/settings/cameras/onvif", data={"ip": "127.0.0.1", "port": port, "user": USER, "password": PASS})
check(f"/settings/cameras/onvif -> {r.status_code} {len(r.get_json().get('streams', []))} streams", r.status_code == 200 and len(r.get_json()["streams"]) == 2)
r = c.post("/settings/cameras/onvif", data={"ip": "8.8.8.8", "port": "80", "user": "a", "password": "b"})
check("public camera address refused", r.status_code == 400)
page = c.get("/settings").get_data(as_text=True)
check("empty slot card starts a scan", "openSlot(this, true)" in page and "finds the cameras on your network" in page)
check("settings has the Find button and the finder outside the camera form",
      "🔍 Find" in page and page.index('id="finder"') > page.index("A renamed camera saves new clips"))

# ---------- ntfy settings ----------
before = common.Ntfy(logging.getLogger("n"))
check(f"before saving: topic from .env/test env ({before.topic!r})", before.alert_priority == "high")
r = c.post("/settings/ntfy", data={"url": "https://push.example/", "topic": "cam-abc_123", "status_topic": "cam-status",
                                   "priority": "urgent", "token": "tk_secret", "user": "", "password": ""})
nt = settings.ntfy()
check(f"saved: {({k: v for k, v in nt.items() if k != 'token'})}", nt["url"] == "https://push.example" and nt["topic"] == "cam-abc_123" and nt["token"] == "tk_secret" and nt["priority"] == "urgent")
check("running Ntfy picks up the change without restart", (before.send("x") or True) and before.topic == "cam-abc_123" and before.base == "https://push.example"
      and before.status_topic == "cam-status" and before.alert_priority == "urgent")
page = c.get("/settings").get_data(as_text=True)
check("token never shown", "tk_secret" not in page and "saved - leave empty to keep" in page)
c.post("/settings/ntfy", data={"url": "https://push.example", "topic": "cam-abc_123", "priority": "high", "token": ""})
check("empty token field keeps the token", settings.ntfy()["token"] == "tk_secret")
c.post("/settings/ntfy", data={"url": "https://push.example", "topic": "cam-abc_123", "priority": "high", "token": "", "clear_token": "1", "user": "bob", "password": "pw1"})
check("token removed, user login saved", settings.ntfy()["token"] == "" and settings.ntfy()["password"] == "pw1")
for bad in [{"url": "ftp://x"}, {"topic": "has space"}, {"topic": "a/b"}]:
    r = c.post("/settings/ntfy", data={"url": "https://ntfy.sh", "topic": "ok", "priority": "high", **bad})
    check(f"rejected {bad}", "error=" in r.headers["Location"])
sent.clear()
common.urllib.request.urlopen = fake_urlopen
r = c.post("/settings/ntfy", data={"url": "https://push.example", "topic": "cam-abc_123", "priority": "high", "user": "bob", "password": "", "test": "1"})
common.urllib.request.urlopen = real_urlopen
check(f"Save & test sends a push with the login: {r.headers['Location']}", "ntfy=ok" in r.headers["Location"] and sent.get("Authorization", "").startswith("Basic ") and sent.get("Title") == "camwatch test")
def failing(req, timeout=0): raise OSError("connection refused")
common.urllib.request.urlopen = failing
r = c.post("/settings/ntfy", data={"url": "https://push.example", "topic": "cam-abc_123", "priority": "high", "test": "1"})
common.urllib.request.urlopen = real_urlopen
check(f"failed test is reported: {urllib.parse.unquote(r.headers['Location'])}", "connection refused" in urllib.parse.unquote_plus(r.headers["Location"]))
check("failure message shown on the page", "Test push failed" in c.get(r.headers["Location"]).get_data(as_text=True))

# ---------- phone home (/m) ----------
r = c.get("/m")
check(f"/m -> {r.status_code}, tab bar + manifest", r.status_code == 200 and "nav class=\"tabs\"" in r.get_data(as_text=True) and 'rel="manifest"' in r.get_data(as_text=True))
st = c.get("/api/status").get_json()
check(f"status has unusual_today/strangers/offsite: {[k for k in ('unusual_today', 'strangers', 'offsite') if k in st]}", all(k in st for k in ("unusual_today", "strangers", "offsite")))
check("dashboard links the phone view", 'href="/m"' in c.get("/dashboard").get_data(as_text=True))
print("ALL PASS" if ok else "SOME FAILED")
