"""Presence log: who came and when, from the camera's finished events, stored in MariaDB.

Every PRESENCE_SCAN_INTERVAL seconds the recordings folder is scanned. Each event (<stem>.json from the
recorder) becomes one row in `visits`; who was there goes into `visitors`, combining
  * identified faces            (<stem>.faces.json, from facematch)
  * manual tags in the web UI   (<stem>.labels.json)
  * number plates               (plates in <stem>.json, named when the plate is known)
  * plain detections            (unknown person, car, dog, ...) when nothing more specific is known.
Direction comes from <stem>.track.json (where people stood over time, written by the recorder or by
tracks.py) and the house / street zones drawn in the web UI: a path from a street zone to a house zone
is "arrived", the reverse "left", street -> house -> street "visited" (e.g. a delivery).
A visit is re-read whenever one of those files or the house/street zones change.
When retention deletes a clip the visit stays in the log, marked clip_deleted.

    python presence.py            run forever
    python presence.py --once     one pass, then exit
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import time
from pathlib import Path

import pymysql

from common import Ntfy, env, setup_logging
import settings

log = setup_logging("presence")

REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
SCAN_INTERVAL = env("PRESENCE_SCAN_INTERVAL", 15, int)
SUMMARY_TIME = env("DAILY_SUMMARY_TIME", "21:00")  # HH:MM local time; empty = no daily summary push
WEEKLY_SUMMARY = env("WEEKLY_SUMMARY", "sun 20:00")  # "<day> HH:MM" for the weekly report push; empty = none
HEALTH_FILE = Path("/tmp/healthy")

VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle"}
ANIMALS = {"dog", "cat", "bird", "horse", "sheep", "cow", "bear"}

ASPECT = 16 / 9   # frame width / height: distances are measured in frame heights
ZONE_NEAR = 0.06  # a foot point this close to a zone counts as in it (people near the frame edge, short boxes)
TRACK_GAP = 3.0   # seconds without a matching detection before a path ends
MIN_POINTS = 3    # shorter paths are noise

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS visits (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        camera VARCHAR(64) NOT NULL,
        day CHAR(10) NOT NULL,
        stem VARCHAR(128) NOT NULL,
        started_at DATETIME NOT NULL,
        ended_at DATETIME NULL,
        duration_s INT UNSIGNED NULL,
        labels JSON NULL COMMENT 'detected object types -> best confidence',
        zones JSON NULL,
        loitering TINYINT(1) NOT NULL DEFAULT 0,
        test TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'simulated from the web UI',
        faces_seen INT UNSIGNED NULL COMMENT 'NULL until facematch has processed the clip',
        unknown_faces INT UNSIGNED NULL,
        clip_deleted TINYINT(1) NOT NULL DEFAULT 0,
        source_sig VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'mtimes of the source files + zones hash last imported',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY clip (day, stem),
        KEY (started_at)
    )""",
    "ALTER TABLE visits ADD COLUMN IF NOT EXISTS direction VARCHAR(32) NULL "
    "COMMENT 'arrived / left / visited, comma separated in time order; NULL = unknown' AFTER duration_s",
    "ALTER TABLE visits ADD COLUMN IF NOT EXISTS movements JSON NULL "
    "COMMENT 'per person path: direction, from/to zone, seconds, points' AFTER direction",
    """CREATE TABLE IF NOT EXISTS visitors (
        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        visit_id INT UNSIGNED NOT NULL,
        kind ENUM('person', 'vehicle', 'animal') NOT NULL,
        name VARCHAR(128) NULL COMMENT 'NULL = not identified',
        source ENUM('face', 'manual', 'plate', 'detection') NOT NULL,
        detail VARCHAR(64) NULL COMMENT 'plate number or object type',
        confidence DECIMAL(4,3) NULL,
        first_seen_s DECIMAL(7,1) NULL COMMENT 'seconds into the clip',
        direction VARCHAR(16) NULL COMMENT 'set when the path can be tied to this person',
        KEY (visit_id),
        KEY (name),
        CONSTRAINT FOREIGN KEY (visit_id) REFERENCES visits (id) ON DELETE CASCADE
    )""",
    "ALTER TABLE visitors ADD COLUMN IF NOT EXISTS direction VARCHAR(16) NULL "
    "COMMENT 'set when the path can be tied to this person' AFTER first_seen_s",
    # One line per visit: when, who, what. Simulated events are left out.
    """CREATE OR REPLACE VIEW presence_log AS
        SELECT v.id AS visit_id, v.started_at, v.ended_at, v.duration_s, v.direction,
               COALESCE(GROUP_CONCAT(DISTINCT COALESCE(p.name,
                   CASE p.kind WHEN 'person' THEN 'unknown person' ELSE COALESCE(p.detail, p.kind) END)
                   ORDER BY p.name IS NULL, p.name SEPARATOR ', '), 'motion') AS who,
               SUM(p.name IS NOT NULL) > 0 AS identified,
               v.camera, CONCAT(v.day, '/', v.stem) AS clip, v.clip_deleted
        FROM visits v LEFT JOIN visitors p ON p.visit_id = v.id
        WHERE v.test = 0
        GROUP BY v.id""",
]


