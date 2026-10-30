"""Where the image models run: on the CPU, or on a GPU when Settings -> Image processing allows it.

Every ONNX model in camwatch (objects, number plates, search) gets its providers and session options here. The face
models (OpenCV) stay on the CPU, see facematch.py. A GPU needs three things: the switch in Settings, a GPU build
(CAMWATCH_GPU=intel or nvidia in .env, see Dockerfile) and the device in the container (docker-compose.gpu-*.yml).
Without one of them the models run on the CPU, as before.

The models check providers() before each use. A change in Settings therefore takes effect without a restart.
Each part reports what it really runs on in DATA_DIR/accel/<part>.json, and Settings shows that.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path

import settings
from common import env

DIR = Path(env("DATA_DIR", "/data")) / "accel"
CPU = "CPUExecutionProvider"
# The GPU providers camwatch uses, best first, with the options that point them at the GPU
GPU = {"CUDAExecutionProvider": {}, "OpenVINOExecutionProvider": {"device_type": "GPU"}, "DmlExecutionProvider": {}}
NAMES = {"CUDAExecutionProvider": "NVIDIA GPU (CUDA)", "OpenVINOExecutionProvider": "Intel GPU (OpenVINO)",
         "DmlExecutionProvider": "GPU (DirectML)", CPU: "CPU"}
_cache = {"mtime": None, "providers": [CPU]}


def available():
    """The GPU providers this build has, best first. OpenVINO counts only when the container has a GPU device."""
    try:
        import onnxruntime as ort
        have = ort.get_available_providers()
    except ImportError:
        return []
    found = [p for p in GPU if p in have]
    if "OpenVINOExecutionProvider" in found and not any(Path("/dev/dri").glob("renderD*")):
        found.remove("OpenVINOExecutionProvider")
    return found


def providers():
    """[(name, options), ...] to hand to onnxruntime: the GPU first when Settings allows it, the CPU always last."""
    mtime = settings.mtime()
    if mtime != _cache["mtime"]:
        _cache["mtime"] = mtime
        gpu = settings.processing()["gpu"]
        _cache["providers"] = [(p, GPU[p]) for p in (available() if gpu else [])[:1]] + [(CPU, {})]
    return _cache["providers"]


def session_options(threads=2):
    """Session options with a fixed number of threads. Without one, onnxruntime pins its threads to CPU cores, and in
    a container that may only use some cores this fails with 'pthread_setaffinity_np failed ... Invalid argument'."""
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    return opts


def session(model_path, threads=2, part=None):
    """An onnxruntime session on the GPU when allowed and working, else on the CPU. Returns (session, providers)."""
    import onnxruntime as ort
    wanted = providers()
    try:
        s = ort.InferenceSession(str(model_path), session_options(threads), providers=wanted)
        error = ""
    except Exception as exc:          # a GPU that the driver refuses: the CPU still works
        if len(wanted) == 1:
            raise
        s = ort.InferenceSession(str(model_path), session_options(threads), providers=[CPU])
        print(f"accel: {part or model_path} runs on the CPU: {exc}", flush=True)
        error = clean_error(str(exc))
    if part:
        report(part, s.get_providers()[0], error)
    return s, wanted


def clean_error(text):
    """A provider's failure -> one short line a person can read.

    onnxruntime puts the whole thing on one line: a bracketed code, the C++
    file and line the provider gave up in, and the signature of the function
    it was in. The table's tooltip showed the first 300 characters of that,
    which cut mid-symbol and told nobody anything. Keep the words, drop the
    machinery, and say plainly when there are no words worth keeping.
    """
    msg = " ".join((text or "").split())
    msg = re.sub(r"^\[\w*Error\]\s*:\s*\d+\s*:\s*\w+\s*:\s*", "", msg)
    msg = re.sub(r"(?i)\bexception during initialization\s*:?\s*", "", msg)
    msg = re.sub(r"\S+\.(?:cc|cpp|cxx|h|hpp):\d+", "", msg)       # source locations
    msg = " ".join(w for w in msg.split() if "::" not in w and not w.startswith("/"))
    # What a dropped signature leaves behind: "const", "&", a stray comma.
    msg = re.sub(r"^(?:const|struct|class|enum|unsigned|void|std)\b[\s,&*]*", "", msg, flags=re.I)
    msg = msg.strip(" ,:;-&*")
    if len(re.findall(r"[A-Za-z]{3,}", msg)) < 3:                 # nothing but machinery
        return "the GPU driver refused this model"
    if len(msg) > 200:                                            # never cut mid-word
        msg = msg[:200].rsplit(" ", 1)[0] + "..."
    return msg


def report(part, provider, error=""):
    """Note what a part runs on, for Settings -> Image processing."""
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^a-z0-9-]+", "-", part.lower()).strip("-")
        data = {"part": part, "provider": provider, "name": NAMES.get(provider, provider), "error": error,
                "at": dt.datetime.now().isoformat(timespec="seconds")}
        tmp = DIR / f"{name}.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, DIR / f"{name}.json")
    except OSError:
        pass


def reports():
    """[{"part", "provider", "name", "error", "at"}] as the parts reported them, sorted by part."""
    out = []
    for f in sorted(DIR.glob("*.json")) if DIR.is_dir() else []:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return out
