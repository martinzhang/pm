"""
Projects Blueprint -- projects CRUD & project files
"""
import os, uuid, json, copy
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, render_template, send_from_directory
from werkzeug.utils import secure_filename
from models import get_db
from auth import (
    get_project_access, parse_visible_usernames,
    load_org, load_users_map, enrich_org_usernames,
)
from config import UPLOAD_DIR, ALLOWED_EXT, GATEWAY_USERS_FILE

bp = Blueprint("projects", __name__)


# ── Page ──
@bp.route("/")
def index():
    from flask import current_app
    resp = current_app.make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ── Me ──
@bp.route("/api/me")
def api_me():
    return jsonify(g.user)


# ── Users ──
@bp.route("/api/users")
def api_users():
    try:
        with open(GATEWAY_USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = [
            {"id": u["id"], "username": u["username"], "display_name": u["name"], "role": u["role"]}
            for u in data.get("users", [])
            if u.get("enabled", True)
        ]
        users.sort(key=lambda u: u["display_name"])
        return jsonify(users)
    except Exception:
        conn = get_db()
        rows = conn.execute("SELECT id,username,display_name,role FROM users ORDER BY display_name").fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])


# ── Org ──
@bp.route("/api/org")
def api_org():
    org = load_org()
    if not org:
        return jsonify({"error": "无法加载组织架构"}), 500
    enriched = copy.deepcopy(org)
    enrich_org_usernames(enriched, load_users_map())
    return jsonify(enriched)


# ── Projects CRUD ──
@bp.route("/api/projects", methods=["GET"])
def api_list_projects():
    status = request.args.get("status", "")
    conn = get_db()
    uid = g.user["id"]
    is_admin = g.user["role"] == "admin"
    conditions = []
    args = []
    if status:
        conditions.append("status=?")
        args.append(status)
    if not is_admin:
        conditions.append("(owner_id=? OR id IN (SELECT DISTINCT project_id FROM tasks WHERE assignee_id=?) OR (visible_to IS NOT NULL AND visible_to != ''))")
        args.extend([uid, uid])
    q = "SELECT * FROM projects"
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY updated_at DESC"
    rows = conn.execute(q, args).fetchall()
    projects = []
    for r in rows:
        p = dict(r)
        if not is_admin and p["owner_id"] != uid:
            has_task = conn.execute(
                "SELECT 1 FROM tasks WHERE project_id=? AND assignee_id=? LIMIT 1", (p["id"], uid)
            ).fetchone()
            if not has_task:
                visible_usernames = parse_visible_usernames(p.get("visible_to"))
                if visible_usernames is not None and g.user["username"] not in visible_usernames:
                    continue
        s = conn.execute(
            "SELECT COUNT(*) as total,SUM(CASE WHEN progress=100 THEN 1 ELSE 0 END) as done,"
            "COALESCE(AVG(progress),0) as avg FROM tasks WHERE project_id=?", (p["id"],)
        ).fetchone()
        p["task_total"] = s["total"]
        p["task_done"] = s["done"] or 0
        p["avg_progress"] = round(s["avg"])
        try:
            p["visible_to"] = json.loads(p["visible_to"]) if p.get("visible_to") else []
        except (json.JSONDecodeError, TypeError):
            p["visible_to"] = []
        projects.append(p)
    conn.close()
    return jsonify(projects)


@bp.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "项目名称不能为空"}), 400
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    visible_to_val = data.get("visible_to", [])
    visible_to_str = json.dumps(visible_to_val) if visible_to_val else ""
    cur = conn.execute(
        "INSERT INTO projects (name,description,status,color,owner_id,owner_name,start_date,deadline,visible_to,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (name, data.get("description", ""), "active", data.get("color", "#95A3B3"),
         g.user["id"], g.user["name"], data.get("start_date", now[:10]), data.get("deadline", ""), visible_to_str, now, now),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return jsonify({"success": True, "id": pid})


@bp.route("/api/projects/<int:pid>", methods=["GET"])
def api_get_project(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "项目不存在"}), 404
    if not get_project_access(conn, pid, g.user):
        conn.close()
        return jsonify({"error": "无权访问此项目"}), 403
    p = dict(row)
    tasks = conn.execute(
        "SELECT t.*,"
        "(SELECT COUNT(*) FROM comments WHERE task_id=t.id) as comment_count,"
        "(SELECT COUNT(*) FROM task_files WHERE task_id=t.id) as file_count "
        "FROM tasks t WHERE t.project_id=? ORDER BY COALESCE(t.start_date,'9999-12-31'), t.sort_order, t.id", (pid,)
    ).fetchall()
    p["tasks"] = [dict(t) for t in tasks]
    s = conn.execute(
        "SELECT COUNT(*) as total,SUM(CASE WHEN progress=100 THEN 1 ELSE 0 END) as done,"
        "COALESCE(AVG(progress),0) as avg FROM tasks WHERE project_id=?", (pid,)
    ).fetchone()
    p["task_total"] = s["total"]
    p["task_done"] = s["done"] or 0
    p["avg_progress"] = round(s["avg"])
    p["files"] = [dict(f) for f in conn.execute(
        "SELECT * FROM project_files WHERE project_id=? ORDER BY created_at DESC", (pid,)
    ).fetchall()]
    try:
        p["visible_to"] = json.loads(p["visible_to"]) if p.get("visible_to") else []
    except (json.JSONDecodeError, TypeError):
        p["visible_to"] = []
    conn.close()
    return jsonify(p)


