"""
统一日志配置 -- 基于 loguru，供企微 bot（及未来的其它入口）复用。

为什么用 loguru：
- enqueue=True：写盘在后台线程完成，不阻塞 bot 的 asyncio 事件循环
- rotation/retention/compression：一行搞定日志轮转、保留、压缩
- logger.bind(uid=...)：把企微 userid 绑进每行日志，一个用户的整段对话可 grep

用法：进程启动时调一次 setup()，各模块直接 `from loguru import logger`。

安全约定：
- 生产文件日志 diagnose=False —— 不把局部变量（可能含 API key / 用户消息）写进栈
- 记录用户消息时请自行截断（见 truncate()），避免超长与敏感内容整段落盘
"""
from pathlib import Path
import sys

from loguru import logger

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 控制台/文件统一格式；{extra[uid]} 是当前对话者的企微 userid（无则为 "-"）
_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | "
    "{name}:{function}:{line} | uid={extra[uid]} | {message}"
)

_configured = False


def setup(console: bool = True, level: str = "INFO") -> None:
    """配置全局 logger。幂等：重复调用只生效第一次。

    :param console: 是否同时输出到 stderr（前台运行/开发时看得见）
    :param level: 控制台与主文件的最低级别
    """
    global _configured
    if _configured:
        return

    logger.remove()  # 去掉 loguru 默认的 stderr sink，避免重复输出

    # 给 {extra[uid]} 一个兜底值，未 bind(uid=...) 的日志也不会 KeyError
    logger.configure(extra={"uid": "-"})

    if console:
        logger.add(
            sys.stderr,
            level=level,
            format=_FORMAT,
            enqueue=True,
        )

    # 主日志：全量（INFO+），自动轮转 + 保留 + 压缩
    logger.add(
        LOG_DIR / "bot.log",
        level=level,
        format=_FORMAT,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,  # 生产：不展开局部变量，防止密钥/用户内容落盘
        encoding="utf-8",
    )

    # 错误日志：只收 ERROR+，出事只翻这一个；保留更久，允许变量展开便于定位
    logger.add(
        LOG_DIR / "bot.error.log",
        level="ERROR",
        format=_FORMAT,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=True,
        encoding="utf-8",
    )

    _configured = True


def truncate(text: str, limit: int = 50) -> str:
    """截断用户内容用于日志：超长截断并标注原始长度，避免整段敏感内容落盘。"""
    if text is None:
        return ""
    text = text.replace("\n", " ")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…(共{len(text)}字)"
