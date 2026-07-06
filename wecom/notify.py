"""
企业微信到期提醒 -- 领域逻辑

只管「该提醒谁、提醒什么、提醒过没有」；所有 SQL 都下沉到 repositories/。
bot.py 负责把这里的结果通过 WSClient 发出去。
"""
from collections import defaultdict

from repositories import tasks as tasks_repo
from repositories import alerts as alerts_repo
from repositories import users as users_repo
from wecom import cards

DUE_SOON_ALERT_TYPE = "due_soon_wecom"
OA_URL = "https://oa.nevermindcoffee.cn/pm/"


def resolve_recipients(conn, task):
    """任务的 assignee_id + collaborator_ids → 已绑定企微的收件人列表。

    领域职责：从任务字段里解析出「涉及哪些人」（负责人 + 协作者，去重）；
    「这些人谁绑了企微」交给 users_repo 查。
    返回 [(internal_user_id, wecom_userid, display_name), ...]
    """
    ids = set()
    if task.get("assignee_id"):
        ids.add(task["assignee_id"])
    for cid in (task.get("collaborator_ids") or "").split(","):
        cid = cid.strip()
        if cid:
            ids.add(cid)
    users = users_repo.find_bound(conn, ids)
    return [(u["id"], u["wecom_userid"], u["display_name"]) for u in users]


def _due_title_message(task):
    """拼这条到期提醒落库用的标题与正文（领域文案）。"""
    title = "任务即将到期"
    message = f"「{task['name']}」({task['project_name']}) 截止日期 {task['end_date']}"
    return title, message


def build_due_card(tasks):
    """将多个到期任务合并成一张文本通知卡片（点击跳转 OA）。"""
    n = len(tasks)
    rows = [
        cards.kv(t["name"], t["end_date"])
        for t in tasks[:4]
    ]
    if n > 4:
        rows.append(cards.kv("……", f"另有 {n - 4} 个，点击查看全部"))
    card = cards.text_notice(
        title="任务即将到期提醒",
        emphasis=(str(n), "个任务即将到期"),
        horizontal=rows,
        action_url=OA_URL,
    )
    return {"msgtype": "template_card", "template_card": card}


async def reply_due_card_for_user(ws_client, frame, user_id):
    """查当前用户的到期任务，回复一张卡片（供 bot.py 关键词触发调用）。"""
    from datetime import date, timedelta
    from models import get_db

    conn = get_db()
    try:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        all_tasks = tasks_repo.find_open_by_user(conn, user_id)
    finally:
        conn.close()

    due_tasks = [t for t in all_tasks if t.get("end_date") and t["end_date"] <= tomorrow]
    if not due_tasks:
        card = cards.text_notice(
            title="暂无即将到期的任务",
            action_url=OA_URL,
        )
    else:
        card = build_due_card(due_tasks)["template_card"]
    await ws_client.reply_template_card(frame, card)


async def run_due_check(ws_client, logger=None):
    """完整跑一遍到期检查：找到期任务 → 按收件人聚合 → 每人一张卡片。"""
    from models import get_db

    conn = get_db()
    try:
        # 收集每个收件人的「尚未通知」任务
        recipient_tasks: dict[tuple, list] = defaultdict(list)
        for task in tasks_repo.find_due_soon(conn):
            for user_id, wecom_userid, _name in resolve_recipients(conn, task):
                if not alerts_repo.exists_today(conn, task["id"], user_id, DUE_SOON_ALERT_TYPE):
                    recipient_tasks[(user_id, wecom_userid)].append(task)

        # 每个收件人发一张合并卡片
        for (user_id, wecom_userid), pending in recipient_tasks.items():
            try:
                await ws_client.send_message(wecom_userid, build_due_card(pending))
                # 逐条落库，保证下次检查不重复推送
                for task in pending:
                    title, message = _due_title_message(task)
                    alerts_repo.insert(
                        conn, user_id, DUE_SOON_ALERT_TYPE, title, message,
                        task["id"], task["project_id"],
                    )
            except Exception as e:
                if logger:
                    logger.error(f"到期提醒推送失败 user={user_id}: {e}")
    finally:
        conn.close()
