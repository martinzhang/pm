"""
PM Agent Blueprint -- 网页端对接 Agno Agent 的 SSE 流式聊天

背景：老板要求砍掉企业微信渠道、改用网页对话，但后端仍复用已在企微侧验证过的
Agno Agent（agent/core.py 的 astream_reply）。本蓝图【不改动】blueprints/ai.py，
只新增一条网页专用的 SSE 路由，把 Agno 的「正文增量」桥接成浏览器可读的
text/event-stream，线格式与 ai.py 的 /api/chat 完全一致（data: {"content": ...} /
data: [DONE] / data: {"error": ...}），前端 reader 逻辑无需改动。

与企微渠道的关键差异（都朝「更简单」的方向）：
- 身份：网页用户经 nginx 认证、已在 users 表里，天然「已绑定」，直接用 g.user 构造
  identity；不需要 bind_user 那套绑定引导。
- 能力：只读。Agno 侧只挂载 get_my_* / get_project_status 等只读工具（见 agent/core.py
  的 _build_tools）。写操作仍走 ai.py 的「执行:」→ propose/apply 流程，本蓝图不涉及。
- 记忆：多轮对话历史由 Agno 存在 Postgres（add_history_to_context），按 session_id
  隔离。所以本蓝图每次只把「最新一条用户消息」交给 Agent，历史由 Agent 自己带。

── 技术要点：async 生成器 → 同步 SSE 的桥接 ──
Agno 的 astream_reply 是 async 生成器，且底层 AsyncPostgresDb(asyncpg) 的连接池
【绑定在创建它的事件循环上】。Flask（同步 gunicorn worker）若为每个请求新建
event loop，第二个请求就会命中「attached to a different loop」。因此每个 worker
进程常驻【一个】后台事件循环线程，Agent 单例与 pg 连接池都绑在它上面、跨请求复用；
请求侧通过 run_coroutine_threadsafe + 线程安全 queue 把增量捞回同步生成器。
"""
import asyncio
import json
import queue
import threading

from flask import Blueprint, request, jsonify, g, Response, stream_with_context

from agent.core import astream_reply

bp = Blueprint("pm_agent", __name__)


# ── 常驻后台事件循环（每个 worker 进程一个）──
#
# asyncpg 连接池绑定在创建它的 loop 上：必须让所有 Agent 运行都发生在同一个 loop，
# 才能跨请求复用连接池。这里用一个 daemon 线程 run_forever 托管该 loop。
_loop = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """惰性启动并返回本进程常驻的后台事件循环。双重检查加锁，保证只启一个。"""
    global _loop
    if _loop is None:
        with _loop_lock:
            if _loop is None:
                loop = asyncio.new_event_loop()
                t = threading.Thread(
                    target=loop.run_forever,
                    name="pm-agent-loop",
                    daemon=True,
                )
                t.start()
                _loop = loop
    return _loop


def _sse_from_agent(message, session_id, user_id, identity):
    """把 astream_reply（async 生成器）跑在常驻 loop 上，产出同步的 SSE 数据帧。

    线格式与 blueprints/ai.py 的 /api/chat 保持一致，前端无需区分来源：
      data: {"content": "..."}   逐段正文增量
      data: {"error": "..."}     出错（Agent 内部已兜底，这里再兜一层）
      data: [DONE]               收尾
    """
    loop = _get_loop()
    q: "queue.Queue" = queue.Queue()  # 无界：SSE 增量都是小段文本，且上游受 MiniMax 网络限速，不会暴涨

    async def _pump():
        # 在后台 loop 里消费 async 生成器，把每段增量塞进线程安全队列。
        try:
            async for delta in astream_reply(
                message, session_id=session_id, user_id=user_id, identity=identity
            ):
                q.put(("data", delta))
        except Exception as e:  # noqa: BLE001 -- astream_reply 已兜底，这里是最后一道保险
            q.put(("err", str(e)))
        finally:
            q.put(("done", None))

    fut = asyncio.run_coroutine_threadsafe(_pump(), loop)
    try:
        while True:
            kind, payload = q.get()
            if kind == "done":
                break
            if kind == "err":
                yield f"data: {json.dumps({'error': payload})}\n\n"
                break
            if payload:
                yield f"data: {json.dumps({'content': payload})}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        # 客户端中途断开时，同步生成器被 GC 会在此抛 GeneratorExit：取消后台协程，
        # 避免它继续空跑占着 loop 与 pg 连接。
        if not fut.done():
            fut.cancel()


def _last_user_message(messages):
    """从前端传来的消息列表里取「最新一条用户消息」。

    Agno 自带多轮记忆（按 session_id 存 Postgres），所以只需把最后一句用户输入交给它，
    历史由 Agent 自己带上，无需重复投喂整个 chatHistory。
    """
    for m in reversed(messages or []):
        if isinstance(m, dict) and m.get("role") == "user":
            text = (m.get("content") or "").strip()
            if text:
                return text
    return ""


@bp.route("/api/agent/chat", methods=["POST"])
def api_agent_chat():
    """网页端聊天入口：对接 Agno Agent，SSE 流式返回。

    请求体沿用 /api/chat 的形状 {"messages": [{role, content}, ...]}，便于前端最小改动。
    身份直接取自 g.user（nginx 已认证），网页用户天然「已绑定」，可直接调用只读 PM 工具。
    """
    data = request.get_json(force=True)
    messages = data.get("messages", [])
    message = _last_user_message(messages)
    if not message:
        return jsonify({"error": "消息不能为空"}), 400

    # 网页用户天然「已绑定」：用 g.user 构造 Agno 侧约定的身份契约（见 agent/core.py 文档）。
    identity = {
        "bound": True,
        "id": g.user["id"],
        "display_name": g.user.get("name") or g.user.get("username") or "",
        "username": g.user.get("username") or "",
        "role": g.user.get("role") or "member",
    }
    # session_id 用 web-{uid}，与企微渠道（用企微 userid 作 session）天然隔离，各存各的多轮记忆。
    session_id = f"web-{g.user['id']}"

    return Response(
        stream_with_context(
            _sse_from_agent(message, session_id=session_id, user_id=g.user["id"], identity=identity)
        ),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
