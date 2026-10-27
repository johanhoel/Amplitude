import datetime as dt, json, logging, os, sys, tempfile
from pathlib import Path
import cv2, numpy as np

root = Path(tempfile.mkdtemp())
(root / "recordings").mkdir(); (root / "data").mkdir()
os.environ.update(RECORDINGS_DIR=str(root / "recordings"), DATA_DIR=str(root / "data"))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
import strangers  # noqa: E402

rng = np.random.default_rng(7)
IDS = {name: (lambda v: v / np.linalg.norm(v))(rng.normal(size=128)) for name in ("courier", "neighbour", "once", "alex")}


class Face:
    def __init__(self, emb): self.emb, self.area = emb, 1


class FakeEngine:
    """The crop's red channel encodes who it is; each sighting gets its own noise, like real photos."""
    calls = 0
    def faces(self, img, min_size=0, max_width=0):
        FakeEngine.calls += 1
        who = list(IDS)[int(img[0, 0, 2]) // 50]
        e = IDS[who] + rng.normal(0, 0.035, 128).astype(np.float32)
        return [Face((e / np.linalg.norm(e)).astype(np.float32))]


class FakeLibrary:
    def match(self, emb):
        s = float(IDS["alex"] @ emb)
        return "Alex", s


plan = {"courier": [0, 1, 2, 4, 6], "neighbour": [0, 3], "once": [5], "alex": [1, 2]}   # days ago
n = 0
for who, days_ago in plan.items():
    for k, ago in enumerate(days_ago):
        day = (dt.date.today() - dt.timedelta(days=ago)).isoformat()
        folder = root / "recordings" / day; folder.mkdir(exist_ok=True)
        stem = f"camera1_{10 + n % 10:02d}{n:02d}00"; n += 1
        (folder / f"{stem}_faces").mkdir()
        img = np.full((100, 80, 3), 10, np.uint8); img[..., 2] = list(IDS).index(who) * 50 + 5
        cv2.imwrite(str(folder / f"{stem}_faces" / "unknown_1.jpg"), img)
        (folder / f"{stem}.json").write_text(json.dumps({"start": f"{day}T{stem[-6:-4]}:{stem[-4:-2]}:00", "test": False}))
        (folder / f"{stem}.faces.json").write_text(json.dumps({"faces_seen": 1, "known": [], "unknown": [{"crop": f"{stem}_faces/unknown_1.jpg", "count": 3}]}))
        if who == "neighbour" and k == 1:   # one neighbour face was already tagged by hand -> left out
            (folder / f"{stem}.labels.json").write_text(json.dumps([{"name": "Kim", "crop": f"{stem}_faces/unknown_1.jpg"}]))

log = logging.getLogger("t")
strangers.update(FakeEngine(), FakeLibrary(), log)
out = json.loads((root / "data" / "strangers.json").read_text())
groups = {len(g["faces"]): g for g in out["groups"]}
print("groups:", [(g["clips"], g["days"], (g["probably"] or {}).get("name")) for g in out["groups"]])
checks = [
    ("courier: 5 clips on 5 days, listed first", out["groups"][0]["clips"] == 5 and out["groups"][0]["days"] == 5),
    ("alex-like group gets 'probably Alex'", any((g["probably"] or {}).get("name") == "Alex" and g["clips"] == 2 for g in out["groups"])),
    ("neighbour (1 untagged clip) and 'once' not listed", len(out["groups"]) == 2),
    ("no group mixes people", all(len({f["crop"][:0] for f in g["faces"]}) == 1 for g in out["groups"])),
]
calls = FakeEngine.calls
strangers.update(FakeEngine(), FakeLibrary(), log)
checks.append(("second run uses the cache (no new embeddings)", FakeEngine.calls == calls))
(root / "data" / "strangers_hidden.json").write_text(json.dumps([out["groups"][0]["id"]]))
strangers.update(FakeEngine(), FakeLibrary(), log)
checks.append(("hidden group disappears", len(json.loads((root / "data" / "strangers.json").read_text())["groups"]) == 1))
for text, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {text}")
