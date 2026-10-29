#!/usr/bin/env python3
"""No emoji in the interface, and every icon resolves. Exits non-zero on a failure.

The panels used to draw 440 icons as emoji. An emoji is rendered by whichever
colour font the device happens to have, so the same page looked different on a
phone, a PC and a wall panel - and showed empty boxes on a Linux panel with no
emoji font installed. This keeps them from coming back.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "design"))
from icons import ICONS, EMOJI  # noqa: E402

SOURCE = ("*.html", "*.js", "*.py", "*.css")
# network.html embeds a base64 font that is not interface text.
SKIP_NAMES = {"network.html"}
SKIP_DIRS = {"node_modules", ".git", "out", ".snapshots"}
# design/ documents the emoji it replaces, so it is allowed to name them.
SCAN_ROOTS = ("panels", "CamWatch/app")

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def is_pictographic(ch):
    o = ord(ch)
    if 0x1F300 <= o <= 0x1FAFF:
        return True
    return o in {0x231A, 0x231B, 0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23F0, 0x23F3,
                 0x25FD, 0x25FE, 0x2614, 0x2615, 0x267F, 0x2693, 0x26A1, 0x26AA,
                 0x26AB, 0x26BD, 0x26BE, 0x26C4, 0x26C5, 0x26CE, 0x26D4, 0x26EA,
                 0x26F2, 0x26F3, 0x26F5, 0x26FA, 0x26FD, 0x2705, 0x270A, 0x270B,
                 0x2728, 0x274C, 0x274E, 0x2753, 0x2754, 0x2755, 0x2757, 0x2795,
                 0x2796, 0x2797, 0x27B0, 0x27BF, 0x2B50, 0x2B55,
                 # Missed on the first pass: these look like plain arrows and
                 # boxes but are colour-by-default, so a phone draws them as
                 # emoji. The Update button was one of them.
                 0x2B05, 0x2B06, 0x2B07, 0x2B1B, 0x2B1C, 0x2611, 0x2614,
                 0x2721, 0x2733, 0x2734, 0x2747, 0x203C, 0x2049, 0x2139,
                 0x24C2, 0x25FB, 0x25FC}


def sources():
    for rel in SCAN_ROOTS:
        for ext in SOURCE:
            for p in (ROOT / rel).rglob(ext):
                if p.name in SKIP_NAMES or SKIP_DIRS & set(p.parts):
                    continue
                yield p


files = sorted(sources())
check("there are source files to scan", len(files) > 40, f"found {len(files)}")

emoji_hits, vs_hits = [], []
for p in files:
    text = p.read_text(encoding="utf-8")
    rel = p.relative_to(ROOT)
    for i, line in enumerate(text.split("\n"), 1):
        for ch in line:
            if is_pictographic(ch) or ch in EMOJI:
                emoji_hits.append(f"{rel}:{i} {ch}")
        if "️" in line:
            vs_hits.append(f"{rel}:{i}")

check("no emoji in the interface", not emoji_hits,
      f"{len(emoji_hits)}: {', '.join(emoji_hits[:6])} - use an icon from design/icons.py")
# U+FE0F forces the colour-emoji form of an otherwise plain glyph, which is the
# same problem wearing a different hat.
check("no U+FE0F variation selectors", not vs_hits,
      f"{len(vs_hits)}: {', '.join(vs_hits[:6])}")

# Every generated stylesheet is present and current.
GENERATED = ["panels/server/www/icons.css", "panels/friend/src/www/icons.css",
             "panels/friend/extra/icons.css", "CamWatch/app/static/icons.css"]
bodies = {}
for rel in GENERATED:
    p = ROOT / rel
    check(f"{rel} exists", p.exists(), "run design/sync-icons.py")
    if p.exists():
        bodies[rel] = p.read_text()
        check(f"{rel} says where it came from", "design/icons.py" in bodies[rel])
if len(bodies) == len(GENERATED):
    check("every server ships the same icons",
          len(set(bodies.values())) == 1,
          "one is stale; run design/sync-icons.py")

defined = set(re.findall(r"^\.icon-([a-z0-9-]+)", bodies.get(GENERATED[0], ""), re.M))
check("the stylesheet defines every icon in design/icons.py",
      defined == set(ICONS), f"missing {sorted(set(ICONS) - defined)}")

# Every class the markup asks for has to exist, or the icon silently renders
# as a blank box the size of a letter.
used, needs_sheet, scripts = set(), [], set()
for p in files:
    text = p.read_text(encoding="utf-8")
    hits = set(re.findall(r'class="icon icon-([a-z0-9-]+)', text))
    hits |= set(re.findall(r"'icon icon-([a-z0-9-]+)'", text))
    hits |= set(re.findall(r"icon icon-\$\{[^}]*?'([a-z0-9-]+)'", text))
    used |= hits
    if hits and p.suffix == ".js":
        scripts.add(p.name)

check("every icon class used is defined", not (used - defined),
      f"undefined: {sorted(used - defined)}")

# A page that draws icons, directly or through one of those scripts, must load
# the stylesheet - otherwise .icon paints a solid block where the icon was.
for p in files:
    # The test suite documents these classes; it does not render them.
    if p.suffix not in (".html", ".py") or "tests" in p.parts:
        continue
    text = p.read_text(encoding="utf-8")
    draws = 'class="icon icon-' in text or "'icon icon-' +" in text
    pulls = any(j in text for j in scripts)
    if draws or pulls:
        needs_sheet.append((p.relative_to(ROOT), "icons.css" in text))
check("there are pages drawing icons", len(needs_sheet) > 20, f"found {len(needs_sheet)}")
for rel, ok in needs_sheet:
    check(f"{rel} links icons.css", ok, "without it .icon paints a solid block")

# .icon must not collide with a class the pages already use. It did: the panels
# have their own .ic, and 391 rules were styling it.
for p in files:
    if p.suffix == ".css" and p.name == "icons.css":
        continue
    text = p.read_text(encoding="utf-8")
    bad = [a for a in re.findall(r'class="([^"]*)"', text)
           if "icon" in a.split() and not any(t.startswith("icon-") for t in a.split())]
    check(f"{p.relative_to(ROOT)} does not reuse .icon for something else",
          not bad, f"{bad[:3]}")

# Icon markup must never sit in a data value. Four separate bugs came from
# this in one sitting - a Jinja label, a user-editable admin field, a module
# definition, a select option - each one printing raw HTML on screen, because
# somewhere downstream the value went through an escape. Keep the name in the
# data and build the markup at the point it is written into the page.
MARKUP = re.compile(r"""['"`]<i class="icon icon-""")
for p in files:
    text = p.read_text(encoding="utf-8")
    rel = p.relative_to(ROOT)

    bad = [m for m in re.finditer(r"(icon|ic)\s*:\s*['\"]<i class=\"icon", text)]
    check(f"{rel} keeps icon names, not markup, in data", not bad,
          f"{len(bad)} field(s) hold markup; store the name and build the <i> at render")

    # esc(...) round an icon literal renders the tag as visible text.
    bad = [m.group(0)[:70] for m in re.finditer(r"esc\([^()]*<i class=\"icon[^()]*\)", text)]
    check(f"{rel} does not escape icon markup", not bad, "; ".join(bad[:2]))

    # Jinja escapes {{ }}, so markup carried inside a {% %} value prints raw.
    bad = [m.group(0)[:70] for m in re.finditer(r"\{%[^%]*<i class=\"icon[^%]*%\}", text, re.S)]
    check(f"{rel} keeps icon markup out of Jinja values", not bad, "; ".join(bad[:2]))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
