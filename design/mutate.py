#!/usr/bin/env python3
"""Break every gate on purpose, one assertion at a time, and say what is not covered.

    python3 design/mutate.py              all gates
    python3 design/mutate.py check-icons  one gate

A check that cannot be made to fail is not a check. Two of them were found
that way in one afternoon: one compared a set to a filtered copy of itself,
so adding a page to its exemption list kept it green; another validated an
icon name by SHAPE, and every icon name has that shape, so it could only
catch names nobody writes. Both had been green and trusted for sessions.

THREE OUTCOMES, NOT TWO

  fired         the gate went red, and named the assertion aimed at
  stayed green  the assertion cannot catch what it claims to
  not injected  the needle did not match, so nothing changed

The third matters most. A mutation that fails to apply leaves the gate green,
and by hand that reads exactly like "I tested it and it was fine" - which is
how a break aimed at markup behind a disabled feature flag once passed
silently. It is a distinct result here, never a pass.

COVERAGE

Breaking what you remembered to break is the same trap one level up: a
mutation list complete on the day it was written, a check added later with
nothing pointing at it, and a green run that means less than it looks. So
this reports every assertion with no mutation aimed at it. Uncovered is not
a failure - most of these gates have never been audited - but it is never
silent.
"""
import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP = Path("/tmp/mutate-backup")

# gate name -> (script, working directory)
GATES = {
    "check-icons": ("design/check-icons.py", "."),
    "check-theme": ("design/check-theme.py", "."),
    "panels-tokens": ("panels/tests/tokens.py", "."),
    "panels-scripts": ("panels/tests/scripts.py", "."),
    "cw-tokens": ("CamWatch/tests/test_design_tokens.py", "CamWatch"),
    "cw-routes": ("CamWatch/tests/test_routes.py", "CamWatch"),
    "cw-release-notes": ("CamWatch/tests/test_release_notes.py", "CamWatch"),
    "cw-brand": ("CamWatch/tests/test_brand_assets.py", "CamWatch"),
}

