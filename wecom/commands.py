"""
机器人指令路由 -- 关键词 / 斜线命令的集中注册与分发

所有「确定性指令」在此注册；bot.py 只做一次 dispatch() 调用，不含任何指令逻辑。

新增指令步骤：
  1. 实现 async _cmd_xxx(ws_client, frame, identity) 函数
  2. 在 _ROUTES 中添加触发词 -> 函数的映射
"""
from __future__ import annotations

import os

from aibot import generate_req_id
from models import get_db
from repositories import users as users_repo
from wecom import cards, notify


async def _reply_text(ws_client, frame, text: str) -> None:
    """发送一条纯文本回复（企微无 reply_text，用单帧 reply_stream 模拟）。"""
    await ws_client.reply_stream(frame, generate_req_id("cmd"), text, True)

OA_URL = "https://oa.nevermindcoffee.cn/pm/"

# 运行时检查（不能用模块级常量：bot.py 先 import 再加载 .env.dev，常量会永远为 False）
def _is_dev() -> bool:
    return os.environ.get("FLASK_ENV") == "development"

# 内存切换表： wecom_userid -> 覆盖的 identity dict。进程重启后清空。
_IMPERSONATION: dict[str, dict] = {}


def apply_impersonation(wecom_userid: str, identity: dict) -> dict:
    """bot.py 入口调用：若存在 dev 切换，返回覆盖后的 identity。"""
    override = _IMPERSONATION.get(wecom_userid)
    if override is None:
        return identity
    return override


# ── 测试卡（开发调试用） ─────────────────────────────────────────────

async def _cmd_test_text(ws_client, frame, identity):
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


async def _cmd_test_news(ws_client, frame, identity):
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


async def _cmd_test_button(ws_client, frame, identity):
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


async def _cmd_test_vote(ws_client, frame, identity):
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
        mode=0,
        card_action=cards.action_jump("https://example.com"),
    )
    await ws_client.reply_template_card(frame, card)


async def _cmd_test_multiple(ws_client, frame, identity):
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


# ── 开发调试：切换用户身份 ─────────────────────────────────────────────

async def _cmd_su(ws_client, frame, identity, content: str):
    """/su <username|off> — [DEV ONLY] 切换为指定系统用户。

    /su <username>  切换到该用户
    /su off         取消切换，恢复原始身份
    /su             显示当前切换状态
    """
    if not _is_dev():
        await _reply_text(ws_client, frame, "该命令仅在开发环境可用。")
        return

    wecom_userid = frame.get("body", {}).get("from", {}).get("userid", "") or "anon"
    arg = content[len("/su"):].strip()

    # 查看当前状态
    if not arg:
        current = _IMPERSONATION.get(wecom_userid)
        if current:
            await _reply_text(
                ws_client, frame,
                f"[DEV] 当前切换为：{current['display_name']} (@{current['username']})\n"
                "  /su off  取消切换",
            )
        else:
            await _reply_text(
                ws_client, frame,
                "[DEV] 未切换，使用原始身份。\n  /su <username>  切换用户",
            )
        return

    # 取消切换
    if arg.lower() in ("off", "reset", "exit"):
        _IMPERSONATION.pop(wecom_userid, None)
        await _reply_text(ws_client, frame, "[DEV] 已退出用户切换，恢复原始身份。")
        return

    # 切换到指定用户
    conn = None
    try:
        conn = get_db()
        user = users_repo.get_by_username(conn, arg)
        if user is None:
            await _reply_text(ws_client, frame, f"[DEV] 未找到用户「{arg}」，请检查 username。")
            return
        overridden = {
            "bound": True,
            "id": user.get("id"),
            "display_name": user.get("display_name") or user.get("username") or "",
            "username": user.get("username") or "",
            "role": user.get("role") or "",
            "_impersonated": True,  # 供日志区分
        }
        _IMPERSONATION[wecom_userid] = overridden
        await _reply_text(
            ws_client, frame,
            f"[DEV] 已切换为：{overridden['display_name']} (@{arg})\n"
            "  /su off  取消切换",
        )
    except Exception as exc:
        await _reply_text(ws_client, frame, f"[DEV] 查询失败：{exc}")
    finally:
        if conn is not None:
            conn.close()


# ── 斜线命令（正式功能） ─────────────────────────────────────────────

async def _cmd_due(ws_client, frame, identity):
    """/到期 -- 查询当前用户截止日 ≤ 明天的任务，回复汇总卡片。"""
    user_id = identity.get("id")
    if not user_id:
        await _reply_text(ws_client, frame, "您尚未绑定账号，无法查询任务。")
        return
    await notify.reply_due_card_for_user(ws_client, frame, user_id)


# ── 路由表 ───────────────────────────────────────────────────────────
# 格式：触发词（完整匹配） -> handler
_ROUTES: dict[str, object] = {
    # 测试卡
    "测试文本卡":   _cmd_test_text,
    "测试图文卡":   _cmd_test_news,
    "测试按钮卡":   _cmd_test_button,
    "测试投票卡":   _cmd_test_vote,
    "测试多选卡":   _cmd_test_multiple,
    # 斜线命令（首选 /xxx，中文关键词保留作为别名）
    "/到期":        _cmd_due,
    "/due":         _cmd_due,
    "/到期任务":     _cmd_due,
    "/我的到期":     _cmd_due,
}


async def dispatch(content: str, ws_client, frame, identity: dict) -> bool:
    """尝试匹配并执行指令。

    已处理 -> 返回 True（调用方应直接 return）
    未匹配 -> 返回 False（调用方继续走 Agent）
    """
    # 带参数的前缀命令（只有 dev 环境开放）
    if content.startswith("/su") and (len(content) == 3 or content[3] == " "):
        await _cmd_su(ws_client, frame, identity, content)
        return True

    handler = _ROUTES.get(content)
    if handler is None:
        return False
    await handler(ws_client, frame, identity)
    return True
