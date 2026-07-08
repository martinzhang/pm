"""
Agent 工具集 -- 供 Agno Agent 调用的能力(function-calling）

【组织方式】一域一文件（对称 repositories/ 的「一表一文件」）。本 __init__ 是门面：
统一 re-export 全部工具，对外契约就是「from agent.tools import 某工具」——各工具落在
哪个域文件里，调用方无需关心。Agno 按函数名注册工具，拆分不影响 LLM 看到的工具名。

  binding.py       bind_user
  tasks.py         get_my_tasks
  projects.py      get_my_projects / get_project_status
  task_detail.py   get_task_detail
  schedule.py      get_my_schedule
  alerts.py        get_my_alerts
  _shared.py       域间共享 helper（包内私有）

【工具本身的约定】
工具是同步函数；Agno 在 async 运行时会正确调度它们。
`run_context: RunContext` 是 Agno 的内置参数：由框架自动注入、对 LLM 隐藏，
用来拿到调用方在 arun(user_id=..., dependencies=...) 时传入的运行时上下文。

两类工具：
- bind_user：写操作（绑定），仅未绑定用户挂载。安全敏感，写库前强校验（见 binding.py）。
- get_my_* / get_project_status / get_task_detail：只读，仅已绑定用户挂载。靠 dependencies
  里的「当前对话者」身份拿到内部 user id / role，只查「ta 参与的 / ta 自己的」数据，
  天然无越权。

返回约定：工具返回的是「给 LLM 看的紧凑事实文本」（含真实任务名/项目名/日期，逾期已显式标注），
不是给用户的最终话术——语气由 Agent 按人设再组织。查不到就如实说「没有」，绝不编造。
"""
from agent.tools.binding import bind_user
from agent.tools.tasks import get_my_tasks
from agent.tools.projects import get_my_projects, get_project_status
from agent.tools.task_detail import get_task_detail
from agent.tools.schedule import get_my_schedule
from agent.tools.alerts import get_my_alerts

__all__ = [
    "bind_user",
    "get_my_tasks",
    "get_my_projects",
    "get_project_status",
    "get_task_detail",
    "get_my_schedule",
    "get_my_alerts",
]
