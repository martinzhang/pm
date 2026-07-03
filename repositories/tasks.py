"""
tasks 表 -- 数据访问

目前只服务到期提醒：查「快到期 / 已逾期」的活跃项目任务。
只碰 tasks（JOIN projects 取项目名），返回 dict 列表；不决定「提醒谁」（领域层的事）。
"""
from datetime import date, timedelta


def find_due_soon(conn):
    """查 progress<100 且 end_date 在明天（含）以内的活跃项目任务，包含已逾期的。

    返回 [dict(...task 列..., project_name), ...]。
    """
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    rows = conn.execute(
        "SELECT t.*, p.name as project_name FROM tasks t "
        "JOIN projects p ON t.project_id=p.id "
        "WHERE t.progress<100 AND t.end_date IS NOT NULL AND t.end_date!='' "
        "AND t.end_date<=? AND p.status='active'",
        (tomorrow,),
    ).fetchall()
    return [dict(r) for r in rows]
