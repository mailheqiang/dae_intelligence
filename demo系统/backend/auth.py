"""登录 / 会话 / 用户文件。用户存 data/users.json：{"用户名": {"password_sha256": "...", "role": "admin|user"}}"""
import json, os, hashlib, secrets, time

DATA = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
USERS = os.path.join(DATA, "users.json")
_sessions = {}   # token -> {"user":..., "role":..., "ts":...}
TTL = 12 * 3600

def _h(pw): return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def load_users():
    if not os.path.exists(USERS):
        os.makedirs(DATA, exist_ok=True)
        save_users({"heqiang": {"password_sha256": _h(os.environ.get("DAE_ADMIN_PASSWORD", "heqiang123")), "role": "admin"}})
    return json.load(open(USERS, encoding="utf-8"))

def save_users(users):
    os.makedirs(DATA, exist_ok=True)
    json.dump(users, open(USERS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def login(username, password):
    u = load_users().get(username)
    if not u or u.get("password_sha256") != _h(password or ""): return None
    tok = secrets.token_hex(24)
    _sessions[tok] = {"user": username, "role": u.get("role", "user"), "ts": time.time()}
    return tok

def logout(tok): _sessions.pop(tok, None)

def session(tok):
    s = _sessions.get(tok)
    if not s: return None
    if time.time() - s["ts"] > TTL: _sessions.pop(tok, None); return None
    s["ts"] = time.time()
    return s

def list_users():
    return [{"username": k, "role": v.get("role", "user")} for k, v in load_users().items()]

def upsert_user(username, password=None, role=None):
    users = load_users(); u = users.get(username, {"password_sha256": _h("123456"), "role": "user"})
    if password: u["password_sha256"] = _h(password)
    if role: u["role"] = role
    users[username] = u; save_users(users)

def delete_user(username):
    users = load_users()
    if username in users and len(users) > 1:
        users.pop(username); save_users(users); return True
    return False
