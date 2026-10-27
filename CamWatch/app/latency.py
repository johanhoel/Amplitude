"""Compare the delay of two RTSP streams of the same camera (e.g. direct vs. through a restreamer like Scrypted).

Both streams are read side by side; for every frame the amount of change from the previous frame is recorded with its
arrival time. Motion in front of the camera makes both signals spike; lining the two signals up gives how much later
stream B shows the same thing than stream A. Walk past or wave at the camera while it runs.

    docker compose run --rm recorder python latency.py --seconds 60                       # A = RTSP_URL, health only
    docker compose run --rm recorder python latency.py --b "rtsp://user:pass@camera/..."  # A = RTSP_URL vs B
    docker compose run --rm recorder python latency.py --a URL --b URL

Tip: put the direct URL in an environment variable instead of the command line so the password isn't kept in your
shell history: `read -rs CAM && docker compose run --rm -e LATENCY_B="$CAM" recorder python latency.py`.
"""
import argparse
import os
import threading
import time

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

WIDTH = 320


class Probe(threading.Thread):
    def __init__(self, name, url, seconds):
        super().__init__(daemon=True)
        self.name, self.url, self.seconds = name, url, seconds
        self.samples = []      # (arrival time, mean absolute change)
        self.opened = None     # seconds to the first frame
        self.size = None
        self.error = None

    def run(self):
        t0 = time.time()
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000,
                                                          cv2.CAP_PROP_READ_TIMEOUT_MSEC, 15000])
        if not cap.isOpened():
            self.error = "could not open the stream"
            return
        prev = None
        end = t0 + self.seconds
        while time.time() < end:
            ok, frame = cap.read()
            now = time.time()
            if not ok:
                self.error = "stream stopped"
                break
            if self.opened is None:
                self.opened, self.size = now - t0, frame.shape[1::-1]
            h, w = frame.shape[:2]
            small = cv2.cvtColor(cv2.resize(frame, (WIDTH, round(h * WIDTH / w))), cv2.COLOR_BGR2GRAY).astype(np.float32)
            if prev is not None:
                self.samples.append((now, float(np.mean(np.abs(small - prev)))))
            prev = small
        cap.release()

    def report(self):
        if self.error and not self.samples:
            return f"{self.name}: {self.error}"
        t = np.array([s[0] for s in self.samples])
        gaps = np.diff(t) if len(t) > 1 else np.array([0.0])
        fps = (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 else 0
        stalls = int((gaps > 1.0).sum())
        return (f"{self.name}: {self.size[0]}x{self.size[1]}, first frame after {self.opened:.1f} s, {fps:.1f} fps, "
                f"longest gap {gaps.max() * 1000:.0f} ms, stalls > 1 s: {stalls}" + (f" ({self.error})" if self.error else ""))


def signal(samples, t0, t1, step):
    """Change per time slot (max of the frames that arrived in it), zero-mean, unit variance."""
    grid = np.arange(t0, t1, step)
    out = np.zeros(len(grid))
    for t, v in samples:
        i = int((t - t0) / step)
        if 0 <= i < len(out):
            out[i] = max(out[i], v)
    out -= out.mean()
    sd = out.std()
    return out / sd if sd > 0 else out


def lag(a, b, step=0.02, max_lag=5.0):
    """Seconds by which B is behind A (positive = B later), and how strong the match is (0..1)."""
    t0 = max(a[0][0], b[0][0]) + 1
    t1 = min(a[-1][0], b[-1][0])
    if t1 - t0 < 10:
        return None, 0.0
    sa, sb = signal(a, t0, t1, step), signal(b, t0, t1, step)
    n = int(max_lag / step)
    best, best_k = -1.0, 0
    for k in range(-n, n + 1):
        x, y = (sa[:len(sa) - k], sb[k:]) if k >= 0 else (sa[-k:], sb[:len(sb) + k])
        if len(x) > 100:
            c = float(np.dot(x, y) / len(x))
            if c > best:
                best, best_k = c, k
    return best_k * step, best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default=os.environ.get("RTSP_URL"), help="stream A (default: RTSP_URL)")
    ap.add_argument("--b", default=os.environ.get("LATENCY_B"), help="stream B (default: LATENCY_B)")
    ap.add_argument("--seconds", type=int, default=60)
    args = ap.parse_args()
    if not args.a:
        raise SystemExit("no stream A: set RTSP_URL or pass --a")

    probes = [Probe("A", args.a, args.seconds)] + ([Probe("B", args.b, args.seconds)] if args.b else [])
    print(f"Reading {len(probes)} stream(s) for {args.seconds} s" + (" - walk past or wave at the camera now." if args.b else "."))
    for p in probes:
        p.start()
    for p in probes:
        p.join()
    for p in probes:
        print(p.report())
    if len(probes) == 2 and probes[0].samples and probes[1].samples:
        seconds, strength = lag(probes[0].samples, probes[1].samples)
        if seconds is None:
            print("Not enough overlapping video to compare.")
        elif strength < 0.3:
            print(f"No clear match (strength {strength:.2f}): there was too little motion. Run again and move in front of the camera.")
        else:
            who, by = ("B", seconds) if seconds >= 0 else ("A", -seconds)
            print(f"Stream {who} is {by * 1000:.0f} ms behind the other (match strength {strength:.2f}).")


if __name__ == "__main__":
    main()
