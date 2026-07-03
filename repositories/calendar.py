"""
calendar_events 表 -- 数据访问

服务企微小鱼的「我的日程」只读工具：查某人从某天起的即将到来的日程。
calendar_events 是用户私有的（每条带 user_id），查自己的天然安全。只碰本表，返回 dict 列表。
"""


def find_upcoming_events(conn, user_id, from_date, limit=20):
    """查某人 event_date >= from_date 的日程，按日期、开始时间升序。

    返回 [dict(...event 列...), ...]；user_id 为空返回 []。
    """
    if not user_id:
        return []
    rows = conn.execute(
        "SELECT * FROM calendar_events WHERE user_id=? AND event_date>=? "
        "ORDER BY event_date ASC, start_time ASC LIMIT ?",
        (user_id, from_date, limit),
    ).fetchall()
    return [dict(r) for r in rows]