def connect():
    """MariaDB on the host, reached through its socket (mounted into the container)."""
    return pymysql.connect(unix_socket=env("DB_SOCKET", "/run/mysqld/mysqld.sock"), user=env("DB_USER", "camwatch"),
                           password=env("DB_PASSWORD", ""), database=env("DB_NAME", "camwatch"),
                           charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None


def mtime(path):
    try:
        return int(path.stat().st_mtime)
    except FileNotFoundError:
        return 0


def visitors_for(meta, faces, tags, car_moves=()):
    """[(kind, name, source, detail, confidence, first_seen_s, direction)] for one event."""
    out, named = [], set()
    for k in (faces or {}).get("known", []):
        if k.get("name") and k["name"] not in named:
            named.add(k["name"])
            out.append(("person", k["name"], "face", None, k.get("score"), k.get("first_seen_s"), None))
    for t in tags or []:
        if t.get("name") and t["name"] not in named:
            named.add(t["name"])
            out.append(("person", t["name"], "manual", None, None, None, None))
    labels = meta.get("labels") or {}
    if "person" in labels and not named:
        out.append(("person", None, "detection", "person", labels["person"], None, None))
    plated = set()
    for m in car_moves:  # a car arriving at / leaving a parking zone
        if m.get("plate"):
            plated.add(m["plate"])
        out.append(("vehicle", m.get("name") or None, "plate" if m.get("plate") else "detection",
                    m.get("plate") or m.get("label") or "car", m.get("conf"), None, m["direction"]))
    for p in meta.get("plates") or []:
        if p.get("plate") and p["plate"] not in plated:
            plated.add(p["plate"])
            out.append(("vehicle", p.get("name") or None, "plate", p["plate"], p.get("conf"), None, None))
    for label, conf in labels.items():
        if label in VEHICLES and not plated and not car_moves:
            out.append(("vehicle", None, "detection", label, conf, None, None))
        elif label in ANIMALS:
            out.append(("animal", None, "detection", label, conf, None, None))
    return out


def car_moves_for(meta, track, zones):
    """Cars arriving / leaving. New clips: what the recorder saw live (meta "vehicles"). Older clips: compare
    the parking zones in the first and last seconds of the backfilled track."""
    if "vehicles" in meta:
        return meta["vehicles"] or []
    parking = [z for z in zones if z["type"] == "parking"]
    if not parking or not track or track.get("source") != "backfill" or not track.get("duration"):
        return []
    end = track["duration"]
    plates = [p for p in meta.get("plates") or [] if p.get("plate")]
    moves = []
    for z in parking:
        def cars(lo, hi):
            return [(label, c) for t, label, x, y, _, _, c in track.get("points") or []
                    if lo <= t <= hi and label in VEHICLES and _inside(x, y, z["points"])]
        before, after = cars(0, 3), cars(end - 3, end)
        if bool(before) != bool(after):
            label, conf = max(before or after, key=lambda c: c[1])
            plate = plates[0] if len(plates) == 1 else {}
            moves.append({"direction": "arrived" if after else "left", "zone": z["name"], "label": label,
                          "conf": conf, "at": None, "plate": plate.get("plate"), "name": plate.get("name")})
    return moves


def direction_zones():
    """House, street and parking zones from the web UI, plus a short hash so zone edits re-evaluate old visits."""
    zones = [z for z in settings.load()["zones"]
             if z.get("type") in ("house", "street", "parking") and len(z.get("points", [])) >= 3]
    return zones, hashlib.sha1(json.dumps(zones, sort_keys=True).encode()).hexdigest()[:8]


def _inside(x, y, pts):
    hit = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _edge_distance(x, y, pts):
    """Distance from a point to a polygon's outline, in frame heights."""
    best = math.inf
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        ax, ay, bx, by, px = x1 * ASPECT, y1, x2 * ASPECT, y2, x * ASPECT
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy or 1)))
        best = min(best, math.hypot(px - ax - t * dx, y - ay - t * dy))
    return best


