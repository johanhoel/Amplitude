import os, json, logging
os.environ.setdefault("SEARCH_MODEL_DIR", str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"))
import runpy
ns = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("test_webui.py")))
c, root, webui = ns["c"], ns["root"], ns["webui"]
import datetime as dt
import search
log = logging.getLogger("t")
n, total = search.index_new(log)
print(f"{'PASS' if total == 12 else 'FAIL'} search index built: {n} new, {total} total")
r = c.get("/search?q=person+with+a+dog")
html = r.get_data(as_text=True)
cards = html.count('class="card"')
print(f"{'PASS' if r.status_code == 200 and cards == 12 else 'FAIL'} /search -> {r.status_code}, {cards} result cards")
print(f"{'PASS' if 'Search isn' not in html else 'FAIL'} search reported no error")
day = dt.date.today().isoformat()
group = {"id": f"{day}/camera1_100000_faces/unknown_1.jpg", "clips": 2, "days": 1, "first": f"{day}T10:00:00", "last": f"{day}T12:00:00",
         "probably": {"name": "Alex", "score": 0.34},
         "faces": [{"day": day, "stem": s, "crop": f"{s}_faces/unknown_1.jpg", "start": f"{day}T10:00:00", "count": 1} for s in ("camera1_100000", "camera1_120000")]}
(root / "data" / "strangers.json").write_text(json.dumps({"updated": f"{day}T22:00:00", "days": 30, "groups": [group]}))
r = c.get("/strangers"); html = r.get_data(as_text=True)
print(f"{'PASS' if r.status_code == 200 and 'Seen in 2 clips' in html and 'probably Alex' in html else 'FAIL'} /strangers renders the group")
r = c.post("/strangers/name", data={"id": group["id"], "new_name": "Courier"})
tags = [json.loads((root / "recordings" / day / f"{s}.labels.json").read_text())[-1]["name"] for s in ("camera1_100000", "camera1_120000")]
lib = sorted(p.name for p in (root / "photos" / "Courier").iterdir())
print(f"{'PASS' if r.status_code == 302 and tags == ['Courier', 'Courier'] and len(lib) == 2 and (root / 'data' / 'strangers.refresh').exists() else 'FAIL'} naming a group tags both clips {tags}, library {lib}, regroup requested")
r = c.post("/strangers/hide", data={"id": group["id"]})
print(f"{'PASS' if 'Seen in' not in c.get('/strangers').get_data(as_text=True) else 'FAIL'} hiding removes the group")
d = c.get("/dashboard").get_data(as_text=True)
print(f"{'PASS' if '/search' in d and '/strangers' in d and '/timelapse' in d else 'FAIL'} dashboard has Search, Strangers and Timelapse tiles")
r = c.get("/settings"); h = r.get_data(as_text=True)
print(f"{'PASS' if 'No password required on the LAN' not in h and 'No password is set' in h else 'FAIL'} settings: login section (no password set in this test)")
