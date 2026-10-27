"""Off-site storage, rclone mocked: selection, alarm queue, config steps, web routes."""
import datetime as dt, json, os, runpy, time
os.environ.setdefault("SEARCH_MODEL_DIR", str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"))
ns = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("test_webui.py")))
c, root, webui = ns["c"], ns["root"], ns["webui"]
import settings, offsite

ok = True
def check(text, cond):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {text}")

calls = []
def fake_rclone(*args, timeout=120, check=True, bwlimit=0):
    calls.append((args, bwlimit))
    if args[:2] == ("config", "create"):
        if args[3] == "iclouddrive":
            return json.dumps({"State": "*2fa", "Option": {"Name": "config_2fa", "Help": "Two-factor authentication: enter the code", "DefaultStr": "", "IsPassword": False}, "Error": ""})
        offsite.CONF.write_text(offsite.CONF.read_text() + f"\n[{args[2]}]\ntype = {args[3]}\n" + "".join(f"{a.split('=')[0]} = OBSC{a.split('=',1)[1]}\n" for a in args[4:] if "=" in a))
        return json.dumps({"State": "", "Option": None, "Error": ""})
    if args[:2] == ("config", "update"):
        offsite.CONF.write_text(offsite.CONF.read_text() + "\n[camwatch]\ntype = iclouddrive\n")
        return json.dumps({"State": "", "Option": None, "Error": ""})
    if args[:2] == ("config", "delete"):
        text = offsite.CONF.read_text() if offsite.CONF.exists() else ""
        import re
        offsite.CONF.write_text(re.sub(rf"\n?\[{args[2]}\]\n(?:(?!\[).*\n)*", "\n", text))
        return ""
    if args[0] == "reveal":
        return args[1].replace("OBSC", "") + "\n"
    return ""
offsite.rclone = fake_rclone
if not offsite.CONF.exists():
    offsite.CONF.parent.mkdir(parents=True, exist_ok=True); offsite.CONF.write_text("")

# ---------- config steps ----------
st = offsite._config_step(json.dumps({"State": "abc", "Option": {"Name": "config_driveid", "Help": "Choose drive", "DefaultStr": "x",
                                      "Examples": [{"Value": "x", "Help": "OneDrive (personal)"}]}, "Error": ""}))
check(f"question parsed: {st['name']} examples={st['examples']}", st["step"] == "question" and st["state"] == "abc" and st["examples"][0]["help"] == "OneDrive (personal)")
check("empty output = done", offsite._config_step("") == {"step": "done"} and offsite._config_step('{"State":"","Option":null}') == {"step": "done"})
check("error", offsite._config_step('{"State":"","Option":null,"Error":"bad key"}')["error"] == "bad key")

# ---------- connecting through the web UI ----------
r = c.post("/settings/offsite/connect", data={"type": "b2", "path": "my-bucket/home", "f_account": "kid", "f_key": "appkey"})
j = r.get_json()
check(f"B2 connect -> {j}", j["step"] == "done" and j["test"] == "ok")
o = offsite.options()
check(f"saved: type={o['type']} path={o['path']} enabled={o['enabled']} encrypt={o['encrypt']}", o["type"] == "b2" and o["path"] == "my-bucket/home" and o["enabled"] and o["encrypt"])
create = [a for a, _ in calls if a[:3] == ("config", "create", "camwatch")][-1]
check(f"rclone config create b2 with account/key: {create[:6]}", create[3] == "b2" and "account=kid" in create and "key=appkey" in create)
crypt = [a for a, _ in calls if a[:3] == ("config", "create", "camwatch-crypt")][-1]
check(f"crypt remote over the folder: {crypt[4]}", crypt[4] == "remote=camwatch:my-bucket/home/encrypted")
keys = c.get("/settings/offsite/recovery")
txt = keys.get_data(as_text=True)
pw = [a for a in crypt if a.startswith("password=")][0].split("=", 1)[1]
check("recovery file has the real (revealed) keys, as a download", keys.status_code == 200 and pw in txt and "attachment" in keys.headers["Content-Disposition"])
page = c.get("/settings").get_data(as_text=True)
check("settings shows connected, never the key", "● Connected" in page and "Backblaze B2" in page and "appkey" not in page and pw not in page)
# saving options keeps the same crypt keys
c.post("/settings/offsite", data={"enabled": "1", "encrypt": "1", "instant": "1", "keep_days": "45", "bwlimit_mbps": "2.5",
                                  "what_starred": "1", "what_people": "1", "what_timelapse": "1"})
