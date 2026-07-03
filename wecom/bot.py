"""
企业微信机器人 -- 消息监听入口

独立进程运行（与 Flask 应用分开），基于 wecom-aibot-python-sdk 的 WebSocket 长连接。
在仓库根目录执行: uv run python -m wecom.bot
- 所有文本消息统一交给 Agno Agent（wecom/agent.py）：聊天、绑定账号等都靠对话+工具完成，
  不再有关键字匹配（"绑定 xxx" 由 Agent 的 bind_user 工具处理）
- 认证成功后启动后台循环，定期检查任务到期情况并主动推送（到期提醒是确定性定时任务，
  不走 Agent）
"""
import asyncio
import os
from pathlib import Path

from aibot import WSClient, WSClientOptions

from wecom import notify
from wecom import agent as wecom_agent
from repositories import users as users_repo

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_LOCAL = REPO_ROOT / ".env.local"

DUE_CHECK_INTERVAL_SECONDS = 30 * 60


def _load_env_local():
    env = {}
    if ENV_LOCAL.exists():
        for line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


_env = _load_env_local()
BOT_ID = os.environ.get("WECHAT_BOT_ID") or _env.get("WECHAT_BOT_ID")
BOT_SECRET = os.environ.get("WECHAT_BOT_SECRET") or _env.get("WECHAT_BOT_SECRET")

ws_client = WSClient(WSClientOptions(bot_id=BOT_ID, secret=BOT_SECRET))


@ws_client.on("authenticated")
def on_authenticated():
    print("机器人已上线")
    asyncio.ensure_future(_due_check_loop())


async def _due_check_loop():
    while True:
        try:
            await notify.run_due_check(ws_client)
        except Exception as e:
            print(f"到期检查出错: {e}")
        await asyncio.sleep(DUE_CHECK_INTERVAL_SECONDS)


def _resolve_identity(wecom_userid):
    """把企微 userid 解析成给 Agent 的通用身份契约。

    已绑定 -> {"bound": True, "display_name", "username", "role"}
    未绑定/查库异常 -> {"bound": False}
    异常时静默降级为未绑定，不阻断聊天。
    """
    from models import get_db

    if not wecom_userid or wecom_userid == "anon":
        return {"bound": False}
    conn = None
    try:
        conn = get_db()
        user = users_repo.get_by_wecom(conn, wecom_userid)
    except Exception as e:
        print(f"身份解析出错: {e}", flush=True)
        user = None
    finally:
        if conn is not None:
            conn.close()
    if not user:
        return {"bound": False}
    return {
        "bound": True,
        "display_name": user.get("display_name") or user.get("username") or "",
        "username": user.get("username") or "",
        "role": user.get("role") or "",
    }


@ws_client.on("message.text")
async def on_text(frame):
    body = frame.get("body", {})
    content = body.get("text", {}).get("content", "").strip()
    print(f"收到消息: {content}")

    if not content:
        return

    # 所有文本统一交给 Agno 小鱼助手：聊天、绑定账号等都靠对话+工具完成。
    # session_id / user_id 用发送者 userid——既实现每人独立的多轮记忆，
    # 也让 bind_user 工具能从 RunContext.user_id 拿到当前企微身份。
    wecom_userid = body.get("from", {}).get("userid", "") or "anon"

    # 反查身份：这个企微 userid 绑没绑系统账号、绑的是谁。作为通用契约传给 Agent，
    # 让它区分「已绑定同事(称呼名字)」和「未绑定(引导绑定)」。DB 访问集中在入口层。
    identity = _resolve_identity(wecom_userid)

    await wecom_agent.handle_message(
        ws_client, frame, content,
        session_id=wecom_userid, user_id=wecom_userid,
        identity=identity,
    )


@ws_client.on("error")
def on_error(error):
    print(f"发生错误: {error}")


if __name__ == "__main__":
    ws_client.run()
