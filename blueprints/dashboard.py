"""
Dashboard Blueprint -- dashboard summary + alerts CRUD
"""
from datetime import date
from flask import Blueprint, request, jsonify, g
from models import get_db
from auth import parse_visible_usernames

bp = Blueprint("dashboard", __name__)


# ── Alerts ──
@bp.route("/api/alerts")
def api_list_alerts():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM alerts WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (g.user["id"],)
    ).fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE user_id=? AND is_read=0", (g.user["id"],)).fetchone()[0]
    conn.close()
    return jsonify({"alerts": [dict(r) for r in rows], "unread": unread})


@bp.route("/api/alerts/read-all", methods=["POST"])
def api_read_all_alerts():
    conn = get_db()
    conn.execute("UPDATE alerts SET is_read=1 WHERE user_id=?", (g.user["id"],))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/alerts/<int:aid>/read", methods=["PUT"])
def api_read_alert(aid):
    conn = get_db()
    conn.execute("UPDATE alerts SET is_read=1 WHERE id=? AND user_id=?", (aid, g.user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Dashboard ──
@bp.route("/api/dashboard")
def api_dashboard():
    conn = get_db()
    uid = g.user["id"]
    if g.user["role"] == "admin":
        total_projects = conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0]
    else:
        uid_like = f"%{uid}%"
        rows = conn.execute(
            "SELECT id, owner_id, visible_to FROM projects WHERE status='active' AND "
            "(owner_id=? "
            "OR id IN (SELECT DISTINCT project_id FROM tasks WHERE assignee_id=? OR collaborator_ids LIKE ?) "
            "OR (visible_to IS NOT NULL AND visible_to != ''))",
            (uid, uid, uid_like),
        ).fetchall()
        total_projects = 0
        for r in rows:
            if r["owner_id"] == uid:
                total_projects += 1
            elif conn.execute(
                "SELECT 1 FROM tasks WHERE project_id=? AND (assignee_id=? OR collaborator_ids LIKE ?) LIMIT 1",
                (r["id"], uid, uid_like),
            ).fetchone():
                total_projects += 1
            else:
                visible_usernames = parse_visible_usernames(r["visible_to"])
                if visible_usernames is not None and g.user["username"] in visible_usernames:
                    total_projects += 1
    uid_like = f"%{uid}%"
    my_tasks = conn.execute(
        "SELECT t.*,p.name as project_name,p.color as project_color,"
        "CASE WHEN t.assignee_id=? THEN 'owner' ELSE 'collaborator' END as my_role "
        "FROM tasks t JOIN projects p ON t.project_id=p.id "
        "WHERE (t.assignee_id=? OR t.collaborator_ids LIKE ?) AND t.progress<100 "
        "ORDER BY t.end_date ASC LIMIT 20", (uid, uid, uid_like),
    ).fetchall()
    today_str = date.today().isoformat()
    overdue = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE (assignee_id=? OR collaborator_ids LIKE ?) "
        "AND end_date<? AND progress<100", (uid, uid_like, today_str)
    ).fetchone()[0]
    unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE user_id=? AND is_read=0", (uid,)).fetchone()[0]
    # Recently completed tasks (last 14 days) — for showing "逐期完成" / "已完成"
    recent_completed = conn.execute(
        "SELECT t.*,p.name as project_name,p.color as project_color "
        "FROM tasks t JOIN projects p ON t.project_id=p.id "
        "WHERE (t.assignee_id=? OR t.collaborator_ids LIKE ?) AND t.progress=100 "
        "AND t.completed_at IS NOT NULL "
        "AND date(t.completed_at) >= date('now','-14 days') "
        "ORDER BY t.completed_at DESC LIMIT 10", (uid, uid_like),
    ).fetchall()
    conn.close()
    return jsonify({
        "total_projects": total_projects,
        "my_tasks": [dict(t) for t in my_tasks],
        "overdue_count": overdue,
        "unread_alerts": unread,
        "recent_completed": [dict(t) for t in recent_completed],
    })
