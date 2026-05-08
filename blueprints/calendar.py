"""
Calendar Blueprint -- calendar events CRUD
"""
from datetime import date, datetime
from flask import Blueprint, request, jsonify, g
from models import get_db

bp = Blueprint("calendar", __name__)


@bp.route("/api/calendar")
def api_list_calendar():
    y = request.args.get("year", str(date.today().year))
    m = request.args.get("month", str(date.today().month)).zfill(2)
    conn = get_db()
    events = conn.execute(
        "SELECT * FROM calendar_events WHERE user_id=? AND event_date LIKE ? ORDER BY event_date,start_time",
        (g.user["id"], f"{y}-{m}%"),
    ).fetchall()
    deadlines = conn.execute(
        "SELECT t.id,t.name,t.end_date,t.priority,t.phase,t.project_id,t.assignee_id,t.collaborator_ids,"
        "p.name as project_name,p.color as project_color "
        "FROM tasks t JOIN projects p ON t.project_id=p.id "
        "WHERE (t.assignee_id=? OR t.collaborator_ids LIKE ?) "
        "AND t.end_date LIKE ? AND t.progress<100 ORDER BY t.end_date",
        (g.user["id"], f"%{g.user['id']}%", f"{y}-{m}%"),
    ).fetchall()
    # Mark each deadline with role so frontend can distinguish
    uid = g.user["id"]
    out_deadlines = []
    for r in deadlines:
        d = dict(r)
        d["role"] = "owner" if d.get("assignee_id") == uid else "collaborator"
        out_deadlines.append(d)
    conn.close()
    return jsonify({"events": [dict(r) for r in events], "deadlines": out_deadlines})


@bp.route("/api/calendar", methods=["POST"])
def api_create_calendar_event():
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "标题不能为空"}), 400
    conn = get_db()
    conn.execute(
        "INSERT INTO calendar_events (user_id,title,description,event_date,start_time,end_time,event_type,color,related_project_id,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (g.user["id"], title, data.get("description", ""), data.get("event_date", date.today().isoformat()),
         data.get("start_time", ""), data.get("end_time", ""), data.get("event_type", "meeting"),
         data.get("color", "#95A3B3"), data.get("related_project_id"), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route("/api/calendar/<int:eid>", methods=["DELETE"])
def api_delete_calendar_event(eid):
    conn = get_db()
    conn.execute("DELETE FROM calendar_events WHERE id=? AND user_id=?", (eid, g.user["id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
