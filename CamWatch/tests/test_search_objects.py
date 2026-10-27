import os, logging, runpy
os.environ.setdefault("SEARCH_MODEL_DIR", str(__import__("pathlib").Path(__file__).resolve().parent / ".cache" / "fastembed"))
ns = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("test_webui.py")))
import numpy as np, search
log = logging.getLogger("t")
class FakeDetector:          # two objects per frame, like a person and a dog
    def detect(self, frame):
        h, w = frame.shape[:2]
        return [("person", 0.9, (w // 4, h // 4, w // 5, h // 2)), ("dog", 0.8, (w // 2, h // 2, w // 8, h // 8))]
search._detector = FakeDetector()
# start from a version-1 index (whole frames only), as on the server today
search.OBJECTS = 0
search.VERSION = 1
search.index_new(log)
v1 = sum(len(v) for v in search.load_index().values())
search.OBJECTS, search.VERSION = 4, 2
n, total = search.index_new(log)
idx, ver = search.load_index(with_versions=True)
v2 = sum(len(v) for v in idx.values())
print(f"{'PASS' if v2 == v1 * 3 and set(ver.values()) == {2} else 'FAIL'}  upgrade to v2: {v1} vectors -> {v2} (frames + 2 objects each), versions {set(ver.values())}")
n2, _ = search.index_new(log)
print(f"{'PASS' if n2 == 0 else 'FAIL'}  next pass has nothing to redo ({n2})")
print(f"{'PASS' if len(search.search('a dog')) == 12 else 'FAIL'}  search still returns every clip")
