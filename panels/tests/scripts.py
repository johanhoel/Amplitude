"""Every script parses: python3 panels/tests/scripts.py

A file that does not parse fails silently. The browser logs a SyntaxError and
moves on, so the page still renders and only the feature in that file is dead.
studio-guide.js was broken this way for an unknown length of time - an
apostrophe inside a single-quoted string - and the whole Studio guide it
defines never loaded. Nothing in the suite would have caught it, because
nothing ran the file.

Checks both standalone .js files and the inline <script> blocks in the pages.
Needs node; skips with a clear message if it is not installed.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOTS = ("panels", "CamWatch")
SKIP = {"network.html"}          # embeds a base64 font, not a page we ship logic in
# Test and dev tooling builds HTML inside Python strings, so a <script> there
# is a template, not source we ship. This file's own docstring is one too.
SKIP_PARTS = {"tests", "dev", ".drafts", "node_modules"}

NODE = next((p for p in ("/opt/nodejs/bin/node", shutil.which("node") or "")
             if p and Path(p).exists()), None)

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def parses(code):
    """True if node can parse this source. Returns (ok, first error line)."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        r = subprocess.run([NODE, "--check", tmp], capture_output=True, text=True)
    finally:
        os.unlink(tmp)
    if r.returncode == 0:
        return True, ""
    err = next((l.strip() for l in r.stderr.splitlines()
                if "Error:" in l), r.stderr.strip().splitlines()[-1:] or [""])
    return False, (err if isinstance(err, str) else err[0])[:160]


if not NODE:
    print("SKIP no node on this machine; cannot parse-check the scripts")
    raise SystemExit(0)

js = sorted(p for r in ROOTS for p in (ROOT / r).rglob("*.js"))
check("there are scripts to check", len(js) > 5, f"found {len(js)}")
for p in js:
    ok, err = parses(p.read_text(encoding="utf-8"))
    check(f"{p.relative_to(ROOT)} parses", ok, err)

# An inline block is the same risk, and most of the logic in these pages lives
# in one. Blocks with a src= attribute load a file already checked above.
pages = sorted(p for r in ROOTS for ext in ("*.html", "*.py")
               for p in (ROOT / r).rglob(ext)
               if p.name not in SKIP and not SKIP_PARTS & set(p.parts))
blocks = 0
for p in pages:
    html = p.read_text(encoding="utf-8")
    for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
        code = m.group(1)
        if not code.strip():
            continue
        # A template is not JavaScript until it is rendered: Jinja in the
        # pages, and f-string interpolation where Python builds the markup.
        if re.search(r"\{\{|\{%", code) or (p.suffix == ".py" and "{" in code):
            continue
        blocks += 1
        line = html[:m.start(1)].count("\n") + 1
        ok, err = parses(code)
        check(f"{p.relative_to(ROOT)}:{line} inline script parses", ok, err)
check("there are inline scripts to check", blocks > 10, f"found {blocks}")

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
