"""
Projects -- authentication, user loading, org helpers, access control
"""
import json, os, urllib.parse
from datetime import datetime, timezone
from flask import request, g
from models import get_db
from config import GATEWAY_USERS_FILE, GATEWAY_ORG_FILE, URL_PREFIX, PHASES, PHASE_MAP, PHASE_COLORS, PROJECT_COLORS, PRIORITIES, PROJECT_STATUS

_ENV_DEV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.dev")


def _load_env_dev():
    """Parse .env.dev and return dict of key=value pairs."""
    env = {}
    try:
        with open(_ENV_DEV, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def _dev_user_from_db(username):
    """Look up a user by username from the users table. Returns (id, username, display_name, role) or None."""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT id, username, display_name, role FROM users WHERE username=?", (username,)
        ).fetchone()
        conn.close()
        if row:
            return row["id"], row["username"], row["display_name"] or row["username"], row["role"]
    except Exception:
        pass
    return None


def load_user():
    """before_request handler: load user from nginx auth headers."""
    uid = request.headers.get("X-Auth-UserId", "")
    uname = request.headers.get("X-Auth-User", "")
    dname = urllib.parse.unquote(request.headers.get("X-Auth-Name", "") or "")
    role = request.headers.get("X-Auth-Role", "member")

    if not uid:
        # 开发模式：优先读 .env.dev 中的 DEV_USER
        dev_username = _load_env_dev().get("DEV_USER", "").strip()
        if dev_username:
            found = _dev_user_from_db(dev_username)
            if found:
                uid, uname, dname, role = found
            else:
                uid, uname, dname, role = "local", dev_username, dev_username, "member"
        else:
            uid, uname, dname, role = "local", "local", "本地用户", "admin"

    g.user = {"id": uid, "username": uname, "name": dname or uname, "role": role}
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (id,username,display_name,role,created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,role=excluded.role",
            (uid, uname, dname or uname, role, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _static_version():
    """取 static/ 下所有 css/js 的最新 mtime 作为缓存版本号。

    扫描整个目录(而非硬编码文件名)：新增静态模块(如 chat-commands.js)时无需改这里，
    改动任一 css/js 都会让 ?v= 变化、强制浏览器拉新版本，避免加载到旧缓存。
    """
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    latest = 0
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name.endswith((".js", ".css")):
                try:
                    latest = max(latest, int(os.path.getmtime(os.path.join(root, name))))
                except OSError:
                    pass
    return latest


def inject_globals():
    """context_processor: inject template globals."""
    return {
        "B": URL_PREFIX,
        "phases": PHASES,
        "phase_map": PHASE_MAP,
        "phase_colors": PHASE_COLORS,
        "project_colors": PROJECT_COLORS,
        "priorities": PRIORITIES,
        "project_status": PROJECT_STATUS,
        "static_v": _static_version(),
    }


# ── Org helpers ──
def load_org():
    try:
        with open(GATEWAY_ORG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("org")
    except Exception:
        return None


def load_users_map():
    """Return dict: userId -> username."""
    try:
        with open(GATEWAY_USERS_FILE, "r", encoding="utf-8") as f:
            return {u["id"]: u["username"] for u in json.load(f).get("users", [])}
    except Exception:
        return {}


def enrich_org_usernames(node, uid_map):
    """Add username field to every member in the org tree."""
    if not node:
        return
    for m in node.get("members", []):
        m["username"] = uid_map.get(m.get("userId"), "")
    for child in node.get("children", []):
        enrich_org_usernames(child, uid_map)


# ── Visibility helpers ──
def parse_visible_usernames(visible_to_json):
    """Parse visible_to JSON string, return set of usernames or None (all visible)."""
    if not visible_to_json:
        return None
    try:
        usernames = json.loads(visible_to_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not usernames:
        return None
    return set(usernames)


# ── Access Control ──
def get_project_access(conn, pid, user):
    """Returns 'owner', 'member', or None."""
    if user["role"] == "admin":
        return "owner"
    row = conn.execute("SELECT owner_id, visible_to FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    if row["owner_id"] == user["id"]:
        return "owner"
    has_task = conn.execute(
        "SELECT 1 FROM tasks WHERE project_id=? AND assignee_id=? LIMIT 1", (pid, user["id"])
    ).fetchone()
    if has_task:
        return "member"
    # Also allow access if user is a collaborator on any task
    is_collab = conn.execute(
        "SELECT 1 FROM tasks WHERE project_id=? AND collaborator_ids LIKE ? LIMIT 1",
        (pid, f"%{user['id']}%"),
    ).fetchone()
    if is_collab:
        return "member"
    visible_usernames = parse_visible_usernames(row["visible_to"])
    if visible_usernames is not None and user["username"] in visible_usernames:
        return "member"
    return None


def check_task_access(conn, tid, user):
    """Returns (project_id, access_level) or (None, None)."""
    t = conn.execute("SELECT project_id FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t:
        return None, None
    return t["project_id"], get_project_access(conn, t["project_id"], user)
