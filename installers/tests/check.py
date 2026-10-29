"""The installers' checks: python3 installers/tests/check.py

Nothing here can run AppleScript or a shell installer end to end, so these
are the things that can be checked by reading - and they are the things that
have actually broken.

There is no Windows installer any more. There was, and its version gate
rejected every machine for a week because it asked [Environment]::OSVersion,
which reports Windows 8 inside a ps2exe wrapper. It was fixed, and then
removed entirely: DStreamer needs the host's network for the PTP clock, and
Windows puts WSL behind a virtual one, so the audio had gaps no setting could
close. The other two gained nothing from a path nobody could support.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


# --- the Windows installer is gone and should stay gone -----------------
check("there is no Windows installer", not (ROOT / "installers" / "windows").exists(),
      "it was removed on purpose; DStreamer cannot get the host network there")

wf = (ROOT / ".github" / "workflows" / "installers.yml").read_text(encoding="utf-8")
check("the workflow does not build a .exe", "ps2exe" not in wf and "Setup.exe" not in wf)
check("the workflow has no windows runner", "windows-latest" not in wf)
check("the release does not wait on a windows job", "needs: [macos]" in wf,
      "a job that no longer exists would block every release")

# --- what the workflow does still build ---------------------------------
check("the workflow still builds the Mac installers", "macos-latest" in wf)
check("the release publishes what it downloads", "files: dist/*" in wf)
check("the release says where DStreamer should actually run",
      "Raspberry Pi" in wf or "Linux" in wf,
      "the release notes are the only place most people will read this")

# --- the installers that remain -----------------------------------------
mac_cmd = ROOT / "installers" / "macos" / "install.command"
linux_sh = ROOT / "installers" / "linux" / "setup.sh"
for p in (mac_cmd, linux_sh, ROOT / "installers" / "macos" / "build.sh"):
    check(f"{p.relative_to(ROOT)} is present", p.exists())
    if p.exists():
        check(f"{p.relative_to(ROOT)} is LF", b"\r\n" not in p.read_bytes(),
              "a CRLF shell script fails with a confusing error on the first line")

for p in (mac_cmd, linux_sh):
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    # Not "set -e": install.command is interactive and handles its own
    # failures so the Terminal window stays open with the error in it.
    # Unset variables and a broken pipe are the silent ones.
    # Read the flags out of the set line rather than matching a substring:
    # "set -euo pipefail" does not contain "set -u", which is how the first
    # version of this check failed a script that was perfectly correct.
    flags = "".join(re.findall(r"^set -([a-z]+)", text, re.M))
    check(f"{p.relative_to(ROOT)} catches unset variables and broken pipes",
          "u" in flags and "pipefail" in text,
          f"set flags are {flags!r}; an unset variable expands to empty and the installer goes quietly wrong")

# --- the rename, which is easy to half-finish ----------------------------
for name, path in (("installers.yml", ROOT / ".github/workflows/installers.yml"),
                   ("installers/README.md", ROOT / "installers/README.md"),
                   ("linux/setup.sh", linux_sh)):
    if path.exists():
        check(f"{name} says DStreamer, not DanteStreamer",
              "DanteStreamer" not in path.read_text(encoding="utf-8"))

# --- the README should not promise Windows -------------------------------
readme = ROOT / "installers" / "README.md"
if readme.exists():
    text = readme.read_text(encoding="utf-8")
    bad = [l for l in text.splitlines()
           if re.search(r"\.exe|WSL|Windows (10|11|protected)", l)]
    check("installers/README.md does not describe a Windows install", not bad,
          f"{len(bad)} line(s) still do, e.g. {bad[0][:60] if bad else ''}")

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
