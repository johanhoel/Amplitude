"""The update button: python3 panels/tests/updates.py

Checks the parts that do not need the network. The GitHub call itself is not
exercised here - a test that fails when the internet is slow teaches people
to ignore the suite.

The thing most worth protecting is the refusal to offer an update when the
running commit is unknown. Without a recorded commit the only comparison left
is a date-shaped version string, and offering "update" on that could move a
panel backwards.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # panels/
sys.path.insert(0, str(ROOT / "server"))
from homedeck import updates  # noqa: E402

WEB = (ROOT / "server" / "homedeck" / "web.py").read_text(encoding="utf-8")
AUTH = (ROOT / "server" / "homedeck" / "auth.py").read_text(encoding="utf-8")
ADMIN = (ROOT / "server" / "www" / "admin.html").read_text(encoding="utf-8")
WORKER = (ROOT / "kit" / "homedeck-update").read_text(encoding="utf-8")
BUILD = (ROOT / "build_kit.sh").read_text(encoding="utf-8")

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


def commit(sha, date, msg):
    return {"sha": sha, "commit": {"message": msg, "committer": {"date": date + "T10:00:00Z"}}}


# ---- what this install is running -----------------------------------
check("there is a VERSION to report", (ROOT / "server" / "VERSION").exists(),
      "without one the card cannot say what is installed")
cur = updates.current()
check("current() reports a version", bool(cur["version"]) and cur["version"] != "unknown")
check("current() reports a commit field", "commit" in cur)

# ---- the notes ------------------------------------------------------
COMMITS = [
    commit("aaa1111", "2026-10-29", "panels: a change\n\nbody text"),
    commit("bbb2222", "2026-10-28", "Merge pull request #4 from someone/branch"),
    commit("ccc3333", "2026-10-27", "panels: another change"),
    commit("ddd4444", "2026-10-20", "panels: the version running here"),
]
notes = updates._notes(COMMITS, "ddd4444")
check("notes stop at the running commit", [n["short"] for n in notes] == ["aaa1111", "ccc3333"],
      f"got {[n['short'] for n in notes]}")
check("a merge commit is left out", all("Merge" not in n["text"] for n in notes))
check("only the first line of a message is used",
      all("\n" not in n["text"] and "body text" not in n["text"] for n in notes))
check("each note carries a date", all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", n["date"]) for n in notes))
check("an up-to-date install gets no notes", updates._notes(COMMITS, "aaa1111") == [])
check("a long subject is cut",
      len(updates._notes([commit("1" * 7, "2026-10-29", "x" * 400)], "zz")[0]["text"]) <= 140)
check("the list is capped",
      len(updates._notes([commit(f"{i:07d}", "2026-10-29", f"c{i}") for i in range(40)], "zz")) <= 15)

# ---- the folder filter ----------------------------------------------
src = (ROOT / "server" / "homedeck" / "updates.py").read_text(encoding="utf-8")
check("the check asks GitHub only about this folder", "path={FOLDER}" in src or "path=panels" in src,
      "the repository holds several projects; a CamWatch commit is not a Home Deck update")
check("it fetches enough commits to build notes from",
      bool(re.search(r"per_page=(\d+)", src)) and int(re.search(r"per_page=(\d+)", src).group(1)) > 1)

# ---- the routes ------------------------------------------------------
check("GET /api/update exists", "'/api/update'" in WEB)
check("GET /api/update/status exists", "'/api/update/status'" in WEB)
check("POST /api/update/run exists", "'/api/update/run'" in WEB)
check("installing needs the admin PIN", "'/api/update/run'" in AUTH,
      "it must be in ADMIN_POSTS or anyone on the network can reinstall the panels")
check("the updater is started detached", "start_new_session=True" in WEB,
      "homedeck-apply restarts this server; a child process would be killed mid-copy")
check("it refuses to install when nothing is newer", "already up to date" in WEB)

# ---- the worker ------------------------------------------------------
# It decides WHAT to install. install-homedeck.sh decides HOW, and it is the
# same code a fresh install runs - checksum per file, your edits kept as
# .new-<version>, homedeck-apply with rollback at the end. The one thing worth
# guarding here is that the worker keeps delegating instead of growing its own
# copy of that.
check("the worker delegates the install to install-homedeck.sh",
      "install-homedeck.sh" in WORKER and "--update" in WORKER,
      "that script is what keeps a file you edited; a cp -a here would overwrite it")
check("the worker does not copy app files itself",
      not re.search(r"cp -a .*\$(ROOT|SRC)", WORKER),
      "two copies of the merge rules is one copy too many")
check("the worker never writes homedeck.toml",
      not re.search(r">\s*\S*homedeck\.toml|cp\s+(-\w+\s+)?\S*/homedeck\.toml", WORKER),
      "the settings belong to this house, not to whoever committed last")
check("the worker checks the archive is complete",
      "the archive is incomplete" in WORKER,
      "a truncated download still untars; building half a release is worse than failing")
check("the worker builds before it installs",
      WORKER.index('bash "$SRC/build_kit.sh"') < WORKER.index('bash "$SRC/dist'),
      "build_kit.sh refuses code that does not import, and failing there touches nothing")
check("the worker records the installed commit", ".commit" in WORKER,
      "without it the next check cannot tell new from old")
check("the worker runs from a copy of itself",
      'cp "$0"' in WORKER,
      "install-homedeck.sh reinstalls this very file; bash reads a script as it runs it")
check("the worker carries no credential",
      not re.search(r"(?i)(key|token|secret|password)\s*[:=]\s*[\"']?[A-Za-z0-9]{16,}", WORKER),
      "it is fetched from a public repo; it needs no secret, and this file is published")

def _guard_alts():
    """The alternatives of the guard's -E pattern, as a set."""
    m = re.search(r'grep -rIl -i -E "([^"]+)"', BUILD)
    return set(m.group(1).split("|")) if m else set()


