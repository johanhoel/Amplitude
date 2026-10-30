#!/usr/bin/env python3
"""Put the house's own values into a copy of server/, or take them out again.

The repository is public, so it holds placeholders: 192.168.1.x, home.example.net, sample names. The real values live
in private.map on the Home Deck server (/opt/panel-wrapper/private.map), never in git. One pair per line:

    192.168.1.==>192.0.2.
    home.example.net==>example.org
    # comments and empty lines are skipped

    private.py apply   MAP DIR    placeholder -> real value in every text file under DIR (deploy.sh, on a copy)
    private.py reverse MAP DIR    real value -> placeholder (pull-live.sh, before anything reaches git)

A pair only matches whole words: "Sam" does not touch "Samsung", and 192.168.1.5 does not touch 192.168.1.50.
All pairs are replaced in one pass, so one replacement never feeds the next.
"""
import re
import sys
from pathlib import Path

TEXT = {".py", ".html", ".js", ".css", ".json", ".md", ".txt", ".svg", ".webmanifest", ".sh"}


def pairs(map_file, reverse=False):
    out = []
    for line in Path(map_file).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        old, sep, new = line.partition("==>")
        if not sep or not old:
            raise SystemExit(f"{map_file}: not a pair: {line!r}")
        out.append((new, old) if reverse else (old, new))
    return out


def pattern(found):
    """One regex for all pairs, longest first. A word character at either end must not touch another one."""
    parts = []
    for old in sorted(found, key=len, reverse=True):
        p = re.escape(old)
        if re.match(r"\w", old):
            p = r"(?<![\w])" + p
        if re.search(r"\w$", old):
            p = p + r"(?![\w])"
        parts.append(p)
    return re.compile("|".join(parts))


def run(map_file, folder, reverse=False):
    table = dict(pairs(map_file, reverse))
    if not table:
        return 0
    rx = pattern(table)
    changed = 0
    for f in sorted(Path(folder).rglob("*")):
        if not f.is_file() or f.suffix.lower() not in TEXT or "__pycache__" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = rx.sub(lambda m: table[m.group(0)], text)
        if new != text:
            f.write_bytes(new.encode("utf-8"))
            changed += 1
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("apply", "reverse"):
        raise SystemExit(__doc__)
    n = run(sys.argv[2], sys.argv[3], reverse=sys.argv[1] == "reverse")
    print(f"private.py {sys.argv[1]}: {n} file(s) changed")
