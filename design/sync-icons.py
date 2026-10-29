#!/usr/bin/env python3
"""Generate icons.css for every server from design/icons.py.

The icons ship as CSS masks, not inline SVG. That keeps the markup to
<i class="icon icon-bulb"></i>, which is identical in a static page and inside a
JavaScript template string - and there are hundreds of the latter. A masked
icon takes its colour from currentColor and its size from font-size, so it
behaves like a letter: put it in muted text and it goes muted with the text.

Run this after editing design/icons.py, then commit both.
"""
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icons import ICONS, FILLED  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    "panels/server/www/icons.css",
    "CamWatch/app/static/icons.css",
]

HEAD = """/* Generated from design/icons.py by design/sync-icons.py - edit there, not here.
 *
 * Replaces the emoji that used to stand in for icons. An emoji is drawn by
 * whichever colour font the device has, so the same page showed Apple glyphs
 * on a phone, Segoe on Windows, Noto's orange on Linux, and empty boxes on a
 * wall panel with no emoji font at all.
 *
 * Usage:  <i class="icon icon-bulb" aria-hidden="true"></i>
 * The icon inherits colour from currentColor and size from font-size, so it
 * sits in a line of text like a letter and goes muted when the text does.
 * Scale one with font-size, or set --icon-size for a fixed box.
 */

.icon {
  /* A name with no matching rule would otherwise leave --icon unset, and the
     element would paint as a solid block of currentColor. This fallback makes
     an unknown icon look like a missing icon instead of a bug. */
  --icon: url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'><path d='M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M9.5 9.5a2.5 2.5 0 1 1 3.3 2.4c-.5.2-.8.6-.8 1.1v.5M12 17h.01'/></svg>");
  display: inline-block;
  width: var(--icon-size, 1em);
  height: var(--icon-size, 1em);
  vertical-align: -0.135em;
  flex: none;
  background-color: currentColor;
  -webkit-mask: var(--icon) center / contain no-repeat;
  mask: var(--icon) center / contain no-repeat;
}
/* A mask has no intrinsic colour, so a forced-colours display would drop the
   icon entirely. Fall back to the system text colour there. */
@media (forced-colors: active) {
  .icon { background-color: CanvasText; }
}
"""


def data_uri(name, path):
    if name in FILLED:
        attrs = "fill='%23000' stroke='none'"
    else:
        attrs = ("fill='none' stroke='%23000' stroke-width='1.7' "
                 "stroke-linecap='round' stroke-linejoin='round'")
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' {attrs}>"
           f"<path d='{path}'/></svg>")
    # Only the characters that break a CSS url() need escaping; leaving the
    # rest readable keeps the file diffable.
    return "url(\"data:image/svg+xml," + quote(svg, safe="/:;=' <>%") .replace('"', "%22") + "\")"


def main():
    body = HEAD + "\n"
    for name in sorted(ICONS):
        body += f".icon-{name} {{ --icon: {data_uri(name, ICONS[name])}; }}\n"

    changed = []
    for rel in TARGETS:
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != body:
            path.write_text(body)
            changed.append(rel)
        print(f"{'updated' if rel in changed else '  same '}  {rel}")
    size = len(body.encode()) / 1024
    print(f"\n{len(ICONS)} icons, {size:.1f} KB, {len(changed)} of {len(TARGETS)} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