def zone_at(x, y, zones):
    """The house/street zone a foot point is in (or right next to), else None."""
    near = None, ZONE_NEAR
    for z in zones:
        if _inside(x, y, z["points"]):
            return z
        d = _edge_distance(x, y, z["points"])
        if d < near[1]:
            near = z, d
    return near[0]


def person_paths(points):
    """Split person detections into one path per person: each pass's detections join the nearest path
    that was seen recently and could have walked that far, otherwise start a new path."""
    by_time = {}
    for t, label, x, y, *_ in points:
        if label == "person":
            by_time.setdefault(t, []).append((x, y))
    paths = []
    for t in sorted(by_time):
        free = [p for p in paths if t - p[-1][0] <= TRACK_GAP]
        for x, y in by_time[t]:
            def dist(p):
                return math.hypot((x - p[-1][1]) * ASPECT, y - p[-1][2])
            reachable = [p for p in free if dist(p) <= 0.15 + 0.25 * (t - p[-1][0])]
            if reachable:
                best = min(reachable, key=dist)
                best.append((t, x, y))
                free.remove(best)
            else:
                paths.append([(t, x, y)])
    return [p for p in paths if len(p) >= MIN_POINTS]


def path_movement(path, zones):
    """Where one path started and ended, and what that means (arrived / left / visited / None)."""
    hits = [zone_at(x, y, zones) for _, x, y in path]
    head = max(MIN_POINTS, len(path) // 3)
    start = next((z for z in hits[:head] if z), None)
    end = next((z for z in reversed(hits[-head:]) if z), None)
    kinds = (start and start["type"], end and end["type"])
    direction = {("street", "house"): "arrived", ("house", "street"): "left"}.get(kinds)
    if kinds == ("street", "street") and any(z and z["type"] == "house" for z in hits):
        direction = "visited"  # came to the house and went away again (delivery, visitor at the door)
    return {"direction": direction, "from": start and start["name"], "to": end and end["name"],
            "from_s": path[0][0], "to_s": path[-1][0], "points": len(path)}


def movements_for(track, zones):
    zones = [z for z in zones if z["type"] in ("house", "street")]
    if not track or not zones:
        return []
    return sorted((path_movement(p, zones) for p in person_paths(track.get("points") or [])), key=lambda m: m["from_s"])


def import_visit(cur, day, stem, meta, faces, tags, sig, track=None, zones=()):
    start = dt.datetime.fromisoformat(meta["start"])
    end = dt.datetime.fromisoformat(meta["end"]) if meta.get("end") else None
    moves = movements_for(track, zones)
    directions = [m["direction"] for m in moves if m["direction"]]
    direction = ",".join(dict.fromkeys(directions)) or None
    cur.execute("""INSERT INTO visits (camera, day, stem, started_at, ended_at, duration_s, direction, movements, labels,
                                       zones, loitering, test, faces_seen, unknown_faces, clip_deleted, source_sig)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
                   ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id), camera = VALUES(camera),
                       started_at = VALUES(started_at), ended_at = VALUES(ended_at), duration_s = VALUES(duration_s),
                       direction = VALUES(direction), movements = VALUES(movements),
                       labels = VALUES(labels), zones = VALUES(zones), loitering = VALUES(loitering), test = VALUES(test),
                       faces_seen = VALUES(faces_seen), unknown_faces = VALUES(unknown_faces), clip_deleted = 0,
                       source_sig = VALUES(source_sig)""",
                (meta.get("camera", ""), day, stem, start, end,
                 max(0, round((end - start).total_seconds())) if end else None,
                 direction, json.dumps(moves) if track else None,
                 json.dumps(meta.get("labels") or {}), json.dumps(meta.get("zones") or []),
                 bool(meta.get("loitering")), bool(meta.get("test")),
                 faces.get("faces_seen") if faces and "error" not in faces else None,
                 sum(u.get("count", 1) for u in faces.get("unknown", [])) if faces and "error" not in faces else None,
                 sig))
    visit_id = cur.lastrowid
    cur.execute("DELETE FROM visitors WHERE visit_id = %s", (visit_id,))
    rows = visitors_for(meta, faces, tags, car_moves_for(meta, track, zones))
    # A direction belongs to a person only when it can't be anyone else: one person in the visit, and every
    # path that has a direction agrees
    people = [r for r in rows if r[0] == "person"]
    person_dir = directions[0] if len(people) == 1 and len(set(directions)) == 1 else None
    rows = [(*r[:6], person_dir) if r[0] == "person" else r for r in rows]
    if rows:
        cur.executemany("""INSERT INTO visitors (visit_id, kind, name, source, detail, confidence, first_seen_s, direction)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", [(visit_id, *r) for r in rows])
    cars = [f"car {r[6]}" for r in rows if r[0] == "vehicle" and r[6]]
    return rows, ", ".join(filter(None, [direction] + cars)) or None


def scan(db):
    """One pass over the recordings folder. Returns the number of visits (re)imported."""
    with db.cursor() as cur:
        cur.execute("SELECT day, stem, source_sig, clip_deleted FROM visits")
        known = {(r["day"], r["stem"]): r for r in cur.fetchall()}
    seen, changed = set(), 0
    zones, zones_hash = direction_zones()
    for folder in sorted(p for p in REC_DIR.iterdir() if p.is_dir()):
        for meta_path in folder.glob("*.json"):
            stem = meta_path.name[:-5]
            if stem.endswith((".faces", ".labels", ".track")):
                continue
            key = (folder.name, stem)
            seen.add(key)
            files = [meta_path, folder / f"{stem}.faces.json", folder / f"{stem}.labels.json", folder / f"{stem}.track.json"]
            sig = "-".join(str(mtime(f)) for f in files) + "-" + zones_hash
            if key in known and known[key]["source_sig"] == sig and not known[key]["clip_deleted"]:
                continue
            meta = read_json(meta_path)
            if not meta or "start" not in meta:
                continue
            try:
                with db.cursor() as cur:
                    camera = meta.get("camera") or settings.primary_camera()
                    cam_zones = [z for z in zones if z.get("camera", settings.primary_camera()) == camera]
                    who, direction = import_visit(cur, *key, meta, read_json(files[1]), read_json(files[2]), sig,
                                                  read_json(files[3]), cam_zones)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("could not import %s/%s", *key)
                continue
            changed += 1
            names = ", ".join(n or (d if k != "person" else "unknown person") for k, n, _, d, *_ in who) or "motion"
            log.info("%s %s/%s: %s%s", "updated" if key in known else "logged", *key, names,
                     f" ({direction})" if direction else "")
    gone = [k for k, r in known.items() if k not in seen and not r["clip_deleted"]]
    if gone:
        with db.cursor() as cur:
            cur.executemany("UPDATE visits SET clip_deleted = 1 WHERE day = %s AND stem = %s", gone)
        db.commit()
        log.info("%d clip(s) deleted from disk; their visits stay in the log", len(gone))
    return changed


def daily_summary(db, day):
    """(title, message) summarising one day's visits from the presence log."""
    start = dt.datetime.combine(day, dt.time())
    end = start + dt.timedelta(days=1)
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n, SUM(direction LIKE %s) visited FROM visits "
                    "WHERE test = 0 AND started_at >= %s AND started_at < %s", ("%visited%", start, end))
        totals = cur.fetchone()
        cur.execute("""SELECT p.kind, p.name, p.detail, p.direction, v.started_at
                       FROM visitors p JOIN visits v ON v.id = p.visit_id
                       WHERE v.test = 0 AND v.started_at >= %s AND v.started_at < %s
                       ORDER BY v.started_at""", (start, end))
        rows = cur.fetchall()

    people, unknown, cars, animals = {}, 0, [], {}
    for r in rows:
        at = r["started_at"].strftime("%H:%M")
        if r["kind"] == "person" and r["name"]:
            p = people.setdefault(r["name"], {"count": 0, "first": at, "last": at})
            p["count"] += 1
            p["last"] = at
        elif r["kind"] == "person":
            unknown += 1
        elif r["kind"] == "vehicle" and r["direction"]:
            cars.append(f"{at} {r['name'] or r['detail'] or 'car'} {r['direction']}")
        elif r["kind"] == "animal":
            animals[r["detail"]] = animals.get(r["detail"], 0) + 1

    lines = [f"{totals['n'] or 0} event{'' if totals['n'] == 1 else 's'}"]
    for name, p in sorted(people.items(), key=lambda kv: -kv[1]["count"]):
        times = p["first"] if p["count"] == 1 else f"{p['first']}-{p['last']}"
        lines.append(f"{name}: {p['count']}x ({times})")
    if unknown:
        lines.append(f"Unidentified people: {unknown} visit{'' if unknown == 1 else 's'}")
    if totals["visited"]:
        lines.append(f"Came to the door and left (delivery/visitor): {int(totals['visited'])}")
    if cars:
        lines.append("Cars: " + "; ".join(cars))
    if animals:
        lines.append("Animals: " + ", ".join(f"{k} {v}x" for k, v in sorted(animals.items())))
    return f"{env('CAMERA_NAME', 'camera')}: summary {day:%a %d %b}", "\n".join(lines)


def weekly_report(db, monday):
    """Numbers for the week starting `monday` (a date), plus the previous week's total for comparison."""
    start = dt.datetime.combine(monday, dt.time())
    end, prev = start + dt.timedelta(days=7), start - dt.timedelta(days=7)
    rng = (start, end)
    with db.cursor() as cur:
        def one(sql, args):
            cur.execute(sql, args)
            return cur.fetchone()

        def rows(sql, args):
            cur.execute(sql, args)
            return cur.fetchall()

        base = "FROM visits v WHERE v.test = 0 AND v.started_at >= %s AND v.started_at < %s"
        total = one(f"SELECT COUNT(*) n {base}", rng)["n"]
        prev_total = one(f"SELECT COUNT(*) n {base}", (prev, start))["n"]
        per_day = {r["d"]: r["n"] for r in rows(f"SELECT DATE(v.started_at) d, COUNT(*) n {base} GROUP BY d", rng)}
        per_hour = {r["h"]: r["n"] for r in rows(f"SELECT HOUR(v.started_at) h, COUNT(*) n {base} GROUP BY h", rng)}
        door = one(f"SELECT COUNT(*) n {base} AND v.direction LIKE %s", (*rng, "%visited%"))["n"]
        joined = ("FROM visitors p JOIN visits v ON v.id = p.visit_id "
                  "WHERE v.test = 0 AND v.started_at >= %s AND v.started_at < %s")
        people = rows(f"""SELECT p.name, COUNT(DISTINCT v.id) n, MIN(v.started_at) first, MAX(v.started_at) last,
                                 SUM(p.direction = 'arrived') arrived, SUM(p.direction = 'left') lft
                          {joined} AND p.kind = 'person' AND p.name IS NOT NULL GROUP BY p.name ORDER BY n DESC""", rng)
        unknown = one(f"SELECT COUNT(DISTINCT v.id) n {joined} AND p.kind = 'person' AND p.name IS NULL", rng)["n"]
        cars = rows(f"""SELECT v.started_at at, v.day, v.stem, COALESCE(p.name, p.detail) who, p.direction
                        {joined} AND p.kind = 'vehicle' AND p.direction IS NOT NULL ORDER BY v.started_at""", rng)
        animals = rows(f"SELECT p.detail kind, COUNT(*) n {joined} AND p.kind = 'animal' GROUP BY p.detail ORDER BY n DESC", rng)

    packages = []
    try:
        for line in (Path(env("DATA_DIR", "/data")) / "packages.jsonl").read_text().splitlines():
            p = json.loads(line)
            if start <= dt.datetime.fromisoformat(p["at"]) < end:
                packages.append(p)
    except (FileNotFoundError, ValueError, KeyError):
        pass
    days = [(monday + dt.timedelta(days=i)) for i in range(7)]
    busiest = max(per_hour, key=per_hour.get) if per_hour else None
    return {"monday": monday, "sunday": monday + dt.timedelta(days=6), "total": total, "prev_total": prev_total,
            "change": round((total - prev_total) * 100 / prev_total) if prev_total else None,
            "per_day": [(d, per_day.get(d, 0)) for d in days], "per_hour": [per_hour.get(h, 0) for h in range(24)],
            "busiest_hour": busiest, "people": people, "unknown": unknown, "door_visits": door, "cars": cars,
            "animals": animals, "packages": packages}


def weekly_text(r):
    """The weekly push: short, one fact per line."""
    lines = [f"{r['total']} events" + (f" ({r['change']:+d}% vs last week)" if r["change"] is not None else "")]
    if r["people"]:
        lines.append(", ".join(f"{p['name']} {p['n']}x" for p in r["people"][:5]))
    if r["unknown"]:
        lines.append(f"Unidentified people: {r['unknown']} visits")
    if r["door_visits"]:
        lines.append(f"Came to the door and left: {r['door_visits']}")
    delivered = sum(1 for p in r["packages"] if p.get("kind") == "delivered")
    if delivered:
        lines.append(f"Packages: {delivered}")
    arrived = sum(1 for c in r["cars"] if c["direction"] == "arrived")
    if arrived:
        lines.append(f"Car arrivals: {arrived}")
    if r["busiest_hour"] is not None:
        lines.append(f"Busiest hour: {r['busiest_hour']:02d}-{(r['busiest_hour'] + 1) % 24:02d}")
    return f"{env('CAMERA_NAME', 'camera')}: week {r['monday']:%V} ({r['monday']:%d %b} - {r['sunday']:%d %b})", "\n".join(lines)


def weekly_due(last_week, now):
    """Monday of the week to report if the weekly push should go out now (WEEKLY_SUMMARY like "sun 20:00"), else None."""
    try:
        day, at = WEEKLY_SUMMARY.split()
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(day.lower()[:3])
        at = dt.time.fromisoformat(at)
    except (ValueError, AttributeError):
        return None
    monday = now.date() - dt.timedelta(days=now.weekday())
    if (now.weekday(), now.time()) >= (weekday, at) and last_week != monday:
        return monday
    return None


def summary_due(last_sent, now):
    """Today's date if the daily summary should go out now, else None."""
    if not SUMMARY_TIME:
        return None
    try:
        at = dt.time.fromisoformat(SUMMARY_TIME)
    except ValueError:
        return None
    return now.date() if now.time() >= at and last_sent != now.date() else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--summary", metavar="YYYY-MM-DD", nargs="?", const="today",
                    help="print the daily summary for a day (default today) and exit; add --send to push it")
    ap.add_argument("--week", metavar="YYYY-MM-DD", nargs="?", const="this",
                    help="print the weekly report for the week containing that day (default this week); --send pushes it")
    ap.add_argument("--send", action="store_true", help="with --summary / --week: also send it to ntfy")
    args = ap.parse_args()
    web = (env("WEB_BASE_URL", "") or "").rstrip("/")

    if args.week:
        day = dt.date.today() if args.week == "this" else dt.date.fromisoformat(args.week)
        monday = day - dt.timedelta(days=day.weekday())
        title, message = weekly_text(weekly_report(connect(), monday))
        print(f"{title}\n{message}")
        if args.send:
            Ntfy(log).send(message, title=title, tags="bar_chart", priority="low",
                           click=f"{web}/report?week={monday}" if web else None)
        return

    if args.summary:
        day = dt.date.today() if args.summary == "today" else dt.date.fromisoformat(args.summary)
        title, message = daily_summary(connect(), day)
        print(f"{title}\n{message}")
        if args.send:
            web = (env("WEB_BASE_URL", "") or "").rstrip("/")
            Ntfy(log).send(message, title=title, tags="calendar", priority="low", click=f"{web}/log" if web else None)
        return

    ntfy = Ntfy(log)
    # Starting after today's summary time counts as "already sent" so a restart doesn't repeat it
    summary_sent = dt.date.today() if summary_due(None, dt.datetime.now()) else None
    week_sent = weekly_due(None, dt.datetime.now())  # same for the weekly report
    db = None
    while True:
        try:
            if db is None:
                db = connect()
                with db.cursor() as cur:
                    for stmt in SCHEMA:
                        cur.execute(stmt)
                db.commit()
                log.info("connected to database, logging visits from %s", REC_DIR)
            db.ping()  # raises if the connection dropped; the handler below reconnects
            scan(db)
            day = summary_due(summary_sent, dt.datetime.now())
            if day and not args.once:
                summary_sent = day
                title, message = daily_summary(db, day)
                web = (env("WEB_BASE_URL", "") or "").rstrip("/")
                ntfy.send(message, title=title, tags="calendar", priority="low", click=f"{web}/log" if web else None)
                log.info("daily summary sent: %s", message.replace("\n", " | "))
            monday = weekly_due(week_sent, dt.datetime.now())
            if monday and not args.once:
                week_sent = monday
                title, message = weekly_text(weekly_report(db, monday))
                ntfy.send(message, title=title, tags="bar_chart", priority="low",
                          click=f"{web}/report?week={monday}" if web else None)
                log.info("weekly report sent: %s", message.replace("\n", " | "))
            HEALTH_FILE.touch()
        except pymysql.MySQLError:
            log.exception("database error, retrying")
            try:
                db and db.close()
            except Exception:
                pass
            db = None
        if args.once:
            break
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
