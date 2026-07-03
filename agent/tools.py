"""
Agent 工具集 -- 供 Agno Agent 调用的能力(function-calling）

工具是同步函数；Agno 在 async 运行时会正确调度它们。
`run_context: RunContext` 是 Agno 的内置参数：由框架自动注入、对 LLM 隐藏，
用来拿到调用方在 arun(user_id=..., dependencies=...) 时传入的运行时上下文。

两类工具：
- bind_user：写操作（绑定），仅未绑定用户挂载。安全敏感，写库前强校验（见下）。
- get_my_* / get_project_status：只读，仅已绑定用户挂载。靠 dependencies 里的「当前对话者」
  身份拿到内部 user id / role，只查「ta 参与的 / ta 自己的」数据，天然无越权。

返回约定：工具返回的是「给 LLM 看的紧凑事实文本」（含真实任务名/项目名/日期，逾期已显式标注），
不是给用户的最终话术——语气由 Agent 按人设再组织。查不到就如实说「没有」，绝不编造。

安全姿态（bind_user 写库前强校验）：
- 绑定属于写操作 + 安全敏感（绑错人 -> 到期提醒会推给错误的人）。
- 工具内部必查 users 表：查得到才写库，查不到如实返回让 Agent 转达，绝不瞎绑。
"""
from datetime import date
from typing import Any, Dict, Optional

from agno.run import RunContext

from config import PHASE_MAP, PRIORITIES
from models import get_db
from repositories import users as users_repo
from repositories import tasks as tasks_repo
from repositories import projects as projects_repo
from repositories import calendar as calendar_repo
from repositories import alerts as alerts_repo

_PRIORITY_MAP = dict(PRIORITIES)


def _current_user(run_context: RunContext) -> Dict[str, Any]:
    """从 run_context.dependencies 取「当前对话者」身份（已绑定才有 id）。

    不 import agent.core（避免循环依赖）——键名「当前对话者」是与 core 约定的契约。
    缺省返回 {}，工具据此判断「没拿到身份」。
    """
    deps = getattr(run_context, "dependencies", None) or {}
    ident = deps.get("当前对话者") or {}
    return ident if isinstance(ident, dict) else {}


def _fmt_task_line(t: Dict[str, Any], today: str) -> str:
    """把一条任务压成一行给 LLM：名称 | 项目 | 进度 | 阶段 | 截止(逾期标注)。"""
    phase = PHASE_MAP.get(t.get("phase"), t.get("phase") or "")
    prio = _PRIORITY_MAP.get(t.get("priority"), "")
    end = t.get("end_date") or ""
    due = ""
    if end:
        overdue = end < today and (t.get("progress") or 0) < 100
        due = f"｜截止{end}" + ("（已逾期）" if overdue else "")
    proj = t.get("project_name")
    proj_str = f"｜项目「{proj}」" if proj else ""
    prio_str = f"｜{prio}优先级" if prio and prio != "中" else ""
    return f"「{t.get('name','')}」{proj_str}｜进度{t.get('progress',0)}%｜{phase}{prio_str}{due}"


def bind_user(run_context: RunContext, username: str) -> str:
    """把当前企业微信账号绑定到系统里的一个用户，之后任务到期提醒会推送给这个企微账号。

    仅当同事明确要求绑定（例如「帮我绑定」「我是张三，绑一下」）时才调用本工具。

    Args:
        username: 系统里的用户名（登录名），需与 users 表中的 username 完全一致。

    Returns:
        绑定结果的中文说明，供你如实转达给同事。
    """
    wecom_userid = run_context.user_id if run_context else None
    username = (username or "").strip()

    if not wecom_userid:
        return "绑定失败：没拿到你的企业微信身份，请稍后再试。"
    if not username:
        return "绑定需要一个用户名，请告诉我你在系统里的用户名。"

    conn = get_db()
    try:
        # users_repo.bind_wecom 内部按 username 查 users 表；查不到返回 None，不会误写。
        # 成功则返回被绑定用户的 dict（含 display_name），供当轮用真名亲切称呼。
        user = users_repo.bind_wecom(conn, username, wecom_userid)
    finally:
        conn.close()

    if user:
        # 优先用显示名（如「张猛(马丁)」）称呼，比登录名亲切；缺失时回退到登录名
        name = user.get("display_name") or user.get("username") or username
        return (
            f"绑定成功：已把你的企业微信账号绑定到用户「{name}」，之后任务到期提醒会发给你。"
            f"请在回复里用「{name}」亲切地称呼对方，欢迎 ta 完成绑定。"
        )
    return f"没找到用户名「{username}」，绑定未执行。请确认用户名和系统里的登录名一致，或换一个再试。"


def get_my_tasks(run_context: RunContext) -> str:
    """查当前同事手上「未完成」的任务（ta 负责的 + ta 参与协作的）。

    当同事问「我手上有什么任务 / 我有几个逾期 / 我这周/最近要交什么 / 我的进度」时调用。
    返回任务清单（含项目、进度、阶段、截止日期，逾期会标注）。若要按「本周/今天」等时间
    范围筛选，你可依据清单里的截止日期和当前日期自行判断，不必再次调用。

    Returns:
        任务清单文本，供你按需组织后转达。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了你的任务。"

    conn = get_db()
    try:
        rows = tasks_repo.find_open_by_user(conn, uid)
    finally:
        conn.close()

    if not rows:
        return "你名下没有未完成的任务，手头很清爽 🎉。"

    today = date.today().isoformat()
    overdue = [t for t in rows if (t.get("end_date") or "") and t["end_date"] < today]
    lines = [_fmt_task_line(t, today) for t in rows]
    head = f"共 {len(rows)} 个未完成任务" + (f"，其中 {len(overdue)} 个已逾期" if overdue else "") + "："
    return head + "\n" + "\n".join(lines)


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
