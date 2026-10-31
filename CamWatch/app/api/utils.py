"""Shared utilities for reading CamWatch data files."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DATA_DIR = Path(os.environ.get("DATA_PATH", "/data"))
REC_DIR = Path(os.environ.get("RECORDINGS_PATH", "/recordings"))
PHOTOS_DIR = Path(os.environ.get("PHOTOS_PATH", "/photos"))


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return default if default is not None else {}


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def get_settings() -> dict:
    return load_json(DATA_DIR / "settings.json", {})


def get_cameras() -> list:
    settings = get_settings()
    cameras = settings.get("cameras", [])
    primary_name = os.environ.get("CAMERA_NAME", "camera")
    existing_slots = {c.get("slot") for c in cameras}
    if 1 not in existing_slots:
        rtsp_url = os.environ.get("RTSP_URL", "")
        detect_url = os.environ.get("DETECT_URL", "") or rtsp_url
        cameras.insert(0, {
            "slot": 1, "name": primary_name, "rtsp_url": rtsp_url,
            "detect_url": detect_url, "enabled": True,
        })
    return cameras


def get_camera_online_status() -> dict:
    live_dir = Path("/live")
    online = {}
    if live_dir.exists():
        for cam_dir in live_dir.iterdir():
            if cam_dir.is_dir():
                alive_file = cam_dir / "alive"
                if alive_file.exists():
                    mtime = alive_file.stat().st_mtime
                    if (datetime.now().timestamp() - mtime) < 60:
                        online[cam_dir.name] = True
    return online


def get_clip_metadata(day: str, stem: str) -> Optional[dict]:
    json_path = REC_DIR / day / f"{stem}.json"
    data = load_json(json_path)
    if not data:
        return None
    star_path = REC_DIR / day / f"{stem}.star"
    data["starred"] = star_path.exists()
    faces_path = REC_DIR / day / f"{stem}.faces.json"
    faces_data = load_json(faces_path)
    if faces_data and "error" not in faces_data:
        data["faces_seen"] = faces_data.get("faces_seen", 0)
        data["unknown_faces"] = len(faces_data.get("unknown", []))
    labels_path = REC_DIR / day / f"{stem}.labels.json"
    labels_data = load_json(labels_path)
    if labels_data:
        data["labels"] = labels_data
    return data


def get_clips_for_day(day: str) -> list:
    day_dir = REC_DIR / day
    if not day_dir.is_dir():
        return []
    clips = []
    for mp4 in sorted(day_dir.glob("*.mp4")):
        stem = mp4.stem
        meta = get_clip_metadata(day, stem)
        if meta:
            clips.append(meta)
    return clips


def get_all_days() -> list:
    if not REC_DIR.is_dir():
        return []
    days = []
    for item in REC_DIR.iterdir():
        if item.is_dir() and len(item.name) == 10:
            try:
                datetime.strptime(item.name, "%Y-%m-%d")
                days.append(item.name)
            except ValueError:
                pass
    return sorted(days, reverse=True)


def get_disk_usage() -> dict:
    import shutil
    total, used, free = shutil.disk_usage(str(REC_DIR.parent))
    return {
        "total": round(total / 1e9, 1),
        "used": round(used / 1e9, 1),
        "free": round(free / 1e9, 1),
        "pct_used": round(used * 100 / total) if total > 0 else 0,
    }


def get_version_info() -> dict:
    version_file = Path("/opt/camwatch/VERSION") if Path("/opt/camwatch").exists() else Path("VERSION")
    try:
        text = version_file.read_text().strip()
        return {"text": text}
    except (FileNotFoundError, OSError):
        return {}


def mask_url(url: str) -> str:
    if not url or "@" not in url:
        return url or ""
    scheme, sep, rest = url.partition("://")
    userinfo, at, host = rest.rpartition("@")
    if ":" not in userinfo:
        return url
    user, _, _ = userinfo.partition(":")
    return f"{scheme}://{user}:***@{host}"
