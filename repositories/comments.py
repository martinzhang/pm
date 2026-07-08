"""
comments 表 -- 数据访问

服务企微小鱼的「任务详情」只读工具：列某个任务下的评论（人在任务上留下的讨论/决策）。
只碰 comments，返回 dict 列表；「谁能看这个任务」的可见性由调用方（tasks 层的参与口径）
先行把关，本层只出数据。
"""


def list_by_task(conn, task_id):
    """列一个任务下的全部评论，按 created_at 升序（与 Web 端任务详情 SELECT 口径一致）。

    返回 [dict(id, task_id, user_id, user_name, content, created_at), ...]。
    task_id 为空返回 []。
    """
    if not task_id:
        return []
    rows = conn.execute(
        "SELECT * FROM comments WHERE task_id=? ORDER BY created_at", (task_id,)
    ).fetchall()
    return [dict(r) for r in rows]
