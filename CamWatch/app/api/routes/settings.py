"""Settings API endpoints."""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import os
import json
import re
import base64
import urllib.request
from datetime import datetime

from api.models import SettingsResponse, SettingsUpdate
from api.utils import load_json, save_json, DATA_DIR, get_cameras

router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    raw = load_json(DATA_DIR / "settings.json", {})
    ntfy_raw = {k: os.environ.get(f"NTFY_{k.upper()}", "") for k in ["url", "topic", "status_topic", "token", "user", "password"]}
    ntfy_raw["priority"] = os.environ.get("NTFY_PRIORITY", "high")
    integration_raw = {"mqtt_host": os.environ.get("MQTT_HOST", ""), "mqtt_port": int(os.environ.get("MQTT_PORT", 1883)),
                       "mqtt_user": os.environ.get("MQTT_USER", ""), "mqtt_password": os.environ.get("MQTT_PASSWORD", ""),
                       "ha_webhook_url": os.environ.get("HA_WEBHOOK_URL", "")}
    lan_no_auth = os.environ.get("LAN_NO_AUTH", "").lower() in ("1", "true")
    tn_raw = os.environ.get("LAN_NETWORKS", "")
    trusted = [{"net": n.strip(), "label": n.strip()} for n in tn_raw.split(";") if n.strip()]
    return SettingsResponse(
        mode=raw.get("mode", "armed"), schedule=raw.get("schedule", "22:00-07:00"),
        loiter_seconds=raw.get("loiter_seconds", 30), zones=raw.get("zones", []),
        plates=raw.get("plates", []), lan_no_auth=lan_no_auth, trusted_networks=trusted,
        ntfy=ntfy_raw, integration=integration_raw)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdate):
    raw = load_json(DATA_DIR / "settings.json", {})
    if update.mode is not None:
        if update.mode not in ("armed", "disarmed", "schedule"): raise HTTPException(400, "Mode must be armed/disarmed/schedule")
        raw["mode"] = update.mode
    if update.schedule is not None: raw["schedule"] = update.schedule
    if update.loiter_seconds is not None: raw["loiter_seconds"] = max(0, min(3600, update.loiter_seconds))
    if update.zones is not None: raw["zones"] = update.zones
    if update.plates is not None: raw["plates"] = update.plates
    save_json(DATA_DIR / "settings.json", raw)
    return await get_settings()


@router.post("/settings/arm")
async def arm():
    raw = load_json(DATA_DIR / "settings.json", {})
    raw["mode"] = "armed"
    save_json(DATA_DIR / "settings.json", raw)
    return {"mode": "armed"}


@router.post("/settings/disarm")
async def disarm():
    raw = load_json(DATA_DIR / "settings.json", {})
    raw["mode"] = "disarmed"
    save_json(DATA_DIR / "settings.json", raw)
    return {"mode": "disarmed"}


@router.post("/ntfy/test")
async def test_ntfy(body: dict):
    url = body.get("url", os.environ.get("NTFY_URL", ""))
    topic = body.get("topic", os.environ.get("NTFY_TOPIC", ""))
    token = body.get("token", "")
    user = body.get("user", "")
    password = body.get("password", "")
    if not url or not topic: raise HTTPException(400, "URL and topic required")
    try:
        data = f"CamWatch test notification".encode()
        req = urllib.request.Request(f"{url}/{topic}", data=data, headers={"Content-Type": "text/plain; charset=utf-8"}, method="PUT")
        if token: req.add_header("Authorization", f"Bearer {token}")
        elif user and password: req.add_header("Authorization", f"Basic {base64.b64encode(f'{user}:{password}'.encode()).decode()}")
        with urllib.request.urlopen(req, timeout=10) as resp: return {"success": True, "status": resp.status}
    except Exception as e: raise HTTPException(502, detail=f"Failed: {str(e)}")


@router.post("/settings/export")
async def export_settings():
    raw = load_json(DATA_DIR / "settings.json", {})
    return {"version": "2.0", "exported_at": datetime.now().isoformat(), "settings": raw, "cameras": get_cameras()}


@router.post("/settings/import")
async def import_settings(body: dict):
    data = body.get("data", {})
    if "settings" in data: save_json(DATA_DIR / "settings.json", data["settings"])
    return {"imported": True}
