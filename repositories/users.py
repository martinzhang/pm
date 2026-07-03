"""
users 表 -- 数据访问

企业微信绑定相关：按 wecom_userid 反查身份、按 username 写入绑定、批量查已绑定用户。
只碰 users 表，返回 dict / None / list；不做「该不该绑」的判断（那是 wecom/notify.py 的事）。
"""


def get_by_wecom(conn, wecom_userid):
    """反查：这个企业微信 userid 绑定到了哪个系统用户？空入参/未绑定返回 None。

    返回 dict(id, username, display_name, role) 或 None。
    """
    if not wecom_userid:
        return None
    row = conn.execute(
        "SELECT id, username, display_name, role FROM users "
        "WHERE wecom_userid=? AND wecom_userid!=''",
        (wecom_userid,),
    ).fetchone()
    return dict(row) if row else None


def bind_wecom(conn, username, wecom_userid):
    """按 username 查 users 表，写入 wecom_userid。

    成功返回被绑定用户 dict(id, username, display_name)；查无此人返回 None（不写库）。
    返回 dict/None 而非 bool，是为了让上层拿到 display_name，在绑定成功的当轮就能用真名称呼对方。
    """
    row = conn.execute(
        "SELECT id, username, display_name FROM users WHERE username=?", (username,)
    ).fetchone()
    if not row:
        return None
    conn.execute("UPDATE users SET wecom_userid=? WHERE id=?", (wecom_userid, row["id"]))
    conn.commit()
    return dict(row)


def find_bound(conn, user_ids):
    """给定一批系统用户 id，返回其中「已绑定企微」的用户。

    返回 [dict(id, display_name, wecom_userid), ...]；user_ids 为空直接返回 []。
    只管查询，不关心这些 id 从哪来（任务负责人？协作者？那是领域层的事）。
    """
    ids = [i for i in user_ids if i]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, display_name, wecom_userid FROM users "
        f"WHERE id IN ({placeholders}) AND wecom_userid IS NOT NULL AND wecom_userid!=''",
        tuple(ids),
    ).fetchall()
    return [dict(r) for r in rows]
