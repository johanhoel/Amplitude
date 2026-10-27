"""Run the camwatch tests: python tests/run.py [--quick] [-k name] [-v]

Each tests/test_*.py is a script run in its own process (they set environment variables before importing the app).
A test fails on a line starting with FAIL, "SOME FAILED", a traceback or a non-zero exit. Exit code 0 = all passed,
so this is the gate for CI and for AI-made changes.

--quick skips the slow ones (model downloads, video encoding): about 30 s instead of a few minutes.
tests/container/ holds tests that need the Docker image (rclone): run them on the server, see AGENTS.md.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLOW = {"test_clip_model.py", "test_search_objects.py", "test_search_strangers.py", "test_share.py", "test_timelapse.py"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the slow tests")
    ap.add_argument("-k", default="", help="only tests whose file name contains this")
    ap.add_argument("-v", action="store_true", help="print every line of every test")
    args = ap.parse_args()
    tests = sorted(p for p in HERE.glob("test_*.py") if args.k in p.name and not (args.quick and p.name in SLOW))
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    failed, total_pass, started = [], 0, time.time()
    for path in tests:
        t = time.time()
        try:
            out = subprocess.run([sys.executable, str(path)], cwd=HERE, env=env, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=900)
            text, code = out.stdout + out.stderr, out.returncode
        except subprocess.TimeoutExpired:
            text, code = "FAIL timed out after 900 s", 1
        lines = text.splitlines()
        passes = sum(1 for l in lines if l.startswith("PASS"))
        fails = [l for l in lines if l.startswith("FAIL") or l.startswith("SOME FAILED")]
        crashed = code != 0 or any(l.startswith("Traceback") for l in lines)
        total_pass += passes
        ok = not fails and not crashed and passes > 0
        print(f"{'ok  ' if ok else 'FAIL'} {path.name:<34} {passes:>4} checks  {time.time() - t:5.1f}s", flush=True)
        if args.v or not ok:
            shown = lines if args.v else fails + _traceback(lines) + ([] if passes else ["(no PASS lines - the test did not get far)"])
            for l in shown[-60:]:
                print("     " + l)
        if not ok:
            failed.append(path.name)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} test files passed, {total_pass} checks, {time.time() - started:.0f}s"
          + (f" - FAILED: {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)


def _traceback(lines):
    """The last traceback, if any."""
    starts = [i for i, l in enumerate(lines) if l.startswith("Traceback")]
    return lines[starts[-1]:] if starts else []


if __name__ == "__main__":
    main()
