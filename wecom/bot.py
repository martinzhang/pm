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

# ── 最先加载环境文件（必须在所有业务模块 import 之前！）───────────────────
# config.py 等在导入时就会读取 os.environ，必须先把环境变量设置好。
# 规则：先找到 .env.dev（开发机），否则用 .env.prod（生产机）。
# 已在 os.environ 里的变量不被覆盖（pm2 直接注入的优先）。
_REPO_ROOT = Path(__file__).resolve().parent.parent
for _f in (_REPO_ROOT / ".env.dev", _REPO_ROOT / ".env.prod"):
    if _f.exists():
        for _line in _f.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip()
            if _k not in os.environ:
                os.environ[_k] = _v
        break
# ──────────────────────────────────────────────────────────────────────────

from aibot import WSClient, WSClientOptions
from loguru import logger

import logconf
from wecom import notify
from wecom import agent as wecom_agent
from wecom import commands
from repositories import users as users_repo

logconf.setup()

REPO_ROOT = _REPO_ROOT
DUE_CHECK_INTERVAL_SECONDS = 30 * 60

BOT_ID = os.environ.get("WECHAT_BOT_ID")
BOT_SECRET = os.environ.get("WECHAT_BOT_SECRET")

ws_client = WSClient(WSClientOptions(bot_id=BOT_ID, secret=BOT_SECRET))


@ws_client.on("authenticated")
def on_authenticated():
    logger.info("机器人已上线，启动到期检查循环")
    asyncio.ensure_future(_due_check_loop())


async def _due_check_loop():
    while True:
        try:
            await notify.run_due_check(ws_client, logger=logger)
        except Exception:
            logger.exception("到期检查循环出错")
        await asyncio.sleep(DUE_CHECK_INTERVAL_SECONDS)


def _resolve_identity(wecom_userid):
    """把企微 userid 解析成给 Agent 的通用身份契约。

    已绑定 -> {"bound": True, "id", "display_name", "username", "role"}
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
    except Exception:
        logger.bind(uid=wecom_userid).exception("身份解析查库出错，降级为未绑定")
        user = None
    finally:
        if conn is not None:
            conn.close()
    if not user:
        return {"bound": False}
    return {
        "bound": True,
        "id": user.get("id"),  # 内部 user id：只读工具按 assignee_id 查「我的任务」必需
        "display_name": user.get("display_name") or user.get("username") or "",
        "username": user.get("username") or "",
        "role": user.get("role") or "",
    }


@ws_client.on("message.text")
async def on_text(frame):
    body = frame.get("body", {})
    content = body.get("text", {}).get("content", "").strip()

    # session_id / user_id 用发送者 userid——既实现每人独立的多轮记忆，
    # 也让 bind_user 工具能从 RunContext.user_id 拿到当前企微身份。
    wecom_userid = body.get("from", {}).get("userid", "") or "anon"
    log = logger.bind(uid=wecom_userid)
    log.info("收到消息: {}", logconf.truncate(content))

    if not content:
        return

    # 反查身份：这个企微 userid 绑没绑系统账号、绑的是谁。作为通用契约传给 Agent，
    # 让它区分「已绑定同事(称呼名字)」和「未绑定(引导绑定)」。DB 访问集中在入口层。
    identity = _resolve_identity(wecom_userid)
    identity = commands.apply_impersonation(wecom_userid, identity)
    log.info(
        "身份解析: bound={} name={} impersonated={}",
        identity.get("bound"),
        identity.get("display_name", ""),
        identity.get("_impersonated", False),
    )

    # ── 指令分发（测试卡 / 斜线命令）─────────────────────────────────
    if await commands.dispatch(content, ws_client, frame, identity):
        return
    # ────────────────────────────────────────────────────────────────

    try:
        # impersonation 时用被切换用户的内部 id 作为 session/user，
        # 避免原用户的历史记忆污染（Agent 会叫错名字）。
        if identity.get("_impersonated"):
            _su_id = str(identity.get("id") or wecom_userid)
            effective_session = f"su_{_su_id}"
            effective_user = _su_id
        else:
            effective_session = wecom_userid
            effective_user = wecom_userid
        await wecom_agent.handle_message(
            ws_client, frame, content,
            session_id=effective_session, user_id=effective_user,
            identity=identity,
        )
    except Exception:
        log.exception("处理消息失败")


@ws_client.on("error")
def on_error(error):
    logger.error("WebSocket 发生错误: {}", error)


if __name__ == "__main__":
    ws_client.run()
