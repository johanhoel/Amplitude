"""Cameras and Home Assistant set on the Settings page, on top of the fake data of test_webui.py."""
import datetime as dt, json, logging, os, runpy, shutil, time
os.environ.setdefault("SEARCH_MODEL_DIR", str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"))
os.environ["RTSP_URL"] = "rtsp://admin:envpass@192.168.1.50:554/stream1"
ns = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("test_webui.py")))
c, root, webui = ns["c"], ns["root"], ns["webui"]
import cv2, numpy as np
import settings

ok = True
def check(text, cond):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {text}")

def cams_form(**extra):
    form = {"rtsp_1": webui.mask_url(os.environ["RTSP_URL"]), "detect_1": "", "enabled_1": "1"}
    form.update(extra)
    return form

# ---------- cameras ----------
r = c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:s3cret@192.168.1.51/stream1", enabled_2="1"))
check(f"save garden -> {r.status_code} {r.headers.get('Location')}", r.status_code == 302 and "saved=cameras" in r.headers["Location"])
slots = settings.camera_slots()
check("slot 2 stored with password, slot 1 still from .env (nothing stored for it)",
      slots[1]["rtsp_url"] == "rtsp://cam:s3cret@192.168.1.51/stream1" and slots[1]["enabled"]
      and slots[0]["rtsp_url"] == os.environ["RTSP_URL"] and settings.load()["cameras"][0] == {"slot": 1})
page = c.get("/settings").get_data(as_text=True)
check("settings page never contains the passwords", "s3cret" not in page and "envpass" not in page and "cam:••••••@192.168.1.51" in page)
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:••••••@192.168.1.77/stream1", enabled_2="1"))
check("new IP with the masked password keeps the password", settings.camera_slots()[1]["rtsp_url"] == "rtsp://cam:s3cret@192.168.1.77/stream1")
# passwords typed as-is with characters a URL parser misreads: masked whole, kept exactly
for pw in ("ab#cd", "x/y?z", "p@ss:w", "50%off", "Åsa!"):
    url = f"rtsp://admin:{pw}@192.168.1.60:554/cam/realmonitor?channel=1&subtype=0"
    masked = webui.mask_url(url)
    check(f"mask hides all of {pw!r}: {masked}", masked == "rtsp://admin:••••••@192.168.1.60:554/cam/realmonitor?channel=1&subtype=0")
    c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2=url, enabled_2="1"))
    c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2=masked, enabled_2="1"))
    check(f"saving the masked form keeps {pw!r} exactly", settings.camera_slots()[1]["rtsp_url"] == url)
check("no password, @ in the path: left alone", webui.mask_url("rtsp://192.168.1.60/a@b") == "rtsp://192.168.1.60/a@b")
# a half-edited mask used to be saved literally (bullets in the password): now refused, the stored password stays
before = settings.camera_slots()[1]["rtsp_url"]
for edited, why in (("rtsp://admin:•••new@192.168.1.60:554/cam", "bullets partly replaced"),
                    ("rtsp://admin:new••••••@192.168.1.60:554/cam", "typed next to the bullets"),
                    ("rtsp://admin:••••@192.168.1.60:554/cam", "some bullets deleted")):
    r = c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2=edited, enabled_2="1"))
    check(f"refused ({why}): {r.headers['Location'].split('error=')[-1][:50]}", "error=" in r.headers["Location"] and settings.camera_slots()[1]["rtsp_url"] == before)
    r = c.post("/settings/cameras/test", data={"slot": "2", "url": edited})
    check(f"test picture refuses it too: {r.status_code} {r.get_data(as_text=True)[:40]}", r.status_code == 400 and "replace the whole" in r.get_data(as_text=True).lower())
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://admin:N3w-pass@192.168.1.60:554/cam", enabled_2="1"))
check("replacing the whole mask saves the new password", settings.camera_slots()[1]["rtsp_url"] == "rtsp://admin:N3w-pass@192.168.1.60:554/cam")
r = c.post("/settings/cameras", data=cams_form(name_3="porch", rtsp_3="rtsp://admin:••••••@192.168.1.61/cam", enabled_3="1",
                                              name_2="garden", rtsp_2="rtsp://admin:••••••@192.168.1.60:554/cam", enabled_2="1"))