# Each mutation: the gate it attacks, a substring of the assertion it should
# make fail, and how to break it. `edit` replaces text in a file; `page`
# writes a throwaway page into the scanned tree, which is the only way to
# exercise a rule about page content without damaging a real page.
M = [
    # ---- CamWatch/tests/test_design_tokens.py ----
    ("cw-tokens", "tokens.css is LF", "edit", "CamWatch/app/static/tokens.css",
     ":root, :root body {", ":root, :root body {\r"),
    ("cw-tokens", "generated from the shared source", "edit", "CamWatch/app/static/tokens.css",
     "design/tokens.css", "elsewhere.css"),
    ("cw-tokens", "defines --dim", "edit", "CamWatch/app/static/tokens.css",
     "--dim:  #7e91a7;", "--notdim: #7e91a7;"),
    ("cw-tokens", "is an alias of --ink", "edit", "CamWatch/app/static/tokens.css",
     "--fg: var(--ink);", "--fg: #eef2f7;"),
    ("cw-tokens", "links tokens.css", "edit", "CamWatch/app/dashboard.html",
     '<link rel="stylesheet" href="/static/tokens.css">', ""),
    ("cw-tokens", "declares no palette of its own", "edit", "CamWatch/app/dashboard.html",
     "<style>", "<style>\n:root { --bg: #000; }"),
    ("cw-tokens", "resolves every var()", "edit", "CamWatch/app/dashboard.html",
     "<style>", "<style>\n.probe { color: var(--nosuchtoken); }"),
    ("cw-tokens", "does not hardcode", "edit", "CamWatch/app/dashboard.html",
     "<style>", "<style>\n.probe { color: #9aa7b6; }"),
    ("cw-tokens", "offline page still sets its own colours", "edit", "CamWatch/app/webui.py",
     'style="background:#12151d;color:#eef2f7;font:16px system-ui;padding:24px"',
     'style="font:16px system-ui;padding:24px"'),
    ("cw-tokens", "offline page background tracks --bg", "edit", "CamWatch/app/webui.py",
     "background:#12151d;color:#eef2f7", "background:#101418;color:#eef2f7"),
    ("cw-tokens", "offline page text tracks --ink", "edit", "CamWatch/app/webui.py",
     "background:#12151d;color:#eef2f7;font:16px", "background:#12151d;color:#ffffff;font:16px"),
    ("cw-tokens", "theme-color tracks --bg", "edit", "CamWatch/app/dashboard.html",
     '<meta name="theme-color" content="#12151d">', '<meta name="theme-color" content="#101418">'),
    ("cw-tokens", "check-contrast.py passes", "edit", "CamWatch/app/static/tokens.css",
     "--mute: #9aa7b6;", "--mute: #3a4049;"),
    ("cw-tokens", "no self-referential var() fallback", "edit", "CamWatch/app/static/splash.css",
     "var(--bg, #12151d)", "var(--bg, var(--bg))"),
    ("cw-tokens", "fallback matches the token", "edit", "CamWatch/app/static/splash.css",
     "var(--mute, #9aa7b6)", "var(--mute, #888888)"),

    # ---- CamWatch/tests/test_routes.py ----
    ("cw-routes", "no page prints icon markup as text", "edit", "CamWatch/app/webui.py",
     """<i class="icon icon-{{ ic }}" aria-hidden="true"></i> {{ label }}""",
     """{{ '<i class="icon icon-home" aria-hidden="true"></i> ' ~ label }}"""),
    ("cw-routes", "every icon the pages draw resolves", "edit", "CamWatch/app/webui.py",
     "('dashboard', 'home', 'Home')", "('dashboard', 'nosuchicon', 'Home')"),

    # ---- CamWatch/tests/test_release_notes.py ----
    ("cw-release-notes", "stops at the running commit", "edit", "CamWatch/app/updates.py",
     'if running and c["sha"].startswith(running):', "if False:"),
    ("cw-release-notes", "merge commit is left out", "edit", "CamWatch/app/updates.py",
     'if line.startswith("Merge "):', "if False:"),
    ("cw-release-notes", "fetches more than one commit", "edit", "CamWatch/app/updates.py",
     "per_page=20", "per_page=1"),
    ("cw-release-notes", "written as text, never as markup", "edit", "CamWatch/app/webui.py",
     "      b.textContent = n.text;", "      b.innerHTML = n.text;"),

    # ---- design/check-icons.py : content rules, via a throwaway page ----
    ("check-icons", "no emoji in the interface", "page",
     '<p>\U0001F4A1 a bulb</p>'),
    ("check-icons", "no U+FE0F variation selectors", "page",
     '<p>⚠️ warning</p>'),
    ("check-icons", "every icon class used is defined", "page",
     '<i class="icon icon-nosuchicon" aria-hidden="true"></i>'),
    # The rule matches a QUOTED glyph in a data value, so the mutation has to
    # quote it too. An unquoted one changes nothing and the gate stays green,
    # which is the mutation being wrong rather than the check being hollow -
    # exactly the distinction "not injected" exists to make, and this one
    # slipped past it because the needle did apply, it just did not matter.
    ("check-icons", "no bare glyph sits among drawn icons", "page",
     '<i class="icon icon-bulb" aria-hidden="true"></i>\n'
     "<script>const a = ['⏻', 'x'];</script>"),
    ("check-icons", "beside a drawn icon on one line", "page",
     '<span><i class="icon icon-bulb" aria-hidden="true"></i> ⏻</span>'),
    ("check-icons", "links icons.css", "page_nolink",
     '<i class="icon icon-bulb" aria-hidden="true"></i>'),
    ("check-icons", "does not reuse .icon for something else", "page",
     '<span class="icon badge">x</span>'),
    ("check-icons", "keeps icon names, not markup, in data", "page",
     '<script>const m = { icon: \'<i class="icon icon-bulb"></i>\' };</script>'),
    ("check-icons", "icon fields name an icon that exists", "page",
     "<script>const m = { icon: 'nosuchicon' };</script>"),
    ("check-icons", "says where it came from", "edit", "panels/server/www/icons.css",
     "design/icons.py", "nowhere.py"),
    ("check-icons", "every server ships the same icons", "edit",
     "CamWatch/app/static/icons.css", ".icon {", ".icon { /* drift */"),
    ("check-icons", "defines every icon in design/icons.py", "edit",
     "panels/server/www/icons.css", ".icon-bulb {", ".icon-notbulb {"),
    ("check-icons", "does not escape icon markup", "page",
     '<script>el.innerHTML = esc(\'<i class="icon icon-bulb"></i>\');</script>'),
    ("check-icons", "keeps icon markup out of Jinja values", "page",
     '<p>{% set x = \'<i class="icon icon-bulb"></i>\' %}</p>'),

    # ---- design/check-theme.py ----
    ("check-theme", "every card-scale radius comes from a token", "page",
     '<style>.probe { border-radius: 17px; }</style>'),
    ("check-theme", "the scale is ordered", "edit", "design/tokens.css",
     "--r-sm: 12px;", "--r-sm: 30px;"),
    ("check-theme", "uses the same card radius", "edit", "CamWatch/app/static/tokens.css",
     "--r:    18px;", "--r:    15px;"),
    ("check-theme", "is identical on every server", "edit", "CamWatch/app/static/shell.css",
     ".ui-page {", ".ui-page { /* drift */"),

    # ---- panels/tests/scripts.py ----
    ("panels-scripts", "parses", "edit", "panels/server/www/nav.js",
     "const ", "const const "),
]

