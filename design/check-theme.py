#!/usr/bin/env python3
"""One theme across both projects: the shape, not just the colour.

The tokens settled the palette and design/icons.py settled the icons, but the
two projects still disagreed about shape. "A card" was 24px in the panels,
14px in CamWatch and 18px in the shared components, with 10, 11, 12, 16, 20,
22, 26 and 28 scattered through the pages - the shape equivalent of the
fourteen --faint values. A section heading was 11.5px at .16em tracking in one
project and 13px at .12em in the other.

This keeps them agreed. Exits non-zero on a failure.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A radius under 10px is a small detail and 999px is a pill; neither is the
# card shape this is about.
CARD_MIN, CARD_MAX = 10, 28

# Every server that receives the generated sheets. One list, so the scan and
# the fan-out check cannot drift apart, and no message hardcodes a number -
# "all four servers" was wrong within a day of being written.
SERVERS = ("panels/server/www", "CamWatch/app/static")

SKIP_NAMES = {"network.html"}          # embeds a base64 font
SKIP_PARTS = {"designs", ".drafts"}    # theme explorations and drafts differ on purpose

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def sources():
    for rel in ("panels/server/www", "CamWatch/app"):
        for ext in ("*.html", "*.css", "*.py"):
            for p in (ROOT / rel).rglob(ext):
                if p.name in SKIP_NAMES or SKIP_PARTS & set(p.parts):
                    continue
                yield p


# --- one radius scale -------------------------------------------------
RADIUS = re.compile(r"border-radius:\s*(\d+)px")
offenders = {}
for p in sources():
    bad = [int(m.group(1)) for m in RADIUS.finditer(p.read_text(encoding="utf-8"))
           if CARD_MIN <= int(m.group(1)) <= CARD_MAX]
    if bad:
        offenders[p.relative_to(ROOT)] = bad

# An IN_FLIGHT allow-list lived here while three pages were mid-conversion in
# another session. They have landed, so it is gone - and so is a second check
# that claimed to stop the list growing and could not. It read
#
#     set(offenders) <= {p for p in offenders if p.name in IN_FLIGHT}
#
# which compares the offenders to a filtered copy of themselves. That is true
# exactly when the check above already passes, so it was a duplicate, not an
# independent check - and a name ADDED to the list could only ever make it
# pass more easily. It could not fail in any state. Found by breaking all
# twenty assertions in this file one at a time and watching which stayed
# green; it was the only one that did.
check("every card-scale radius comes from a token", not offenders,
      "; ".join(f"{k}: {v}" for k, v in list(offenders.items())[:4])
      + "  - use var(--r-sm), var(--r) or var(--r-lg)")

# --- the scale itself -------------------------------------------------
tokens = (ROOT / "design" / "tokens.css").read_text()
scale = dict(re.findall(r"--(r|r-sm|r-lg|r-pill):\s*(\d+)px", tokens))
for name in ("r", "r-sm", "r-lg"):
    check(f"--{name} is defined", name in scale)
if len(scale) >= 3:
    check("the scale is ordered small < card < large",
          int(scale["r-sm"]) < int(scale["r"]) < int(scale["r-lg"]),
          f"{scale}")

# Both projects start from the same card radius. deck.css may override it;
# that override is declared in design/sync-tokens.py.
OVERRIDE = {"panels/server/www/deck.css"}
base = None
for rel in ("panels/server/www/wall.css", "CamWatch/app/static/tokens.css"):
    m = re.search(r"--r:\s*(\d+)px", (ROOT / rel).read_text())
    check(f"{rel} sets --r", m is not None)
    if m:
        if base is None:
            base = m.group(1)
        check(f"{rel} uses the same card radius as the others", m.group(1) == base,
              f"{m.group(1)}px vs {base}px")

# --- one section heading ----------------------------------------------
shell = (ROOT / "panels" / "server" / "www" / "shell.css").read_text()
wall = (ROOT / "panels" / "server" / "www" / "wall.css").read_text()
ui_cap = re.search(r"\.ui-cap\s*\{(.*?)\}", shell, re.S)
legacy = re.search(r"\.cap, \.lbl, \.label \{(.*?)\}", wall, re.S)
check("shell.css defines .ui-cap", ui_cap is not None)
check("wall.css aligns the legacy caption to it", legacy is not None)
if ui_cap and legacy:
    for prop in ("font-size", "font-weight", "letter-spacing", "text-transform"):
        a = re.search(rf"{prop}:\s*([^;]+);", ui_cap.group(1))
        b = re.search(rf"{prop}:\s*([^;]+);", legacy.group(1))
        check(f"a heading's {prop} is the same in both projects",
              a and b and a.group(1).strip() == b.group(1).strip(),
              f"shell {a.group(1).strip() if a else '-'} vs wall {b.group(1).strip() if b else '-'}")

# --- the shared sheets are all present and identical ------------------
for name in ("icons.css", "shell.css"):
    bodies = {}
    for rel in SERVERS:
        p = ROOT / rel / name
        if p.exists():
            bodies[rel] = p.read_text()
    check(f"{name} ships to every server ({len(SERVERS)})", len(bodies) == len(SERVERS),
          f"found {sorted(bodies)}")
    check(f"{name} is identical on every server", len(set(bodies.values())) <= 1,
          "run the matching design/sync-*.py")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
