#!/usr/bin/env python3
"""Every text token in design/tokens.css must pass WCAG AA on every surface it
can land on. Run from anywhere; exits non-zero on a failure.

This exists because the ratios in tokens.css are written in comments, and a
comment cannot stop someone darkening a value. This can.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
# Every sheet sync-tokens.py writes, because a project may override its accent
# and an override has to clear AA too. Checking only the source would let an
# unreadable brand colour ship.
GENERATED = [
    "panels/server/www/wall.css",
    "panels/server/www/deck.css",
    "panels/friend/extra/wall.css",
    "panels/friend/src/www/wall.css",
    "CamWatch/app/static/tokens.css",
]

# Text tokens and the floor each must clear. --dim is tertiary, but it is still
# text, so it gets the body threshold too: 3:1 is for 24px+, and none of these
# are reliably that large.
TEXT = {"ink": 4.5, "mute": 4.5, "dim": 4.5, "ok": 4.5, "warn": 4.5, "bad": 4.5,
        "accent-text": 4.5}
# Anything a text token can sit on.
SURFACES = ["bg", "card", "card-hi"]
# Tokens used as a fill, and the token naming the type that sits on each.
FILLS = {"accent": "accent-ink", "ok": "status-ink", "warn": "status-ink",
         "bad": "status-ink"}


def channel(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(value):
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def ratio(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def load(path):
    # Only literal hex values; the aliases are var() and resolve to these.
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{3,6})\s*;",
                           path.read_text()))


def audit(label, tok):
    """Check one palette. Returns the list of failures, empty if it passes."""
    print(f"\n=== {label} ===")
    missing = [n for n in list(TEXT) + SURFACES if n not in tok]
    if missing:
        print(f"FAIL  missing: {', '.join(missing)}")
        return [f"{label} is missing {', '.join(missing)}"]

    failures = []
    print(f"{'token':12} {'value':9} " + " ".join(f"{s:>9}" for s in SURFACES))
    for name, floor in TEXT.items():
        ratios = [ratio(tok[name], tok[s]) for s in SURFACES]
        worst = min(ratios)
        mark = "ok " if worst >= floor else "FAIL"
        print(f"{name:12} {tok[name]:9} " + " ".join(f"{r:9.2f}" for r in ratios)
              + f"  worst {worst:5.2f}  {mark}")
        if worst < floor:
            failures.append(f"{label}: --{name} is {worst:.2f}:1 on its worst "
                            f"surface, needs {floor}")

    print()
    for fill, ink in FILLS.items():
        r = ratio(tok[fill], tok[ink])
        print(f"{ink} on --{fill:11} {r:5.2f}  {'ok ' if r >= 4.5 else 'FAIL'}")
        if r < 4.5:
            failures.append(f"{label}: --{ink} on --{fill} is {r:.2f}:1, needs 4.5")

    # A surface token must never be bright enough to be mistaken for text.
    # If --faint ever passes AA, someone will use it as type again.
    print()
    for s in SURFACES:
        r = ratio(tok["faint"], tok[s])
        print(f"--faint on --{s:9} {r:5.2f}  (surface token: must stay under 4.5)")
        if r >= 4.5:
            failures.append(
                f"{label}: --faint is {r:.2f}:1 on --{s}: bright enough to be "
                "used as text, which is the bug this split fixed. Use --dim.")
    return failures


def main():
    failures = audit("design/tokens.css (source)", load(TOKENS))
    for rel in GENERATED:
        path = ROOT / rel
        if not path.exists():
            failures.append(f"{rel} has not been generated; run design/sync-tokens.py")
            continue
        failures += audit(rel, load(path))

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print(f"all token contrast checks passed ({len(GENERATED) + 1} palettes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
