"""The install contract: python3 panels/tests/install.py

There is one edition now, and the pages that used to be generated for a
stranger's house are the same pages this house runs. That makes the settings
template the only thing standing between a new install and somebody else's
addresses - so what it promises, and who fills it in, is worth checking.

The bug this starts from: install-homedeck.sh substitutes __HA_URL__ with the
address you type at setup, and the template had stopped containing __HA_URL__.
The sed was a no-op, nothing complained, and every fresh install came up
pointing at the author's own Home Assistant instead of the user's.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOML = (ROOT / "server" / "homedeck.toml").read_text(encoding="utf-8")
INSTALL = (ROOT / "kit" / "install-homedeck.sh").read_text(encoding="utf-8")
STAGING = (ROOT / "tools" / "staging.sh").read_text(encoding="utf-8")
CHECK = (ROOT / "tools" / "check.sh").read_text(encoding="utf-8")

results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ': ' + detail}")
    results.append(bool(ok))


# ---- the address the installer asks for actually lands somewhere ------
url = re.search(r'^url = "([^"]*)"', TOML, re.M)
check("the template has a Home Assistant url", url is not None)
check("it is a placeholder, not an address",
      url is not None and url.group(1) == "__HA_URL__",
      f'found {url.group(1) if url else "-"} - a fresh install would point at it')
check("the installer fills that placeholder in",
      "__HA_URL__" in INSTALL,
      "otherwise the address typed at setup is thrown away")

# ---- everything that reads the template handles the placeholder -------
for name, body in (("build_kit.sh", (ROOT / "build_kit.sh").read_text(encoding="utf-8")),
                   ("tools/check.sh", CHECK), ("tools/staging.sh", STAGING)):
    check(f"{name} substitutes the placeholder before using the settings",
          "__HA_URL__" in body,
          "the settings will not validate with a placeholder in them")

# ---- the suite is runnable by somebody who is not the author ----------
check("staging can run without a Home Assistant token",
      "HOMEDECK_STUB" in STAGING and (ROOT / "tools" / "stub-ha.py").exists(),
      "tests/smoke.py was unrunnable for anyone but the owner of that house")
check("staging still refuses to guess a real address",
      "HOMEDECK_HA_URL" in STAGING,
      "silently falling back to localhost would look like Home Assistant is down")
check("the smoke test does not need docker",
      "import playwright" in CHECK,
      "it was skipped on every machine without docker, which is most of them")
check("the stub is never mistaken for a credential store",
      "stub-no-real-credential" in STAGING)

print(f"{sum(results)}/{len(results)} passed")
raise SystemExit(0 if all(results) else 1)
