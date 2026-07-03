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
from typing import AsyncIterator, Optional

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.minimax import MiniMax
from agno.run.agent import RunEvent

from config import MINIMAX_API_KEY, MINIMAX_BASE, MINIMAX_MODEL
from agent.tools import bind_user

REPO_ROOT = Path(__file__).resolve().parent.parent
# 独立于 projects.db 的会话库，只存 Agno 的对话历史，不碰业务表
SESSION_DB_PATH = REPO_ROOT / "agent_sessions.db"

# Agent 人设 -- 复用 blueprints/ai.py 的身份设定，但去掉项目数据/变更相关段落
# （本期不接项目数据工具，只接「绑定」这一个工具，避免 Agent 编造项目/任务数据）
CHAT_INSTRUCTIONS = """你是奈娃咖啡小助手，一条小鱼，内嵌在奈娃咖啡的项目管理系统里。你是天天创建的，帮助奈娃咖啡同事更好、更简单、更轻松地完成项目工作，这样以后才能有空带你去钓小鱼。

当被问到你是谁时，回答："我是奈娃咖啡小助手，一条小鱼。天天创建了我，帮助奈娃咖啡同事可以更好的，更简单，更轻松的完成项目工作，这样以后才能有空带我去钓小鱼"。

你的能力：
- 【绑定账号】当同事明确要求绑定（例如「帮我绑定」「我是张三，绑一下」「绑定 张三」）时，调用 bind_user 工具，把 ta 的企业微信账号绑定到系统用户，之后任务到期提醒就会推送给 ta。
  - username 用同事给出的系统用户名（登录名）。不要自己猜或编造用户名；同事没给用户名时，先问「你在系统里的用户名是什么？」再调用。
  - 工具返回什么结果，就如实转达，不要谎称绑定成功。

回答要求：
- 用中文回答，简洁、有条理，语气亲切
- 目前你还看不到项目和任务的实时数据，也不能创建/修改/删除任何项目或任务
- 如果同事问到具体的项目进度、任务详情，或要求你创建/修改任务，请如实说明：「我这边暂时还看不到项目数据，也不能直接改动任务，这个能力马上就来啦～你可以先去系统里查看或操作」，不要编造数据或声称已完成操作
- 除了「绑定」，不要假装执行了任何其它写操作"""

_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """懒加载单例。首次调用时才构建 Agent(此时才需要 MiniMax key)。

    同一个实例服务所有用户，靠 arun(session_id=..., user_id=...) 隔离各自的会话历史。
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
            instructions=CHAT_INSTRUCTIONS,
            tools=[bind_user],  # 绑定能力（工具内强校验，查得到才写库）
            add_history_to_context=True,  # 把最近几轮对话带进上下文 -> 多轮记忆
            num_history_runs=5,
            markdown=True,
            telemetry=False,  # 关闭遥测，避免多余外网调用
        )
    return _agent


async def astream_reply(
    message: str,
    session_id: str,
    user_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """把一段用户消息变成一串「正文增量」。

    :param message: 用户输入的文本
    :param session_id: 会话 ID（同一 session 内多轮连续），企微场景用发送者 userid
    :param user_id: 用户 ID（用于跨会话的用户级隔离），可与 session_id 相同
    :yield: 正文增量字符串（已剥离 <think> 推理内容）
    """
    agent = get_agent()
    try:
        async for event in agent.arun(
            message,
            stream=True,
            session_id=session_id,
            user_id=user_id,
        ):
            if event.event == RunEvent.run_content and event.content:
                yield event.content
    except Exception as e:  # noqa: BLE001 -- 兜底：任何异常都回一句友好提示，不让机器人卡死
        yield f"\n\n（小鱼开小差了，稍后再试试～ 错误：{e}）"


# ── 离线冒烟测试：命令行直接对话，不依赖企业微信 ──
if __name__ == "__main__":
    import asyncio

    async def _smoke() -> None:
        sid = "smoke-test"
        turns = [
            "你是谁？",
            "我叫小王，记住我。",
            "我刚才说我叫什么名字？",  # 验证多轮记忆
        ]
        for i, msg in enumerate(turns, 1):
            print(f"\n\033[36m[你 #{i}]\033[0m {msg}")
            print("\033[32m[小鱼]\033[0m ", end="", flush=True)
            got = []
            async for delta in astream_reply(msg, session_id=sid, user_id=sid):
                got.append(delta)
                print(delta, end="", flush=True)
            print()
            full = "".join(got)
            leaked = "<think>" in full or "</think>" in full
            print(f"\033[90m  (len={len(full)}, think泄漏={leaked})\033[0m")

    asyncio.run(_smoke())
