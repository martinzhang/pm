"""
AI 大脑 -- 框架无关的 Agno Agent

不依赖 Flask、不依赖企业微信 SDK；只把「一段用户消息」变成「一串正文增量」。
- Web 端(未来)可直接 import 本模块做 SSE 流式
- wecom/chat.py 把增量适配成企业微信的「全量替换」流式回复

模型走 MiniMax（OpenAI 兼容接口），复用根 config.py 里已验证的 key / 端点 / 模型。
MiniMax 的 <think>...</think> 推理标签由 Agno 的 MiniMax 模型类自动剥离，
正文增量(run_content 事件)里不会泄漏推理内容。

离线冒烟(不依赖企业微信):
    uv run python -m agent.core
"""
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.minimax import MiniMax
from agno.run.agent import RunEvent

from config import MINIMAX_API_KEY, MINIMAX_BASE, MINIMAX_MODEL
from agent.tools import bind_user

REPO_ROOT = Path(__file__).resolve().parent.parent
# 独立于 projects.db 的会话库，只存 Agno 的对话历史，不碰业务表
SESSION_DB_PATH = REPO_ROOT / "agent_sessions.db"

# ── Agent 人设：核心恒定，能力块按身份动态挂载 ──
#
# 设计：把「人设」和「能力」拆开。
#   - BASE_INSTRUCTIONS：核心身份/语气/边界，恒定不变。新增能力时不改这里。
#   - 每个「能力」= 一块可插拔积木：(该不该挂给当前对话者, 指令块, 需要的工具)。
#     由 _build_instructions / _build_tools 两个 callable 在每轮运行时按身份拼装。
#
# 收益：
#   1. 已绑定用户的上下文里【完全没有】绑定指令，连 bind_user 的工具 schema 都不注入
#      —— 对永远用不到绑定的老用户，零 token 浪费。
#   2. 新增能力 = 加一个能力块 + 一个挂载条件，核心人设一字不动。
BASE_INSTRUCTIONS = """你是奈娃咖啡小助手，一条小鱼，在奈娃咖啡项目管理系统里。帮助奈娃咖啡同事更好、更简单、更轻松地完成项目工作，这样以后才能有空带你去钓小鱼。

回答要求：
- 用中文回答，简洁、有条理，语气亲切
- 不要假装执行了任何写操作"""

# 【能力块·绑定】只在「当前对话者未绑定」时才挂载。已绑定用户永远看不到这段。
BIND_INSTRUCTIONS = """【关于当前对话者】ta 还没绑定系统账号。可以正常闲聊（限项目管理话题），但要顺势告诉 ta 还没绑定，邀请提供 OA 登录用户名来绑定，说明绑定后能收到任务到期提醒等功能。语气亲切、点到为止，不要生硬催促。

当 ta 明确要求绑定，或发来的内容像 OA 登录用户名时，调用 bind_user 工具：
- username 用 ta 给出的登录名，不要自己猜或编造；没给就先问。
- 工具返回什么就如实转达，不要谎称成功；绑定成功时用返回的名字亲切称呼 ta。"""


def _identity_of(run_context) -> Dict[str, Any]:
    """从 run_context 里取出本轮注入的「当前对话者」身份；缺省视作未绑定。"""
    deps = getattr(run_context, "dependencies", None) or {}
    ident = deps.get("当前对话者") or {}
    return ident if isinstance(ident, dict) else {}


def _build_instructions(run_context) -> list:
    """按当前对话者身份拼装指令：核心恒定 + 能力块动态挂载。

    - 未绑定：核心 + 绑定能力块（引导 + 绑定动作）
    - 已绑定：核心 + 一句「你在跟谁说话」，不含任何绑定相关文字
    """
    ident = _identity_of(run_context)
    blocks = [BASE_INSTRUCTIONS]
    if ident.get("bound"):
        name = ident.get("display_name") or ident.get("username") or "这位同事"
        blocks.append(
            f"【关于当前对话者】ta 是你已经认识的同事「{name}」。请自然地称呼 ta 的名字，"
            f"把 ta 当作老朋友一样交流。"
        )
    else:
        blocks.append(BIND_INSTRUCTIONS)
    return blocks


def _build_tools(run_context) -> list:
    """按身份挂载工具：只有未绑定用户才需要 bind_user；已绑定用户连工具 schema 都不注入。"""
    return [] if _identity_of(run_context).get("bound") else [bind_user]

