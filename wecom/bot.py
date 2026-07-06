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
from loguru import logger

import logconf
from wecom import notify
from wecom import agent as wecom_agent
from wecom import cards
from repositories import users as users_repo

logconf.setup()

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
    log.info(
        "身份解析: bound={} name={}",
        identity.get("bound"),
        identity.get("display_name", ""),
    )

    # ── 卡片效果测试（关键词触发） ──────────────────────────────────
    if content == "测试文本卡":
        card = cards.text_notice(
            title="文本通知卡片",
            desc="这是副标题说明",
            source_desc="PM 系统",
            emphasis=("42", "进行中任务"),
            horizontal=[
                cards.kv("负责人", "张三"),
                cards.kv_link("项目", "NMC 研发", "https://example.com"),
            ],
            jumps=[cards.jump("查看详情", "https://example.com/tasks")],
            action_url="https://example.com/tasks",
        )
        await ws_client.reply_template_card(frame, card)
        return
    elif content == "测试图文卡":
        card = cards.news_notice(
            title="图文展示卡片",
            desc="这是一段图文卡副标题",
            source_desc="PM 系统",
            image_url="https://picsum.photos/seed/pm/800/360",
            vertical=[
                {"title": "版本", "desc": "v2.0.0"},
                {"title": "环境", "desc": "生产"},
            ],
            horizontal=[cards.kv("发布人", "张三")],
            jumps=[cards.jump("查看发布记录", "https://example.com/releases")],
            action_url="https://example.com/releases",
        )
        await ws_client.reply_template_card(frame, card)
        return
    elif content == "测试按钮卡":
        card = cards.button_interaction(
            title="按钮交互卡片",
            desc="请选择操作",
            task_id="btn_test_001",
            horizontal=[cards.kv("任务", "修复登录 Bug")],
            buttons=[
                cards.button("确认完成", key="done", style=cards.BTN_BLUE),
                cards.button("暂缓处理", key="defer", style=cards.BTN_GRAY),
                cards.button("拒绝", key="reject", style=cards.BTN_RED),
            ],
            action_url="https://example.com/tasks",
        )
        await ws_client.reply_template_card(frame, card)
        return
    elif content == "测试投票卡":
        card = cards.vote_interaction(
            title="投票交互卡片",
            desc="请投票选择优先级",
            task_id="vote_test_001",
            question_key="priority",
            options=[
                ("high", "高优先级"),
                ("mid", "中优先级"),
                ("low", "低优先级"),
            ],
            mode=0,  # 单选
            card_action=cards.action_jump("https://example.com"),
        )
        await ws_client.reply_template_card(frame, card)
        return
    elif content == "测试多选卡":
        card = cards.multiple_interaction(
            title="多项选择卡片",
            desc="请选择负责人和截止时间",
            task_id="multi_test_001",
            selects=[
                ("assignee", "负责人", [("u1", "张三"), ("u2", "李四"), ("u3", "王五")]),
                ("due", "截止时间", [("d1", "本周"), ("d2", "下周"), ("d3", "本月")]),
            ],
            card_action=cards.action_jump("https://example.com"),
        )
        await ws_client.reply_template_card(frame, card)
        return
    elif content == "测试到期卡":
        user_id = identity.get("id")
        if not user_id:
            await ws_client.reply_text(frame, "您尚未绑定账号，无法查询任务。")
            return
        await notify.reply_due_card_for_user(ws_client, frame, user_id)
        return
    # ────────────────────────────────────────────────────────────────

    try:
        await wecom_agent.handle_message(
            ws_client, frame, content,
            session_id=wecom_userid, user_id=wecom_userid,
            identity=identity,
        )
    except Exception:
        log.exception("处理消息失败")


@ws_client.on("error")
def on_error(error):
    logger.error("WebSocket 发生错误: {}", error)


if __name__ == "__main__":
    ws_client.run()
