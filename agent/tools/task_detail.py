"""
工具·任务详情域（只读，跨三表下钻）

单个任务的内部细节：基本信息 + 子任务清单 + 评论讨论。是唯一横跨
tasks（可见性把关）+ subtasks + comments 三张表的工具，独立成域，
其三表依赖不再污染其它只读工具。

可见性口径复用 repositories.tasks 的参与口径（任务跟随项目可见性）；
评论是协作讨论的唯一载体，正文照实给、不压缩。
"""
from datetime import date

from models import get_db
from repositories import tasks as tasks_repo
from repositories import subtasks as subtasks_repo
from repositories import comments as comments_repo

from agno.run import RunContext

from agent.tools._shared import _current_user, _fmt_task_line


def get_task_detail(run_context: RunContext, task_name: str) -> str:
    """查某个任务的详情：基本信息 + 子任务清单 + 评论讨论（该同事能看到的任务）。

    当同事问「XX 任务有哪些子任务 / XX 任务做到哪一步了 / XX 任务下面讨论了什么 /
    XX 任务的评论」这类想看【单个任务内部细节】的问题时调用。
    按任务名模糊匹配，返回该任务的进度、子任务完成情况、以及评论正文。
    若同事只想看整个项目的任务列表（而非某个任务内部），用 get_project_status。

    Args:
        task_name: 任务名（可为部分名字，模糊匹配）。

    Returns:
        任务详情文本；找不到、无权查看或匹配到多个时如实说明。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了任务详情。"
    name = (task_name or "").strip()
    if not name:
        return "请告诉我要查哪个任务的名字。"

    is_admin = (ident.get("role") == "admin")
    conn = get_db()
    try:
        rows = tasks_repo.find_participating_by_name(conn, uid, is_admin, name, limit=5)
        if not rows:
            return f"没找到你参与的、名字含「{name}」的任务。换个关键词，或确认下任务名？"
        # 多个匹配时先列出来让用户挑，不硬猜（与 get_project_status 一致的消歧模式）
        if len(rows) > 1:
            names = "、".join(
                f"「{t.get('name','')}」（{t.get('project_name','')}）" for t in rows
            )
            return f"匹配到多个任务：{names}。你想看哪一个？（可以说得更具体些）"
        t = rows[0]
        subs = subtasks_repo.list_by_task(conn, t["id"])
        cmts = comments_repo.list_by_task(conn, t["id"])
    finally:
        conn.close()

    today = date.today().isoformat()
    parts = [_fmt_task_line(t, today)]

    # 子任务：给出 完成/总数 概览 + 逐条勾选状态
    if subs:
        done = sum(1 for s in subs if s.get("is_done"))
        parts.append(f"\n子任务（{done}/{len(subs)} 完成）：")
        for s in subs:
            mark = "✅" if s.get("is_done") else "⬜"
            parts.append(f"{mark} {s.get('content','')}")
    else:
        parts.append("\n子任务：无")

    # 评论：带上是谁、哪天说的，正文照实给（这是协作讨论的唯一载体，不压缩）
    if cmts:
        parts.append(f"\n评论（{len(cmts)} 条）：")
        for c in cmts:
            who = c.get("user_name") or "某同事"
            when = (c.get("created_at") or "")[:10]
            when_str = f"（{when}）" if when else ""
            parts.append(f"- {who}{when_str}：{c.get('content','')}")
    else:
        parts.append("\n评论：无")

    return "\n".join(parts)
