"""Starts the recorder for one camera slot (CAMERA_SLOT=1..4) with the camera set on the Settings page.

An empty or disabled slot waits here until a camera is configured. The recorder exits when its slot's settings
change (name, URLs, enabled) and Docker starts this launcher again, so changes apply without touching Docker.
"""
import os
import sys
import time
from pathlib import Path

from common import env, setup_logging
import settings

log = setup_logging("camslot")
SLOT = env("CAMERA_SLOT", 1, int)
IDLE_FILE = Path("/tmp/idle")  # the healthcheck counts a waiting slot as healthy


def main():
    waiting = False
    while True:
        cam = settings.camera_slots()[SLOT - 1]
        if cam["enabled"]:
            break
        if not waiting:
            log.info("camera slot %d is empty - add a camera on the Settings page", SLOT)
            waiting = True
        IDLE_FILE.touch()
        time.sleep(10)
    IDLE_FILE.unlink(missing_ok=True)
    os.environ.update(CAMERA_NAME=cam["name"], RTSP_URL=cam["rtsp_url"], DETECT_URL=cam["detect_url"],
                      PRIMARY_CAMERA=settings.primary_camera(), CAMERA_SLOT=str(SLOT))
    log.info("camera slot %d: starting %s", SLOT, cam["name"])
    os.execv(sys.executable, [sys.executable, "recorder.py"])


if __name__ == "__main__":
    main()
