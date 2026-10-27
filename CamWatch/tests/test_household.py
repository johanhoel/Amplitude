import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
from household import PendingAlert, quiet_title
def run(name, steps, want, ended_at=None):
    a = PendingAlert("ev", b"", "person", "Person at 10:00", now=0.0)
    got = None
    for t, results in steps:
        a.add(results)
        got = a.decision(t, ended=(ended_at == t))
        if got: break
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name:<52} -> {got} (want {want})" + (f"  title: {quiet_title(a.known)}" if got == 'quiet' else ''))
run("household face at once", [(0.0, [("Alex", 0.6)]), (3.0, [])], "quiet")
run("household + stranger -> loud at once", [(0.0, [("Alex", 0.6)]), (0.4, [(None, 0.2)])], "loud")
run("stranger first frame -> loud immediately", [(0.0, [(None, 0.1)])], "loud")
run("no face by the deadline -> loud", [(0.0, []), (1.0, []), (3.0, [])], "loud")
run("still waiting before the deadline", [(0.0, []), (1.0, [])], None)
run("two household members", [(0.0, [("Alex", 0.6)]), (1.2, [("Sam", 0.5)]), (3.0, [])], "quiet")
run("event ends early with a household face", [(0.0, []), (1.0, [("Alex", 0.55)])], "quiet", ended_at=1.0)
