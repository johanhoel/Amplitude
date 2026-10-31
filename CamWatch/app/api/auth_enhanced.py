"""Enhanced authentication with JWT tokens and role-based access."""
import os, json, hashlib, secrets
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get('DATA_PATH', '/data'))
_SECRET_KEY_FILE = DATA_DIR / 'api_secret.key'


def get_secret_key():
    if _SECRET_KEY_FILE.exists():
        return _SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    _SECRET_KEY_FILE.write_text(key)
    _SECRET_KEY_FILE.chmod(0o600)
    return key


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt, hashed


def verify_password(password, salt, stored_hash):
    _, computed = hash_password(password, salt)
    return computed == stored_hash


def create_jwt_token(username, role, secret_key=None):
    if secret_key is None:
        secret_key = get_secret_key()
    import time
    header = {'alg': 'HS256', 'typ': 'JWT'}
    payload = {'sub': username, 'role': role, 'iat': int(time.time()), 'exp': int(time.time()) + 3600 * 24 * 7}
    import base64
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b'=').decode()
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    sig_input = f'{h_b64}.{p_b64}'
    signature = hashlib.sha256((sig_input + secret_key).encode()).hexdigest()
    return f'{h_b64}.{p_b64}.{signature}'


def decode_jwt_token(token, secret_key=None):
    if secret_key is None:
        secret_key = get_secret_key()
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        h_b64, p_b64, signature = parts
        sig_input = f'{h_b64}.{p_b64}'
        expected_sig = hashlib.sha256((sig_input + secret_key).encode()).hexdigest()
        if signature != expected_sig:
            return {}
        import base64
        padding = 4 - len(p_b64) % 4
        if padding != 4:
            p_b64 += '=' * padding
        payload = json.loads(base64.urlsafe_b64decode(p_b64))
        exp = payload.get('exp', 0)
        if int(datetime.now(timezone.utc).timestamp()) > exp:
            return {}
        return payload
    except Exception:
        return {}


def get_users_db():
    users_file = DATA_DIR / 'users.json'
    env_enabled = os.environ.get('MULTI_USER_ENABLED', '').lower() in ('1', 'true')
    if not env_enabled:
        return {}
    if not users_file.exists():
        salt, hashed = hash_password(os.environ.get('WEB_PASSWORD', 'camwatch'))
        users_file.write_text(json.dumps({'admin': {'salt': salt, 'hash': hashed, 'role': 'admin', 'created_at': datetime.now(timezone.utc).isoformat()}}))
    try:
        return json.loads(users_file.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_users_db(users):
    users_file = DATA_DIR / 'users.json'
    tmp = users_file.with_suffix('.tmp')
    tmp.write_text(json.dumps(users, indent=2))
    tmp.replace(users_file)


def multi_user_enabled():
    return os.environ.get('MULTI_USER_ENABLED', '').lower() in ('1', 'true')


ROLE_PERMISSIONS = {
    'admin': {'view_live','view_clips','delete_clips','star_clips','tag_faces','edit_zones','manage_cameras','manage_users','change_settings','view_reports','export_import'},
    'operator': {'view_live','view_clips','delete_clips','star_clips','tag_faces','edit_zones','change_settings','view_reports'},
    'viewer': {'view_live','view_clips','star_clips','view_reports'},
}


def check_permission(role, permission):
    return permission in ROLE_PERMISSIONS.get(role, set())