check("bullets on a camera without a saved password are refused", "error=" in r.headers["Location"] and settings.camera_slots()[2]["name"] != "porch")
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:s3cret@192.168.1.77/stream1", enabled_2="1"))
check(f"settings.json is private: {oct(settings.PATH.stat().st_mode & 0o777)}", os.name == "nt" or settings.PATH.stat().st_mode & 0o077 == 0)
for bad, why in [(dict(name_2="Garden!", rtsp_2="rtsp://x/1"), "bad name"), (dict(name_2="camera1", rtsp_2="rtsp://x/1"), "primary's name"),
                 (dict(name_2="gate", rtsp_2="http://x/1"), "not rtsp"), (dict(name_2="gate"), "no URL"),
                 (dict(name_2="gate", rtsp_2="rtsp://x/1", name_3="gate", rtsp_3="rtsp://y/1"), "duplicate")]:
    before = settings.load()["cameras"]
    r = c.post("/settings/cameras", data=cams_form(**bad))
    check(f"rejected ({why}): {r.headers['Location'].split('error=')[-1][:60]}", "error=" in r.headers["Location"] and settings.load()["cameras"] == before)
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:••••••@192.168.1.77/stream1", enabled_2="1",
                                          name_3="drive", rtsp_3="rtsp://d/1", enabled_3="1"))
check(f"/api/cameras: {[x['name'] for x in c.get('/api/cameras').get_json()]}", [x["name"] for x in c.get("/api/cameras").get_json()] == ["camera1", "garden", "drive"])
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:••••••@192.168.1.77/stream1", enabled_2="1",
                                          name_3="drive", rtsp_3="rtsp://d/1"))   # drive switched off (no enabled_3)
check("switched-off camera disappears from the camera list", [x["name"] for x in c.get("/api/cameras").get_json()] == ["camera1", "garden"])
check("its settings are kept", settings.camera_slots()[2]["name"] == "drive" and not settings.camera_slots()[2]["enabled"])

# camera test button: unreachable camera -> clear message, password not leaked
t0 = time.time()
r = c.post("/settings/cameras/test", data={"slot": "2", "url": "rtsp://cam:••••••@127.0.0.1:9/x"})
msg = r.get_data(as_text=True)
check(f"test picture of a dead address -> {r.status_code} '{msg[:80]}' ({time.time() - t0:.1f}s)", r.status_code == 502 and "s3cret" not in msg)

# launcher: slot 2 starts the recorder as 'garden'; an empty slot waits
import camslot
captured = {}
def fake_exec(exe, args):
    captured.update(args=args, env={k: os.environ.get(k) for k in ("CAMERA_NAME", "RTSP_URL", "PRIMARY_CAMERA", "PRUNE_RECORDINGS", "CAMERA_SLOT")})
    raise SystemExit
saved_env = dict(os.environ)
camslot.os.execv, camslot.SLOT = fake_exec, 2
try:
    camslot.main()
except SystemExit:
    pass
os.environ.clear(); os.environ.update(saved_env)
check(f"launcher slot 2 -> {captured.get('env')}", captured.get("env") == {"CAMERA_NAME": "garden", "RTSP_URL": "rtsp://cam:s3cret@192.168.1.77/stream1",
      "PRIMARY_CAMERA": "camera1", "PRUNE_RECORDINGS": None, "CAMERA_SLOT": "2"} and captured["args"][-1] == "recorder.py")
check("camera_key changes when the URL changes", settings.camera_key(settings.camera_slots()[1]) != settings.camera_key({**settings.camera_slots()[1], "rtsp_url": "rtsp://other"}))

