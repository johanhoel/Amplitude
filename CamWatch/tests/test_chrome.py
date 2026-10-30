"""The page chrome: the bar that says where you are, and labels that count.

Two things that were wrong for anyone looking:

  The page bar holds fifteen pages and shows about ten. It scrolls sideways
  with its scrollbar hidden, so the five behind the edge were not merely out
  of sight - nothing said they were there at all. Now the edge with more
  behind it is faded, set from the real scroll position so a bar with nothing
  hidden is not dimmed for show, and the page you are on is scrolled into
  view when it loads.

  "1 people seen" on the phone home. A number whose label disagrees with it
  teaches people not to trust the number.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


web = (APP / "webui.py").read_text(encoding="utf-8")
mob = (APP / "mobile.html").read_text(encoding="utf-8")

# ---- the page bar says there is more of it ----------------------------
check("the bar still scrolls rather than wrapping",
      re.search(r"header nav\{[^}]*overflow-x:auto", web) is not None)
check("the scroller sits in a wrapper that can be faded",
      re.search(r'<div class="navwrap"><nav', web) is not None
      and re.search(r"header \.navwrap\{[^}]*position:relative", web) is not None)
check("both edges have a fade, shown only when that side has more",
      re.search(r"header \.navwrap\.more-l::before,\s*header \.navwrap\.more-r::after\{opacity:1\}", web) is not None,
      "the rule that turns a fade on is what makes it mean anything")
check("the fades are drawn over the bar, not in it",
      re.search(r"header \.navwrap::before,header \.navwrap::after\{[^}]*pointer-events:none", web) is not None,
      "a gradient that eats clicks would block the page you are reaching for")
check("the fade follows the real scroll position",
      re.search(r"classList\.toggle\('more-r',\s*nav\.scrollLeft < max", web) is not None
      and re.search(r"classList\.toggle\('more-l',\s*nav\.scrollLeft > ", web) is not None,
      "a fade that is always on is a lie about what is hidden")
check("it is kept right as the bar is scrolled and the window resized",
      "nav.addEventListener('scroll'" in web and "addEventListener('resize', edges)" in web)
check("the page you are on is brought into view",
      re.search(r"if \(here\) here\.scrollIntoView\(\{ block: 'nearest', inline: 'center' \}\)", web) is not None,
      "landing on Settings with the bar scrolled to Home hides where you are")
check("the sideways scroll is dropped for reduced motion",
      re.search(r"prefers-reduced-motion[^}]*\}header nav\{scroll-behavior:auto\}", web) is not None
      or re.search(r"@media \(prefers-reduced-motion:reduce\)\{header nav\{scroll-behavior:auto\}", web) is not None)

# ---- a label that agrees with its number ------------------------------
check("the phone stats label is written, not hard-coded",
      re.search(r'id="n-people-l"', mob) is not None and re.search(r'id="n-today-l"', mob) is not None)
check("one person is a person",
      re.search(r"plural\(s\.people_today\.length, 'person seen', 'people seen'\)", mob) is not None,
      "it read \"1 people seen\"")
check("and one visit is a visit",
      re.search(r"plural\(s\.today, 'visit today', 'visits today'\)", mob) is not None)
check("the plural helper picks the singular only at one",
      re.search(r"plural = \(n, one, many\) => n === 1 \? one : many", mob) is not None)

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