o = offsite.options()
check(f"options saved: keep {o['keep_days']} bw {o['bwlimit_mbps']} what {o['what']}", o["keep_days"] == 45 and o["bwlimit_mbps"] == 2.5 and o["what"]["timelapse"] and not o["what"]["db_backup"] and not o["what"]["all"])
crypt2 = [a for a, _ in calls if a[:3] == ("config", "create", "camwatch-crypt")][-1]
check("re-saving keeps the encryption keys", [a for a in crypt2 if a.startswith("password")] == [a for a in crypt if a.startswith("password")])
# "Sign in again": same destination connected again -> same encryption keys, options kept
keys_before = [a for a in crypt2 if a.startswith("password")]
r = c.post("/settings/offsite/connect", data={"type": "b2", "path": "my-bucket/home", "f_account": "kid", "f_key": "newkey"}).get_json()
crypt3 = [a for a, _ in calls if a[:3] == ("config", "create", "camwatch-crypt")][-1]
check(f"sign in again keeps the encryption keys and options ({r['step']})", r["step"] == "done" and [a for a in crypt3 if a.startswith("password")] == keys_before
      and offsite.options()["keep_days"] == 45)
check("settings page has Sign in again", "Sign in again" in c.get("/settings").get_data(as_text=True))
for bad in ({"keep_days": "0"}, {"bwlimit_mbps": "-1"}):
    r = c.post("/settings/offsite", data={"keep_days": "30", "bwlimit_mbps": "0", **bad})
    check(f"rejected {bad}", "error=" in r.headers["Location"])
for bad in ({"type": "ftp", "path": "x"}, {"type": "b2", "path": "../etc"}, {"type": "b2", "path": "a;rm"}):
    check(f"connect refused {bad}", c.post("/settings/offsite/connect", data=bad).status_code == 400)

# iCloud: 2FA question, then done
r = c.post("/settings/offsite/connect", data={"type": "iclouddrive", "path": "camwatch", "f_apple_id": "me@example.com", "f_password": "pw"}).get_json()
check(f"iCloud asks for the 2FA code: {r.get('help')}", r["step"] == "question" and r["name"] == "config_2fa")
r = c.post("/settings/offsite/answer", data={"state": r["state"], "result": "123456"}).get_json()
upd = [a for a, _ in calls if a[:2] == ("config", "update")][-1]
check(f"code passed on: {upd}", r["step"] == "done" and "--result" in upd and upd[upd.index("--result") + 1] == "123456")
check("now iCloud", offsite.options()["type"] == "iclouddrive")

# OAuth: pasted address validated
try:
    offsite.authorizer.finish("http://example.com/?code=1"); check("bad paste refused", False)
except offsite.RcloneError as e:
    check(f"OAuth without a running sign-in refused: {e}", "expired" in str(e) or "paste" in str(e))

