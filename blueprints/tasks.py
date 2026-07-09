"""
Projects Blueprint -- tasks, subtasks, task files, comments
"""
import os, uuid
from datetime import datetime, timezone
import re
from flask import Blueprint, request, jsonify, g, send_from_directory
from werkzeug.utils import secure_filename
from models import get_db
from auth import get_project_access, check_task_access
from config import UPLOAD_DIR, ALLOWED_EXT

bp = Blueprint("tasks", __name__)


def _norm_collab_ids(val):
    """Normalize collaborator_ids input (list/str) → 'id1,id2' string."""
    if val is None:
        return None
    if isinstance(val, list):
        ids = [str(x).strip() for x in val if x]
    else:
        ids = [x.strip() for x in str(val).split(",") if x.strip()]
    # dedupe preserve order
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i); out.append(i)
    return ",".join(out)


# ── Tasks CRUD ──

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

def _norm_time(val):
    """Return HH:MM string, or None if empty/invalid."""
    if val is None:
        return None
    v = str(val).strip()
    if not v:
        return None
    if not _TIME_RE.match(v):
        return None
    h, m = v.split(":")
    try:
        hi, mi = int(h), int(m)
    except Exception:
        return None
    if not (0 <= hi <= 23 and 0 <= mi <= 59):
        return None
    return f"{hi:02d}:{mi:02d}"

@bp.route("/api/projects/<int:pid>/tasks", methods=["POST"])
def api_create_task(pid):
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "任务名称不能为空"}), 400
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]
    conn = get_db()
    if not get_project_access(conn, pid, g.user):
        conn.close()
        return jsonify({"error": "无权访问此项目"}), 403
    mx = conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM tasks WHERE project_id=?", (pid,)).fetchone()[0]
    collab_ids = _norm_collab_ids(data.get("collaborator_ids")) or ""
    st_time = _norm_time(data.get("start_time"))
    en_time = _norm_time(data.get("end_time"))
    cur = conn.execute(
        "INSERT INTO tasks (project_id,name,description,assignee_id,assignee_name,phase,priority,"
        "start_date,end_date,start_time,end_time,progress,sort_order,depends_on,collaborator_ids,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid, name, data.get("description", ""),
         data.get("assignee_id", ""), data.get("assignee_name", ""),
         data.get("phase", "concept"), data.get("priority", "medium"),
         data.get("start_date", today), data.get("end_date", today),
         st_time, en_time,
         data.get("progress", 0), mx, data.get("depends_on", ""), collab_ids, now, now),
    )
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, pid))
    tid = cur.lastrowid
    aid = data.get("assignee_id", "")
    if aid and aid != g.user["id"]:
        conn.execute(
            "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (aid, "task_assigned", "新任务分配", f"{g.user['name']} 给你分配了任务: {name}", tid, pid, now),
        )
    # Notify newly added collaborators
    for cid in [x for x in collab_ids.split(",") if x]:
        if cid == g.user["id"] or cid == aid:
            continue
        conn.execute(
            "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (cid, "task_assigned", "新增协作", f"{g.user['name']} 把你加为 \"{name}\" 的协作者", tid, pid, now),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "id": tid})


@bp.route("/api/tasks/<int:tid>", methods=["GET"])
def api_get_task(tid):
    conn = get_db()
    t = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404
    if not get_project_access(conn, t["project_id"], g.user):
        conn.close()
        return jsonify({"error": "无权访问此任务"}), 403
    d = dict(t)
    d["subtasks"] = [dict(s) for s in conn.execute("SELECT * FROM subtasks WHERE task_id=? ORDER BY id", (tid,)).fetchall()]
    d["files"] = [dict(f) for f in conn.execute("SELECT * FROM task_files WHERE task_id=? ORDER BY created_at DESC", (tid,)).fetchall()]
    d["comments"] = [dict(c) for c in conn.execute("SELECT * FROM comments WHERE task_id=? ORDER BY created_at", (tid,)).fetchall()]
    conn.close()
    return jsonify(d)


