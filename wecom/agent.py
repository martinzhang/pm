"""
企业微信 Agent 适配层 -- 把 Agno 的「正文增量」适配成企业微信的「全量替换」流式回复

关键差异：
- agent.astream_reply() 吐的是增量(delta)，和 Web SSE 一样天然
- 企业微信 reply_stream(frame, stream_id, content, finish) 是「全量替换」语义：
  每次传当前累计的完整内容，客户端渲染最新值，最后一帧 finish=True 收尾

所以本层负责：累积增量 -> 按字数/时间节流 -> 全量下发。
把这个「怪癖」隔离在企微侧，agent/ 包保持框架无关。

企微机器人的所有文本消息都经由本层进入 Agent（聊天、绑定等都靠对话+工具完成，
不再有关键字匹配）。
"""
import time
from typing import Any, Dict, Optional

from aibot import generate_req_id
from loguru import logger

from agent.core import astream_reply

# 节流参数：累计新增 ≥ FLUSH_CHARS 字，或距上次下发 ≥ FLUSH_INTERVAL 秒，就推一帧
FLUSH_CHARS = 40
FLUSH_INTERVAL = 0.5
# 首字延迟期间的占位提示（全量替换语义，真正内容一到就覆盖它）
THINKING_PLACEHOLDER = "正在思考…"
# 空回复兜底
EMPTY_FALLBACK = "（小鱼没有想到要说什么，换个说法试试？）"


async def handle_message(
    ws_client,
    frame,
    text: str,
    session_id: str,
    user_id: Optional[str] = None,
    identity: Optional[Dict[str, Any]] = None,
) -> None:
    """接收一条用户文本，交给 Agno Agent，流式回复到企业微信。

    :param ws_client: aibot WSClient 实例
    :param frame: 收到的原始 WebSocket 帧（透传 req_id）
    :param text: 用户消息文本
    :param session_id: 会话 ID（企微场景用发送者 userid，实现多轮记忆）
    :param user_id: 用户 ID，默认与 session_id 相同；工具靠它拿到当前企微身份
    :param identity: 当前对话者身份（已绑定/未绑定 + 名字），透传给 Agent 做区分对待
    """
    stream_id = generate_req_id("stream")
    log = logger.bind(uid=user_id or session_id or "-")

    # 先发占位，降低首字延迟的等待感；后续真正内容会全量覆盖它
    try:
        await ws_client.reply_stream(frame, stream_id, THINKING_PLACEHOLDER, False)
    except Exception:
        log.warning("发送占位帧失败（忽略，不影响后续内容）")

    started = time.monotonic()
    first_token_ts = None    # 首字到达时间，用于观测首字延迟
    full = ""
    last_sent = ""           # 上次真正发出去的内容，避免重复推同样内容
    last_flush_len = 0       # 上次下发时的正文长度
    last_flush_ts = time.monotonic()

    async for delta in astream_reply(
        text, session_id=session_id, user_id=user_id, identity=identity
    ):
        full += delta
        if first_token_ts is None:
            first_token_ts = time.monotonic()
        # lstrip 掉 MiniMax 剥 <think> 后残留的前导空行；全量语义下每帧重算，幂等
        display = full.lstrip()
        if not display:
            continue
        now = time.monotonic()
        grew = len(display) - last_flush_len
        if grew >= FLUSH_CHARS or (now - last_flush_ts) >= FLUSH_INTERVAL:
            if display != last_sent:
                try:
                    await ws_client.reply_stream(frame, stream_id, display, False)
                    last_sent = display
                except Exception:
                    log.warning("发送流式增量帧失败（忽略，等收尾帧重试）")
                last_flush_len = len(display)
                last_flush_ts = now

    # 收尾帧：finish=True 关闭流式（即使内容与上次相同也要发，用于结束）
    final = full.lstrip() or EMPTY_FALLBACK
    try:
        await ws_client.reply_stream(frame, stream_id, final, True)
    except Exception:
        log.exception("发送最终回复失败")

    # 回复完成的可观测指标：首字延迟 + 总耗时 + 字数，便于上线后调优
    first_latency = (first_token_ts - started) if first_token_ts else -1
    log.info(
        "回复完成: chars={} first_latency={:.2f}s total={:.2f}s",
        len(final), first_latency, time.monotonic() - started,
    )
