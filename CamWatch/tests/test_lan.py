import os, sys, tempfile, pathlib
root = pathlib.Path(tempfile.mkdtemp())
for d in ("recordings", "photos", "data", "live"): (root / d).mkdir()
os.environ.update(RECORDINGS_DIR=str(root/"recordings"), PHOTOS_DIR=str(root/"photos"), DATA_DIR=str(root/"data"),
                  LIVE_DIR=str(root/"live"), WEB_PASSWORD="secret-test", WEB_USER="admin")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app"))
import webui, settings
c = webui.app.test_client()
def get(ip, headers=None, auth=None):
    return c.get("/dashboard", environ_base={"REMOTE_ADDR": ip}, headers=headers or {}, auth=auth).status_code
cases = []
for toggle in (False, True):
    settings.update(lan_no_auth=toggle)
    cases += [(toggle, "LAN 192.168.1.50", get("192.168.1.50"), 200 if toggle else 401),
              (toggle, "LAN 10.0.0.5", get("10.0.0.5"), 200 if toggle else 401),
              (toggle, "Docker bridge 172.18.0.1", get("172.18.0.1"), 401),
              (toggle, "internet 85.1.2.3", get("85.1.2.3"), 401),
              (toggle, "via proxy (X-Forwarded-For)", get("192.168.1.230", {"X-Forwarded-For": "85.1.2.3"}), 401),
              (toggle, "internet with password", get("85.1.2.3", auth=("admin", "secret-test")), 200)]
for toggle, what, got, want in cases:
    print(f"{'PASS' if got == want else 'FAIL'}  toggle={'on ' if toggle else 'off'}  {what:<32} -> {got} (want {want})")
