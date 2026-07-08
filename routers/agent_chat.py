import json

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
    session_id = f"web-{user['id']}"

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
