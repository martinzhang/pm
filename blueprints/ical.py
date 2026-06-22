"""
iCal Blueprint — public iCalendar subscription feeds.

Each user gets a long-lived secret token; subscribing to
  webcal://oa.nevermindcoffee.cn/pm/cal/<token>.ics
adds their assigned tasks to the device's native calendar.
"""
import secrets
from datetime import datetime, date
from urllib.parse import quote
from flask import Blueprint, Response, jsonify, g, request, current_app

from models import get_db
from config import URL_PREFIX

bp = Blueprint("ical", __name__)

PUBLIC_BASE = "https://oa.nevermindcoffee.cn"
CAL_NAME = "奈娃 PM · 我的任务"
CAL_COLOR = "#8B6F47"  # coffee brown
PRODID = "-//Nevermind Coffee//PM Calendar//ZH"


# ---------- token helpers ----------
def _ensure_cal_token_column():
    c = get_db()
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "cal_token" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN cal_token TEXT DEFAULT ''")
        c.commit()
    c.close()


def _get_or_create_token(user_id: str) -> str:
    _ensure_cal_token_column()
    c = get_db()
    row = c.execute("SELECT cal_token FROM users WHERE id=?", (user_id,)).fetchone()
    token = row["cal_token"] if row else ""
    if not token:
        token = secrets.token_urlsafe(24)
        c.execute("UPDATE users SET cal_token=? WHERE id=?", (token, user_id))
        c.commit()
    c.close()
    return token


