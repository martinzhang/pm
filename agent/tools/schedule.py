"""
工具·日程域（只读）

服务「我今天/这周有什么安排」：查当前对话者从今天起即将到来的日程。
时间范围筛选（今天/本周）交给 LLM 依返回里的日期自行判断，不反复调用。
"""
from datetime import date

from models import get_db
from repositories import calendar as calendar_repo

from agno.run import RunContext

from agent.tools._shared import _current_user


def get_my_schedule(run_context: RunContext) -> str:
    """查当前同事「即将到来」的日程安排（从今天起）。

    当同事问「我今天/这周有什么安排 / 我的日程 / 接下来有什么会」时调用。
    返回从今天起的日程列表；要筛「今天/本周」可依据返回里的日期自行判断。

    Returns:
        日程列表文本；没有则如实说明。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了你的日程。"

    today = date.today().isoformat()
    conn = get_db()
    try:
        events = calendar_repo.find_upcoming_events(conn, uid, today)
    finally:
        conn.close()

    if not events:
        return "从今天起你还没有登记的日程安排。"
    lines = []
    for e in events:
        t = e.get("start_time") or ""
        t_str = f" {t}" if t else ""
        etype = e.get("event_type") or ""
        etype_str = f"（{etype}）" if etype else ""
        lines.append(f"{e.get('event_date','')}{t_str}｜{e.get('title','')}{etype_str}")
    return f"接下来有 {len(events)} 项日程：\n" + "\n".join(lines)
