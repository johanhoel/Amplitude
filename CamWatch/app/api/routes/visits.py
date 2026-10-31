"""Presence log API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os
import json
from pathlib import Path
from datetime import datetime

from api.models import VisitResponse, VisitListResponse
from api.utils import load_json, REC_DIR, DATA_DIR

router = APIRouter()


@router.get("/visits", response_model=VisitListResponse)
async def list_visits(
    day: Optional[str] = Query(None),
    person: Optional[str] = Query(None),
    camera: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    sightings_file = DATA_DIR / "sightings.jsonl"
    all_visits = []

    if sightings_file.exists():
        lines = sightings_file.read_text().strip().split("\n")
        for line in lines:
            if not line.strip(): continue
            try:
                visit = json.loads(line)
                stem = visit.get("stem", "")
                visit_day = visit.get("day") or _extract_day(stem)
                if not visit_day: continue
                all_visits.append({
                    "id": len(all_visits) + 1, "camera": visit.get("camera", ""),
                    "day": visit_day, "stem": stem,
                    "started_at": visit.get("start", ""), "ended_at": visit.get("end"),
                    "duration_s": visit.get("duration_s"), "direction": visit.get("direction"),
                    "who": _build_who(visit), "visitors": _extract_visitors(visit),
                    "clip_deleted": False,
                })
            except json.JSONDecodeError: continue

    filtered = all_visits
    if day: filtered = [v for v in filtered if v["day"] == day]
    if person:
        pl = person.lower()
        filtered = [v for v in filtered if pl in v["who"].lower()]
    if camera: filtered = [v for v in filtered if v["camera"] == camera]
    if kind: filtered = [v for v in filtered if any(vis["kind"] == kind for vis in v.get("visitors", []))]
    if direction: filtered = [v for v in filtered if direction in (v.get("direction") or "")]
    if from_date: filtered = [v for v in filtered if v["day"] >= from_date]
    if to_date: filtered = [v for v in filtered if v["day"] <= to_date]

    filtered.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    return VisitListResponse(visits=filtered[start:end], total=total, page=page, per_page=per_page)


@router.get("/visits/weekly")
async def get_weekly_report(week: Optional[str] = Query(None)):
    sightings_file = DATA_DIR / "sightings.jsonl"
    if not sightings_file.exists():
        return {"visits_per_day": {}, "visits_per_hour": {}, "people_count": 0, "packages": [], "animals": []}

    lines = sightings_file.read_text().strip().split("\n")
    visits_data = []
    for line in lines:
        if not line.strip(): continue
        try: visits_data.append(json.loads(line))
        except json.JSONDecodeError: continue

    vpd, vph, people_set, packages, animals = {}, {}, set(), [], []
    for v in visits_data:
        day = v.get("day", "")
        start = v.get("start", "")
        if day: vpd[day] = vpd.get(day, 0) + 1
        if start and len(start) >= 16: vph[start[11:13]] = vph.get(start[11:13], 0) + 1
        for face in v.get("known", []):
            name = face.get("name")
            if name: people_set.add(name)

    return {"visits_per_day": vpd, "visits_per_hour": vph, "people_count": len(people_set), "packages": packages, "animals": animals}


def _extract_day(stem):
    import re
    match = re.search(r"(\d{8})", stem)
    if match:
        try: return datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError: pass
    return None


def _build_who(visit):
    parts = []
    known = visit.get("known", [])
    if known:
        names = [f.get("name", "Unknown") for f in known if f.get("name")]
        if names: parts.append(", ".join(names))
    plates = visit.get("plates", [])
    if plates:
        ps = [p.get("name") or p.get("plate", "") for p in plates]
        ps = [n for n in ps if n]
        if ps: parts.append("Vehicle: " + ", ".join(ps))
    uc = visit.get("unknown_faces", 0) or len(visit.get("unknown", []))
    if uc > 0: parts.append(f"{uc} unknown {'person' if uc == 1 else 'people'}")
    return "; ".join(parts) if parts else "Motion detected"


def _extract_visitors(visit):
    visitors = []
    for face in visit.get("known", []):
        visitors.append({"kind": "person", "name": face.get("name"), "source": "face", "detail": None})
    for plate in visit.get("plates", []):
        name = plate.get("name") or ""
        visitors.append({"kind": "vehicle", "name": name if name else plate.get("plate"), "source": "plate", "detail": plate.get("plate")})
    labels = visit.get("labels", {})
    for label in labels:
        if label in ("dog", "cat", "bird"):
            visitors.append({"kind": "animal", "name": None, "source": "detection", "detail": label})
    return visitors
