"""
工具·提醒域（只读）

服务「我有什么新消息 / 提醒」：查当前对话者最近的未读提醒。
"""
from models import get_db
from repositories import alerts as alerts_repo

from agno.run import RunContext

from agent.tools._shared import _current_user


def get_my_alerts(run_context: RunContext) -> str:
    """查当前同事最近的「未读提醒」。

    当同事问「我有什么新消息 / 有啥提醒 / 有人 @ 我吗」时调用。
    返回最近的未读提醒列表。

    Returns:
        未读提醒列表文本；没有则如实说明。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了你的提醒。"

    conn = get_db()
    try:
        rows = alerts_repo.find_unread_by_user(conn, uid, limit=10)
    finally:
        conn.close()

    if not rows:
        return "你没有未读提醒，消息都看完啦。"
    lines = []
    for a in rows:
        title = a.get("title") or "提醒"
        msg = a.get("message") or ""
        when = (a.get("created_at") or "")[:10]
        lines.append(f"[{title}] {msg}" + (f"（{when}）" if when else ""))
    return f"你有 {len(rows)} 条未读提醒：\n" + "\n".join(lines)
