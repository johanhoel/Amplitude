#!/usr/bin/env python3
"""Copy the :root block from design/tokens.css into every stylesheet that
serves it, then report what changed.

The projects run on different servers and cannot share a file over HTTP, so
the token block is copied rather than linked. This script is the copy. Edit
design/tokens.css, run this, commit both.

A target may override a few tokens - a project is allowed its own accent and
its own corner radius. It is not allowed its own idea of what --mute means.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "design" / "tokens.css"
MARK_START = "/* >>> generated from design/tokens.css - edit there, run design/sync-tokens.py */"
MARK_END = "/* <<< end generated tokens */"

# path -> what this target may change about the base.
#
#   override: a canonical token given a different value here. A project may
#             have its own accent and its own corner radius. It may not have
#             its own idea of what --mute means, so text tokens are refused.
#   extra:    names that exist only in this project. Aliases must point at a
#             canonical token with var(), so they cannot drift from it.
# Fixed everywhere: these are the reading weights and the status colours, and
# a project having its own idea of them is the sprawl this file exists to end.
# The accent trio is deliberately NOT in here - a project may have its own
# brand colour - but design/check-contrast.py verifies every generated sheet,
# so an override still has to clear AA.
FIXED = {"ink", "mute", "dim", "ok", "warn", "bad"}

# The friend edition is violet, not cyan. All three accent tokens move
# together: a violet readable AS text on a dark card is too pale to sit under
# black type, so this accent takes white type where the owner's cyan takes
# black. --status-ink stays dark in both, because green, amber and red are
# light colours whoever is looking at them.
FRIEND_ACCENT = {
    "accent": "#7958ff",
    "accent-text": "#a075ff",   # 4.50:1, the brand violet lightened until it reads
    "accent-ink": "#ffffff",    # 4.51:1 on the accent; black would be 4.43 and fail
    "r": "24px",                # the friend pages were drawn with a softer corner
}

TARGETS = {
    "panels/server/www/wall.css": {},
    "panels/server/www/deck.css": {
        # The deck is the phone/tablet home screen: full-bleed cards with a
        # much larger radius than a dashboard panel.
        "override": {"r": "22px"},
    },
    # The friend edition ships its own sheet twice on purpose: extra/ is the
    # source build_www.py copies into every build (it copies that whole folder,
    # so this needs no change to the generator), and src/www/ is the build
    # output that is checked in and served today. Both come from here, so they
    # cannot disagree.
    "panels/friend/extra/wall.css": {
        "override": dict(FRIEND_ACCENT),
    },
    "panels/friend/src/www/wall.css": {
        "override": dict(FRIEND_ACCENT),
    },
    "CamWatch/app/static/tokens.css": {
        "extra": {
            # webui.py and the phone pages grew up with different names for
            # the same two text weights. Aliased rather than renamed, so this
            # change cannot break a selector.
            "fg": "var(--ink)",
            "muted": "var(--mute)",
            "danger": "var(--bad)",
            "known": "var(--ok)",
            "unknown": "var(--warn)",
            # Genuinely local: the recording red is not a status colour, it is
            # a badge that must not be mistaken for --bad.
            "live": "#e11d48",
            # Height of the phone tab bar, including the home indicator.
            "tab": "calc(64px + env(safe-area-inset-bottom))",
        },
    },
}


def block():
    text = SOURCE.read_text()
    m = re.search(r"^:root, :root body \{.*?^\}", text, re.S | re.M)
    if not m:
        sys.exit("could not find the :root block in design/tokens.css")
    return m.group(0)


def apply_overrides(css, overrides):
    for name, value in overrides.items():
        if name in FIXED:
            sys.exit(f"--{name} is a shared reading weight: it is the same in "
                     "every project by design and cannot be overridden")
        css, n = re.subn(rf"(--{name}:\s*)[^;]+;", rf"\g<1>{value};", css, count=1)
        if not n:
            sys.exit(f"override --{name} does not exist in tokens.css")
    return css


def apply_extras(css, extras):
    if not extras:
        return css
    lines = "\n".join(f"  --{k}: {v};" for k, v in extras.items())
    return css[:css.rstrip().rfind("}")] + (
        "\n  /* ---- local to this project ---- */\n" + lines + "\n}\n")


def main():
    base = block()
    changed = []
    for rel, spec in TARGETS.items():
        overrides, extras = spec.get("override", {}), spec.get("extra", {})
        path = ROOT / rel
        css = apply_extras(apply_overrides(base, overrides), extras)
        note = ""
        if overrides:
            note = "\n/* " + ", ".join(f"--{k} overridden for this project"
                                       for k in overrides) + " */"
        payload = f"{MARK_START}{note}\n{css}\n{MARK_END}"

        if path.exists():
            old = path.read_text()
            if MARK_START in old:
                new = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
                             lambda _: payload, old, flags=re.S)
            else:
                # First run: replace whatever :root block is already there.
                new = re.sub(r"^:root[^{]*\{.*?^\}", lambda _: payload, old,
                             count=1, flags=re.S | re.M)
                if new == old:
                    new = payload + "\n\n" + old
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            new = payload + "\n"

        if not path.exists() or new != path.read_text():
            path.write_text(new)
            changed.append(rel)
        print(f"{'updated' if rel in changed else '  same '}  {rel}"
              + (f"   override {', '.join('--' + k for k in overrides)}" if overrides else "")
            + (f"   +{len(extras)} local" if extras else ""))

    print(f"\n{len(changed)} of {len(TARGETS)} stylesheets updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
