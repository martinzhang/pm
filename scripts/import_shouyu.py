"""One-off import: 奈娃咖啡线下部门手语微课堂 project + tasks."""
import sqlite3
from datetime import datetime

DB = "/home/nmcafe/projects/projects.db"
UID = "user_1775197051721_jv8x8"
UNAME = "李俊岩(俊岩)"
USERNAME = "lijunyan"

PHASE = {"概念": "concept", "设计": "design", "打样": "prototype",
         "评审": "review", "量产": "production", "质检": "qc", "交付": "shipped"}
PRIO = {"紧急": "urgent", "高": "high", "中": "medium", "低": "low"}

# (name, phase_cn, assignee_cn, priority_cn, start, end, progress)
TASKS = [
    ("手语微课堂活动流程确认", "概念", UNAME, "紧急", "2026-04-17", "2026-04-17", 100),
    ("活动海报文案素材整理", "设计", UNAME, "紧急", "2026-04-18", "2026-04-18", 100),
    ("活动场地确认", "概念", UNAME, "紧急", "2026-04-19", "2026-04-19", 100),
    ("活动招募发布", "概念", "", "紧急", "2026-04-21", "2026-04-29", 0),
    ("活动海报设计", "设计", UNAME, "紧急", "2026-04-20", "2026-04-21", 0),
    ("参加活动人员名单确认", "概念", UNAME, "高", "2026-04-28", "2026-04-28", 0),
    ("店长及咖啡师培训", "交付", UNAME, "高", "2026-04-23", "2026-04-28", 10),
    ("活动物料采买", "概念", UNAME, "高", "2026-04-29", "2026-04-29", 0),
    ("店长与咖啡师试讲", "交付", UNAME, "高", "2026-04-29", "2026-04-29", 20),
    ("南昌大学4月手语微课堂", "交付", UNAME, "高", "2026-04-30", "2026-04-30", 0),
    ("活动结束复盘", "概念", UNAME, "中", "2026-04-30", "2026-04-30", 0),
    ("五月第一周课堂", "概念", UNAME, "中", "2026-05-06", "2026-05-10", 0),
    ("五月第一周活动名单及教学内容确认", "交付", UNAME, "中", "2026-05-06", "2026-05-06", 0),
    ("五月第一周课堂活动当天", "交付", "", "中", "2026-05-07", "2026-05-07", 0),
    ("五月第一周活动结束复盘", "交付", UNAME, "中", "2026-05-08", "2026-05-08", 0),
    ("五月第二周课堂", "概念", UNAME, "中", "2026-05-11", "2026-05-17", 0),
    ("五月第二周课堂教案内容", "交付", UNAME, "中", "2026-05-11", "2026-05-12", 0),
    ("五月第二周课堂名单确认", "交付", UNAME, "中", "2026-05-13", "2026-05-13", 0),
    ("五月第二周课堂活动当天", "交付", UNAME, "中", "2026-05-14", "2026-05-14", 0),
    ("五月第三周课堂", "概念", UNAME, "中", "2026-05-18", "2026-05-24", 0),
    ("五月第三周课堂教案内容确认", "概念", UNAME, "中", "2026-05-19", "2026-05-20", 0),
    ("五月第三周活动名单确认", "概念", UNAME, "中", "2026-05-20", "2026-05-20", 0),
    ("五月第三周课堂活动当天", "交付", UNAME, "中", "2026-05-21", "2026-05-21", 0),
    ("五月第四周课堂活动", "概念", UNAME, "中", "2026-05-25", "2026-05-31", 0),
    ("五月第四周课堂教案内容确认", "概念", UNAME, "中", "2026-05-26", "2026-05-27", 0),
    ("五月第四周活动名单确认", "交付", UNAME, "中", "2026-05-27", "2026-05-27", 0),
    ("五月第四周课堂活动当天", "交付", UNAME, "中", "2026-05-28", "2026-05-28", 0),
    ("六月第一周课堂活动", "概念", UNAME, "低", "2026-06-01", "2026-06-07", 0),
    ("六月第一周课堂教案内容确认", "概念", UNAME, "低", "2026-06-02", "2026-06-03", 0),
    ("六月第一周课堂名单确认", "交付", UNAME, "低", "2026-06-03", "2026-06-03", 0),
    ("六月第一周课堂活动当天", "交付", UNAME, "低", "2026-06-04", "2026-06-04", 0),
    ("六月第二周课堂活动", "概念", UNAME, "低", "2026-06-08", "2026-06-14", 0),
    ("六月第二周课堂教案内容确认", "概念", UNAME, "低", "2026-06-09", "2026-06-10", 0),
    ("六月第二周活动名单确认", "交付", UNAME, "低", "2026-06-10", "2026-06-10", 0),
    ("六月第二周课堂活动当天", "交付", UNAME, "低", "2026-06-11", "2026-06-11", 0),
    ("六月第三周课堂活动", "概念", UNAME, "低", "2026-06-15", "2026-06-21", 0),
    ("六月第三周课堂教案内容确认", "概念", UNAME, "低", "2026-06-16", "2026-06-17", 0),
    ("六月第三周活动名单确认", "交付", UNAME, "低", "2026-06-17", "2026-06-17", 0),
    ("六月第三周课堂活动当天", "交付", UNAME, "低", "2026-06-18", "2026-06-18", 0),
    ("六月第四周课堂活动", "概念", UNAME, "低", "2026-06-22", "2026-06-28", 0),
    ("六月第四周课堂教案内容确认", "概念", UNAME, "低", "2026-06-23", "2026-06-24", 0),
    ("六月第四周活动名单确认", "交付", UNAME, "低", "2026-06-24", "2026-06-24", 0),
    ("六月第四周课堂活动当天", "交付", UNAME, "低", "2026-06-25", "2026-06-25", 0),
]

now = datetime.now().isoformat(timespec="seconds")

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys=ON")
cur = conn.cursor()

# Upsert user
cur.execute("INSERT OR IGNORE INTO users(id, username, display_name, role, created_at) VALUES(?,?,?,?,?)",
            (UID, USERNAME, UNAME, "member", now))

# Avoid duplicate project
cur.execute("SELECT id FROM projects WHERE name=?", ("奈娃咖啡线下部门手语微课堂",))
row = cur.fetchone()
if row:
    print(f"Project already exists id={row['id']}, aborting.")
    raise SystemExit(1)

cur.execute("""INSERT INTO projects(name, description, status, color, owner_id, owner_name,
             start_date, deadline, visible_to, created_at, updated_at)
             VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            ("奈娃咖啡线下部门手语微课堂", "", "active", "#95A3B3", UID, UNAME,
             "2026-04-17", "", "", now, now))
pid = cur.lastrowid
print(f"Created project id={pid}")

for i, (name, phase_cn, assignee_cn, prio_cn, s, e, prog) in enumerate(TASKS):
    aid = UID if assignee_cn else ""
    aname = assignee_cn or ""
    cur.execute("""INSERT INTO tasks(project_id, name, description, assignee_id, assignee_name,
                 phase, priority, start_date, end_date, progress, sort_order, depends_on,
                 created_at, updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (pid, name, "", aid, aname, PHASE[phase_cn], PRIO[prio_cn],
                 s, e, prog, i, "", now, now))

conn.commit()
cnt = cur.execute("SELECT COUNT(*) FROM tasks WHERE project_id=?", (pid,)).fetchone()[0]
print(f"Inserted {cnt} tasks.")
conn.close()