# ---- the publishing guard -------------------------------------------
# It used to ban the bare words "claude" and "llm", which stopped building the
# day the Local AI panel shipped - /llm/ routes and a "claude" setup id are the
# product's own vocabulary. Narrowed to authorship shapes. These keep it narrow
# in one direction and strict in the other.
check("the guard still bans an authorship byline",
      all(x in BUILD for x in ("co-authored-by", "generated with", "written by claude"))
      and re.search(r"claude\\+\.ai", BUILD) is not None,
      "that is the only thing it was ever for")
check("the guard does not ban the product's own vocabulary",
      not ({"claude", "llm", "\\\\bllm\\\\b", "anthropic"} & _guard_alts()),
      "the Local AI panel routes under /llm/ and launches a setup called claude")

# ---- nothing published carries a secret ------------------------------
# kit/ is what a stranger downloads and reads. It carried the file-server key
# for every install in this repo's public history; the key is gone from the
# files but not from the history, so it still has to be rotated. This keeps
# the next one from being added.
SECRETISH = re.compile(r"(?i)(key|token|secret|password|passwd)\s*[:=]\s*[\"']?[A-Za-z0-9+/]{16,}")
leaky = []
for f in sorted((ROOT / "kit").iterdir()):
    if f.is_file():
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if SECRETISH.search(line) and "${" not in line:
                leaky.append(f"{f.name}:{i}")
check("no file in kit/ carries a credential", not leaky, ", ".join(leaky))
check("the installer needs no private file server",
      "winrepo" not in (ROOT / "kit" / "homedeck.sh").read_text(encoding="utf-8").lower(),
      "anyone should be able to install this; a key in a public file helps nobody")

# ---- the card --------------------------------------------------------
check("the admin page has the update card", 'id="upd"' in ADMIN)
check("the card is hidden until there is something to say",
      'id="upd"' in ADMIN and re.search(r'id="upd"[^>]*\bhidden', ADMIN) is not None)
check("a commit message is written as text, never as markup",
      "w.textContent = n.text" in ADMIN and "innerHTML = n.text" not in ADMIN,
      "these lines come from a repository")
check("the page follows the update after starting it", "followUpdate" in ADMIN)

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
