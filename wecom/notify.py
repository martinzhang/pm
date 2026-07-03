"""
企业微信到期提醒 -- 领域逻辑

不依赖 aibot SDK 类型，只依赖 models.get_db()。bot.py 负责把这里的结果通过
WSClient 发出去；本模块只管"该提醒谁、提醒什么、提醒过没有"。
"""
from datetime import date, timedelta, timezone
from datetime import datetime as dt

DUE_SOON_ALERT_TYPE = "due_soon_wecom"


def bind_wecom_user(conn, username, wecom_userid):
    """按 username 查 users 表，写入 wecom_userid。返回是否绑定成功。"""
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE users SET wecom_userid=? WHERE id=?", (wecom_userid, row["id"]))
    conn.commit()
    return True


def find_due_soon_tasks(conn):
    """查 progress<100 且 end_date 在明天（含）以内的任务，包含已逾期的。"""
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    rows = conn.execute(
        "SELECT t.*, p.name as project_name FROM tasks t "
        "JOIN projects p ON t.project_id=p.id "
        "WHERE t.progress<100 AND t.end_date IS NOT NULL AND t.end_date!='' "
        "AND t.end_date<=? AND p.status='active'",
        (tomorrow,),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_recipients(conn, task):
    """任务的 assignee_id + collaborator_ids 转换成已绑定 wecom_userid 的收件人列表。

    返回 [(internal_user_id, wecom_userid, display_name), ...]
    """
    ids = set()
    if task.get("assignee_id"):
        ids.add(task["assignee_id"])
    for cid in (task.get("collaborator_ids") or "").split(","):
        cid = cid.strip()
        if cid:
            ids.add(cid)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, display_name, wecom_userid FROM users "
        f"WHERE id IN ({placeholders}) AND wecom_userid IS NOT NULL AND wecom_userid!=''",
        tuple(ids),
    ).fetchall()
    return [(r["id"], r["wecom_userid"], r["display_name"]) for r in rows]


def already_notified_today(conn, task_id, user_id):
    row = conn.execute(
        "SELECT 1 FROM alerts WHERE related_task_id=? AND user_id=? AND alert_type=? "
        "AND date(created_at)=date('now') LIMIT 1",
        (task_id, user_id, DUE_SOON_ALERT_TYPE),
    ).fetchone()
    return row is not None


def mark_notified(conn, task, user_id):
    now = dt.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            user_id,
            DUE_SOON_ALERT_TYPE,
            "任务即将到期",
            f"「{task['name']}」({task['project_name']}) 截止日期 {task['end_date']}",
            task["id"],
            task["project_id"],
            now,
        ),
    )
    conn.commit()


def build_due_message(task):
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": (
                f"### ⏰ 任务即将到期\n"
                f"**{task['name']}**\n"
                f"项目：{task['project_name']}\n"
                f"截止日期：{task['end_date']}\n"
                f"当前进度：{task['progress']}%"
            )
        },
    }


async def run_due_check(ws_client, logger=None):
    """完整跑一遍到期检查：找到期任务 -> 逐个收件人查重 -> 未通知则推送 + 记录。"""
    from models import get_db

    conn = get_db()
    try:
        tasks = find_due_soon_tasks(conn)
        for task in tasks:
            for user_id, wecom_userid, _name in resolve_recipients(conn, task):
                if already_notified_today(conn, task["id"], user_id):
                    continue
                try:
                    await ws_client.send_message(wecom_userid, build_due_message(task))
                    mark_notified(conn, task, user_id)
                except Exception as e:
                    if logger:
                        logger.error(f"到期提醒推送失败 task={task['id']} user={user_id}: {e}")
    finally:
        conn.close()
