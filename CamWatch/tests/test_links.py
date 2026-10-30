"""Every link the static pages hardcode points at a route that exists.

This exists because the dashboard shipped a "Package at <zone>" card linking
to /clips, which is not a route: the clips list is "/" and the only /clips
rules are the two POSTs for delete and download. Clicking the card on the
live server gave a bare "Not Found". The page is served as-is and its links
are string literals, so nothing in the suite looked at them: test_routes.py
walks the routes and asks whether they render, which is the other direction.

Reading both sides statically catches the mismatch without flask or the
model stack, so it runs anywhere the suite does.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["dashboard.html", "mobile.html", "wallview.html"]

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


# --- the routes, read out of the decorators -----------------------------
source = (ROOT / "app" / "webui.py").read_text(encoding="utf-8")
rules = []
for verb, rule, rest in re.findall(r'@app\.(get|post|route)\(\s*"([^"]+)"([^)]*)\)', source):
    methods = re.findall(r'"(GET|POST)"', rest) or (["GET"] if verb in ("get", "route") else ["POST"])
    rules.append((rule, set(methods)))

check("routes were found in webui.py", len(rules) > 20, f"found {len(rules)}")

def matcher(rule):
    """A flask rule as a regex. <path:x> spans slashes, <x> and <int:x> do not."""
    out = ""
    for part in re.split(r"(<[^>]+>)", rule):
        if part.startswith("<"):
            out += r"[^/]+" if not part.startswith("<path:") else r".+"
        else:
            out += re.escape(part)
    return re.compile(r"\A" + out + r"\Z")

# Any method: a page both links to pages and posts to endpoints, and the two
# are not told apart by a string literal. /arm and /snooze are POST-only and
# reached with post(), which is correct and must not be flagged. What cannot
# be correct is a path no rule serves at all - that is a dead link whichever
# way the page reaches for it.
ALL = [matcher(r) for r, _ in rules]


def resolves(path):
    return any(m.match(path) for m in ALL)


# --- the links, read out of the pages -----------------------------------
# Only literals: a string with ${...} in it is built at runtime from data we
# do not have here, and guessing values would test the guess.
missing, looked = [], 0
for name in PAGES:
    page = ROOT / "app" / name
    if not page.exists():
        check(f"{name} exists", False, "listed in PAGES but not on disk")
        continue
    text = page.read_text(encoding="utf-8")
    for quote in ('"', "'", "`"):
        for lit in re.findall(rf"{quote}(/[^{quote}\n]*){quote}", text):
            if "${" in lit or "{{" in lit or lit.startswith("/static/"):
                continue
            path = lit.split("?")[0].split("#")[0]
            # Markup and CSS inside these files produce quoted fragments that
            # start with a slash but are not paths ("/><path class=").
            if not re.fullmatch(r"/[A-Za-z0-9._~/-]*", path):
                continue
            if path.endswith("/") and path != "/":
                continue
            looked += 1
            if not resolves(path):
                missing.append(f"{name} -> {lit}")

check("there were links to look at", looked > 10, f"only {looked}")
check(f"every path the pages name is served by a route ({looked} looked at)",
      not missing, "; ".join(sorted(set(missing))) + "  - no route serves this; the page gives Not Found")

# The bug in its exact shape, so a rewrite of the block cannot bring it back.
check("no page links to /clips",
      not any("/clips" in m for m in missing),
      "/clips is POST-only (delete, download); the clips list is /")

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
