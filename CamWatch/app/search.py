"""Search recordings by description ("white van", "person with a dog", "red jacket", "someone at night") with CLIP
(ViT-B/32, ONNX via fastembed, on the CPU).

Indexing (facematch's loop calls index_new()): each finished clip gets image embeddings of SEARCH_FRAMES frames (its
snapshot plus frames from inside the video) and of every person, vehicle and animal the object model finds in them
(up to SEARCH_OBJECTS per frame, cropped with a margin). Whole frames find scenes ("car at night"); the crops find
details that are small in a wide camera view ("dog", "red jacket", "someone carrying a box"). Stored in
/data/search_index.npz with an index version per clip, so clips indexed by an older version are redone in the
background. Searching (web UI): the query is embedded as "a photo of <query>" and a clip scores as its best frame
or object. CLIP similarities are small numbers (about 0.2 to 0.35); only the order matters.
"""
import json
import re
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import accel
from common import env

REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
DATA_DIR = Path(env("DATA_DIR", "/data"))
MODEL_DIR = env("SEARCH_MODEL_DIR", "/models/fastembed")
IMAGE_MODEL = "Qdrant/clip-ViT-B-32-vision"
TEXT_MODEL = "Qdrant/clip-ViT-B-32-text"
FRAMES = env("SEARCH_FRAMES", 3, int)
BATCH = env("SEARCH_BATCH", 30, int)          # clips indexed per pass (keeps facematch responsive)
INDEX = DATA_DIR / "search_index.npz"
VERSION = 2                                    # 1 = whole frames only, 2 = frames + object crops
OBJECTS = env("SEARCH_OBJECTS", 4, int)
OBJECT_CLASSES = ["person", "car", "truck", "bus", "motorcycle", "bicycle", "dog", "cat", "bird", "horse"]
OBJECT_MODEL = env("OBJECT_MODEL", "/models/yolov8s-coco.onnx")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SIDECAR_RE = re.compile(r"\.(faces|labels|track)\.json$")
_text_model = None
_image_model = None
_detector = None
_text_lock = threading.Lock()


def load_index(with_versions=False):
    """{"day/stem": array (images, 512)}; with_versions=True also returns {"day/stem": index version}."""
    try:
        with np.load(INDEX, allow_pickle=False) as z:
            keys, vecs, owner = list(z["keys"]), z["vecs"].astype(np.float32), z["owner"]
            versions = list(z["version"]) if "version" in z.files else [1] * len(keys)
    except (FileNotFoundError, ValueError, KeyError, OSError):
        return ({}, {}) if with_versions else {}
    index = {k: vecs[owner == i] for i, k in enumerate(keys)}
    return (index, {k: int(v) for k, v in zip(keys, versions)}) if with_versions else index


def save_index(index, versions):
    keys = sorted(index)
    vecs = np.concatenate([index[k] for k in keys]) if keys else np.zeros((0, 512), np.float16)
    owner = np.concatenate([np.full(len(index[k]), i, np.int32) for i, k in enumerate(keys)]) if keys else np.zeros(0, np.int32)
    tmp = INDEX.with_name("search_index.tmp.npz")
    np.savez(tmp, keys=np.array(keys), vecs=vecs.astype(np.float16), owner=owner,
             version=np.array([versions.get(k, 1) for k in keys], np.int16))
    tmp.replace(INDEX)


def object_crops(frame):
    """Crops (BGR) of the largest people / vehicles / animals in a frame, with a margin around each."""
    global _detector
    if OBJECTS <= 0:
        return []
    if _detector is None:
        from objects import ObjectDetector
        _detector = ObjectDetector(OBJECT_MODEL, OBJECT_CLASSES, 0.4, part="search objects")
    h, w = frame.shape[:2]
    found = sorted(_detector.detect(frame), key=lambda d: -d[2][2] * d[2][3])
    crops = []
    for _, _, (x, y, bw, bh) in found:
        if bw * bh < 0.003 * w * h or min(bw, bh) < 32:
            continue
        mx, my = int(bw * 0.15), int(bh * 0.15)
        crops.append(frame[max(0, y - my):min(h, y + bh + my), max(0, x - mx):min(w, x + bw + mx)])
        if len(crops) == OBJECTS:
            break
    return crops