# ---------- Home Assistant / network ----------
r = c.post("/settings/integration", data={"mqtt_host": "127.0.0.1", "mqtt_port": "9", "mqtt_user": "camwatch", "mqtt_password": "mq-pass",
                                         "ha_webhook_url": "http://192.168.1.10:8123/api/webhook/x", "lan_networks": "192.168.1.0/24"})
loc = r.headers["Location"]
check(f"MQTT saved, login test reports the failure: {loc.split('mqtt=')[-1][:70]}", "saved=integration" in loc and "mqtt=" in loc and "mqtt=ok" not in loc)
i = settings.integration()
check("integration stored", (i["mqtt_host"], i["mqtt_port"], i["mqtt_user"], i["mqtt_password"]) == ("127.0.0.1", 9, "camwatch", "mq-pass"))
page = c.get("/settings").get_data(as_text=True)
check("MQTT password never shown", "mq-pass" not in page and "saved - leave empty to keep" in page)
c.post("/settings/integration", data={"mqtt_host": "127.0.0.1", "mqtt_port": "9", "mqtt_user": "camwatch", "mqtt_password": "",
                                     "ha_webhook_url": "", "lan_networks": "192.168.1.0/24"})
check("empty password field keeps the password", settings.integration()["mqtt_password"] == "mq-pass" and settings.integration()["ha_webhook_url"] == "")
for bad in [{"mqtt_host": "http://ha:1883"}, {"mqtt_port": "70000"}, {"ha_webhook_url": "ha.local"}]:
    r = c.post("/settings/integration", data={"mqtt_host": "", "mqtt_port": "1883", "lan_networks": "10.0.0.0/8", **bad})
    check(f"rejected {bad}", "error=" in r.headers["Location"])

# ---------- trusted networks (no password) ----------
check(f"before saving: networks from LAN_NETWORKS/default {[n['net'] for n in settings.trusted_networks()]}", settings.trusted_networks()[0]["net"] == "192.168.0.0/16")
base = {"mode": "armed", "from": "22:00", "to": "07:00", "loiter_seconds": "30", "lan_no_auth": "1"}
def save_nets(nets, labels):
    return c.post("/settings", data={**base, "net": nets, "net_label": labels})
r = save_nets(["192.168.1.7/24", "10.8.0.0/24", "", "192.168.1.0/24"], ["Home", "WireGuard", "", "dup"])
check(f"saved -> {settings.trusted_networks()}", settings.trusted_networks() == [{"net": "192.168.1.0/24", "label": "Home"}, {"net": "10.8.0.0/24", "label": "WireGuard"}])
def status(ip, auth=None):
    return c.get("/dashboard", environ_base={"REMOTE_ADDR": ip}, auth=auth).status_code
webui.WEB_PASSWORD, keep_pw = "pw", webui.WEB_PASSWORD
check("VPN device 10.8.0.5 gets in without password", status("10.8.0.5") == 200)
check("home device 192.168.1.20 gets in", status("192.168.1.20") == 200)
check("192.168.2.20 (not listed any more) needs the password", status("192.168.2.20") == 401)
check("10.9.0.5 needs the password", status("10.9.0.5") == 401)
page = c.get("/settings", environ_base={"REMOTE_ADDR": "10.8.0.5"}, auth=("admin", "pw")).get_data(as_text=True)
check("settings page marks the VPN row for this device", "this device is on this network" in page and "Add this device" not in page)
page = c.get("/settings", environ_base={"REMOTE_ADDR": "100.64.3.9"}, auth=("admin", "pw")).get_data(as_text=True)
check("unknown device gets an 'add this device's network' button", "Add this device&#39;s network (100.64.3.0/24)" in page or "Add this device's network (100.64.3.0/24)" in page)
webui.WEB_PASSWORD = keep_pw
for bad in ["0.0.0.0/0", "10.0.0.0/7", "home", "300.1.1.0/24"]:
    before = settings.trusted_networks()
    r = save_nets([bad], ["x"])
    check(f"rejected {bad}: {r.headers['Location'].split('error=')[-1][:50]}", "error=" in r.headers["Location"] and settings.trusted_networks() == before)
