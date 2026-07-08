"""
subtasks 表 -- 数据访问

服务企微小鱼的「任务详情」只读工具：列某个任务下的子任务执行细项清单。
只碰 subtasks，返回 dict 列表；「谁能看这个任务」的可见性由调用方（tasks 层的参与口径）
先行把关，本层只出数据。
"""


def list_by_task(conn, task_id):
    """列一个任务下的全部子任务，按 id 升序（与 Web 端任务详情 SELECT 口径一致）。

    返回 [dict(id, task_id, content, is_done, created_at), ...]。task_id 为空返回 []。
    """
    if not task_id:
        return []
    rows = conn.execute(
        "SELECT * FROM subtasks WHERE task_id=? ORDER BY id", (task_id,)
    ).fetchall()
    return [dict(r) for r in rows]
