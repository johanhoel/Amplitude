"""The shared token layer, checked without a browser: python3 panels/tests/tokens.py

smoke.py needs Playwright and a running server. This needs neither, so it can
run on any change. It guards the thing that was actually broken: every page
used to carry its own copy of the palette, so --faint meant fourteen different
things and a contrast fix had to be made in every file.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WWW = ROOT / "panels" / "server" / "www"

# Pages that keep their own palette on purpose, and the reason. Anything else
# with a page-level :root is a fork.
EXEMPT = {
    "ambient.html": "the bedside night clock is deliberately dim amber, not slate",
}
EXEMPT_DIRS = ("designs", ".drafts")   # theme explorations and drafts

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def tokens_of(path):
    return set(re.findall(r"--([a-z0-9-]+)\s*:", path.read_text()))


sheets = {
    "panels/server/www/wall.css": WWW / "wall.css",
    "panels/server/www/deck.css": WWW / "deck.css",
}
for label, path in sheets.items():
    check(f"{label} exists", path.exists(), "run design/sync-tokens.py")
    if path.exists():
        check(f"{label} is generated from the shared source",
              "design/tokens.css" in path.read_text(),
              "it should carry the header naming where to edit it")

wall, deck = tokens_of(WWW / "wall.css"), tokens_of(WWW / "deck.css")

# There used to be a second edition here, and these checks made sure the two
# agreed about what --mute meant. There is one set of pages now, so the
# question is only whether the reading weights come from the shared source at
# all - which is what the "generated from" check above already asserts.
for name in ("ink", "mute", "dim", "ok", "warn", "bad"):
    m = re.search(rf"--{name}:\s*([^;]+);", (WWW / "wall.css").read_text())
    check(f"--{name} is defined in wall.css", m is not None,
          "it comes from design/tokens.css; a missing one means sync-tokens did not run")

# A page may only keep tokens that are its own; the palette comes from a sheet.
pages = [p for p in sorted(WWW.rglob("*.html"))
         if p.name not in EXEMPT and not any(d in p.parts for d in EXEMPT_DIRS)]
check("there are pages to check", len(pages) > 20, f"found {len(pages)}")

for p in pages:
    text = p.read_text()
    rel = str(p.relative_to(ROOT))
    linked = set()
    if 'href="/wall.css"' in text:
        linked |= wall
    if 'href="/deck.css"' in text:
        linked |= deck
    check(f"{rel} links a shared stylesheet", bool(linked),
          "every page draws its palette from wall.css or deck.css")

    own = set(re.findall(r"--([a-z0-9-]+)\s*:", text))
    forked = own & linked
    check(f"{rel} does not redefine a shared token", not forked,
          f"redefines {sorted(forked)}; change it in design/tokens.css instead")

    # A var() with no definition and no fallback renders as nothing, which
    # looks like a missing style rather than an error.
    hard = set(re.findall(r"var\(\s*--([a-z0-9-]+)\s*\)", text))
    missing = hard - own - linked
    # board.html sets --row from JavaScript on load; it is never in the CSS.
    if p.name == "board.html":
        missing -= {"row"}
    check(f"{rel} resolves every var()", not missing, f"undefined: {sorted(missing)}")

# A fill needs to say what colour the type on it is, or the type inherits --ink
# and lands at 1.9:1 on a bright accent. Dots hold no text, so they are exempt.
FILL = re.compile(r"([^{}\n]*)\{([^{}]*background(?:-color)?:\s*var\(--(?:accent|ok|warn|bad)\)[^{}]*)\}")
WORDS = re.compile(r"\b(button|\.pill|\.chip|\.tab|\.save|\.btn|\.badge|\.n\.done|a\.on)\b")
for p in pages + [WWW / "wall.css", WWW / "deck.css"]:
    text = p.read_text()
    for m in FILL.finditer(text):
        sel = m.group(1).strip().splitlines()[-1].strip() if m.group(1).strip() else ""
        if WORDS.search(sel) and not re.search(r"(?<!-)\bcolor:", m.group(2)):
            check(f"{p.name}: '{sel[:40]}' declares its type colour", False,
                  "a filled control must set color: var(--accent-ink) or var(--status-ink)")

# The contrast and icon gates, so a bad value or a stray emoji fails here too
# and not only in a design/ script someone may forget to run.
for name in ("check-contrast.py", "check-icons.py", "check-theme.py"):
    proc = subprocess.run([sys.executable, str(ROOT / "design" / name)],
                          capture_output=True, text=True)
    check(f"design/{name} passes", proc.returncode == 0,
          (proc.stdout.strip().splitlines() or [proc.stderr[:200]])[-1])

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
