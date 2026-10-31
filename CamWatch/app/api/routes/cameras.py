"""Camera management API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os
from pathlib import Path
import json
import subprocess

from api.models import CameraCreate, CameraUpdate, CameraResponse
from api.utils import get_cameras, save_json, load_json, mask_url, get_camera_online_status

router = APIRouter()


@router.get("/cameras", response_model=list[CameraResponse])
async def list_cameras():
    cameras = get_cameras()
    online = get_camera_online_status()
    result = []
    for cam in cameras:
        if not cam.get("enabled"):
            continue
        name = cam.get("name", "")
        result.append(CameraResponse(
            slot=cam.get("slot", 0),
            name=name,
            rtsp_url=mask_url(cam.get("rtsp_url", "")),
            detect_url=mask_url(cam.get("detect_url")) if cam.get("detect_url") else None,
            enabled=cam.get("enabled", True),
            online=online.get(name, False),
        ))
    return result


@router.post("/cameras", response_model=CameraResponse, status_code=201)
async def create_camera(camera: CameraCreate):
    cameras = get_cameras()
    existing_slots = {c.get("slot") for c in cameras}
    for slot in range(2, 5):
        if slot not in existing_slots:
            break
    else:
        raise HTTPException(status_code=409, detail="Maximum of 4 cameras reached")

    new_camera = {
        "slot": slot, "name": camera.name, "rtsp_url": camera.rtsp_url,
        "detect_url": camera.detect_url or camera.rtsp_url, "enabled": True,
    }
    settings = load_json(Path(os.environ.get("DATA_PATH", "/data")) / "settings.json", {})
    existing_cameras = settings.get("cameras", [])
    existing_cameras.append(new_camera)
    settings["cameras"] = existing_cameras
    save_json(Path(os.environ.get("DATA_PATH", "/data")) / "settings.json", settings)

    return CameraResponse(
        slot=new_camera["slot"], name=new_camera["name"],
        rtsp_url=mask_url(new_camera["rtsp_url"]),
        detect_url=mask_url(new_camera["detect_url"]), enabled=True, online=False,
    )


@router.put("/cameras/{camera_name}", response_model=CameraResponse)
async def update_camera(camera_name: str, update: CameraUpdate):
    cameras = get_cameras()
    for i, cam in enumerate(cameras):
        if cam.get("name") == camera_name:
            if update.name is not None: cameras[i]["name"] = update.name
            if update.rtsp_url is not None: cameras[i]["rtsp_url"] = update.rtsp_url
            if update.detect_url is not None: cameras[i]["detect_url"] = update.detect_url
            if update.enabled is not None: cameras[i]["enabled"] = update.enabled
            settings = load_json(Path(os.environ.get("DATA_PATH", "/data")) / "settings.json", {})
            settings["cameras"] = [c for c in cameras if c.get("slot", 0) > 1]
            save_json(Path(os.environ.get("DATA_PATH", "/data")) / "settings.json", settings)
            return CameraResponse(
                slot=cameras[i].get("slot", 0), name=cameras[i]["name"],
                rtsp_url=mask_url(cameras[i]["rtsp_url"]),
                detect_url=mask_url(cameras[i].get("detect_url")) if cameras[i].get("detect_url") else None,
                enabled=cameras[i].get("enabled", True), online=False,
            )
    raise HTTPException(status_code=404, detail=f"Camera '{camera_name}' not found")


@router.delete("/cameras/{camera_name}", status_code=204)
async def delete_camera(camera_name: str):
    cameras = get_cameras()
    if camera_name == os.environ.get("CAMERA_NAME", "camera"):
        raise HTTPException(status_code=409, detail="Primary camera (slot 1) cannot be removed")
    updated = [c for c in cameras if c.get("name") != camera_name]
    settings = load_json(Path(os.environ.get("DATA_PATH", "/data")) / "settings.json", {})
    settings["cameras"] = [c for c in updated if c.get("slot", 0) > 1]
    save_json(Path(os.environ.get("DATA_PATH", "/data")) / "settings.json", settings)
    return None


@router.post("/cameras/{camera_name}/test")
async def test_camera(camera_name: str):
    cameras = get_cameras()
    cam = next((c for c in cameras if c.get("name") == camera_name), None)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_name}' not found")
    rtsp_url = cam.get("rtsp_url", "")
    if not rtsp_url:
        raise HTTPException(status_code=400, detail="No RTSP URL configured")
    try:
        result = subprocess.run(
            ["ffmpeg", "-rtsp_transport", "tcp", "-timeout", "10000000", "-i", rtsp_url,
             "-frames:v", "1", "-f", "image2", "/tmp/camtest.jpg"],
            capture_output=True, timeout=20)
        if result.returncode != 0:
            raise HTTPException(status_code=502, detail=f"Connection failed: {result.stderr.decode()[:200]}")
        import os as _os
        frame_size = _os.path.getsize("/tmp/camtest.jpg") if _os.path.exists("/tmp/camtest.jpg") else 0
        return {"success": True, "frame_bytes": frame_size}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Connection timed out (20s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cameras/scan")
async def scan_cameras():
    try:
        from api.onvif_helper import discover_cameras
        return {"cameras": discover_cameras()}
    except ImportError:
        raise HTTPException(status_code=501, detail="ONVIF scanner not available")


@router.post("/cameras/onvif")
async def discover_onvif(subnet: str = Query("192.168.1")):
    try:
        from api.onvif_helper import discover_onvif
        return {"cameras": discover_onvif(subnet)}
    except ImportError:
        raise HTTPException(status_code=501, detail="ONVIF scanner not available")
