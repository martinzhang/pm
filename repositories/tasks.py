"""
tasks 表 -- 数据访问

服务两类读：
- 到期提醒：查「快到期 / 已逾期」的活跃项目任务（find_due_soon）
- 企微小鱼只读工具：查「某个人手上未完成的任务」（find_open_by_user）
只碰 tasks（JOIN projects 取项目名），返回 dict 列表；不决定「提醒谁 / 该不该看」（领域层的事）。
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


def find_open_by_user(conn, user_id):
    """查某人手上「未完成」的任务：负责人是 ta，或 ta 是协作者，且 progress<100。

    JOIN projects 取项目名，按截止日期升序（无截止日排最后）。逾期与否由领域/工具层
    按 end_date 自行判断，本层只出数据。返回 [dict(...task 列..., project_name), ...]。
    user_id 为空直接返回 []。
    """
    if not user_id:
        return []
    uid_like = f"%{user_id}%"
    rows = conn.execute(
        "SELECT t.*, p.name as project_name FROM tasks t "
        "JOIN projects p ON t.project_id=p.id "
        "WHERE (t.assignee_id=? OR t.collaborator_ids LIKE ?) AND t.progress<100 "
        "ORDER BY COALESCE(NULLIF(t.end_date,''),'9999-12-31') ASC, t.id",
        (user_id, uid_like),
    ).fetchall()
    return [dict(r) for r in rows]


def find_participating_by_name(conn, user_id, is_admin, name, project_name=None, limit=5):
    """按任务名模糊查「当前用户能看到的」任务（供任务详情下钻用）。

    可见性口径与 projects.find_participating_by_name 完全一致（任务跟随项目可见性）：
    任务所属项目须是「我参与的活跃项目」——owner_id=我，或项目下有我负责/协作的任务；
    admin 放宽到全部活跃项目。JOIN projects 取项目名，按 updated_at 倒序。
    name 为空返回 []（任务详情必须指名道姓，不做无名兜底）。

    project_name 可选：跨项目重名任务的消歧钥匙——给了就再叠一层项目名模糊过滤，
    把「不同项目下的同名任务」区分开；为空/None 时不限项目（保持原行为）。
    返回 [dict(...task 列..., project_name), ...]。
    """
    if not user_id or not name:
        return []
    conds = ["p.status='active'", "t.name LIKE ?"]
    args = [f"%{name}%"]
    if project_name:
        conds.append("p.name LIKE ?")
        args.append(f"%{project_name}%")
    if not is_admin:
        uid_like = f"%{user_id}%"
        conds.append(
            "(p.owner_id=? "
            "OR t.project_id IN (SELECT DISTINCT project_id FROM tasks "
            "                    WHERE assignee_id=? OR collaborator_ids LIKE ?))"
        )
        args.extend([user_id, user_id, uid_like])
    q = (
        "SELECT t.*, p.name as project_name FROM tasks t "
        "JOIN projects p ON t.project_id=p.id "
        "WHERE " + " AND ".join(conds) + " ORDER BY t.updated_at DESC LIMIT ?"
    )
    args.append(limit)
    rows = conn.execute(q, args).fetchall()
    return [dict(r) for r in rows]