save_nets(["172.20.0.0/16"], ["odd"])
webui.WEB_PASSWORD = "pw"
check("Docker overlap warning shown", "Overlaps Docker" in c.get("/settings", auth=("admin", "pw")).get_data(as_text=True))
webui.WEB_PASSWORD = keep_pw
save_nets(["192.168.1.0/24", "10.8.0.0/24"], ["Home", "WireGuard"])
ha_page = c.get("/homeassistant").get_data(as_text=True)
check("HA page shows the broker from settings", "MQTT enabled (127.0.0.1)" in ha_page)

# HomeAssistant object follows the settings without a restart
from homeassistant import HomeAssistant
ha = HomeAssistant(logging.getLogger("ha"), "facematch")
check("HA client created for the saved broker", ha.client is not None and ha.broker[0] == "127.0.0.1")
first = ha.client
ha.state("motion", True)
c.post("/settings/integration", data={"mqtt_host": "localhost", "mqtt_port": "1883", "mqtt_user": "", "lan_networks": "192.168.1.0/24",
                                     "ha_webhook_url": "http://192.168.1.10:8123/api/webhook/y"})
time.sleep(0.05); ha.next_check = 0; ha.event("test")
check("new broker -> new client, webhook picked up", ha.client is not first and ha.broker == ("localhost", 1883, "", "") and ha.webhook.endswith("/y"))
check("retained states kept for re-publishing", ha.retained_msgs.get(f"{ha.base}/motion") == "ON")
c.post("/settings/integration", data={"mqtt_host": "", "mqtt_port": "1883", "lan_networks": "192.168.1.0/24"})
time.sleep(0.05); ha.next_check = 0; ha.state("motion", False)
check("broker removed -> MQTT off", ha.client is None and ha.webhook is None)

# ---------- camera 1 can be switched off ("deleted") and back on ----------
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:••••••@192.168.1.77/stream1", enabled_2="1"))
check("camera 1 on: it cleans up old recordings and is the default", settings.pruning_camera() == "camera1" and settings.default_camera() == "camera1")
off = cams_form(name_2="garden", rtsp_2="rtsp://cam:••••••@192.168.1.77/stream1", enabled_2="1")
off.pop("enabled_1")
r = c.post("/settings/cameras", data=off)
s1 = settings.camera_slots()[0]
check(f"camera 1 switched off: {r.headers['Location']}", "saved=cameras" in r.headers["Location"] and not s1["enabled"] and s1["name"] == "camera1")
check(f"camera list without camera 1: {[x['name'] for x in c.get('/api/cameras').get_json()]}", [x["name"] for x in c.get("/api/cameras").get_json()] == ["garden"])
check("garden now cleans up old recordings and is the default camera", settings.pruning_camera() == "garden" and settings.default_camera() == "garden")
with webui.app.test_request_context("/live"):
    check("camera_arg() defaults to garden", webui.camera_arg() == "garden")
check("settings page still shows camera 1 (switched off) to turn back on", "Switch it off to remove it" in c.get("/settings").get_data(as_text=True))
off_no_url = dict(off, rtsp_1="")
r = c.post("/settings/cameras", data=off_no_url)
check("switched off, camera 1 needs no stream address", "saved=cameras" in r.headers["Location"])
r = c.post("/settings/cameras", data=dict(off_no_url, enabled_1="1"))
check(f"switching it on without an address is refused: {r.headers['Location'][:80]}", "error=" in r.headers["Location"])
c.post("/settings/cameras", data=cams_form(name_2="garden", rtsp_2="rtsp://cam:••••••@192.168.1.77/stream1", enabled_2="1"))
check("camera 1 back on, with its .env address", settings.camera_slots()[0]["enabled"] and settings.camera_slots()[0]["rtsp_url"] == os.environ["RTSP_URL"]
      and settings.pruning_camera() == "camera1")
print("ALL PASS" if ok else "SOME FAILED")
