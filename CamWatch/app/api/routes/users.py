"""User management API endpoints."""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional

from api.models import UserCreate, UserResponse, LoginRequest
from api.auth import get_users_db, save_users_db, hash_password, verify_password, create_jwt_token, decode_jwt_token

router = APIRouter()


@router.get("", response_model=list[UserResponse])
async def list_users(authorization: Optional[str] = Header(None)):
    if not _require_admin(authorization): raise HTTPException(401, "Admin access required")
    users_db = get_users_db()
    return [UserResponse(id=u, username=u, role=i.get("role", "viewer"), created_at=i.get("created_at", "")) for u, i in users_db.items()]


@router.post("", status_code=201)
async def create_user(user: UserCreate, authorization: Optional[str] = Header(None)):
    if not _require_admin(authorization): raise HTTPException(401, "Admin access required")
    if user.role not in ("admin", "operator", "viewer"): raise HTTPException(400, "Invalid role")
    users_db = get_users_db()
    if user.username in users_db: raise HTTPException(409, f"User '{user.username}' exists")
    salt, hashed = hash_password(user.password)
    from datetime import datetime, timezone
    users_db[user.username] = {"salt": salt, "hash": hashed, "role": user.role, "created_at": datetime.now(timezone.utc).isoformat()}
    save_users_db(users_db)
    return UserResponse(id=user.username, username=user.username, role=user.role, created_at=users_db[user.username]["created_at"])


@router.delete("/{username}")
async def delete_user(username: str, authorization: Optional[str] = Header(None)):
    if not _require_admin(authorization): raise HTTPException(401, "Admin access required")
    users_db = get_users_db()
    if username not in users_db: raise HTTPException(404, f"User '{username}' not found")
    admins = [u for u, info in users_db.items() if info.get("role") == "admin"]
    if len(admins) <= 1 and username in admins: raise HTTPException(409, "Cannot delete last admin")
    del users_db[username]
    save_users_db(users_db)
    return {"deleted": username}


@router.post("/login")
async def login(request: LoginRequest):
    users_db = get_users_db()
    if request.username not in users_db: raise HTTPException(401, "Invalid credentials")
    user_info = users_db[request.username]
    if not verify_password(request.password, user_info["salt"], user_info["hash"]): raise HTTPException(401, "Invalid credentials")
    token = create_jwt_token(request.username, user_info.get("role", "viewer"))
    return {"token": token, "username": request.username, "role": user_info.get("role", "viewer")}


def _require_admin(auth: Optional[str]) -> bool:
    if not auth: return False
    payload = decode_jwt_token(auth.replace("Bearer ", ""))
    return bool(payload and payload.get("role") == "admin")
