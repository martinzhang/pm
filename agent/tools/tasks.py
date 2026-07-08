"""
工具·任务域（只读）

服务「我手上有什么任务」这类问题：靠当前对话者身份查 ta 参与的未完成任务，天然无越权。
返回给 LLM 看的紧凑任务清单（含项目/进度/阶段/截止，逾期已显式标注）；查不到就说没有。
"""
from datetime import date

from models import get_db
from repositories import tasks as tasks_repo

from agno.run import RunContext

from agent.tools._shared import _current_user, _fmt_task_line


def get_my_tasks(run_context: RunContext) -> str:
    """查当前同事手上「未完成」的任务（ta 负责的 + ta 参与协作的）。

    当同事问「我手上有什么任务 / 我有几个逾期 / 我这周/最近要交什么 / 我的进度」时调用。
    返回任务清单（含项目、进度、阶段、截止日期，逾期会标注）。若要按「本周/今天」等时间
    范围筛选，你可依据清单里的截止日期和当前日期自行判断，不必再次调用。

    Returns:
        任务清单文本，供你按需组织后转达。
    """
    ident = _current_user(run_context)
    uid = ident.get("id")
    if not uid:
        return "没拿到你的系统身份（可能还没绑定），暂时查不了你的任务。"

    conn = get_db()
    try:
        rows = tasks_repo.find_open_by_user(conn, uid)
    finally:
        conn.close()

    if not rows:
        return "你名下没有未完成的任务，手头很清爽 🎉。"

    today = date.today().isoformat()
    overdue = [t for t in rows if (t.get("end_date") or "") and t["end_date"] < today]
    lines = [_fmt_task_line(t, today) for t in rows]
    head = f"共 {len(rows)} 个未完成任务" + (f"，其中 {len(overdue)} 个已逾期" if overdue else "") + "："
    return head + "\n" + "\n".join(lines)
