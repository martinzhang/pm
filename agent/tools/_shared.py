"""
工具集·域间共享件（包内私有，勿从外部 import）

三样横切件，被多个域工具（tasks / projects / task_detail）共用，独立成模块，
避免任一工具文件为了拿这几个 helper 而反向依赖另一个工具文件：

- _current_user：从 run_context.dependencies 取「当前对话者」身份（读身份契约）。
- _fmt_task_line：把一条任务压成一行给 LLM 看（名称/项目/进度/阶段/截止）。
- _PRIORITY_MAP：优先级 code → 中文名。

下划线前缀 = 约定的包内私有；对外只暴露 __init__.py re-export 的 7 个工具。
"""
from typing import Any, Dict

from agno.run import RunContext

from config import PHASE_MAP, PRIORITIES

_PRIORITY_MAP = dict(PRIORITIES)


def _current_user(run_context: RunContext) -> Dict[str, Any]:
    """从 run_context.dependencies 取「当前对话者」身份（已绑定才有 id）。

    不 import agent.core（避免循环依赖）——键名「当前对话者」是与 core 约定的契约。
    缺省返回 {}，工具据此判断「没拿到身份」。
    """
    deps = getattr(run_context, "dependencies", None) or {}
    ident = deps.get("当前对话者") or {}
    return ident if isinstance(ident, dict) else {}


def _fmt_task_line(t: Dict[str, Any], today: str) -> str:
    """把一条任务压成一行给 LLM：名称 | 项目 | 进度 | 阶段 | 截止(逾期标注)。"""
    phase = PHASE_MAP.get(t.get("phase"), t.get("phase") or "")
    prio = _PRIORITY_MAP.get(t.get("priority"), "")
    end = t.get("end_date") or ""
    due = ""
    if end:
        overdue = end < today and (t.get("progress") or 0) < 100
        due = f"｜截止{end}" + ("（已逾期）" if overdue else "")
    proj = t.get("project_name")
    proj_str = f"｜项目「{proj}」" if proj else ""
    prio_str = f"｜{prio}优先级" if prio and prio != "中" else ""
    return f"「{t.get('name','')}」{proj_str}｜进度{t.get('progress',0)}%｜{phase}{prio_str}{due}"
