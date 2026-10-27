import os, subprocess, sys, tempfile
from pathlib import Path
import cv2, numpy as np

tmp = Path(tempfile.mkdtemp())
os.environ["DATA_DIR"] = str(tmp)
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
import share  # noqa: E402

# a 2 s, 1920x1080 test clip with fine texture everywhere (so pixelation is measurable)
src = tmp / "clip.mp4"
rng = np.random.default_rng(0)
vw = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 15, (1920, 1080))
base = rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
for i in range(30):
    vw.write(np.roll(base, i * 4, axis=1))
vw.release()

S = 1920 / 1280                  # detections are reported at full resolution, checked at 1280 output
PERSON, KNOWN_PERSON = (750, 300, 180, 450), (1350, 300, 180, 450)          # full-res person boxes
FACE = (500, 200, 120, 100)      # the stranger's head area in 1280-wide output coordinates
KNOWN_FACE = (900, 200, 120, 100)
PLATE = (300, 500, 160, 50)
PLATE_FULL = tuple(int(v * 1.5) for v in PLATE)


class F:
    def __init__(self, box, emb): self.box, self.emb = box, emb


class Faces:   # called with a head crop; the known person's crop is the one 180 px wide at x=1350 -> we mark by width parity
    calls = []
    def faces(self, img, min_size=0, max_width=0):
        Faces.calls.append(img.shape)
        return [F((0, 0, 20, 20), np.ones(128, np.float32) if Faces.known_next.pop(0) else np.zeros(128, np.float32))]
    known_next = []


class People:
    def detect(self, frame):
        Faces.known_next += [False, True]   # first person is a stranger, second is known
        return [("person", 0.9, PERSON), ("person", 0.9, KNOWN_PERSON)]


class Known:
    def refresh(self): pass
    def match(self, emb): return ("Alex", 0.9) if emb[0] == 1 else ("Alex", 0.1)


class Box:
    def __init__(self, x, y, w, h): self.x1, self.y1, self.x2, self.y2 = x, y, x + w, y + h


class R:
    def __init__(self, b): self.bounding_box = Box(*b)


class Plates:
    def predict(self, img): return [R(PLATE_FULL)]


share._models.update(faces=Faces(), known=Known(), plates=Plates(), people=People())


def detail(img, box):
    x, y, w, h = box
    region = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(np.diff(region, axis=1)).mean())   # fine detail; pixelation flattens it


for mode, want_known_blurred in (("strangers", False), ("all", True)):
    out = tmp / f"out-{mode}.mp4"
    n = share.render(src, out, faces_mode=mode, plates=True)
    cap = cv2.VideoCapture(str(out)); cap.set(cv2.CAP_PROP_POS_FRAMES, 15); ok, frame = cap.read()
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); size = (int(cap.get(3)), int(cap.get(4))); cap.release()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.split()
    head = (int(PERSON[0] / S) + 10, int(PERSON[1] / S) + 10, 90, 70)            # inside the stranger's head area
    known_head = (int(KNOWN_PERSON[0] / S) + 10, int(KNOWN_PERSON[1] / S) + 10, 90, 70)
    body = (int(PERSON[0] / S) + 10, int(PERSON[1] / S) + 200, 90, 60)           # lower body: not blurred
    face, known, plate, other = (detail(frame, b) for b in (head, known_head, (310, 510, 140, 30), (1000, 600, 150, 100)))
    print(f"      body detail {detail(frame, body):.1f} (should stay sharp)")
    checks = [
        (f"[{mode}] output 1280x720, {frames} frames, video only", size == (1280, 720) and frames == 30 and probe == ["video"]),
        (f"[{mode}] stranger face pixelated (detail {face:.1f} vs {other:.1f} elsewhere)", face < other * 0.35),
        (f"[{mode}] plate pixelated (detail {plate:.1f})", plate < other * 0.35),
        (f"[{mode}] known face {'pixelated' if want_known_blurred else 'kept'} (detail {known:.1f})", (known < other * 0.35) == want_known_blurred),
    ]
    for text, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {text}")
