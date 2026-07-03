"""
Agent 工具集 -- 供 Agno Agent 调用的能力(function-calling）

工具是同步函数；Agno 在 async 运行时会正确调度它们。
`run_context: RunContext` 是 Agno 的内置参数：由框架自动注入、对 LLM 隐藏，
用来拿到调用方在 arun(user_id=...) 时传入的运行时上下文（此处即企业微信 userid）。

安全姿态（写库前强校验）：
- 绑定属于写操作 + 安全敏感（绑错人 -> 到期提醒会推给错误的人）。
- 工具内部必查 users 表：查得到才写库，查不到如实返回让 Agent 转达，绝不瞎绑。
- 是否「该绑定」由 Agent 依据 instructions 判断（仅用户明确要求时才调用本工具）。
"""
from agno.run import RunContext

from models import get_db
from repositories import users as users_repo


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
