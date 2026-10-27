"""Check latency.lag() with synthetic motion signals: B is the same motion as A, arriving 750 ms later."""
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
from latency import lag  # noqa: E402

rng = np.random.default_rng(3)
fps, seconds, delay = 15, 60, 0.75
t = np.arange(0, seconds, 1 / fps) + 1000
motion = np.zeros(len(t))
for start in rng.uniform(5, 55, 6):              # six walk-pasts of ~2 s
    motion += np.exp(-((t - 1000 - start) / 0.8) ** 2) * 20
a = [(ti + rng.normal(0, 0.01), m + abs(rng.normal(0, 0.5))) for ti, m in zip(t, motion)]
b = [(ti + delay + rng.normal(0, 0.01), m + abs(rng.normal(0, 0.5))) for ti, m in zip(t[::2], motion[::2])]  # B at half the fps
s, strength = lag(a, b)
print(f"{'PASS' if abs(s - delay) < 0.08 else 'FAIL'} measured B behind A: {s * 1000:.0f} ms (true {delay * 1000:.0f} ms), strength {strength:.2f}")
s, strength = lag(b, a)
print(f"{'PASS' if abs(s + delay) < 0.08 else 'FAIL'} swapped: {s * 1000:.0f} ms (true {-delay * 1000:.0f} ms)")
flat = [(ti, abs(rng.normal(0, 0.5))) for ti in t]
s, strength = lag(flat, [(ti + delay, v) for ti, v in flat[::-1]])
print(f"{'PASS' if strength < 0.3 else 'FAIL'} no motion -> weak match (strength {strength:.2f})")
