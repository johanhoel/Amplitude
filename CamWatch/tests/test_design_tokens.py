"""The shared token layer: every page draws its colours from one file.

Before this, each page carried its own copy of the palette, so --faint meant
fourteen different things across the repo and a contrast fix had to be made
in every file. These checks keep the copies from coming back.
"""
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
REPO = Path(__file__).resolve().parents[2]
TOKENS = APP / "static" / "tokens.css"
PAGES = ("dashboard.html", "wallview.html", "mobile.html", "webui.py")

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


css_raw = TOKENS.read_bytes()
css = css_raw.decode()
check("tokens.css is LF", b"\r\n" not in css_raw)
check("tokens.css is generated from the shared source",
      "design/tokens.css" in css,
      "the header naming its source is how the next person knows not to edit it here")

defined = set(re.findall(r"--([a-z0-9-]+)\s*:", css))
for token in ("bg", "card", "card-hi", "line", "faint", "ink", "mute", "dim",
              "ok", "warn", "bad", "accent", "accent-text", "accent-ink"):
    check(f"tokens.css defines --{token}", token in defined)

# The names this project grew up with still work, and point at the shared value
# rather than a second copy of it.
for alias, target in (("fg", "ink"), ("muted", "mute"), ("danger", "bad"),
                      ("known", "ok"), ("unknown", "warn")):
    m = re.search(rf"--{alias}:\s*([^;]+);", css)
    check(f"--{alias} is an alias of --{target}",
          m is not None and m.group(1).strip() == f"var(--{target})",
          f"found {m.group(1).strip() if m else 'nothing'}")

for page in PAGES:
    text = (APP / page).read_text()
    check(f"{page} links tokens.css", "/static/tokens.css" in text)
    # A page-level :root is how the palette forked last time.
    check(f"{page} declares no palette of its own",
          not re.search(r"^\s*:root\s*\{", text, re.M),
          "page-level :root re-forks the palette; add the token to design/tokens.css")

# Every var() a page uses has to come from somewhere, or it silently renders
# as nothing - which looks like a missing style, not an error.
splash = set(re.findall(r"--([a-z0-9-]+)\s*:",
                        (APP / "static" / "splash.css").read_text()))
for page in PAGES:
    text = (APP / page).read_text()
    local = set(re.findall(r"--([a-z0-9-]+)\s*:", text))
    missing = set(re.findall(r"var\(\s*--([a-z0-9-]+)", text)) - defined - splash - local
    check(f"{page} resolves every var()", not missing, f"undefined: {sorted(missing)}")

# The palette hex belongs in exactly one place. A literal in a page is a fork
# waiting to happen, and it will not follow when the token changes.
PALETTE = re.findall(r"--(?:bg|card|card-hi|line|faint|ink|mute|dim):\s*(#[0-9a-f]{6})", css)
# Two places genuinely cannot use a var(), and both are checked by value below:
# the theme-color meta, and the service worker's offline page, which is served
# with no stylesheet attached.
EXEMPT = ("theme-color", "width=device-width")
for page in PAGES:
    text = (APP / page).read_text()
    for value in set(PALETTE):
        hits = [m for m in re.finditer(re.escape(value), text, re.I)
                if not any(e in text[max(0, m.start() - 160):m.start()] for e in EXEMPT)]
        check(f"{page} does not hardcode {value}", not hits,
              f"{len(hits)} literal uses; use the var() instead")

# The offline page's literals have to follow the tokens, or the one screen a
# user sees when the server is down is the one screen off-palette.
ink = re.search(r"--ink:\s*(#[0-9a-f]{6})", css).group(1)
bg_tok = re.search(r"--bg:\s*(#[0-9a-f]{6})", css).group(1)
sw = (APP / "webui.py").read_text()
offline = re.search(r"<body style=\"background:(#[0-9a-fA-F]{6});color:(#[0-9a-fA-F]{6})", sw)
check("the offline page still sets its own colours", offline is not None,
      "the service worker page has no stylesheet; it must carry literals")
if offline:
    check("offline page background tracks --bg",
          offline.group(1).lower() == bg_tok.lower(),
          f"{offline.group(1)} should be {bg_tok}")
    check("offline page text tracks --ink",
          offline.group(2).lower() == ink.lower(),
          f"{offline.group(2)} should be {ink}")

# The browser chrome colour cannot be a var(), so it is checked instead.
bg = re.search(r"--bg:\s*(#[0-9a-f]{6})", css).group(1)
for page in PAGES:
    text = (APP / page).read_text()
    for found in re.findall(r'theme-color"[^>]*content="(#[0-9a-fA-F]{6})"', text):
        check(f"{page} theme-color tracks --bg", found.lower() == bg.lower(),
              f"{found} should be {bg}")

# The contrast gate itself, so a bad token value fails here too and not only
# in the design/ checker someone may forget to run.
checker = REPO / "design" / "check-contrast.py"
if checker.exists():
    proc = subprocess.run([sys.executable, str(checker)], capture_output=True, text=True)
    check("design/check-contrast.py passes", proc.returncode == 0,
          proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[:200])
else:
    check("design/check-contrast.py is present", False, f"missing at {checker}")

# A var() fallback is what renders when the token sheet has not loaded, so it
# has to be a literal, and the right one. Both of these broke during the
# migration: a bulk replace turned "var(--bg, #101418)" into "var(--bg, var(--bg))".
LITERALS = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-f]{6})\s*;", css))
for rel in [APP / p for p in PAGES] + [APP / "static" / "splash.css"]:
    text = rel.read_text()
    circular = re.findall(r"var\(\s*--([a-z0-9-]+)\s*,\s*var\(\s*--\1\s*\)", text)
    check(f"{rel.name} has no self-referential var() fallback", not circular,
          f"{circular}: a fallback that refers to itself never resolves")
    for name, fallback in re.findall(r"var\(\s*--([a-z0-9-]+)\s*,\s*(#[0-9a-fA-F]{6})\s*\)", text):
        if name in LITERALS:
            check(f"{rel.name}: var(--{name}) fallback matches the token",
                  fallback.lower() == LITERALS[name].lower(),
                  f"{fallback} should be {LITERALS[name]}")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