@bp.route("/api/projects/<int:pid>", methods=["PUT"])
def api_update_project(pid):
    data = request.get_json(force=True)
    conn = get_db()
    if get_project_access(conn, pid, g.user) != "owner":
        conn.close()
        return jsonify({"error": "只有项目负责人或管理员可以修改项目"}), 403
    fields, vals = [], []
    for k in ("name", "description", "status", "color", "start_date", "deadline"):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if "visible_to" in data:
        fields.append("visible_to=?")
        vt = data["visible_to"]
        vals.append(json.dumps(vt) if vt else "")
    if not fields:
        conn.close()
        return jsonify({"error": "无更新"}), 400
    fields.append("updated_at=?")
    vals.append(datetime.now(timezone.utc).isoformat())
    vals.append(pid)
    conn.execute(f"UPDATE projects SET {','.join(fields)} WHERE id=?", vals)
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/projects/<int:pid>", methods=["DELETE"])
def api_delete_project(pid):
    conn = get_db()
    if get_project_access(conn, pid, g.user) != "owner":
        conn.close()
        return jsonify({"error": "只有项目负责人或管理员可以删除项目"}), 403
    task_ids = [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE project_id=?", (pid,)).fetchall()]
    for tid in task_ids:
        conn.execute("DELETE FROM subtasks WHERE task_id=?", (tid,))
        conn.execute("DELETE FROM comments WHERE task_id=?", (tid,))
        conn.execute("DELETE FROM task_files WHERE task_id=?", (tid,))
    conn.execute("DELETE FROM tasks WHERE project_id=?", (pid,))
    pfiles = conn.execute("SELECT filename FROM project_files WHERE project_id=?", (pid,)).fetchall()
    pfile_dir = os.path.join(UPLOAD_DIR, f"project_{pid}")
    for pf in pfiles:
        fp = os.path.join(pfile_dir, pf["filename"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass
    conn.execute("DELETE FROM project_files WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM calendar_events WHERE related_project_id=?", (pid,))
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Project Files ──
@bp.route("/api/projects/<int:pid>/files", methods=["POST"])
def api_upload_project_file(pid):
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"不支持的文件类型: {ext}"}), 400
    conn = get_db()
    if not get_project_access(conn, pid, g.user):
        conn.close()
        return jsonify({"error": "无权访问此项目"}), 403
    proj_dir = os.path.join(UPLOAD_DIR, f"project_{pid}")
    os.makedirs(proj_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}"
    filepath = os.path.join(proj_dir, safe_name)
    f.save(filepath)
    file_size = os.path.getsize(filepath)
    conn.execute(
        "INSERT INTO project_files (project_id,filename,original_name,file_size,uploaded_by,uploaded_by_name,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (pid, safe_name, f.filename, file_size, g.user["id"], g.user["name"], datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/project-uploads/<int:pid>/<filename>")
def api_serve_project_file(pid, filename):
    conn = get_db()
    if not get_project_access(conn, pid, g.user):
        conn.close()
        return jsonify({"error": "无权访问"}), 403
    row = conn.execute(
        "SELECT original_name FROM project_files WHERE project_id=? AND filename=?", (pid, filename)
    ).fetchone()
    conn.close()
    dl_name = row["original_name"] if row else filename
    return send_from_directory(
        os.path.join(UPLOAD_DIR, f"project_{pid}"), filename,
        download_name=dl_name,
    )


@bp.route("/api/project-files/<int:fid>", methods=["DELETE"])
def api_delete_project_file(fid):
    conn = get_db()
    row = conn.execute("SELECT * FROM project_files WHERE id=?", (fid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "文件不存在"}), 404
    if not get_project_access(conn, row["project_id"], g.user):
        conn.close()
        return jsonify({"error": "无权访问"}), 403
    fp = os.path.join(UPLOAD_DIR, f"project_{row['project_id']}", row["filename"])
    if os.path.exists(fp):
        try:
            os.remove(fp)
        except Exception:
            pass
    conn.execute("DELETE FROM project_files WHERE id=?", (fid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
