#!/usr/bin/env python3
"""Every text token in design/tokens.css must pass WCAG AA on every surface it
can land on. Run from anywhere; exits non-zero on a failure.

This exists because the ratios in tokens.css are written in comments, and a
comment cannot stop someone darkening a value. This can.
"""
import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parent / "tokens.css"

# Text tokens and the floor each must clear. --dim is tertiary, but it is still
# text, so it gets the body threshold too: 3:1 is for 24px+, and none of these
# are reliably that large.
TEXT = {"ink": 4.5, "mute": 4.5, "dim": 4.5, "ok": 4.5, "warn": 4.5, "bad": 4.5,
        "accent-text": 4.5}
# Anything a text token can sit on.
SURFACES = ["bg", "card", "card-hi"]
# Tokens used as a fill with --accent-ink type on top.
FILLS = {"accent": "accent-ink", "ok": "accent-ink", "warn": "accent-ink",
         "bad": "accent-ink"}


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


def load():
    text = TOKENS.read_text()
    # Only literal hex values; the aliases are var() and resolve to these.
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{3,6})\s*;", text))


def main():
    tok = load()
    missing = [n for n in list(TEXT) + SURFACES if n not in tok]
    if missing:
        print(f"FAIL  tokens.css is missing: {', '.join(missing)}")
        return 1

    failures = []
    print(f"{'token':12} {'value':9} " + " ".join(f"{s:>9}" for s in SURFACES))
    for name, floor in TEXT.items():
        ratios = [ratio(tok[name], tok[s]) for s in SURFACES]
        worst = min(ratios)
        mark = "ok " if worst >= floor else "FAIL"
        print(f"{name:12} {tok[name]:9} " + " ".join(f"{r:9.2f}" for r in ratios)
              + f"  worst {worst:5.2f}  {mark}")
        if worst < floor:
            failures.append(f"{name} is {worst:.2f}:1 on its worst surface, needs {floor}")

    print()
    for fill, ink in FILLS.items():
        r = ratio(tok[fill], tok[ink])
        print(f"{ink} on --{fill:11} {r:5.2f}  {'ok ' if r >= 4.5 else 'FAIL'}")
        if r < 4.5:
            failures.append(f"--{ink} on --{fill} is {r:.2f}:1, needs 4.5")

    # A surface token must never be bright enough to be mistaken for text.
    # If --faint ever passes AA, someone will use it as type again.
    print()
    for s in SURFACES:
        r = ratio(tok["faint"], tok[s])
        print(f"--faint on --{s:9} {r:5.2f}  (surface token: must stay under 4.5)")
        if r >= 4.5:
            failures.append(
                f"--faint is {r:.2f}:1 on --{s}: bright enough to be used as "
                "text, which is the bug this split fixed. Use --dim for text.")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("all token contrast checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
