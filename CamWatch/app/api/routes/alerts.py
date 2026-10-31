"""Alert rules API endpoints."""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
import json
import uuid
from pathlib import Path
import os

from api.models import AlertRuleCreate, AlertRuleResponse
from api.utils import load_json, save_json, DATA_DIR
from api.auth import decode_jwt_token

router = APIRouter()


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_rules(authorization: Optional[str] = Header(None)):
    if not _require_operator(authorization): raise HTTPException(401, "Operator+ required")
    rules = load_json(DATA_DIR / "alert_rules.json", [])
    return [AlertRuleResponse(id=r.get("id",""), name=r.get("name",""), enabled=r.get("enabled",True), conditions=r.get("conditions",{}), actions=r.get("actions",{}), cooldown_seconds=r.get("cooldown_seconds",300)) for r in rules]


@router.post("/rules", status_code=201)
async def create_rule(rule: AlertRuleCreate, authorization: Optional[str] = Header(None)):
    if not _require_operator(authorization): raise HTTPException(401, "Operator+ required")
    rules = load_json(DATA_DIR / "alert_rules.json", [])
    new = {"id": str(uuid.uuid4())[:8], "name": rule.name, "enabled": rule.enabled, "conditions": rule.conditions, "actions": rule.actions, "cooldown_seconds": rule.cooldown_seconds}
    rules.append(new)
    save_json(DATA_DIR / "alert_rules.json", rules)
    return AlertRuleResponse(**new)


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, rule: AlertRuleCreate, authorization: Optional[str] = Header(None)):
    if not _require_operator(authorization): raise HTTPException(401, "Operator+ required")
    rules = load_json(DATA_DIR / "alert_rules.json", [])
    for i, r in enumerate(rules):
        if r.get("id") == rule_id:
            rules[i].update({"name": rule.name, "enabled": rule.enabled, "conditions": rule.conditions, "actions": rule.actions, "cooldown_seconds": rule.cooldown_seconds})
            save_json(DATA_DIR / "alert_rules.json", rules)
            return AlertRuleResponse(id=rule_id, name=rules[i]["name"], enabled=rules[i]["enabled"], conditions=rules[i]["conditions"], actions=rules[i]["actions"], cooldown_seconds=rules[i].get("cooldown_seconds", 300))
    raise HTTPException(404, f"Rule '{rule_id}' not found")


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, authorization: Optional[str] = Header(None)):
    if not _require_operator(authorization): raise HTTPException(401, "Operator+ required")
    rules = load_json(DATA_DIR / "alert_rules.json", [])
    original = len(rules)
    rules = [r for r in rules if r.get("id") != rule_id]
    if len(rules) == original: raise HTTPException(404, f"Rule '{rule_id}' not found")
    save_json(DATA_DIR / "alert_rules.json", rules)
    return {"deleted": rule_id}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, authorization: Optional[str] = Header(None)):
    if not _require_operator(authorization): raise HTTPException(401, "Operator+ required")
    rules = load_json(DATA_DIR / "alert_rules.json", [])
    for r in rules:
        if r.get("id") == rule_id:
            r["enabled"] = not r.get("enabled", True)
            save_json(DATA_DIR / "alert_rules.json", rules)
            return {"enabled": r["enabled"], "id": rule_id}
    raise HTTPException(404, f"Rule '{rule_id}' not found")


def _require_operator(auth: Optional[str]) -> bool:
    if not auth: return False
    payload = decode_jwt_token(auth.replace("Bearer ", ""))
    return bool(payload and payload.get("role") in ("admin", "operator"))