def clip_frames(folder, stem, meta):
    """RGB images to index: the snapshot and evenly spaced frames from the video, plus the objects found in them."""
    from PIL import Image
    frames = []
    snap = cv2.imread(str(folder / f"{stem}.jpg"))
    if snap is not None:
        frames.append(snap)
    video = folder / (meta.get("video") or f"{stem}.mp4")
    cap = cv2.VideoCapture(str(video))
    count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    for k in range(1, FRAMES):
        if count <= 0:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(count * k / FRAMES))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    images = list(frames)
    for f in frames:
        images += object_crops(f)
    out = []
    for f in images:
        h, w = f.shape[:2]
        small = cv2.resize(f, (640, round(h * 640 / w)), interpolation=cv2.INTER_AREA) if w > 640 else f
        out.append(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
    return out


def image_model():
    """The CLIP image model, on a GPU when Settings -> Image processing allows it (it indexes many frames)."""
    from fastembed import ImageEmbedding
    wanted, error = accel.providers(), ""
    for providers in (wanted, [(accel.CPU, {})]):
        try:
            model = ImageEmbedding(IMAGE_MODEL, cache_dir=MODEL_DIR, threads=2, providers=providers)
            break
        except Exception as exc:      # a GPU that the driver refuses: try again on the CPU
            if len(providers) == 1:
                raise
            error = str(exc).splitlines()[0][:300]
    accel.report("search", providers[0][0], error)
    model.providers = wanted
    return model


def index_new(log):
    """Index up to BATCH clips that aren't indexed yet; forget deleted ones. Returns (indexed now, total)."""
    global _image_model
    index, versions = load_index(with_versions=True)
    clips = {}
    for folder in (p for p in REC_DIR.iterdir() if p.is_dir() and DAY_RE.match(p.name)):
        for meta_path in folder.glob("*.json"):
            if not SIDECAR_RE.search(meta_path.name):
                clips[f"{folder.name}/{meta_path.name[:-5]}"] = meta_path
    removed = [k for k in index if k not in clips]
    for k in removed:
        del index[k]
        versions.pop(k, None)
    todo = sorted((k for k in clips if versions.get(k, 0) < VERSION), reverse=True)[:BATCH]   # newest first
    if not todo and not removed:
        return 0, len(index)
    if todo:
        if _image_model is None or _image_model.providers != accel.providers():
            _image_model = image_model()
        t0 = time.time()
        for key in todo:
            meta_path = clips[key]
            try:
                meta = json.loads(meta_path.read_text())
            except ValueError:
                continue
            versions[key] = VERSION
            if meta.get("test"):
                index[key] = np.zeros((0, 512), np.float32)   # remembered, never matches
                continue
            images = clip_frames(meta_path.parent, key.split("/")[1], meta)
            if images:
                vecs = np.array(list(_image_model.embed(images)), dtype=np.float32)
                index[key] = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
            else:
                index[key] = np.zeros((0, 512), np.float32)   # nothing readable: don't retry every pass
        log.info("search: indexed %d clips in %.0fs (%d in the index, %d still on an older version)", len(todo),
                 time.time() - t0, len(index), sum(1 for k in clips if versions.get(k, 0) < VERSION))
    save_index(index, versions)
    return len(todo), len(index)


def search(query, top=60):
    """[(day/stem, score)] best first."""
    global _text_model
    with _text_lock:
        if _text_model is None:
            from fastembed import TextEmbedding
            _text_model = TextEmbedding(TEXT_MODEL, cache_dir=MODEL_DIR, threads=2)
        q = np.array(next(iter(_text_model.embed([f"a photo of {query.strip()}"]))), dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-9
    scores = [(k, float((v @ q).max())) for k, v in load_index().items() if len(v)]
    return sorted(scores, key=lambda kv: kv[1], reverse=True)[:top]
