#!/usr/bin/env python3
"""Generate shell.css for every server from design/components.py.

Same arrangement as the tokens and the icons: the projects run on different
servers and cannot share a file over HTTP, so the component layer is copied
rather than linked, and this script is the copy.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from components import CSS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "panels/server/www/shell.css",
    "CamWatch/app/static/shell.css",
]

HEAD = """/* Generated from design/components.py by design/sync-components.py.
 * Edit there, not here.
 *
 * The shared parts: a page, a header, a section heading, a stat strip and a
 * grid of tiles. The vocabulary is CamWatch's dashboard, which was already
 * the clearest page in either project, so both now speak it.
 *
 * Every class is prefixed ui- so it cannot collide with a page's own.
 * Load this AFTER the token sheet and BEFORE a page's own <style>.
 */
"""


def main():
    body = HEAD + CSS.lstrip("\n")
    changed = []
    for rel in TARGETS:
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_text() != body:
            p.write_text(body)
            changed.append(rel)
        print(f"{'updated' if rel in changed else '  same '}  {rel}")
    print(f"\n{len(body.encode())/1024:.1f} KB, {len(changed)} of {len(TARGETS)} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
