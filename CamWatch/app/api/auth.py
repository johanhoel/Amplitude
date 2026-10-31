"""JWT-based authentication for the API."""
import os
import json
import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_PATH", "/data"))
_SECRET_KEY_FILE = DATA_DIR / "api_secret.key"


def get_secret_key() -> str:
    if _SECRET_KEY_FILE.exists():
        return _SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    _SECRET_KEY_FILE.write_text(key)
    _SECRET_KEY_FILE.chmod(0o600)
    return key


def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt, hashed


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    _, computed = hash_password(password, salt)
    return computed == stored_hash


def create_jwt_token(username: str, role: str, secret_key: str = None) -> str:
    if secret_key is None:
        secret_key = get_secret_key()
    import time
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": username, "role": role, "iat": int(time.time()), "exp": int(time.time()) + 3600 * 24 * 7}
    import base64
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    signing_input = f"{header_b64}.{payload_b64}"
    signature = hashlib.sha256((signing_input + secret_key).encode()).hexdigest()
    return f"{header_b64}.{payload_b64}.{signature}"


def decode_jwt_token(token: str, secret_key: str = None) -> dict:
    if secret_key is None:
        secret_key = get_secret_key()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        header_b64, payload_b64, signature = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hashlib.sha256((signing_input + secret_key).encode()).hexdigest()
        if signature != expected_sig:
            return {}
        import base64
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        if int(datetime.now(timezone.utc).timestamp()) > exp:
            return {}
        return payload
    except Exception:
        return {}


def get_users_db() -> dict:
    users_file = DATA_DIR / "users.json"
    if not users_file.exists():
        salt, hashed = hash_password(os.environ.get("WEB_PASSWORD", "camwatch"))
        users_file.write_text(json.dumps({"admin": {"salt": salt, "hash": hashed, "role": "admin", "created_at": datetime.now(timezone.utc).isoformat()}}))
    return json.loads(users_file.read_text())


def save_users_db(users: dict):
    users_file = DATA_DIR / "users.json"
    tmp = users_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2))
    tmp.replace(users_file)
