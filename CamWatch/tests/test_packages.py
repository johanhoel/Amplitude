"""Synthetic scenarios for app/packages.py (run with the throwaway OpenCV venv)."""
import logging
import sys

import cv2
import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
import packages as pk  # noqa: E402

rng = np.random.default_rng(1)
H, W = 1520, 2688
NOISE = rng.normal(0, 12, (H // 8, W // 8, 1)).repeat(3, axis=2)
ZONE = {"name": "doorstep", "type": "package", "points": [[0.55, 0.55], [0.80, 0.55], [0.80, 0.85], [0.55, 0.85]]}


def scene(brightness=0, box=None, shadow=0.0, leaf=False, box_color=(60, 110, 160)):
    """Textured ground; optional parcel (fraction of zone width), soft shadow over the left half, a leaf."""
    base = np.full((H, W, 3), 110, np.uint8)
    img = np.clip(base + cv2.resize(NOISE, (W, H), interpolation=cv2.INTER_NEAREST), 0, 255).astype(np.float32)
    cv2.rectangle(img, (int(.6 * W), int(.6 * H)), (int(.75 * W), int(.62 * H)), (150, 150, 150), -1)  # a doormat edge
    if box:
        x0, y0 = int(.62 * W), int(.66 * H)
        cv2.rectangle(img, (x0, y0), (x0 + int(box * .25 * W), y0 + int(box * .30 * H)), box_color, -1)
        cv2.rectangle(img, (x0, y0), (x0 + int(box * .25 * W), y0 + int(box * .30 * H)), (30, 60, 90), 6)
    if leaf:
        cv2.circle(img, (int(.7 * W), int(.8 * H)), 14, (40, 90, 40), -1)
    if shadow:
        mask = np.zeros((H, W), np.float32)
        cv2.rectangle(mask, (int(.5 * W), int(.5 * H)), (int(.66 * W), int(.9 * H)), 1, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), 60)[..., None]
        img = img * (1 - shadow * mask)
    return np.clip(img + brightness, 0, 255).astype(np.uint8)


def run(name, steps, expect):
    events = []
    w = pk.PackageWatcher(lambda kind, z, pic, visit: events.append(kind), logging.getLogger("t"))
    w.set_zones([ZONE])
    t = 0.0
    w.tick(scene(), t + 100, 0)                       # learn the empty reference while quiet
    t = 200.0
    for frame in steps:                               # each step: a visit ended, then the scene looks like `frame`
        w.visit_ended(("day", "stem"), t)
        for dt in range(0, 200, 5):                   # quiet period after the visit, checks every 5 s
            w.tick(frame, t + dt, t)
        t += 300
    ok = events == expect
    print(f"{'PASS' if ok else 'FAIL'}  {name:<48} events={events} expected={expect}")
    return ok


empty = pk.ZonePatch(ZONE, scene())
for label, frame in [("parcel 0.6", scene(box=0.6)), ("parcel 0.3", scene(box=0.3)), ("shadow .35", scene(shadow=0.35)),
                     ("bright +25", scene(brightness=25)), ("leaf", scene(leaf=True))]:
    cur = pk.ZonePatch(ZONE, frame)
    print(f"  {label:<11} mean {empty.mean:.0f}->{cur.mean:.0f}  compare(blob, changed) = {pk.compare(empty, cur)}")
results = [
    run("visit, nothing left", [scene()], []),
    run("parcel left (~25% of zone)", [scene(box=0.6)], ["delivered"]),
    run("parcel left, later picked up", [scene(box=0.6), scene()], ["delivered", "picked_up"]),
    run("small parcel (~8% of zone)", [scene(box=0.3)], ["delivered"]),
    run("slow daylight change +25", [scene(brightness=25)], []),
    run("lights / IR jump +70 (undecidable)", [scene(brightness=70)], []),
    run("soft shadow over part of the zone", [scene(shadow=0.35)], []),
    run("a leaf blows in (tiny)", [scene(leaf=True)], []),
    run("grey parcel, same brightness (texture only)", [scene(box=0.5, box_color=(118, 118, 118))], ["delivered"]),
    run("parcel + shadow at the same time", [scene(box=0.5, shadow=0.35)], ["delivered"]),
]
print(f"{sum(results)}/{len(results)} passed")
