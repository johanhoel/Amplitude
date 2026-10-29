"""Every page rendered through the real app, not a harness.

This is the only check that exercises Jinja end to end. It exists because the
icon work shipped a bug that reached the live server: markup placed inside a
{{ }} expression, which Jinja escapes, so the top menu printed

    <i class="icon icon-home" aria-hidden="true"></i> Home

as visible text on every page. A static reading of the templates passed it,
and so did a harness that served the HTML files directly. Only rendering the
templates shows it.

It walks every GET route that needs no parameters, and asserts three things:
nothing escaped an icon, every icon name resolves to a rule in icons.css, and
the number of pages actually rendered has not quietly collapsed.

Needs flask and the rest of the app's imports; the suite has them.
"""
import re
import runpy
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

# test_webui.py builds the fake recordings and hands back a flask test client.
ns = runpy.run_path(str(Path(__file__).with_name("test_webui.py")))
client = ns["c"]
import webui  # noqa: E402

# A route with a <converter> in it needs a value we would have to invent, and
# inventing one tests the invention rather than the page.
ROUTES = sorted({r.rule for r in webui.app.url_map.iter_rules()
                 if "GET" in r.methods and "<" not in r.rule})

# The floor, not the exact number: a new page should not fail this, but a
# change that makes most pages stop answering should. Without it the whole
# file could pass while checking nothing, which is the failure mode that
# makes a green suite a lie.
MIN_RENDERED = 15

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


check("the app exposes routes to walk", len(ROUTES) > 20, f"found {len(ROUTES)}")

rendered, skipped, names, escaped = [], [], set(), []
for rule in ROUTES:
    try:
        resp = client.get(rule)
    except Exception as exc:                      # a page that raises is a page that is broken
        check(f"{rule} renders without raising", False, f"{type(exc).__name__}: {exc}")
        continue
    if resp.status_code != 200 or not (resp.mimetype or "").startswith("text/html"):
        skipped.append(f"{rule} ({resp.status_code} {resp.mimetype})")
        continue
    body = resp.get_data(as_text=True)
    rendered.append(rule)
    names |= set(re.findall(r'class="icon icon-([a-z0-9-]+)"', body))
    # The exact shape of the bug: Jinja escaped the tag, so the page shows it.
    # Match only "&lt;i " - Jinja escapes the quotes as well (class=&#34;icon),
    # so a needle carrying a literal quote never matches the real output. That
    # mistake made an earlier version of this check pass on a page that was
    # visibly broken, which is the whole reason it is spelled out here.
    n = len(re.findall(r"&lt;i[\s/&]", body))
    if n:
        escaped.append(f"{rule} ({n})")

check(f"enough pages actually rendered ({len(rendered)} of {len(ROUTES)})",
      len(rendered) >= MIN_RENDERED,
      f"only {len(rendered)} answered; skipped: {', '.join(skipped[:6])}")

check("no page prints icon markup as text", not escaped,
      "; ".join(escaped[:5]) + "  - markup inside {{ }} is escaped; move it to {% if %}")

defined = set(re.findall(r"^\.icon-([a-z0-9-]+)",
                         (ROOT / "app" / "static" / "icons.css").read_text(), re.M))
check("icons.css was found and has rules", len(defined) > 50, f"{len(defined)} rules")
check(f"every icon the pages draw resolves ({len(names)} distinct)",
      not (names - defined),
      f"no rule for {sorted(names - defined)} - an unknown name paints the fallback")

# A page that draws no icons at all would hide a stylesheet that never loaded.
check("the pages do draw icons", len(names) > 20, f"only {len(names)} distinct")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
