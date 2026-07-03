"""
企业微信到期提醒 -- 领域逻辑

只管「该提醒谁、提醒什么、提醒过没有」；所有 SQL 都下沉到 repositories/。
bot.py 负责把这里的结果通过 WSClient 发出去。
"""
from repositories import tasks as tasks_repo
from repositories import alerts as alerts_repo
from repositories import users as users_repo

DUE_SOON_ALERT_TYPE = "due_soon_wecom"


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


def build_due_message(task):
    """拼企业微信 markdown 推送体（面向渠道的展示文案）。"""
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": (
                f"### ⏰ 任务即将到期\n"
                f"**{task['name']}**\n"
                f"项目：{task['project_name']}\n"
                f"截止日期：{task['end_date']}\n"
                f"当前进度：{task['progress']}%"
            )
        },
    }


async def run_due_check(ws_client, logger=None):
    """完整跑一遍到期检查：找到期任务 → 逐个收件人查重 → 未通知则推送 + 记录。"""
    from models import get_db

    conn = get_db()
    try:
        for task in tasks_repo.find_due_soon(conn):
            for user_id, wecom_userid, _name in resolve_recipients(conn, task):
                if alerts_repo.exists_today(conn, task["id"], user_id, DUE_SOON_ALERT_TYPE):
                    continue
                try:
                    await ws_client.send_message(wecom_userid, build_due_message(task))
                    title, message = _due_title_message(task)
                    alerts_repo.insert(
                        conn, user_id, DUE_SOON_ALERT_TYPE, title, message,
                        task["id"], task["project_id"],
                    )
                except Exception as e:
                    if logger:
                        logger.error(f"到期提醒推送失败 task={task['id']} user={user_id}: {e}")
    finally:
        conn.close()