# ---------- what is copied ----------
settings.update(offsite={**offsite.options(), "keep_days": 2, "what": {"starred": True, "people": True, "all": False, "timelapse": True, "db_backup": True}})
today = dt.date.today().isoformat()
folder = root / "recordings" / today
stems = sorted(p.stem for p in folder.glob("*.mp4"))
(folder / f"{stems[0]}.star").touch()
(root / "data" / "timelapse").mkdir(exist_ok=True); (root / "data" / "timelapse" / f"{today}-camera1-timelapse.mp4").write_bytes(b"x")
(root / "data" / "db-backup").mkdir(exist_ok=True); (root / "data" / "db-backup" / "camwatch-x.sql.gz").write_bytes(b"x")
sel = offsite.selection(offsite.options())
people = {f.split("/")[1].split(".")[0] for f in sel["clips"]}
check(f"people clips: {sorted(people)}", all((folder / f"{s}.faces.json").exists() or (folder / f"{s}.labels.json").exists() for s in people if s.startswith("camera1")))
check(f"starred: {sel['starred']}", sel["starred"] and all(f.startswith(f"{today}/{stems[0]}.") for f in sel["starred"]))
check("each clip: video + jpg + json", any(f.endswith(".mp4") for f in sel["starred"]) and any(f.endswith(".json") for f in sel["starred"]))
check(f"timelapse + db: {sel['timelapse']} {sel['db-backup']}", sel["timelapse"] and sel["db-backup"])
old_days = [d for d in {f.split('/')[0] for f in sel["clips"]} if d < (dt.date.today() - dt.timedelta(days=2)).isoformat()]
check("clips older than keep_days not uploaded again", not old_days)
calls.clear()
offsite.copy("clips", sel["clips"], offsite.options())
cp = [a for a, b in calls if a[0] == "copy"][0]
check(f"copy to the encrypted target: {cp[1:3]}", cp[2] == "camwatch-crypt:clips" and "--files-from-raw" in cp)
settings.update(offsite={**offsite.options(), "encrypt": False, "bwlimit_mbps": 3})
calls.clear(); offsite.copy("starred", sel["starred"], offsite.options())
cp, bw = [(a, b) for a, b in calls if a[0] == "copy"][0]
check(f"unencrypted target + speed limit: {cp[2]} bw={bw}", cp[2] == "camwatch:camwatch/starred" and bw == 3)
calls.clear(); offsite.prune(offsite.options())
check(f"retention deletes clips/timelapse/db-backup only: {[a[1] for a, _ in calls]}", [a[1] for a, _ in calls] == ["camwatch:camwatch/clips", "camwatch:camwatch/timelapse", "camwatch:camwatch/db-backup"])

# ---------- alarm queue ----------
settings.update(offsite={**offsite.options(), "instant": True, "enabled": True})
offsite.queue_alarm(today, "camera1_999999")
q = list(offsite.QUEUE.glob("*.json"))
check(f"queued: {[p.name for p in q]}", len(q) == 1)
(folder / "camera1_999999.jpg").write_bytes(b"j")
calls.clear(); n = offsite.handle_queue(offsite.options(), webui.log)
check(f"snapshot first, clip not saved yet -> still queued ({n} upload)", n == 1 and len(list(offsite.QUEUE.glob("*.json"))) == 1)
(folder / "camera1_999999.mp4").write_bytes(b"v"); (folder / "camera1_999999.json").write_text("{}")
calls.clear(); n = offsite.handle_queue(offsite.options(), webui.log)
files = open([a for a, _ in calls if a[0] == "copy"][0][a.index("--files-from-raw") + 1] if False else os.devnull).read() if False else None
check(f"clip saved -> uploaded and dequeued ({n})", n == 1 and not list(offsite.QUEUE.glob("*.json")))
settings.update(offsite={**offsite.options(), "instant": False})
offsite.queue_alarm(today, "camera1_888888")
check("instant off -> nothing queued", not list(offsite.QUEUE.glob("*.json")))
(offsite.QUEUE).mkdir(exist_ok=True); (offsite.QUEUE / "evil.json").write_text(json.dumps({"day": "../..", "stem": "x", "at": time.time(), "snapshot": False}))
calls.clear(); offsite.handle_queue(offsite.options(), webui.log)
check("bad queue entry dropped, nothing copied", not calls and not list(offsite.QUEUE.glob("*.json")))

# ---------- disconnect ----------
c.post("/settings/offsite/disconnect")
check("disconnect removes both remotes", "[camwatch" not in offsite.CONF.read_text() and offsite.options()["type"] == "" and not offsite.options()["enabled"])
page = c.get("/settings").get_data(as_text=True)
check("connect form shown again with all destinations", "iCloud Drive" in page and "Backblaze B2" in page and "Google Drive" in page and "NAS over SMB" in page)
print("ALL PASS" if ok else "SOME FAILED")
