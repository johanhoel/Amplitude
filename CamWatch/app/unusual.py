"""Unusual activity: is this kind of visit rare for this camera at this time of day?

History is the clip sidecars of the last HISTORY_DAYS days before today (test clips left out), split into
weekdays and weekends. A person / vehicle / animal is unusual when this camera recorded that kind on none of those
days within WINDOW_MINUTES of this time of day - or saw it at this time, but never in this zone. Nothing is called
unusual until the camera has MIN_DAYS of history.
"""
import datetime as dt
import json
import re
import time

from alerts import kind_of
from common import env

HISTORY_DAYS = env("UNUSUAL_HISTORY_DAYS", 28, int)
WINDOW = env("UNUSUAL_WINDOW_MINUTES", 60, int)
MIN_DAYS = env("UNUSUAL_MIN_DAYS", 14, int)
REFRESH_SECONDS = 3600


def _minutes_apart(a, b):
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


class Rarity:
    def __init__(self, rec_dir, camera):
        self.rec_dir, self.camera = rec_dir, camera
        self.stem_re = re.compile(rf"^{re.escape(camera)}_\d{{6}}(?:-\d+)?\.json$")
        self.visits = []       # (date, minute of day, weekend, kind, zones)
        self.span = 0          # days of history
        self.loaded = 0.0       # when the history was read

    def keep_fresh(self):
        """Thread body: re-read the history every hour and right after midnight."""
        while True:
            day = dt.date.today()
            self.refresh(day)
            while time.time() - self.loaded < REFRESH_SECONDS and dt.date.today() == day:
                time.sleep(60)

    def refresh(self, today=None):
        """Re-read the history (the recorder does this hourly in a background thread)."""
        today = today or dt.date.today()
        visits, first = [], None
        for offset in range(1, HISTORY_DAYS + 1):
            day = today - dt.timedelta(days=offset)
            folder = self.rec_dir / day.isoformat()
            if not folder.is_dir():
                continue
            first = day
            for path in folder.iterdir():
                if not self.stem_re.match(path.name):
                    continue
                try:
                    meta = json.loads(path.read_text())
                    start = dt.datetime.fromisoformat(meta["start"])
                except (OSError, ValueError, KeyError):
                    continue
                if meta.get("test"):
                    continue
                kind = kind_of(meta.get("labels") or {})
                visits.append((day, start.hour * 60 + start.minute, start.weekday() >= 5, kind, set(meta.get("zones") or [])))
        self.visits, self.span, self.loaded = visits, (today - first).days if first else 0, time.time()

    def check(self, labels, zones, when=None):
        """A short explanation when this visit is unusual, else None."""
        when = when or dt.datetime.now()
        if not self.loaded:
            self.refresh(when.date())
        kind = kind_of(labels)
        if kind == "motion" or self.span < MIN_DAYS:
            return None
        minute, weekend = when.hour * 60 + when.minute, when.weekday() >= 5
        days = "weekends" if weekend else "weekdays"
        lo = (when - dt.timedelta(minutes=WINDOW)).strftime("%H:%M")
        hi = (when + dt.timedelta(minutes=WINDOW)).strftime("%H:%M")
        near = [v for v in self.visits if v[2] == weekend and v[3] == kind and _minutes_apart(v[1], minute) <= WINDOW]
        if not near:
            return f"no {kind} on {self.camera} between {lo} and {hi} on {days} in the last {self.span} days"
        for zone in sorted(zones or []):
            if not any(zone in v[4] for v in near) and any(zone in v[4] for v in self.visits if v[3] == kind):
                return f"{kind} at {zone}: not seen there between {lo} and {hi} on {days} in the last {self.span} days"
        return None
