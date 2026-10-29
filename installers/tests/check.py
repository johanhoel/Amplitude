"""The installer's checks, verified without Windows: python3 installers/tests/check.py

Nothing here can run PowerShell, so the Windows installer is only ever
exercised by someone double-clicking the .exe. That is how its version gate
shipped broken: it asked [Environment]::OSVersion, which since Windows 8.1
reports version 6.2 (build 9200) to any program whose manifest does not claim
Windows 10 - and the ps2exe wrapper did not claim it. Every machine looked
like Windows 8, so the installer refused to run, on Windows 11 included.

These are static checks over the script and over the workflow that wraps it.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "installers" / "windows" / "Install.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "installers.yml"

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


ps1 = PS1.read_text(encoding="utf-8")
wf = WORKFLOW.read_text(encoding="utf-8")

# The gate has to read the build from somewhere that does not lie.
check("the version gate reads CurrentBuildNumber from the registry",
      "CurrentBuildNumber" in ps1,
      "an API that depends on the manifest cannot be trusted inside the .exe")

gate = re.search(r"if \(\$build -lt (\d+)\)", ps1)
check("the gate compares a $build variable to a build number", gate is not None,
      "expected: if ($build -lt 19041)")

# OSVersion may stay, but only as the fallback inside the catch. The comment
# above it names the API too, so count code lines only.
code = "\n".join("" if ln.lstrip().startswith("#") else ln for ln in ps1.split("\n"))
uses = [m.start() for m in re.finditer(r"\[Environment\]::OSVersion", code)]
check("OSVersion appears at most once in code", len(uses) <= 1,
      f"{len(uses)} uses; it must never be the primary source")
if uses:
    # The fallback sits on its own line directly under "} catch {".
    lines = code.split("\n")
    at = next(i for i, ln in enumerate(lines) if "[Environment]::OSVersion" in ln)
    prev = next((lines[j] for j in range(at - 1, -1, -1) if lines[j].strip()), "")
    check("that one use is the fallback inside the catch block",
          "catch" in prev,
          f"the line above it is {prev.strip()!r}; outside a catch it is the lying value again")

if gate:
    build = gate.group(1)
    check("the gate requires build 19041 (Windows 10 2004)", build == "19041", build)
    # The message must name the number the code tests, or whoever reads it
    # goes looking for the wrong Windows version.
    after = ps1.split("if ($build -lt", 1)[1][:400]
    check("the message names the build number it tests", build in after,
          "say the build number, not only the marketing version")

check("a failed check prints the build it saw",
      re.search(r"reports build \$build", ps1) is not None,
      "without it, a wrong answer here is a dead end for whoever hits it")

# And the cause, so everything else in the script sees the real Windows too.
check("ps2exe writes the Windows 10 compatibility manifest", "-supportOS" in wf,
      "without -supportOS the .exe reports Windows 8 to every version API")
check("the exe is still built with -requireAdmin", "-requireAdmin" in wf)

# The rename landed in 937bc0b. An installer still calling itself DanteStreamer
# would mean the script and the workflow had drifted apart again.
for name, text in (("Install.ps1", ps1), ("installers.yml", wf)):
    check(f"{name} says DStreamer, not DanteStreamer", "DanteStreamer" not in text)

PS1 = (ROOT / "installers" / "windows" / "Install.ps1").read_text(encoding="utf-8")

# Opening the browser the instant the install finishes lands on "can't reach
# this page" - the service is still starting. The wait is what makes the
# shortcut useful rather than alarming.
wait_at, open_at = PS1.find("Waiting for it to start"), PS1.find("Start-Process $P.Url")
check("the installer waits for the port before opening the browser", wait_at != -1)
check("the wait comes before the browser opens", -1 < wait_at < open_at)
check("the wait gives up rather than hanging", "AddSeconds(60)" in PS1)

# Stopping it used to mean removing it, recordings and all.
check("the installer can stop without uninstalling", "if ($Stop) {" in PS1)
check("and start again", "if ($Start) {" in PS1)
check("-Stop and -Start are accepted on the command line",
      "[switch]$Stop" in PS1 and "[switch]$Start" in PS1)
check("stopping leaves the distro registered",
      "--terminate" in PS1.split("if ($Stop) {")[1].split("if ($Uninstall)")[0]
      and "--unregister" not in PS1.split("if ($Stop) {")[1].split("if ($Uninstall)")[0],
      "terminate stops it; unregister would delete it")
check("there are Start-menu shortcuts for both", "foreach ($verb in 'Stop', 'Start')" in PS1)
check("the installer says how to stop it", "Stop or start it:" in PS1)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
