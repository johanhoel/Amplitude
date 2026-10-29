"""Release notes in Settings → Updates: what changed since the running version.

They are built from the commit list the version check already fetches, so they
cost no extra GitHub request, and only commits that touched this project's
folder are in that list - which matters because the repository holds several
projects.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import updates  # noqa: E402

WEBUI = (ROOT / "app" / "webui.py").read_text(encoding="utf-8")
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def commit(sha, date, msg):
    return {"sha": sha, "commit": {"message": msg, "committer": {"date": date + "T10:00:00Z"}}}


COMMITS = [
    commit("aaa1111", "2026-10-29", "camwatch: faster person search\n\nlonger body text"),
    commit("bbb2222", "2026-10-28", "Merge pull request #4 from someone/branch"),
    commit("ccc3333", "2026-10-27", "camwatch: fix the arm toggle"),
    commit("ddd4444", "2026-10-20", "camwatch: the version running here"),
    commit("eee5555", "2026-10-19", "camwatch: older still"),
]

notes = updates._notes(COMMITS, "ddd4444")
check("stops at the running commit", [n["short"] for n in notes] == ["aaa1111", "ccc3333"],
      f"got {[n['short'] for n in notes]}")
check("the running version's own commit is not listed",
      all(n["short"] != "ddd4444" for n in notes))
check("anything older than the running commit is not listed",
      all(n["short"] != "eee5555" for n in notes))
check("a merge commit is left out", all("Merge" not in n["text"] for n in notes),
      "merges are bookkeeping, not a change anyone reads about")
check("only the first line of a message is used",
      all("\n" not in n["text"] and "longer body" not in n["text"] for n in notes))
check("each note carries a date", all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", n["date"]) for n in notes))
check("each note carries a short sha", all(len(n["short"]) == 7 for n in notes))

check("an install that does not know its commit still gets notes",
      len(updates._notes(COMMITS, "")) == 4, "it should show what it has rather than nothing")
check("an up-to-date install gets none", updates._notes(COMMITS, "aaa1111") == [])
check("no commits means no notes", updates._notes([], "aaa1111") == [])
check("a commit with an empty message is skipped",
      updates._notes([commit("f0f0f0f", "2026-10-29", "   ")], "zzz") == [])

long = updates._notes([commit("1111111", "2026-10-29", "x" * 400)], "zzz")
check("a very long subject is cut", len(long[0]["text"]) <= 140, f"{len(long[0]['text'])} chars")
many = updates._notes([commit(f"{i:07d}", "2026-10-29", f"change {i}") for i in range(40)], "zzz")
check("the list is capped", len(many) <= 15, f"{len(many)}")

# The check must keep asking for enough commits to build notes from.
src = (ROOT / "app" / "updates.py").read_text(encoding="utf-8")
m = re.search(r"per_page=(\d+)", src)
check("the version check fetches more than one commit", m and int(m.group(1)) > 1,
      "with per_page=1 there is nothing to build notes from")
check("notes ride on the existing request", src.count("/commits?sha=") == 1,
      "a second call would spend another GitHub request per check")
check("check() returns the notes", '"notes": _notes(' in src)

# The page has somewhere to put them, and writes them as text.
check("settings has the notes list", 'id="upd-notes-list"' in WEBUI)
check("the list is hidden when there is nothing to say", "$('upd-notes').hidden = !notes.length" in WEBUI)
check("a commit message is written as text, never as markup",
      "b.textContent = n.text" in WEBUI and "innerHTML = n.text" not in WEBUI,
      "these lines come from a repository")
check("the notes are styled", ".relnotes{" in WEBUI)

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
