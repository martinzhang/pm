"""
AI 大脑 -- 框架无关的 Agno Agent（MiniMax 模型）

对外只暴露两个入口：
- get_agent()      构建/获取单例 Agent
- astream_reply()  把一段用户消息流式转成「正文增量」

惰性导入(PEP 562)：`import agent` 不会立即加载 agno 栈，也避免
`python -m agent.core` 时的重复导入警告；真正访问属性时才加载 core。
"""
__all__ = ["astream_reply", "get_agent"]


def __getattr__(name):
    if name in __all__:
        from agent import core
        return getattr(core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