@bp.route("/api/tasks/<int:tid>", methods=["PUT"])
def api_update_task(tid):
    data = request.get_json(force=True)
    conn = get_db()
    pid_row = conn.execute("SELECT project_id FROM tasks WHERE id=?", (tid,)).fetchone()
    if not pid_row:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404
    if not get_project_access(conn, pid_row["project_id"], g.user):
        conn.close()
        return jsonify({"error": "无权修改此任务"}), 403
    # Compute collaborator diff for notifications
    prev = conn.execute(
        "SELECT collaborator_ids, name, project_id FROM tasks WHERE id=?", (tid,)
    ).fetchone()
    new_collab_added = []
    if "collaborator_ids" in data:
        new_val = _norm_collab_ids(data.get("collaborator_ids")) or ""
        data["collaborator_ids"] = new_val
        prev_set = set((prev["collaborator_ids"] or "").split(",")) if prev else set()
        new_set = set(new_val.split(","))
        new_collab_added = [x for x in new_set - prev_set if x]
    # Normalize optional times before write
    if "start_time" in data:
        data["start_time"] = _norm_time(data.get("start_time"))
    if "end_time" in data:
        data["end_time"] = _norm_time(data.get("end_time"))
    fields, vals = [], []
    for k in ("name", "description", "assignee_id", "assignee_name", "phase",
              "priority", "start_date", "end_date", "start_time", "end_time",
              "progress", "sort_order", "depends_on", "collaborator_ids"):
        if k in data:
            fields.append(f"{k}=?")
            vals.append(data[k])
    if not fields:
        conn.close()
        return jsonify({"error": "无更新"}), 400
    now = datetime.now(timezone.utc).isoformat()
    # Track completion timestamp: set on first transition to 100, clear if reopened
    if "progress" in data:
        try:
            new_prog = int(data["progress"])
        except Exception:
            new_prog = None
        if new_prog is not None:
            prev_prog_row = conn.execute("SELECT progress, completed_at FROM tasks WHERE id=?", (tid,)).fetchone()
            prev_prog = prev_prog_row["progress"] if prev_prog_row else 0
            if new_prog >= 100 and prev_prog < 100:
                fields.append("completed_at=?")
                vals.append(now)
            elif new_prog < 100 and prev_prog >= 100:
                fields.append("completed_at=?")
                vals.append(None)
    fields.append("updated_at=?")
    vals.append(now)
    vals.append(tid)
    conn.execute(f"UPDATE tasks SET {','.join(fields)} WHERE id=?", vals)
    t = conn.execute("SELECT project_id FROM tasks WHERE id=?", (tid,)).fetchone()
    if t:
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, t["project_id"]))
    # Notify newly added collaborators
    for cid in new_collab_added:
        if cid == g.user["id"]:
            continue
        conn.execute(
            "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (cid, "task_assigned", "新增协作",
             f"{g.user['name']} 把你加为 \"{prev['name']}\" 的协作者",
             tid, prev["project_id"], now),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/tasks/<int:tid>", methods=["DELETE"])