def _user_by_token(token: str):
    _ensure_cal_token_column()
    c = get_db()
    row = c.execute(
        "SELECT id, username, display_name FROM users WHERE cal_token=?", (token,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


# ---------- iCal builder ----------
def _esc(s: str) -> str:
    """Escape per RFC 5545."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets."""
    out = []
    while len(line.encode("utf-8")) > 75:
        # find a safe break around 73 bytes
        cut = 73
        while cut > 1 and len(line[:cut].encode("utf-8")) > 73:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def _parse_date(s: str):
    if not s:
        return None
    s = s.strip()
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def _fmt_date(d) -> str:
    return d.strftime("%Y%m%d")


def _build_ical(user: dict) -> str:
    """Build iCal feed: all incomplete/recent tasks assigned to this user."""
    uid = user["id"]
    c = get_db()
    # Tasks where the user is assignee OR collaborator
    rows = c.execute(
        """
        SELECT t.*, p.name AS project_name, p.color AS project_color
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        WHERE (t.assignee_id = ?
               OR ',' || COALESCE(t.collaborator_ids, '') || ',' LIKE ?)
          AND t.end_date IS NOT NULL AND t.end_date != ''
          AND (t.progress < 100 OR DATE(t.end_date) >= DATE('now', '-30 days'))
        ORDER BY t.end_date
        """,
        (uid, f"%,{uid},%"),
    ).fetchall()
    c.close()

    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(CAL_NAME)}",
        f"X-WR-CALDESC:{_esc('分配给 ' + (user.get('display_name') or user.get('username') or '我') + ' 的项目任务')}",
        "X-WR-TIMEZONE:Asia/Shanghai",
        f"X-APPLE-CALENDAR-COLOR:{CAL_COLOR}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]

    PRIORITY_TAG = {"high": "🔴", "medium": "🟡", "low": "⚪"}
    STATUS_TAG = {0: "未开始", 100: "已完成"}

    # VTIMEZONE block for Asia/Shanghai (CST, UTC+8, no DST) — needed for TZID refs
    lines.extend([
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "X-LIC-LOCATION:Asia/Shanghai",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:CST",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
    ])

    from datetime import timedelta

    def _parse_hm(v):
        if not v or ":" not in v:
            return None
        try:
            hh, mm = v.split(":")
            return int(hh), int(mm)
        except Exception:
            return None

    for r in rows:
        end_d = _parse_date(r["end_date"])
        if not end_d:
            continue
        start_d = _parse_date(r["start_date"]) or end_d
        # tasks rows are date-only here (TEXT YYYY-MM-DD) — coerce to date
        if isinstance(start_d, datetime):
            start_d = start_d.date()
        if isinstance(end_d, datetime):
            end_d = end_d.date()

        st_hm = _parse_hm(r["start_time"]) if "start_time" in r.keys() else None
        en_hm = _parse_hm(r["end_time"]) if "end_time" in r.keys() else None

        is_timed = bool(st_hm or en_hm)
        timed_alarm = False
        deadline_only = False
        if not is_timed:
            # All-day: DTEND is exclusive — add 1 day
            dt_lines = [
                f"DTSTART;VALUE=DATE:{_fmt_date(start_d)}",
                f"DTEND;VALUE=DATE:{_fmt_date(end_d + timedelta(days=1))}",
            ]
        else:
            timed_alarm = True
            if st_hm and en_hm:
                sdt = datetime(start_d.year, start_d.month, start_d.day, st_hm[0], st_hm[1])
                edt = datetime(end_d.year, end_d.month, end_d.day, en_hm[0], en_hm[1])
                if edt <= sdt:
                    edt = sdt + timedelta(hours=1)
            elif st_hm and not en_hm:
                # "starts at X" — default 1h duration on start_date
                sdt = datetime(start_d.year, start_d.month, start_d.day, st_hm[0], st_hm[1])
                edt = sdt + timedelta(hours=1)
            else:
                # only end_time — "deadline by X" on end_date — 15min window ending at deadline
                deadline_only = True
                edt = datetime(end_d.year, end_d.month, end_d.day, en_hm[0], en_hm[1])
                sdt = edt - timedelta(minutes=15)
            dt_lines = [
                f"DTSTART;TZID=Asia/Shanghai:{sdt.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID=Asia/Shanghai:{edt.strftime('%Y%m%dT%H%M%S')}",
            ]

        prio = PRIORITY_TAG.get((r["priority"] or "medium").lower(), "")
        title_prefix = "⏰ 截止 " if deadline_only else "☕ "
        title = f"{title_prefix}{prio} [{r['project_name']}] {r['name']}".strip()

        # Description body
        prog = r["progress"] or 0
        status_txt = "已完成 ✅" if prog >= 100 else ("未开始" if prog == 0 else f"进行中 {prog}%")
        body_lines = [
            f"项目: {r['project_name']}",
            f"任务: {r['name']}",
            f"负责人: {r['assignee_name'] or '—'}",
            f"状态: {status_txt}",
        ]
        if r["description"]:
            body_lines.append("")
            body_lines.append(r["description"][:500])
        task_url = f"{PUBLIC_BASE}{URL_PREFIX}/?project={r['project_id']}&task={r['id']}"
        body_lines.append("")
        body_lines.append("👉 在 PM 中打开此任务:")
        body_lines.append(task_url)

        ev = [
            "BEGIN:VEVENT",
            f"UID:pm-task-{r['id']}@nevermindcoffee.cn",
            f"DTSTAMP:{now_utc}",
            f"LAST-MODIFIED:{now_utc}",
            f"SUMMARY:{_esc(title)}",
            *dt_lines,
            f"DESCRIPTION:{_esc(chr(10).join(body_lines))}",
            f"URL:{task_url}",
            f"CATEGORIES:{_esc(CAL_NAME)},{_esc(r['project_name'])}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE" if is_timed else "TRANSP:TRANSPARENT",
        ]
        if timed_alarm and prog < 100:
            ev.extend([
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_esc(title)}",
                "TRIGGER:-PT30M",
                "END:VALARM",
            ])
        ev.append("END:VEVENT")
        lines.extend(ev)

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"


# ---------- routes ----------
@bp.route("/cal/<token>.ics")
def public_feed(token):
    """Public — no auth, secured by unguessable token."""
    user = _user_by_token(token)
    if not user:
        return Response("Not Found", status=404)
    body = _build_ical(user)
    resp = Response(body, mimetype="text/calendar; charset=utf-8")
    fn = f"pm-{user["username"]}.ics"
    resp.headers["Content-Disposition"] = f'inline; filename="{fn}"'
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@bp.route("/api/cal/me")
def my_subscription():
    """Return current user's subscription URLs."""
    u = g.user
    token = _get_or_create_token(u["id"])
    https_url = f"{PUBLIC_BASE}{URL_PREFIX}/cal/{token}.ics"
    webcal_url = "webcal://oa.nevermindcoffee.cn" + URL_PREFIX + f"/cal/{token}.ics"
    return jsonify({
        "token": token,
        "https_url": https_url,
        "webcal_url": webcal_url,
        "name": CAL_NAME,
    })


@bp.route("/api/cal/regenerate", methods=["POST"])
def regenerate():
    """Rotate token — invalidates old subscription."""
    _ensure_cal_token_column()
    u = g.user
    new = secrets.token_urlsafe(24)
    c = get_db()
    c.execute("UPDATE users SET cal_token=? WHERE id=?", (new, u["id"]))
    c.commit()
    c.close()
    return jsonify({"token": new, "ok": True})
