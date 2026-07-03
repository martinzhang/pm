"""
projects 表 -- 数据访问

服务企微小鱼的「项目进度」只读工具：按名字模糊找「我参与的」项目、取进度聚合、列任务。
只碰 projects / tasks，返回 dict / list；「谁能看哪个项目」的可见性口径在本层用 SQL 落实
（owner 或有我负责/协作的任务；admin 放宽到全部活跃项目），与 Web 端 api_list_projects 一致。
"""


def find_participating_by_name(conn, user_id, is_admin, name, limit=5):
    """按项目名模糊查「当前用户参与的」活跃项目。

    参与口径：owner_id=我 OR 项目下有我负责/协作的任务；admin 放宽到全部活跃项目。
    name 为空则不加名字过滤（返回参与的活跃项目，供「我有哪些项目」之类兜底）。
    返回 [dict(id, name, status, deadline, owner_name, ...), ...]，按 updated_at 倒序。
    """
    conds = ["status='active'"]
    args = []
    if name:
        conds.append("name LIKE ?")
        args.append(f"%{name}%")
    if not is_admin:
        uid_like = f"%{user_id}%"
        conds.append(
            "(owner_id=? "
            "OR id IN (SELECT DISTINCT project_id FROM tasks "
            "          WHERE assignee_id=? OR collaborator_ids LIKE ?))"
        )
        args.extend([user_id, user_id, uid_like])
    q = "SELECT * FROM projects WHERE " + " AND ".join(conds)
    q += " ORDER BY updated_at DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def progress_summary(conn, pid):
    """项目的进度聚合：任务总数 / 已完成数(progress=100) / 平均进度。

    返回 {"total": int, "done": int, "avg_progress": int}。
    """
    s = conn.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN progress=100 THEN 1 ELSE 0 END) as done, "
        "COALESCE(AVG(progress),0) as avg FROM tasks WHERE project_id=?",
        (pid,),
    ).fetchone()
    return {
        "total": s["total"],
        "done": s["done"] or 0,
        "avg_progress": round(s["avg"]),
    }


def list_tasks(conn, pid):
    """列一个项目下的全部任务，按截止日期升序（无截止日排最后）。

    返回 [dict(...task 列...), ...]。
    """
    rows = conn.execute(
        "SELECT * FROM tasks WHERE project_id=? "
        "ORDER BY COALESCE(NULLIF(end_date,''),'9999-12-31') ASC, sort_order, id",
        (pid,),
    ).fetchall()
    return [dict(r) for r in rows]
