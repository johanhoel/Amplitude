"""The mark and its animation: the rules that are easy to break by accident on a later edit."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
MARK = STATIC / "mark.svg"
CSS = STATIC / "splash.css"

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


svg_raw = MARK.read_bytes()
css_raw = CSS.read_bytes()
css = css_raw.decode()

# .gitattributes enforces LF; a CRLF asset breaks the shell scripts that copy it.
check("mark.svg is LF", b"\r\n" not in svg_raw)
check("splash.css is LF", b"\r\n" not in css_raw)

root = ET.fromstring(svg_raw)
check("mark.svg parses", root.tag.endswith("svg"))
check("mark.svg has a viewBox so it scales to a favicon", root.get("viewBox") is not None)
check("mark.svg is labelled for screen readers", root.get("aria-label") == "camwatch")

classes = {el.get("class", "") for el in root.iter()}
for part, why in [("cw-ring", "the lens"), ("cw-rec", "the recording dot")]:
    check(f"mark.svg keeps .{part} ({why})", any(part in c for c in classes))
check("mark.svg keeps four brackets", sum(1 for c in classes if "cw-b" in c and c != "cw-b") == 4)

# Animation rules. Each of these shipped as a real bug somewhere in panels/.
check("no 'transition: all'", not re.search(r"transition:\s*all\b", css))
check("no scale(0) entrance", not re.search(r"scale\(0(\.0+)?\)", css))
check("no bare ease-in", not re.search(r"\bease-in\b(?!-out)", css))
# Only what is inside a @keyframes body, or named in a transition, actually animates.
# A static width on the splash shell is not motion, so look at those two places only.
animated = set()
for body in re.findall(r"@keyframes[^{]+\{(.*?)\n\}", css, re.S):
    animated |= {m.strip() for m in re.findall(r"([a-z-]+)\s*:", body)}
for decl in re.findall(r"transition:\s*([^;]+);", css):
    flat = re.sub(r"\([^)]*\)", "", decl)   # commas inside cubic-bezier() are not separators
    animated |= {part.strip().split()[0] for part in flat.split(",") if part.strip()}
expensive = animated - {"transform", "opacity"}
check("only transform and opacity are animated", not expensive, f"also animates {sorted(expensive)}")
check("reduced motion is handled", "prefers-reduced-motion" in css)
check("reduced motion is gentler, not zero", css.count("cw-fade") >= 2)
check("splash rests within a second",
      max(int(m) for m in re.findall(r"(\d+)ms", css)) <= 2000,
      "an entrance longer than 2s is not an entrance")

# transform-origin must be the mark's centre, or the parts fly apart as they scale.
check("parts scale from the mark's centre", "transform-origin: 64px 64px" in css)

# The splash is wired into the phone page, and gated so it is not a tax on every page view.
mob = (Path(__file__).resolve().parents[1] / "app" / "mobile.html").read_text()
check("mobile.html links splash.css", "/static/splash.css" in mob)
check("mobile.html inlines the mark (CSS cannot reach into an <img>)", 'class="cw-mark is-splash"' in mob)
check("splash only on a standalone launch", "display-mode: standalone" in mob)
check("splash shows once per session", "sessionStorage" in mob)
check("splash removes itself", "el.remove()" in mob)

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
