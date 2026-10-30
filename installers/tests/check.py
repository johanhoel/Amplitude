"""The installer's checks: python3 installers/tests/check.py

Nothing here can run a shell installer end to end, so these are the things
that can be checked by reading - and they are the things that have actually
broken.

There is one installer now: linux/setup.sh. There was a Windows one, whose
version gate rejected every machine for a week because it asked
[Environment]::OSVersion, which reports Windows 8 inside a ps2exe wrapper.
There was a Mac one that built a .dmg around a Linux virtual machine. Both
are gone: DStreamer needs the host's network for the PTP clock, which neither
gives it, and the other two gained nothing from paths nobody could test.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


# --- the installers that are gone should stay gone ----------------------
for gone, why in (("windows", "DStreamer cannot get the host network there"),
                  ("macos", "a Mac VM has the same clock problem, milder")):
    check(f"there is no {gone} installer", not (ROOT / "installers" / gone).exists(),
          f"it was removed on purpose; {why}")

check("no workflow builds installers",
      not (ROOT / ".github/workflows/installers.yml").exists(),
      "nothing is built any more; setup.sh is read from the repository")

# --- the installer that remains -----------------------------------------
linux_sh = ROOT / "installers" / "linux" / "setup.sh"
check(f"{linux_sh.relative_to(ROOT)} is present", linux_sh.exists())

if linux_sh.exists():
    check(f"{linux_sh.relative_to(ROOT)} is LF", b"\r\n" not in linux_sh.read_bytes(),
          "a CRLF shell script fails with a confusing error on the first line")

    text = linux_sh.read_text(encoding="utf-8")
    # Read the flags out of the set line rather than matching a substring:
    # "set -euo pipefail" does not contain "set -u", which is how the first
    # version of this check failed a script that was perfectly correct.
    flags = "".join(re.findall(r"^set -([a-z]+)", text, re.M))
    check(f"{linux_sh.relative_to(ROOT)} catches unset variables and broken pipes",
          "u" in flags and "pipefail" in text,
          f"set flags are {flags!r}; an unset variable expands to empty and the installer goes quietly wrong")

    check("setup.sh takes all three projects",
          all(p in text for p in ("camwatch", "homedeck", "dstreamer")))

# --- the rename, which is easy to half-finish ----------------------------
for name, path in (("installers/README.md", ROOT / "installers/README.md"),
                   ("linux/setup.sh", linux_sh)):
    if path.exists():
        check(f"{name} says DStreamer, not DanteStreamer",
              "DanteStreamer" not in path.read_text(encoding="utf-8"))

# --- the README should not promise a Mac or Windows install --------------
readme = ROOT / "installers" / "README.md"
if readme.exists():
    text = readme.read_text(encoding="utf-8")
    # Instruction-shaped text only. The README explains why Windows and the
    # Mac went, and that explanation names WSL and virtual machines; saying
    # why a path is gone is not offering it.
    bad = [l for l in text.splitlines()
           if re.search(r"\.exe|\.dmg|Windows (10|11|protected)|drag the app", l)]
    check("installers/README.md does not describe a Mac or Windows install", not bad,
          f"{len(bad)} line(s) still do, e.g. {bad[0][:60] if bad else ''}")

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