def api_delete_task(tid):
    conn = get_db()
    pid_row = conn.execute("SELECT project_id FROM tasks WHERE id=?", (tid,)).fetchone()
    if not pid_row:
        conn.close()
        return jsonify({"error": "任务不存在"}), 404
    if not get_project_access(conn, pid_row["project_id"], g.user):
        conn.close()
        return jsonify({"error": "无权删除此任务"}), 403
    conn.execute("DELETE FROM subtasks WHERE task_id=?", (tid,))
    conn.execute("DELETE FROM comments WHERE task_id=?", (tid,))
    files = conn.execute("SELECT filename FROM task_files WHERE task_id=?", (tid,)).fetchall()
    for f in files:
        fp = os.path.join(UPLOAD_DIR, str(tid), f["filename"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass
    conn.execute("DELETE FROM task_files WHERE task_id=?", (tid,))
    conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    # 知识库同步删除（即时）：一条 metadata SQL 清掉该任务名下所有附件 chunk
    from agent.knowledge import remove_task
    remove_task(tid)
    return jsonify({"success": True})


# ── Subtasks ──
@bp.route("/api/tasks/<int:tid>/subtasks", methods=["POST"])
def api_create_subtask(tid):
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "子任务不能为空"}), 400
    conn = get_db()
    _, access = check_task_access(conn, tid, g.user)
    if not access:
        conn.close()
        return jsonify({"error": "无权访问此任务"}), 403
    conn.execute("INSERT INTO subtasks (task_id,content,is_done,created_at) VALUES (?,?,0,?)",
                 (tid, content, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/subtasks/<int:sid>", methods=["PUT"])
def api_update_subtask(sid):
    data = request.get_json(force=True)
    conn = get_db()
    sub = conn.execute("SELECT task_id FROM subtasks WHERE id=?", (sid,)).fetchone()
    if sub:
        _, access = check_task_access(conn, sub["task_id"], g.user)
        if not access:
            conn.close()
            return jsonify({"error": "无权访问"}), 403
    if "is_done" in data:
        conn.execute("UPDATE subtasks SET is_done=? WHERE id=?", (1 if data["is_done"] else 0, sid))
    if "content" in data:
        conn.execute("UPDATE subtasks SET content=? WHERE id=?", (data["content"], sid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/subtasks/<int:sid>", methods=["DELETE"])
def api_delete_subtask(sid):
    conn = get_db()
    sub = conn.execute("SELECT task_id FROM subtasks WHERE id=?", (sid,)).fetchone()
    if sub:
        _, access = check_task_access(conn, sub["task_id"], g.user)
        if not access:
            conn.close()
            return jsonify({"error": "无权访问"}), 403
    conn.execute("DELETE FROM subtasks WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Task Files ──
@bp.route("/api/tasks/<int:tid>/files", methods=["POST"])
def api_upload_file(tid):
    if "file" not in request.files:
        return jsonify({"error": "没有文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"不支持的文件类型: {ext}"}), 400
    conn_chk = get_db()
    project_id, access = check_task_access(conn_chk, tid, g.user)
    conn_chk.close()
    if not access:
        return jsonify({"error": "无权访问此任务"}), 403
    task_dir = os.path.join(UPLOAD_DIR, str(tid))
    os.makedirs(task_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}"
    filepath = os.path.join(task_dir, safe_name)
    f.save(filepath)
    file_size = os.path.getsize(filepath)
    conn = get_db()
    conn.execute(
        "INSERT INTO task_files (task_id,filename,original_name,file_size,uploaded_by,uploaded_by_name,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (tid, safe_name, f.filename, file_size, g.user["id"], g.user["name"], datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    # 知识库增量索引（后台线程，失败不影响上传）：新附件正文进向量库，agent 才检索得到
    from agent.knowledge import sync_index_file
    sync_index_file("task", project_id, tid, safe_name, f.filename)
    return jsonify({"success": True})


@bp.route("/api/uploads/<int:tid>/<filename>")
def api_serve_file(tid, filename):
    conn = get_db()
    _, access = check_task_access(conn, tid, g.user)
    if not access:
        conn.close()
        return jsonify({"error": "无权访问"}), 403
    row = conn.execute(
        "SELECT original_name FROM task_files WHERE task_id=? AND filename=?", (tid, filename)
    ).fetchone()
    conn.close()
    dl_name = row["original_name"] if row else filename
    return send_from_directory(
        os.path.join(UPLOAD_DIR, str(tid)), filename,
        download_name=dl_name,
    )


@bp.route("/api/files/<int:fid>", methods=["DELETE"])
def api_delete_file(fid):
    conn = get_db()
    row = conn.execute("SELECT * FROM task_files WHERE id=?", (fid,)).fetchone()
    if row:
        project_id, access = check_task_access(conn, row["task_id"], g.user)
        if not access:
            conn.close()
            return jsonify({"error": "无权访问"}), 403
        fp = os.path.join(UPLOAD_DIR, str(row["task_id"]), row["filename"])
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass
        conn.execute("DELETE FROM task_files WHERE id=?", (fid,))
        conn.commit()
        # 知识库同步删除（即时）：stored_name 磁盘唯一，重名不误伤
        from agent.knowledge import remove_file
        remove_file(project_id, row["task_id"], row["filename"])
    conn.close()
    return jsonify({"success": True})


# ── Comments ──
@bp.route("/api/tasks/<int:tid>/comments", methods=["POST"])
def api_create_comment(tid):
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "评论不能为空"}), 400
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    _, access = check_task_access(conn, tid, g.user)
    if not access:
        conn.close()
        return jsonify({"error": "无权访问此任务"}), 403
    conn.execute(
        "INSERT INTO comments (task_id,user_id,user_name,content,created_at) VALUES (?,?,?,?,?)",
        (tid, g.user["id"], g.user["name"], content, now),
    )
    task = conn.execute("SELECT assignee_id,collaborator_ids,name,project_id FROM tasks WHERE id=?", (tid,)).fetchone()
    notified = set()
    if task and task["assignee_id"] and task["assignee_id"] != g.user["id"]:
        conn.execute(
            "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (task["assignee_id"], "comment", "新评论",
             f"{g.user['name']} 在 \"{task['name']}\" 上留言了", tid, task["project_id"], now),
        )
        notified.add(task["assignee_id"])
    # Collaborators get @-mention notifications only if their name appears in the content
    if task and task["collaborator_ids"]:
        for cid in task["collaborator_ids"].split(","):
            cid = cid.strip()
            if not cid or cid == g.user["id"] or cid in notified:
                continue
            # Fetch display name and check @mention
            u = conn.execute("SELECT display_name FROM users WHERE id=?", (cid,)).fetchone()
            if u and u["display_name"] and f"@{u['display_name']}" in content:
                conn.execute(
                    "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (cid, "mention", "有人@你",
                     f"{g.user['name']} 在 \"{task['name']}\" 提到了你", tid, task["project_id"], now),
                )
                notified.add(cid)
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/comments/<int:cid>", methods=["DELETE"])
def api_delete_comment(cid):
    conn = get_db()
    row = conn.execute("SELECT user_id, task_id FROM comments WHERE id=?", (cid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "评论不存在"}), 404
    if row["user_id"] != g.user["id"]:
        conn.close()
        return jsonify({"error": "只能删除自己的评论"}), 403
    conn.execute("DELETE FROM comments WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
