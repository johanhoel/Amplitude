"""Recurring strangers: group the unknown faces of recent clips into people, so a stranger seen on several days shows
up once ("seen in 5 clips on 3 days") and can be named in one go on the web UI's Strangers page.

facematch saves a crop of every unknown face (<stem>_faces/unknown_<n>.jpg). Every STRANGER_EVERY seconds this computes
an SFace embedding per crop (cached in /data/stranger_cache.json, so each crop is processed once), links crops whose
embeddings are similar (cosine >= STRANGER_SIMILARITY, single linkage) and writes the groups seen in at least two clips
to /data/strangers.json. Faces tagged by hand are left out; a group resembling someone in the library gets a
"probably <name>" hint (the faces were below the match threshold, often a side view or a different light).
"""
import datetime as dt
import json
import re
from pathlib import Path

import cv2
import numpy as np

from common import env

REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
DATA_DIR = Path(env("DATA_DIR", "/data"))
DAYS = env("STRANGER_DAYS", 30, int)
SIMILARITY = env("STRANGER_SIMILARITY", 0.45, float)
EVERY = env("STRANGER_EVERY", 600, int)
HINT = env("STRANGER_HINT", 0.30, float)
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CACHE = DATA_DIR / "stranger_cache.json"
OUT = DATA_DIR / "strangers.json"
HIDDEN = DATA_DIR / "strangers_hidden.json"


def _load(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


def _write(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def collect():
    """Every untagged unknown face of the last DAYS days: {day, stem, crop, start, count}."""
    cutoff = (dt.date.today() - dt.timedelta(days=DAYS - 1)).isoformat()
    out = []
    for folder in sorted(p for p in REC_DIR.iterdir() if p.is_dir() and DAY_RE.match(p.name) and p.name >= cutoff):
        for faces_path in folder.glob("*.faces.json"):
            stem = faces_path.name[: -len(".faces.json")]
            meta = _load(folder / f"{stem}.json", {}) or {}
            if meta.get("test"):
                continue
            tagged = {t.get("crop") for t in _load(folder / f"{stem}.labels.json", []) or []}
            for u in (_load(faces_path, {}) or {}).get("unknown", []):
                crop = u.get("crop")
                if crop and crop not in tagged and (folder / crop).exists():
                    out.append({"day": folder.name, "stem": stem, "crop": crop, "count": u.get("count", 1),
                                "start": meta.get("start") or f"{folder.name}T{stem[-6:-4]}:{stem[-4:-2]}:{stem[-2:]}"})
    return out


def embed(engine, path):
    img = cv2.imread(str(path))
    if img is None:
        return None
    faces = engine.faces(img, min_size=16, max_width=640)
    return max(faces, key=lambda f: f.area).emb if faces else None


def group(embeddings, threshold=SIMILARITY):
    """Single-linkage groups (lists of indexes) of unit vectors whose cosine similarity >= threshold."""
    n = len(embeddings)
    parent = list(range(n))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sims = embeddings @ embeddings.T
    for i, j in zip(*np.where(np.triu(sims >= threshold, 1))):
        parent[root(i)] = root(j)
    groups = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())


def update(engine, library, log):
    """Recompute /data/strangers.json. Returns the number of groups listed."""
    items = collect()
    cache = _load(CACHE, {}) or {}
    new = 0
    for it in items:
        key = f"{it['day']}/{it['crop']}"
        if key not in cache:
            e = embed(engine, REC_DIR / it["day"] / it["crop"])
            cache[key] = [round(float(v), 5) for v in e] if e is not None else None
            new += 1
    wanted = {f"{it['day']}/{it['crop']}" for it in items}
    cache = {k: v for k, v in cache.items() if k in wanted}
    _write(CACHE, cache)

    keep = [it for it in items if cache.get(f"{it['day']}/{it['crop']}") is not None]
    groups = []
    if keep:
        emb = np.array([cache[f"{it['day']}/{it['crop']}"] for it in keep], dtype=np.float32)
        emb /= np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
        hidden = set(_load(HIDDEN, []) or [])
        for idxs in group(emb):
            faces = sorted((keep[i] for i in idxs), key=lambda f: f["start"], reverse=True)
            clips = {(f["day"], f["stem"]) for f in faces}
            gid = min(f"{f['day']}/{f['crop']}" for f in faces)
            if len(clips) < 2 or gid in hidden:
                continue
            centroid = emb[idxs].mean(axis=0)
            centroid /= np.linalg.norm(centroid) + 1e-9
            name, score = library.match(centroid)
            groups.append({"id": gid, "faces": faces, "clips": len(clips), "days": len({d for d, _ in clips}),
                           "first": faces[-1]["start"], "last": faces[0]["start"],
                           "probably": {"name": name, "score": round(score, 2)} if name and score >= HINT else None})
    groups.sort(key=lambda g: (g["days"], g["clips"], g["last"]), reverse=True)
    _write(OUT, {"updated": dt.datetime.now().isoformat(timespec="seconds"), "days": DAYS, "groups": groups})
    log.info("strangers: %d unknown faces (%d new), %d recurring groups", len(keep), new, len(groups))
    return len(groups)