# A page written into both scanned trees, so a gate scanning either sees it.
SCRATCH = [ROOT / "panels/server/www/_mutate.html",
           ROOT / "CamWatch/app/_mutate.html"]


def save(files):
    BACKUP.mkdir(exist_ok=True)
    for rel in files:
        src = ROOT / rel
        if src.exists():
            shutil.copy(src, BACKUP / rel.replace("/", "__"))


def restore(files):
    for rel in files:
        bk = BACKUP / rel.replace("/", "__")
        if bk.exists():
            shutil.copy(bk, ROOT / rel)
    for p in SCRATCH:
        p.unlink(missing_ok=True)


def run_gate(name):
    script, cwd = GATES[name]
    proc = subprocess.run([sys.executable, str(ROOT / script)],
                          cwd=ROOT / cwd, capture_output=True, text=True, timeout=600)
    return [l[5:] for l in proc.stdout.splitlines() if l.startswith("FAIL")]


def assertions(script):
    """Every check() label in a gate, as a template with {…} blanked out."""
    tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "check"):
            continue
        if not node.args:
            continue
        a = node.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            out.append(a.value)
        elif isinstance(a, ast.JoinedStr):
            out.append("".join(p.value if isinstance(p, ast.Constant) else "{}"
                               for p in a.values))
    return out


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    mutations = [m for m in M if only is None or m[0] == only]
    gates = sorted({m[0] for m in mutations})
    touched = sorted({m[3] for m in mutations if m[2] == "edit"})
    save(touched)

    print(f"{'gate':18} {'assertion':44} outcome")
    print("-" * 92)
    dead, uninjected = [], []
    for gate, expect, kind, *rest in mutations:
        if kind == "edit":
            rel, find, repl = rest
            path = ROOT / rel
            src = path.read_text(encoding="utf-8")
            if find not in src:
                print(f"{gate:18} {expect[:44]:44} NOT INJECTED  needle absent in {rel}")
                uninjected.append((gate, expect, rel))
                continue
            path.write_text(src.replace(find, repl, 1), encoding="utf-8")
        else:
            # page_nolink leaves the stylesheet out, which is the only way to
            # exercise the rule that a page drawing icons must load it.
            body = rest[0]
            head = "" if kind == "page_nolink" else '<link rel="stylesheet" href="/icons.css">\n'
            for p in SCRATCH:
                p.write_text("<!doctype html>" + head + body, encoding="utf-8")
        fails = run_gate(gate)
        restore(touched)
        if any(expect in f for f in fails):
            print(f"{gate:18} {expect[:44]:44} fired")
        else:
            got = fails[0][:40] if fails else "nothing failed"
            print(f"{gate:18} {expect[:44]:44} STAYED GREEN  got: {got}")
            dead.append((gate, expect))

    # ---- coverage ----
    print()
    print("coverage")
    print("-" * 92)
    total_missing = 0
    for name, (script, _) in GATES.items():
        if only and name != only:
            continue
        labels = assertions(script)
        aimed = [m[1] for m in M if m[0] == name]
        missing = [l for l in labels if not any(a in l for a in aimed)]
        total_missing += len(missing)
        mark = "all covered" if not missing else f"{len(missing)} of {len(labels)} uncovered"
        print(f"  {name:18} {len(labels):3} assertions   {mark}")
        for l in missing:
            print(f"        no mutation aims at: {l[:70]}")

    print()
    if dead:
        print(f"{len(dead)} assertion(s) could not be made to fail — these are not checks:")
        for g, e in dead:
            print(f"   {g}: {e}")
    if uninjected:
        print(f"{len(uninjected)} mutation(s) did not apply — the needle has rotted, fix the mutation:")
        for g, e, rel in uninjected:
            print(f"   {g}: {e}  ({rel})")
    if not dead and not uninjected:
        print("every mutation applied and every targeted assertion fired")
    print(f"{total_missing} assertion(s) have no mutation aimed at them")
    return 1 if dead or uninjected else 0


if __name__ == "__main__":
    sys.exit(main())
