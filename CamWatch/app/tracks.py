"""Backfill <stem>.track.json for clips recorded before the recorder saved tracks.

Runs the object model over the video (DETECT_FPS / 2 frames per second) and writes where each detected
object stood, in the same format the recorder writes live. The presence service turns tracks into
arrived / left. Existing track files are kept unless --force is given.

    python tracks.py                   all clips without a track
    python tracks.py --force           redo every clip
    python tracks.py --file /recordings/2026-10-03/camera1_153427.mp4
"""
import argparse
import json
from pathlib import Path

import cv2

from common import VIDEO_EXT, env, setup_logging
import settings
from objects import ObjectDetector
from recorder import DETECT_OBJECTS, OBJECT_CONFIDENCE, OBJECT_MIN_AREA, OBJECT_MODEL, VEHICLES, Zones

log = setup_logging("tracks")
REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
SAMPLE_FPS = env("TRACK_SAMPLE_FPS", 2.5, float)


def track_video(path, detector, zones):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    step = max(1, round(fps / SAMPLE_FPS))
    points, i = [], 0
    while cap.grab():
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            fh, fw = frame.shape[:2]
            for label, conf, (x, y, w, h) in detector.detect(frame):
                # Vehicles are kept inside ignore zones too: the parking spot is usually in one
                if w * h < OBJECT_MIN_AREA * fw * fh or (label not in VEHICLES and zones.ignored((x + w / 2) / fw, (y + h / 2) / fh)):
                    continue
                points.append([round(i / fps, 2), label, round((x + w / 2) / fw, 4), round(min(y + h, fh) / fh, 4),
                               round(w / fw, 4), round(h / fh, 4), round(conf, 2)])
        i += 1
    cap.release()
    return points, round(i / fps, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="redo clips that already have a track")
    ap.add_argument("--file", help="only this video")
    args = ap.parse_args()

    detector = ObjectDetector(OBJECT_MODEL, DETECT_OBJECTS, OBJECT_CONFIDENCE)
    zones = Zones(settings.load()["zones"])
    videos = [Path(args.file)] if args.file else sorted(
        p for p in REC_DIR.glob("*/*") if p.suffix.lower() in VIDEO_EXT)
    done = 0
    for video in videos:
        out = video.with_suffix(".track.json")
        if out.exists() and not args.force:
            continue
        meta = video.with_suffix(".json")
        if not meta.exists():
            continue
        points, duration = track_video(video, detector, zones)
        # Video time 0 is the start of the pre-roll, so times here run a few seconds ahead of the live format
        out.write_text(json.dumps({"source": "backfill", "start": json.loads(meta.read_text()).get("start"),
                                   "duration": duration, "points": points}))
        done += 1
        log.info("%s: %d detections", video.relative_to(REC_DIR), len(points))
    log.info("done, %d clip(s) tracked", done)


if __name__ == "__main__":
    main()
