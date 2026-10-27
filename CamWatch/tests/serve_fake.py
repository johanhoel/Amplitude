"""The web UI with fake recordings, two cameras and some alerts, for trying pages in a browser:
python tests/serve_fake.py  ->  http://127.0.0.1:18765  (/m for the phone page). No camera, server or database needed."""
import datetime as dt
import json
import os
import runpy
import sys
import time
from pathlib import Path

sys.argv = sys.argv[:1]
os.environ.setdefault("RTSP_URL", "rtsp://admin:example@192.0.2.10:554/stream1")
ns = runpy.run_path(str(Path(__file__).with_name("test_webui.py")))   # builds the fake data, imports webui
root, webui = ns["root"], ns["webui"]
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import settings  # noqa: E402

settings.update(cameras=[{"slot": 1}, {"slot": 2, "name": "garden", "rtsp_url": "rtsp://cam:example@192.0.2.11/stream1",
                                       "detect_url": "", "enabled": True}])
for cam, colour in (("camera1", (60, 60, 60)), ("garden", (40, 90, 40))):
    (root / "live" / cam).mkdir(exist_ok=True)
    cv2.imwrite(str(root / "live" / cam / "frame.jpg"), np.full((720, 1280, 3), colour, np.uint8))


def keep_alive():   # cameras count as online while their heartbeat is fresh
    while True:
        for cam in ("camera1", "garden"):
            (root / "live" / cam / "alive").touch()
        time.sleep(10)


import threading  # noqa: E402
threading.Thread(target=keep_alive, daemon=True).start()
day = dt.date.today().isoformat()
meta_path = root / "recordings" / day / "camera1_130000.json"
meta = json.loads(meta_path.read_text())
meta["unusual"] = "no car on camera1 between 12:00 and 14:00 on weekdays in the last 26 days"
meta_path.write_text(json.dumps(meta))
print(f"fake data in {root}\nopen http://127.0.0.1:18765  (phone page: /m)", flush=True)
from waitress import serve  # noqa: E402
serve(webui.app, host="127.0.0.1", port=18765, threads=8)
