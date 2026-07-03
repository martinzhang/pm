"""
企业微信机器人 -- 消息监听入口

独立进程运行（与 Flask 应用分开），基于 wecom-aibot-python-sdk 的 WebSocket 长连接。
在仓库根目录执行: uv run python -m wecom.bot
- 收到 "hi" 时回复 "hi"（连通性测试）
- 收到 "绑定 <username>" 时把发送者的企业微信 userid 写入 users 表
- 认证成功后启动后台循环，定期检查任务到期情况并主动推送
"""
import asyncio
import os
from pathlib import Path

from aibot import WSClient, WSClientOptions, generate_req_id

from wecom import notify
from models import get_db

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


@ws_client.on("message.text")
async def on_text(frame):
    body = frame.get("body", {})
    content = body.get("text", {}).get("content", "").strip()
    print(f"收到消息: {content}")

    if content.lower() == "hi":
        stream_id = generate_req_id("stream")
        await ws_client.reply_stream(frame, stream_id, "hi", True)
        return

    if content.startswith("绑定 "):
        username = content[len("绑定 "):].strip()
        wecom_userid = body.get("from", {}).get("userid", "")
        stream_id = generate_req_id("stream")
        if not username or not wecom_userid:
            await ws_client.reply_stream(frame, stream_id, "用法: 绑定 你的用户名", True)
            return
        conn = get_db()
        try:
            ok = notify.bind_wecom_user(conn, username, wecom_userid)
        finally:
            conn.close()
        reply_text = f"绑定成功: {username}" if ok else f"未找到用户: {username}"
        await ws_client.reply_stream(frame, stream_id, reply_text, True)


@ws_client.on("error")
def on_error(error):
    print(f"发生错误: {error}")


if __name__ == "__main__":
    ws_client.run()
