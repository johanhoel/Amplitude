"""Settings -> Image processing: the GPU switch, what each model runs on, and the host helper's GPU build."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

root = Path(tempfile.mkdtemp())
for d in ("recordings", "photos", "data", "live"):
    (root / d).mkdir()
REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("OBJECT_MODEL", str(REPO / "models" / "yolov8s-coco.onnx"))
os.environ.update(RECORDINGS_DIR=str(root / "recordings"), PHOTOS_DIR=str(root / "photos"), DATA_DIR=str(root / "data"),
                  LIVE_DIR=str(root / "live"), CAMERA_NAME="camera1", WEB_PASSWORD="", DB_SOCKET=str(root / "nosock"))
sys.path.insert(0, str(REPO / "app"))
import accel  # noqa: E402
import settings  # noqa: E402
import updates  # noqa: E402
import webui  # noqa: E402
from objects import ObjectDetector  # noqa: E402

ok = True


def report(good, text):
    global ok
    ok &= bool(good)
    print(f"{'PASS' if good else 'FAIL'} {text}")


c = webui.app.test_client()

# ---------- the switch ----------
report(settings.processing() == {"gpu": False}, "the GPU is off until Settings switches it on")
report(accel.providers() == [(accel.CPU, {})], f"with the switch off, the models use the CPU: {accel.providers()}")
page = c.get("/settings").get_data(as_text=True)
report('id="processing"' in page and "Use the GPU when the server has one" in page and "No model has started yet" in page,
       "Settings shows Image processing")
r = c.post("/settings/processing", data={"gpu": "1"})
report(settings.processing() == {"gpu": True} and "saved=processing" in r.headers["Location"], "Save switches the GPU on")

real_available = accel.available
accel.available = lambda: []
accel._cache["mtime"] = None
report(accel.providers() == [(accel.CPU, {})], "switched on without a GPU, the models still use the CPU")
accel.available = lambda: ["OpenVINOExecutionProvider"]
accel._cache["mtime"] = None
report(accel.providers() == [("OpenVINOExecutionProvider", {"device_type": "GPU"}), (accel.CPU, {})],
       "switched on with a GPU, the GPU comes first and the CPU stays as the fallback")

# ---------- a model follows the switch ----------
det = ObjectDetector(os.environ["OBJECT_MODEL"], ["person"], 0.4, part="objects camera1")
det.detect(np.zeros((360, 640, 3), np.uint8))
rows = {r["part"]: r for r in accel.reports()}
report(rows.get("objects camera1", {}).get("provider") == accel.CPU,
       f"a GPU that this onnxruntime lacks falls back to the CPU and says so: {rows.get('objects camera1')}")
opts = accel.session_options(3)
report(opts.intra_op_num_threads == 3 and opts.inter_op_num_threads == 1,
       "sessions get a fixed thread count (no pthread_setaffinity_np errors in containers)")
c.post("/settings/processing", data={})
det.detect(np.zeros((360, 640, 3), np.uint8))
report(det.providers == [(accel.CPU, {})] and settings.processing() == {"gpu": False},
       "switching off reopens the model on the CPU without a restart")
accel.available = real_available
page = c.get("/settings").get_data(as_text=True)
report("objects camera1" in page and "<td>CPU" in page, "Settings lists what each part runs on")

# ---------- the GPU on the server ----------
report("update helper is not installed" in page.split('id="gpu"')[1], "without the helper, the GPU card says so")
updates.DIR.mkdir(parents=True, exist_ok=True)
updates.STATUS.write_text(json.dumps({"helper": True, "state": "done"}))


def host(**gpu):
    base = {"cards": [], "intel": False, "amd": False, "nvidia": False, "nvidia_toolkit": False, "virt": "none",
            "lxc": False, "build": ""}
    (updates.DIR / "host.json").write_text(json.dumps({"recordings": "/srv/camwatch/recordings", "disks": [],
                                                       "gpu": {**base, **gpu}}))
    return c.get("/settings").get_data(as_text=True).split('id="gpu"')[1]


def card_(vendor, render="", usable=False, driver=""):
    return {"pci": "0000:00:02.0", "vendor": vendor, "driver": driver, "render": render, "usable": usable}


# the real server: a Proxmox container on a NUC with an Intel and an AMD GPU, neither passed in
nuc = [card_("intel", "renderD129", driver="i915"), card_("amd", "renderD128", driver="amdgpu")]
card = host(cards=nuc, virt="lxc", lxc=True)
report("Proxmox host has an Intel GPU" in card and "pct set &lt;number&gt; -dev0 /dev/dri/renderD129,mode=0666" in card,
       "a Proxmox container gets the steps with the Intel GPU's own render node")
card = host(cards=[card_("intel", "renderD129", True, "i915"), nuc[1]], intel=True, amd=True, virt="lxc", lxc=True)
report("Add Intel GPU support" in card, "an Intel GPU that the container can use offers the GPU build")
card = host(cards=[card_("virtual", driver="bochs-drm")], virt="kvm")
report("virtual machine (kvm)" in card and "PCI Device" in card,
       "a virtual machine with only a virtual graphics card gets the passthrough steps")
card = host(cards=[card_("intel")], virt="kvm")
report("Intel GPU, but no driver uses it" in card, "a passed-through GPU without a driver gets the driver step")
card = host(cards=[card_("nvidia", driver="nvidia", usable=True)], nvidia=True)
report("NVIDIA Container Toolkit" in card and "Add NVIDIA" not in card, "NVIDIA without the toolkit gets the install steps")
card = host(cards=[card_("nvidia", driver="nvidia", usable=True)], nvidia=True, nvidia_toolkit=True)
report("Add NVIDIA GPU support" in card, "NVIDIA with the toolkit offers the GPU build")
card = host(cards=[card_("amd", "renderD128", True, "amdgpu")], amd=True)
report("cannot use AMD GPUs" in card, "an AMD GPU alone is not offered")
card = host()
report("found no GPU" in card, "real hardware without a GPU says so")
card = host(intel=True, build="intel")
report("Intel</b> GPU support" in card and "Remove GPU support" in card, "a GPU build can be removed")

r = c.post("/settings/processing/build", data={"kind": "intel"})
req = json.loads(updates.REQUEST.read_text())
report(req["action"] == "gpu" and req["kind"] == "intel" and r.headers["Location"].endswith("#gpu"),
       f"Add GPU support asks the host helper: {req}")
r = c.post("/settings/processing/build", data={"kind": "nvidia"})
report("error=" in r.headers["Location"], "a second request waits until the first one is done")
report("Waiting for the server to start" in c.get("/settings").get_data(as_text=True), "Settings shows the waiting build")
updates.REQUEST.unlink()
report(c.post("/settings/processing/build", data={"kind": "amd"}).status_code == 400, "an unknown GPU kind is refused")

# ---------- the host helper ----------
host_dir = root / "opt-camwatch"
host_dir.mkdir()
(host_dir / ".env").write_text(f"DATA_PATH={(root / 'data').as_posix()}\n"
                               "COMPOSE_FILE=docker-compose.yml:docker-compose.staging.yml\nTZ=x\n")
sys.argv = ["update.py", str(host_dir)]
spec = importlib.util.spec_from_file_location("helper", REPO / "extras" / "update.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
report(helper.compose_files("intel") == "docker-compose.yml:docker-compose.staging.yml:docker-compose.gpu-intel.yml",
       "the GPU file goes after the files .env has (staging keeps its own)")
helper.set_env("COMPOSE_FILE", helper.compose_files("intel"))
report(helper.compose_files("") == "docker-compose.yml:docker-compose.staging.yml", "no GPU takes the GPU file out again")
helper.set_env("COMPOSE_FILE", "docker-compose.yml:docker-compose.staging.yml")
fake_sys = root / "sys"
for dev, cls, vendor in (("pci-00-02.0", "0x038000", "0x8086"), ("pci-01-00.0", "0x030000", "0x1002"),
                         ("pci-00-1f.3", "0x040300", "0x8086")):
    d = fake_sys / "bus/pci/devices" / dev
    d.mkdir(parents=True)
    (d / "class").write_text(cls + "\n")
    (d / "vendor").write_text(vendor + "\n")
cards = helper.gpu_list(fake_sys)
report([(c["vendor"], c["usable"]) for c in cards] == [("intel", False), ("amd", False)],
       f"the scan finds the graphics cards on the PCI bus and skips the sound card: {cards}")
helper.gpus = lambda: {"cards": cards, "intel": False, "amd": False, "nvidia": False, "nvidia_toolkit": False,
                       "virt": "lxc", "lxc": True, "build": ""}
helper.compose = lambda *a, **k: (_ for _ in ()).throw(AssertionError("compose must not run"))
code = helper.set_gpu({"action": "gpu", "kind": "intel"})
st = json.loads((root / "data" / "update" / "gpu.json").read_text())
env = (host_dir / ".env").read_text()
report(code == 1 and st["state"] == "failed" and "no intel GPU" in st["message"] and "Nothing changed" in st["message"]
       and "CAMWATCH_GPU" not in env, f"without the GPU, the helper changes nothing: {st['message']}")
helper.gpus = lambda: {"cards": cards, "intel": True, "amd": False, "nvidia": False, "nvidia_toolkit": False,
                       "virt": "lxc", "lxc": True, "build": ""}
helper.docker_free_gb = lambda: 1.3      # the real server's system disk on 2026-10-29
code = helper.set_gpu({"action": "gpu", "kind": "intel"})
st = json.loads((root / "data" / "update" / "gpu.json").read_text())
report(code == 1 and "needs 6 GB free" in st["message"] and "pct resize" in st["message"]
       and "CAMWATCH_GPU" not in (host_dir / ".env").read_text(),
       f"with a nearly full disk, the helper does not start the build: {st['message']}")

print("ALL PASSED" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
