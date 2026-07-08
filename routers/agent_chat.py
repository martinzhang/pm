import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from deps import get_current_user
from agent.core import astream_reply

router = APIRouter()


def _last_user_message(messages) -> str:
    """取「最新一条用户消息」。Agno 自带多轮记忆(按 session_id 存 Postgres)，
    只需把最后一句用户输入交给它，历史由 Agent 自己带。逻辑照搬旧 pm_agent。"""
    for m in reversed(messages or []):
        if isinstance(m, dict) and m.get("role") == "user":
            text = (m.get("content") or "").strip()
            if text:
                return text
    return ""


# 会话「话题句柄」：前端 /new 时生成，只允许字母数字、长度受限。
# 前端只持有这个句柄(不含 uid)，session_id 由后端拼成 web-{uid}-{topic}，
# 故前端无从借它读到别人的会话记忆。
_TOPIC_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")


def _resolve_session_id(topic, user_id) -> str:
    """由「话题句柄」拼出可信的 session_id。

    契约：session_id = "web-{uid}"（默认会话）或 "web-{uid}-{topic}"（/new 切出的新会话）。
    - uid 段【永远】用后端认证得到的 user_id，前端不经手，天然无法读到他人记忆。
    - topic 经白名单校验：合法就隔出一条新会话；空/非法则回落默认会话，
      与老客户端(不传 topic)天然兼容。
    """
    base = f"web-{user_id}"
    if isinstance(topic, str) and _TOPIC_RE.match(topic):
        return f"{base}-{topic}"
    return base


@router.post("/api/agent/chat")
async def api_agent_chat(request: Request):
    """网页端聊天入口：对接 Agno Agent，SSE 流式返回。

    请求体沿用 {"messages": [{role, content}, ...]}。身份取自 nginx 认证头(经 deps)，
    网页用户天然「已绑定」，可直接调用只读 PM 工具。
    """
    # 认证：这条路由归 FastAPI 管、不经 Flask 的 before_request，故显式取当前用户。
    user = get_current_user(request)

    data = await request.json()
    messages = data.get("messages", [])
    message = _last_user_message(messages)
    if not message:
        # 与旧版一致：空消息返回 400 JSON
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': '消息不能为空'})}\n\n", "data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    # 网页用户天然「已绑定」：用 user 构造 Agno 侧约定的身份契约(见 agent/core.py 文档)。
    identity = {
        "bound": True,
        "id": user["id"],
        "display_name": user.get("name") or user.get("username") or "",
        "username": user.get("username") or "",
        "role": user.get("role") or "member",
    }
    # session_id 用 web-{uid}，与企微渠道天然隔离，各存各的多轮记忆。
    # 前端可带 topic 句柄(/new 生成)切「话题」；uid 段恒由后端拼，前端不经手。
    session_id = _resolve_session_id(data.get("topic"), user["id"])

    async def gen():
        try:
            async for delta in astream_reply(
                message, session_id=session_id, user_id=user["id"], identity=identity
            ):
                if delta:
                    yield f"data: {json.dumps({'content': delta})}\n\n"
        except Exception as e:  # noqa: BLE001 -- astream_reply 已兜底，这里再兜一层
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
