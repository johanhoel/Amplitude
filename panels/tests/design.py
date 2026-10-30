"""The design contract: python3 panels/tests/design.py

Two rules that kept being broken by hand:

1. A card for hardware this house has not got is not drawn at all. It used to
   be drawn with an en dash in the value slot, which is the loudest piece of
   type on the card - a fresh install read as broken rather than as new. Every
   tile that needs something now names the addon it needs, and addons.py has
   to know that name.

2. The empty state is one component, not one per page. .empty was defined six
   different ways across the pages before .ui-empty existed.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "server" / "www"
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


import tempfile                                                    # noqa: E402

state = tempfile.mkdtemp(prefix="homedeck-design-")
conf = Path(state) / "homedeck.toml"
conf.write_text((ROOT / "server" / "homedeck.toml").read_text(encoding="utf-8")
                .replace("__HA_URL__", "http://127.0.0.1:8123"), encoding="utf-8")
os.environ.update(HOMEDECK_CONFIG=str(conf), STATE_DIRECTORY=state, HOMEDECK_READONLY="1")
sys.path.insert(0, str(ROOT / "server"))
from homedeck import addons                                       # noqa: E402

KNOWN = set(addons.PLUGINS)
check("there are addons to gate on", len(KNOWN) > 5, f"{sorted(KNOWN)}")

# ---- the helper every page gates with ---------------------------------
js = (WWW / "addons.js").read_text(encoding="utf-8")
check("addons.js offers hasAddon to the pages",
      re.search(r"window\.hasAddon\s*=\s*function", js) is not None)
check("it shows everything until the first answer",
      "list === null || list.split" in js,
      "hiding the page while the answer is in flight is the worse direction")

# ---- every gate names an addon that exists ----------------------------
used = set()
for page in sorted(WWW.glob("*.html")):
    body = page.read_text(encoding="utf-8")
    for name in re.findall(r"hasAddon\('([A-Za-z_]+)'\)", body):
        used.add(name)
        check(f"www/{page.name} gates on a real addon ({name})", name in KNOWN,
              f"addons.py knows {sorted(KNOWN)}")
    for name in re.findall(r"need: '([A-Za-z_]+)'", body):
        used.add(name)
        check(f"www/{page.name} needs a real addon ({name})", name in KNOWN, f"not in addons.py")
check("the pages actually gate on something", len(used) >= 6, f"{sorted(used)}")

# ---- the pages that empty out say so ----------------------------------
# A ratchet: the count is what is gated today. Removing a gate is the
# regression this file exists to catch, so it has to fail, not pass quietly.
for name, page, least in (("Pulse", "pulse.html", 8), ("Control", "control.html", 3)):
    body = (WWW / page).read_text(encoding="utf-8")
    n = len(re.findall(r"hasAddon\(", body))
    check(f"{name} drops cards it has no hardware for ({n})", n >= least,
          f"only {n} of its cards ask whether this house has the thing")
check("Control says where the missing switches come from",
      "ui-empty" in (WWW / "control.html").read_text(encoding="utf-8"),
      "a page with one tile on it reads as a page that failed to load")
ctl = (WWW / "control.html").read_text(encoding="utf-8")
check("a heading never outlives its tiles",
      re.search(r"return dropEmptyGroups\(", ctl) is not None
      and re.search(r"function dropEmptyGroups\(", ctl) is not None,
      "the function exists but nothing calls it")
today = (WWW / "today.html").read_text(encoding="utf-8")
check("Today stops saying it is loading when there is nothing to load",
      "$('#ribbon').hidden = true" in today)
check("and the Next hours heading goes with its hours",
      re.search(r"\$\('#hours-block'\)\.hidden = !hrs\.length", today) is not None
      and re.search(r'id="hours-block"', today) is not None,
      "the heading has to be inside the thing that gets hidden")

shared = (ROOT.parent / "design" / "components.py").read_text(encoding="utf-8")

# ---- a component needs its stylesheet on the page ---------------------
# The empty state was moved onto ten pages that did not link shell.css, so the
# class existed and reached nothing. A component used without its layer is a
# class name and no rules.
for page in sorted(WWW.glob("*.html")):
    body = page.read_text(encoding="utf-8")
    if re.search(r'class="[^"]*\bui-[a-z-]+', body):
        check(f"www/{page.name} links the component layer it uses",
              "/shell.css" in body, "the ui- classes on this page have no rules behind them")
check("no page carries its own empty state any more",
      not any(re.search(r"^\.empty \{", p.read_text(encoding="utf-8"), re.M) for p in WWW.glob("*.html")),
      "that is the eight near-copies .ui-empty replaced")
check("a heading hides with the list under it",
      re.search(r"\.ui-cap:has\(\+ :empty\)", shared) is not None,
      "a heading over nothing reads as something that failed to load")

# ---- one empty state, in the shared component layer -------------------
check("the empty state lives in design/components.py",
      re.search(r"^\.ui-empty \{", shared, re.M) is not None)
for css in (WWW / "shell.css", ROOT.parent / "CamWatch" / "app" / "static" / "shell.css"):
    check(f"{css.parent.parent.name}/shell.css has it too",
          re.search(r"^\.ui-empty \{", css.read_text(encoding="utf-8"), re.M) is not None,
          "run design/sync-components.py")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
