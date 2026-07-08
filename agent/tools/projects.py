"""
工具·项目域（只读）

两个以项目为中心的工具，共享「参与口径 + 多匹配消歧」模式，内聚在一处：
- get_my_projects：一次看全部参与项目的完成度概况。
- get_project_status：单个项目的进度 + 任务清单（模糊名匹配，多个先让用户挑）。

可见性口径落在 repositories.projects 层（owner 或有我负责/协作的任务；admin 放宽到全部活跃项目）。
"""
from datetime import date

from models import get_db
from repositories import projects as projects_repo

from agno.run import RunContext

from agent.tools._shared import _current_user, _fmt_task_line


def get_my_projects(run_context: RunContext) -> str:
    """查当前同事参与的「活跃项目」清单（ta 负责的 + ta 有任务在其中的；管理员可见全部）。

    当同事问「我有哪些项目 / 我参与了哪些项目 / 我手上的项目都到哪了 / 我负责的项目」
    这类想一次看到「所有项目」的问题时调用。返回每个项目的完成度与平均进度概况。
    若同事只关心某一个具体项目的细节（任务清单等），用 get_project_status。

    Returns:
        项目清单文本，供你按需组织后转达。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了你的项目。"

    is_admin = (ident.get("role") == "admin")
    conn = get_db()
    try:
        projs = projects_repo.list_participating_with_progress(conn, uid, is_admin)
    finally:
        conn.close()

    if not projs:
        return "你名下暂时没有参与的活跃项目。"
    lines = []
    for p in projs:
        owner = f"｜负责人{p.get('owner_name')}" if p.get("owner_name") else ""
        deadline = f"｜截止{p.get('deadline')}" if p.get("deadline") else ""
        lines.append(
            f"「{p.get('name','')}」{owner}｜{p['done']}/{p['total']} 任务完成"
            f"｜平均进度 {p['avg_progress']}%{deadline}"
        )
    scope = "系统里共" if is_admin else "你参与"
    return f"{scope} {len(projs)} 个活跃项目：\n" + "\n".join(lines)


def get_project_status(run_context: RunContext, project_name: str) -> str:
    """查某个项目的进度概况（该同事参与的项目；管理员可查全部活跃项目）。

    当同事问「XX 项目到哪了 / XX 进展如何 / XX 项目现在什么情况」时调用。
    按名字模糊匹配，返回完成度、平均进度和任务清单。

    Args:
        project_name: 项目名（可为部分名字，模糊匹配）。

    Returns:
        项目进度文本；找不到或无权查看时如实说明。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了项目进度。"
    name = (project_name or "").strip()
    if not name:
        return "请告诉我要查哪个项目的名字。"

    is_admin = (ident.get("role") == "admin")
    conn = get_db()
    try:
        projs = projects_repo.find_participating_by_name(conn, uid, is_admin, name, limit=5)
        if not projs:
            return f"没找到你参与的、名字含「{name}」的活跃项目。换个关键词，或确认下项目名？"
        # 多个匹配时先列出来让用户挑，不硬猜
        if len(projs) > 1:
            names = "、".join(f"「{p['name']}」" for p in projs)
            return f"匹配到多个项目：{names}。你想看哪一个？（可以说得更具体些）"
        p = projs[0]
        summary = projects_repo.progress_summary(conn, p["id"])
        tasks = projects_repo.list_tasks(conn, p["id"])
    finally:
        conn.close()

    today = date.today().isoformat()
    head = (
        f"项目「{p['name']}」"
        + (f"｜负责人{p.get('owner_name')}" if p.get("owner_name") else "")
        + (f"｜截止{p.get('deadline')}" if p.get("deadline") else "")
        + f"\n进度：{summary['done']}/{summary['total']} 个任务完成，平均进度 {summary['avg_progress']}%"
    )
    if not tasks:
        return head + "\n（暂无任务）"
    lines = [_fmt_task_line(t, today) for t in tasks]
    return head + "\n任务清单：\n" + "\n".join(lines)
