"""
alerts 表 -- 数据访问

提醒记录的去重查询与落库。文案（title/message）由领域层拼好后传入，本层不生成文字。
"""
from datetime import datetime, timezone


def exists_today(conn, task_id, user_id, alert_type):
    """今天是否已就 (task, user) 写过某类 alert？供去重，避免一天多推。返回 bool。"""
    row = conn.execute(
        "SELECT 1 FROM alerts WHERE related_task_id=? AND user_id=? AND alert_type=? "
        "AND date(created_at)=date('now') LIMIT 1",
        (task_id, user_id, alert_type),
    ).fetchone()
    return row is not None


def insert(conn, user_id, alert_type, title, message, task_id, project_id):
    """写一条 alert 记录。created_at 用当前 UTC；文案由调用方传入，本层只落库。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO alerts (user_id,alert_type,title,message,related_task_id,related_project_id,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, alert_type, title, message, task_id, project_id, now),
    )
    conn.commit()


def find_unread_by_user(conn, user_id, limit=10):
    """查某人最近的未读提醒（is_read=0），按创建时间倒序。

    返回 [dict(...alert 列...), ...]；user_id 为空返回 []。
    """
    if not user_id:
        return []
    rows = conn.execute(
        "SELECT * FROM alerts WHERE user_id=? AND is_read=0 "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