_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """懒加载单例。首次调用时才构建 Agent(此时才需要 MiniMax key)。

    同一个实例服务所有用户，靠 arun(session_id=..., user_id=...) 隔离各自的会话历史。
    instructions / tools 都是 callable：每轮运行时按注入的身份动态拼装（见 _build_*）。
    """
    global _agent
    if _agent is None:
        _agent = Agent(
            model=MiniMax(
                id=MINIMAX_MODEL,
                api_key=MINIMAX_API_KEY,
                base_url=MINIMAX_BASE,  # 显式指向国内端点 api.minimaxi.com，覆盖 Agno 默认的 .io
            ),
            db=SqliteDb(db_file=str(SESSION_DB_PATH)),
            instructions=_build_instructions, 
            tools=_build_tools,
            add_history_to_context=True,  # 把最近几轮对话带进上下文 -> 多轮记忆
            num_history_runs=5,
            # 不开 add_dependencies_to_context：身份已由 _build_instructions 有目的地呈现，
            # 无需再把原始 JSON dump 进上下文（那是重复注入）。dependencies 仍会传给 arun，
            # 供 callable 从 run_context.dependencies 读取——「读身份」和「dump 身份」是两回事。
            markdown=True,
            telemetry=False,  # 关闭遥测，避免多余外网调用
            add_datetime_to_context=True,
            timezone_identifier="Asia/Shanghai",
            debug_mode=True
        )
    return _agent


async def astream_reply(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
    identity: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[str]:
    """把一段用户消息变成一串「正文增量」。

    :param message: 用户输入的文本
    :param session_id: 会话 ID（同一 session 内多轮连续），企微场景用发送者 userid
    :param user_id: 用户 ID（用于跨会话的用户级隔离），可与 session_id 相同
    :param identity: 当前对话者身份（框架无关的通用契约，由调用方解析后传入）。约定字段：
        - bound (bool): 是否已绑定系统账号
        - display_name (str): 已绑定时的显示名
        - username (str): 已绑定时的登录名
        未绑定时传 {"bound": False} 即可；为 None 时按未知处理。
        本函数把它作为 dependencies 传给 agent，由 _build_instructions / _build_tools
        按身份动态拼装指令与工具（已绑定用户不会看到任何绑定相关内容）。
    :yield: 正文增量字符串（已剥离 <think> 推理内容）
    """
    agent = get_agent()
    # 身份作为「当前对话者」依赖传入；缺省视作未绑定。
    # 注意：这里只是把身份【传给】agent（供 _build_instructions / _build_tools 读取决策），
    # 并不 dump 进上下文——呈现由 callable 按需负责，避免重复注入。
    dependencies = {"当前对话者": identity if identity is not None else {"bound": False}}
    try:
        async for event in agent.arun(
            message,
            stream=True,
            session_id=session_id,
            user_id=user_id,
            dependencies=dependencies,
        ):
            if event.event == RunEvent.run_content and event.content:
                yield event.content
    except Exception as e:  # noqa: BLE001 -- 兜底：任何异常都回一句友好提示，不让机器人卡死
        yield f"\n\n（小鱼开小差了，稍后再试试～ 错误：{e}）"


# ── 离线冒烟测试：命令行直接对话，不依赖企业微信 ──
if __name__ == "__main__":
    import asyncio

    async def _run(sid: str, turns, identity) -> None:
        tag = identity.get("display_name") if identity.get("bound") else "未绑定"
        print(f"\n\033[35m===== 场景：{tag} identity={identity} =====\033[0m")
        for i, msg in enumerate(turns, 1):
            print(f"\n\033[36m[你 #{i}]\033[0m {msg}")
            print("\033[32m[小鱼]\033[0m ", end="", flush=True)
            got = []
            async for delta in astream_reply(
                msg, session_id=sid, user_id=sid, identity=identity
            ):
                got.append(delta)
                print(delta, end="", flush=True)
            print()
            full = "".join(got)
            leaked = "<think>" in full or "</think>" in full
            print(f"\033[90m  (len={len(full)}, think泄漏={leaked})\033[0m")

    async def _smoke() -> None:
        # 场景一：未绑定 —— 期望能闲聊，并在合适时机引导绑定
        await _run(
            "smoke-unbound",
            ["你是谁？", "帮我看看我手上的任务进度", "怎么才能收到任务提醒？"],
            {"bound": False},
        )
        # 场景二：已绑定 —— 期望称呼名字；再要求绑定时应说“已绑定过”而非追问用户名
        await _run(
            "smoke-bound",
            ["你好呀", "帮我绑定一下"],
            {"bound": True, "display_name": "张三", "username": "zhangsan", "role": "member"},
        )

    asyncio.run(_smoke())
