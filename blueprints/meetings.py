"""
Meetings Blueprint -- meeting minutes import, AI analysis, change confirmation
"""
import json, os, re, sys, time, requests
from datetime import datetime, date
from flask import Blueprint, request, jsonify, g
from models import get_db
from config import (
    MINIMAX_API_KEY, MINIMAX_BASE, MINIMAX_MODEL,
    PHASES, PHASE_MAP,
)

bp = Blueprint("meetings", __name__)


def _alog(msg):
    """Stderr log helper -- routed to pm.err by launchd."""
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [analyze] {msg}",
          file=sys.stderr, flush=True)

# Phase-1 text-based file import: markdown / plain text / csv only
EXTRACT_ALLOWED_EXT = {".md", ".txt", ".csv"}
EXTRACT_MAX_CHARS = 500_000


@bp.route("/api/meetings/extract-file", methods=["POST"])
def extract_meeting_file():
    """Parse an uploaded text file (.md / .txt / .csv) and return text for the
    client to drop into the meeting-content textarea. Does not persist anything.
    """
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "请选择文件"}), 400

    filename = f.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in EXTRACT_ALLOWED_EXT:
        return jsonify({"error": "仅支持 .md .txt .csv 格式"}), 400

    raw = f.read()
    if not raw:
        return jsonify({"error": "文件为空"}), 400

    text = None
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="ignore")

    truncated = False
    if len(text) > EXTRACT_MAX_CHARS:
        text = text[:EXTRACT_MAX_CHARS]
        truncated = True

    # Try to guess a title + date from filename, e.g.
    # "纪要_04-22 客户会议. 残障就业与移动咖啡车创新合作.md"
    stem = os.path.splitext(os.path.basename(filename))[0]
    suggested_title = stem
    for pref in ("纪要_", "纪要-", "会议纪要_", "会议纪要-", "Minutes_", "minutes_"):
        if suggested_title.startswith(pref):
            suggested_title = suggested_title[len(pref):]
            break
    suggested_date = None
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", stem)
    if m:
        y, mo, d = m.groups()
        suggested_date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    else:
        m = re.search(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})(?!\d)", stem)
        if m:
            mo, d = m.groups()
            suggested_date = f"{date.today().year:04d}-{int(mo):02d}-{int(d):02d}"

    return jsonify({
        "text": text,
        "filename": filename,
        "chars": len(text),
        "truncated": truncated,
        "suggested_title": suggested_title.strip() or None,
        "suggested_date": suggested_date,
    })


# ── Helpers ──

def _is_admin():
    return g.user["role"] == "admin"


def _get_visible_project_ids(conn):
    uid = g.user["id"]
    if _is_admin():
        rows = conn.execute("SELECT id FROM projects WHERE status='active'").fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM projects WHERE status='active' AND "
            "(owner_id=? OR id IN (SELECT DISTINCT project_id FROM tasks WHERE assignee_id=?))",
            (uid, uid),
        ).fetchall()
    return {r["id"] for r in rows}


def _can_view_meeting(conn, meeting):
    if _is_admin():
        return True
    visible = _get_visible_project_ids(conn)
    related = meeting.get("related_projects") or ""
    if not related:
        return meeting["imported_by"] == g.user["id"]
    try:
        pids = [int(x.strip()) for x in related.split(",") if x.strip()]
        return any(pid in visible for pid in pids)
    except Exception:
        return meeting["imported_by"] == g.user["id"]


def _build_project_context(conn, related_pids=None):
    """Build a text summary of active projects + tasks for AI analysis.

    If related_pids is provided (non-empty list of int), only include those projects.
    Otherwise fall back to all active projects.
    """
    related_pids = [int(x) for x in (related_pids or []) if x is not None]
    if related_pids:
        placeholders = ",".join("?" * len(related_pids))
        projects = [dict(r) for r in conn.execute(
            f"SELECT * FROM projects WHERE id IN ({placeholders}) ORDER BY updated_at DESC",
            related_pids,
        ).fetchall()]
        all_tasks = [dict(r) for r in conn.execute(
            f"SELECT t.*, p.name as project_name FROM tasks t "
            f"JOIN projects p ON t.project_id=p.id WHERE p.id IN ({placeholders})",
            related_pids,
        ).fetchall()]
        all_subtasks = [dict(r) for r in conn.execute(
            f"SELECT s.*, t.name as task_name, t.project_id FROM subtasks s "
            f"JOIN tasks t ON s.task_id=t.id "
            f"JOIN projects p ON t.project_id=p.id WHERE p.id IN ({placeholders})",
            related_pids,
        ).fetchall()]
        scope_label = f"=== 关联项目 (IDs: {','.join(str(i) for i in related_pids)}) ==="
    else:
        projects = [dict(r) for r in conn.execute(
            "SELECT * FROM projects WHERE status='active' ORDER BY updated_at DESC"
        ).fetchall()]
        all_tasks = [dict(r) for r in conn.execute(
            "SELECT t.*, p.name as project_name FROM tasks t "
            "JOIN projects p ON t.project_id=p.id WHERE p.status='active'"
        ).fetchall()]
        all_subtasks = [dict(r) for r in conn.execute(
            "SELECT s.*, t.name as task_name, t.project_id FROM subtasks s "
            "JOIN tasks t ON s.task_id=t.id "
            "JOIN projects p ON t.project_id=p.id WHERE p.status='active'"
        ).fetchall()]
        scope_label = "=== 当前活跃项目和任务 ==="

    lines = [scope_label]
    for p in projects:
        ptasks = [t for t in all_tasks if t["project_id"] == p["id"]]
        lines.append(f"\n项目 [ID:{p['id']}]: {p['name']}")
        lines.append(f"  状态: {p['status']} | 负责人: {p.get('owner_name','未设定')} | 截止: {p.get('deadline','未设定')}")
        lines.append(f"  描述: {p.get('description','')}")
        for t in ptasks:
            lines.append(
                f"  任务 [ID:{t['id']}]: {t['name']} | 阶段:{PHASE_MAP.get(t['phase'],t['phase'])} "
                f"| 进度:{t['progress']}% | 负责:{t['assignee_name'] or '未分配'} "
                f"| 截止:{t['end_date'] or '无'} | 优先级:{t.get('priority','medium')}"
            )
            subs = [s for s in all_subtasks if s["task_id"] == t["id"]]
            for s in subs:
                done = "已完成" if s["is_done"] else "未完成"
                lines.append(f"    子任务 [ID:{s['id']}]: {s['content']} ({done})")

    lines.append(f"\n可用阶段: {', '.join(k+'='+v for k,v in PHASE_MAP.items())}")
    lines.append("可用优先级: urgent=紧急, high=高, medium=中, low=低")
    return "\n".join(lines)


ANALYZE_PROMPT = """你是项目管理 AI 助手。用户会粘贴一段会议纪要文字，你的任务是**尽可能多地**从中抽取可写入项目管理系统的变更，对比当前项目/任务状态后生成变更建议列表。

# 抽取原则（重要）

**你应当倾向于生成变更，而不是返回空数组。** 一份正常的会议纪要通常会产生 3–10 条变更。如果你最后只想返回 `[]`，请先反问自己：

- 会议里提到的**人名 / 项目名 / 任务名**在当前系统里能找到吗？找不到就 `create_*`。
- 会议里有任何**进度推进**（"已完成 / 已确认 / 已签订 / 已发货 / 进入下一阶段"）吗？→ 给对应任务 `modify_task`（更新 phase / progress）或 `add_comment` 记录决策。
- 会议里有任何**新的截止日期 / 行动项 / 待办事项**（"X 日要完成 Y / X 负责 Y"）吗？→ `create_task` 或 `create_subtask`。
- 会议里有任何**决策 / 结论 / 取消事项**（"决定不参加 / 改为 X / 暂缓"）吗？→ 至少 `add_comment` 到最相关的任务上，留痕。
- 会议里出现但当前系统**完全没有**的项目 → `create_project`，哪怕信息不全也先建出来（描述里写"待补充"）。

**只有当**会议内容与所有现有项目都毫无关联、且没有任何新项目/任务/决策可记录时，才返回 `[]`。"已经在做了"不是跳过的理由——进度更新本身就是有效变更。

# 变更类型

- `create_project`: 新建项目
- `modify_project`: 修改项目属性（状态/截止日期/负责人/描述）
- `create_task`: 新建任务（必须指定 project_id）
- `modify_task`: 修改任务属性（阶段/进度/截止日期/负责人/优先级/描述）
- `complete_task`: 标记任务为完成（progress=100）
- `create_subtask`: 新建子任务（必须指定 task_id）
- `add_comment`: 给任务添加评论（必须指定 task_id）—— 用于记录决策、进度更新、风险提示等

# 输出格式

返回一个 JSON 数组，每个元素结构如下：
```
{
  "change_type": "create_task|modify_task|complete_task|create_project|modify_project|create_subtask|add_comment",
  "target_type": "project|task|subtask|comment",
  "target_id": null或已有对象的ID(整数),
  "description": "人类可读的变更说明（必填，一句话）",
  "old_value": {...},   // 修改类操作必填，用于对比展示；新建类可省
  "new_value": {...}    // 必填
}
```

`new_value` 字段示例：
- `create_project`: `{"name": "xxx", "description": "xxx", "deadline": "2026-05-01", "owner_name": "xxx"}`
- `modify_project`: `{"deadline": "2026-06-01"}`（只含变更字段）
- `create_task`: `{"project_id": 1, "name": "xxx", "assignee_name": "xxx", "phase": "concept", "priority": "high", "start_date": "2026-05-08", "end_date": "2026-05-15"}`
  - **日期规则**：若任务名/描述中含明确时间范围（如 `4.8-4.15`、`X 月 X 日至 X 月 X 日`、`本周内`等），**必须同时给出 `start_date` 和 `end_date`**，且 `start_date <= end_date`；只给一头会导致开始/截止颠倒。日期格式 `YYYY-MM-DD`。
- `modify_task`: `{"phase": "design", "progress": 30}`（只含变更字段）
- `complete_task`: `{"progress": 100}`
- `create_subtask`: `{"task_id": 1, "content": "xxx"}`
- `add_comment`: `{"task_id": 1, "content": "会议决定：xxx（YYYY-MM-DD 会议）"}`

# 同批次内引用同批新建对象（重要）

如果要为"本批次刚新建的任务"添加子任务、评论或修改，**禁止**写 `task_id: null`。
请按以下规则使用占位引用：

1. 在 `create_task` / `create_project` 的 `new_value` 中添加字段 `"id_ref": "@new_X"`（X 自取，如 `@new_1`、`@new_task_kaibu`）。
2. 后续同批的 `create_subtask` / `add_comment` / `modify_task` 用 `task_ref`（或 `project_ref`）字段引用，例如：
   - `create_subtask`: `{"task_ref": "@new_1", "content": "..."}`
   - `add_comment`: `{"task_ref": "@new_1", "content": "..."}`
   - `modify_task` / `complete_task`: 把 `target_id` 留 null，并在 `new_value` 加 `"task_ref": "@new_1"`。
3. 后端在执行确认时会按时间顺序解析占位引用。所以**父对象的 `create_*` 必须排在子对象之前**。

示例（同批次新建任务+子任务）：
```json
[
  {"change_type":"create_task","target_type":"task","target_id":null,"description":"门店收尾","new_value":{"project_id":16,"name":"门店收尾","id_ref":"@t_finish"}},
  {"change_type":"create_subtask","target_type":"subtask","target_id":null,"description":"硬装修补","new_value":{"task_ref":"@t_finish","content":"4.2-4.3 硬装修补"}}
]
```

# 示例

**输入会议纪要**（节选）:
> 1. 历博合同预计明日完成签订；
> 2. 27 号下午面试兼职 3 人，最终确定 2 人；
> 3. 5 月 9 日西岸活动经讨论决定不参加；
> 4. 物料 28 号送达浦江，李四负责接收。

**当前系统**: 项目 [ID:9] 上海立博展会，含任务 [ID:21] 历博合同签订、[ID:22] 兼职招聘、[ID:23] 物料筹备。

**期望输出**（至少 4 条）:
```json
[
  {"change_type":"add_comment","target_type":"comment","target_id":21,"description":"记录历博合同签订进展","new_value":{"task_id":21,"content":"会议确认：历博合同预计明日完成签订。"}},
  {"change_type":"modify_task","target_type":"task","target_id":22,"description":"兼职招聘进入面试阶段","old_value":{"phase":"concept"},"new_value":{"phase":"design","progress":50}},
  {"change_type":"add_comment","target_type":"comment","target_id":22,"description":"记录面试安排与录用结果","new_value":{"task_id":22,"content":"27 号下午面试兼职 3 人，最终录用 2 人。"}},
  {"change_type":"add_comment","target_type":"comment","target_id":23,"description":"记录物料到货与负责人","new_value":{"task_id":23,"content":"物料 28 号送达浦江，由李四负责接收。"}},
  {"change_type":"add_comment","target_type":"comment","target_id":21,"description":"记录西岸活动决策（关联到最相关任务）","new_value":{"task_id":21,"content":"决策：5 月 9 日西岸活动经讨论决定不参加。"}}
]
```

# 硬性规则

1. 修改类操作必须填 `old_value` 和 `target_id`，新建类 `target_id` 为 null。
2. `add_comment` 的 `target_id` 必须是已有 `task` 的 ID；如果实在找不到对应任务，宁可 `create_task`（带 `description` 说明）。
3. 直接返回纯 JSON 数组，不要 markdown 代码块、不要任何前后说明文字。
4. 决策 / 取消 / 暂缓 / 风险提示一律用 `add_comment` 留痕，不要丢弃。"""


# ── API Routes ──

@bp.route("/api/meetings", methods=["GET"])
def list_meetings():
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM meeting_minutes ORDER BY created_at DESC"
    ).fetchall()]
    conn.close()
    # Filter by permission
    conn2 = get_db()
    result = [r for r in rows if _can_view_meeting(conn2, r)]
    conn2.close()
    return jsonify(result)


@bp.route("/api/meetings", methods=["POST"])
def create_meeting():
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    meeting_date = data.get("meeting_date") or date.today().isoformat()
    related_projects = data.get("related_projects") or ""

    if not title:
        return jsonify({"error": "会议标题不能为空"}), 400
    if not content:
        return jsonify({"error": "会议内容不能为空"}), 400

    now = datetime.now().isoformat()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO meeting_minutes (title, meeting_date, content, related_projects, "
        "imported_by, imported_by_name, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (title, meeting_date, content, related_projects,
         g.user["id"], g.user["name"], "imported", now),
    )
    meeting_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": meeting_id, "message": "会议纪要已保存"})


@bp.route("/api/meetings/<int:mid>", methods=["GET"])
def get_meeting(mid):
    conn = get_db()
    row = conn.execute("SELECT * FROM meeting_minutes WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "会议不存在"}), 404
    meeting = dict(row)
    if not _can_view_meeting(conn, meeting):
        conn.close()
        return jsonify({"error": "无权查看"}), 403
    changes = [dict(r) for r in conn.execute(
        "SELECT * FROM meeting_changes WHERE meeting_id=? ORDER BY id", (mid,)
    ).fetchall()]
    conn.close()
    meeting["changes"] = changes
    return jsonify(meeting)


@bp.route("/api/meetings/<int:mid>", methods=["DELETE"])
def delete_meeting(mid):
    """删除会议纪要本身及其所有变更建议（包含已确认/已拒绝），但**不会回滚**已生效到任务/项目的真实业务数据。

    权限：仅会议导入者本人或 admin。
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM meeting_minutes WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "会议不存在"}), 404
    meeting = dict(row)
    if not (_is_admin() or meeting.get("imported_by") == g.user["id"]):
        conn.close()
        return jsonify({"error": "无权删除：仅会议导入者本人或管理员可删"}), 403

    conn.execute("DELETE FROM meeting_changes WHERE meeting_id=?", (mid,))
    conn.execute("DELETE FROM meeting_minutes WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "message": "会议纪要已删除（已生效的任务/项目变更不受影响）"})


@bp.route("/api/meetings/<int:mid>/analyze", methods=["POST"])
def analyze_meeting(mid):
    t_start = time.monotonic()
    user_id = getattr(g, "user", {}).get("id") if getattr(g, "user", None) else None
    _alog(f"START mid={mid} user={user_id}")

    conn = get_db()
    row = conn.execute("SELECT * FROM meeting_minutes WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        _alog(f"END mid={mid} not_found elapsed={time.monotonic()-t_start:.2f}s")
        return jsonify({"error": "会议不存在"}), 404
    meeting = dict(row)

    # Build project context (scope to related projects if specified)
    t0 = time.monotonic()
    related_pids = []
    rp_raw = (meeting.get("related_projects") or "").strip()
    if rp_raw:
        for x in rp_raw.split(","):
            x = x.strip()
            if x.isdigit():
                related_pids.append(int(x))
    project_context = _build_project_context(conn, related_pids=related_pids)
    _alog(f"mid={mid} ctx_built len={len(project_context)} related_pids={related_pids} in {time.monotonic()-t0:.2f}s")

    # Call MiniMax API (non-streaming, need structured JSON)
    api_messages = [
        {"role": "system", "content": ANALYZE_PROMPT + "\n\n" + project_context},
        {"role": "user", "content": f"以下是会议纪要内容：\n\n标题：{meeting['title']}\n日期：{meeting['meeting_date']}\n\n{meeting['content']}"},
    ]
    sys_len = len(api_messages[0]["content"])
    user_len = len(api_messages[1]["content"])
    _alog(f"mid={mid} model={MINIMAX_MODEL} sys_len={sys_len} user_len={user_len} -> POST {MINIMAX_BASE}/chat/completions")

    try:
        t_http = time.monotonic()
        resp = requests.post(
            f"{MINIMAX_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MINIMAX_MODEL,
                "messages": api_messages,
                "temperature": 0.3,
                "max_tokens": 131072,
            },
            timeout=300,
        )
        http_elapsed = time.monotonic() - t_http
        _alog(f"mid={mid} HTTP {resp.status_code} in {http_elapsed:.2f}s body_len={len(resp.content)}")
        if resp.status_code != 200:
            _alog(f"mid={mid} MiniMax non-200 body_head={resp.text[:500]!r}")
            conn.close()
            return jsonify({"error": f"AI 分析失败: HTTP {resp.status_code}"}), 502

        result = resp.json()
        choice = result.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason")
        usage = result.get("usage")
        _alog(f"mid={mid} finish_reason={finish_reason} usage={usage} raw_content_len={len(content)}")
        _alog(f"mid={mid} raw_content_head={content[:1000]!r}")
        _alog(f"mid={mid} raw_content_tail={content[-500:]!r}")

        # Strip <think> tags if present
        if "<think>" in content and "</think>" in content:
            before = len(content)
            think_block = content[content.index("<think>"):content.index("</think>") + 8]
            content = content[content.index("</think>") + 8:].strip()
            _alog(f"mid={mid} stripped <think> {before}->{len(content)} think_len={len(think_block)}")
            _alog(f"mid={mid} after_strip={content!r}")
        elif "<think>" in content:
            _alog(f"mid={mid} WARNING <think> not closed (likely truncated) content={content[:500]!r}")

        # Strip markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]  # remove opening ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        content = content.strip()
        if not content:
            _alog(f"mid={mid} empty content after strip. finish_reason={finish_reason} usage={usage}")
            conn.close()
            return jsonify({"error": "AI 返回内容为空（可能 token 不足），请重试"}), 502

        changes = json.loads(content)
        if not isinstance(changes, list):
            changes = []
        _alog(f"mid={mid} parsed_changes={len(changes)}")

    except json.JSONDecodeError as e:
        _alog(f"mid={mid} JSONDecodeError: {e}. content_head={content[:500]!r}")
        conn.close()
        return jsonify({"error": "AI 返回格式异常，请重试"}), 502
    except requests.exceptions.Timeout:
        _alog(f"mid={mid} TIMEOUT after {time.monotonic()-t_start:.2f}s")
        conn.close()
        return jsonify({"error": "AI 分析超时，请重试"}), 504
    except Exception as e:
        _alog(f"mid={mid} EXC {type(e).__name__}: {e} after {time.monotonic()-t_start:.2f}s")
        conn.close()
        return jsonify({"error": f"AI 分析出错: {str(e)}"}), 500

    # Clear old pending changes for this meeting
    conn.execute("DELETE FROM meeting_changes WHERE meeting_id=? AND status='pending'", (mid,))

    # Insert new changes
    for c in changes:
        conn.execute(
            "INSERT INTO meeting_changes (meeting_id, change_type, target_type, target_id, "
            "description, old_value, new_value, status) VALUES (?,?,?,?,?,?,?,?)",
            (
                mid,
                c.get("change_type", ""),
                c.get("target_type", ""),
                c.get("target_id"),
                c.get("description", ""),
                json.dumps(c.get("old_value", ""), ensure_ascii=False) if c.get("old_value") else "",
                json.dumps(c.get("new_value", {}), ensure_ascii=False),
                "pending",
            ),
        )

    conn.execute("UPDATE meeting_minutes SET status='analyzed' WHERE id=?", (mid,))
    conn.commit()

    # Re-fetch changes
    saved = [dict(r) for r in conn.execute(
        "SELECT * FROM meeting_changes WHERE meeting_id=? ORDER BY id", (mid,)
    ).fetchall()]
    conn.close()

    _alog(f"END mid={mid} saved={len(saved)} total_elapsed={time.monotonic()-t_start:.2f}s")
    return jsonify({"changes": saved, "count": len(saved)})


@bp.route("/api/meetings/<int:mid>/changes/<int:cid>/confirm", methods=["POST"])
def confirm_change(mid, cid):
    data = request.get_json(force=True) if request.is_json else {}
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM meeting_changes WHERE id=? AND meeting_id=?", (cid, mid)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "变更不存在"}), 404

    change = dict(row)
    if change["status"] != "pending":
        conn.close()
        return jsonify({"error": "该变更已处理"}), 400

    # Allow user to override new_value
    new_value = data.get("new_value")
    if new_value:
        nv = new_value
    else:
        try:
            nv = json.loads(change["new_value"]) if change["new_value"] else {}
        except Exception:
            nv = {}

    # Resolve same-batch placeholder refs (task_ref / project_ref) -> real ids
    ref_map = _build_ref_map(conn, mid)
    target_id = change["target_id"]
    try:
        nv, target_id = _apply_refs(nv, target_id, change["change_type"], ref_map)
    except _RefError as e:
        conn.close()
        return jsonify({"error": str(e)}), 400

    # Execute the change
    try:
        result = _execute_change(conn, change["change_type"], change["target_type"],
                                 target_id, nv)
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"执行失败: {e}"}), 500

    # _execute_change signals failure via {'error': ...} instead of raising.
    # Treat such returns as failure: do NOT mark confirmed, rollback any partial writes.
    if isinstance(result, dict) and result.get("error"):
        conn.rollback()
        conn.close()
        return jsonify({"error": f"执行失败: {result['error']}", "result": result}), 400

    now = datetime.now().isoformat()
    final_nv = json.dumps(nv, ensure_ascii=False) if isinstance(nv, dict) else change["new_value"]
    result_id = result.get("created_id") or result.get("updated_id") or result.get("completed_id") if isinstance(result, dict) else None
    conn.execute(
        "UPDATE meeting_changes SET status='confirmed', confirmed_by=?, confirmed_at=?, "
        "new_value=?, result_id=? WHERE id=?",
        (g.user["id"], now, final_nv, result_id, cid),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "变更已确认并执行", "result": result})


@bp.route("/api/meetings/<int:mid>/changes/<int:cid>/skip", methods=["POST"])
def skip_change(mid, cid):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM meeting_changes WHERE id=? AND meeting_id=?", (cid, mid)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "变更不存在"}), 404
    conn.execute("UPDATE meeting_changes SET status='skipped' WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "已跳过"})


@bp.route("/api/meetings/<int:mid>/confirm-all", methods=["POST"])
def confirm_all(mid):
    conn = get_db()
    pending = [dict(r) for r in conn.execute(
        "SELECT * FROM meeting_changes WHERE meeting_id=? AND status='pending' ORDER BY id",
        (mid,),
    ).fetchall()]

    now = datetime.now().isoformat()
    confirmed = 0
    errors = []
    # ref_map starts from already-confirmed changes; will grow as we execute pending ones
    ref_map = _build_ref_map(conn, mid)
    for c in pending:
        try:
            nv = json.loads(c["new_value"]) if c["new_value"] else {}
        except Exception:
            nv = {}
        try:
            target_id = c["target_id"]
            try:
                nv, target_id = _apply_refs(nv, target_id, c["change_type"], ref_map)
            except _RefError as e:
                errors.append(f"变更#{c['id']}: {e}")
                continue
            res = _execute_change(conn, c["change_type"], c["target_type"], target_id, nv)
            if isinstance(res, dict) and res.get("error"):
                errors.append(f"变更#{c['id']}: {res['error']}")
                continue
            result_id = (res or {}).get("created_id") or (res or {}).get("updated_id") or (res or {}).get("completed_id")
            final_nv = json.dumps(nv, ensure_ascii=False) if isinstance(nv, dict) else c["new_value"]
            conn.execute(
                "UPDATE meeting_changes SET status='confirmed', confirmed_by=?, confirmed_at=?, new_value=?, result_id=? WHERE id=?",
                (g.user["id"], now, final_nv, result_id, c["id"]),
            )
            # Register newly created id under its id_ref so subsequent rows in this loop can resolve it
            if isinstance(nv, dict) and nv.get("id_ref") and result_id:
                ref_map[nv["id_ref"]] = result_id
            confirmed += 1
        except Exception as e:
            errors.append(f"变更#{c['id']}: {str(e)}")

    conn.execute("UPDATE meeting_minutes SET status='executed' WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({
        "message": f"已确认 {confirmed} 条变更",
        "confirmed": confirmed,
        "errors": errors,
    })


class _RefError(Exception):
    pass


def _build_ref_map(conn, meeting_id):
    """Build {id_ref -> real_id} from already-confirmed create_* changes in the same meeting."""
    ref_map = {}
    rows = conn.execute(
        "SELECT new_value, result_id FROM meeting_changes "
        "WHERE meeting_id=? AND status='confirmed' AND result_id IS NOT NULL",
        (meeting_id,),
    ).fetchall()
    for r in rows:
        try:
            nv = json.loads(r["new_value"]) if r["new_value"] else {}
        except Exception:
            continue
        ref = nv.get("id_ref") if isinstance(nv, dict) else None
        if ref:
            ref_map[ref] = r["result_id"]
    return ref_map


def _apply_refs(nv, target_id, change_type, ref_map):
    """Resolve task_ref/project_ref placeholders into real ids inside new_value.

    For modify_task / complete_task / create_subtask / add_comment, a `task_ref`
    inside new_value is resolved to fill task_id (or target_id for modify/complete).
    For create_task, a `project_ref` is resolved to fill project_id.
    Raises _RefError if a referenced placeholder cannot be resolved.
    """
    if not isinstance(nv, dict):
        return nv, target_id

    def resolve(ref):
        if ref not in ref_map:
            raise _RefError(f"未找到占位引用 {ref}（请先确认其父级新建变更）")
        return ref_map[ref]

    if nv.get("task_ref"):
        rid = resolve(nv["task_ref"])
        if change_type in ("modify_task", "complete_task"):
            target_id = rid
        else:
            nv["task_id"] = rid
        nv.pop("task_ref", None)

    if nv.get("project_ref"):
        rid = resolve(nv["project_ref"])
        if change_type == "modify_project":
            target_id = rid
        else:
            nv["project_id"] = rid
        nv.pop("project_ref", None)

    return nv, target_id


def _resolve_user_names_to_ids(conn, names):
    """Resolve a list of display names to comma-separated user IDs."""
    if not names:
        return ""
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    ids = []
    for n in names:
        if not n:
            continue
        row = conn.execute(
            "SELECT id FROM users WHERE display_name=? OR username=? LIMIT 1", (n, n)
        ).fetchone()
        if row and row["id"] not in ids:
            ids.append(row["id"])
    return ",".join(ids)


def _execute_change(conn, change_type, target_type, target_id, new_value):
    """Execute a single change against the database."""
    now = datetime.now().isoformat()

    if change_type == "create_project":
        cur = conn.execute(
            "INSERT INTO projects (name, description, status, color, owner_id, owner_name, start_date, deadline, visible_to, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                new_value.get("name", "新项目"),
                new_value.get("description", ""),
                "active",
                new_value.get("color", "#95A3B3"),
                g.user["id"],
                new_value.get("owner_name", ""),
                new_value.get("start_date", date.today().isoformat()),
                new_value.get("deadline", ""),
                "",
                now, now,
            ),
        )
        return {"created_id": cur.lastrowid, "type": "project"}

    elif change_type == "modify_project":
        if not target_id:
            return {"error": "缺少 target_id"}
        sets, vals = [], []
        for field in ("name", "description", "status", "deadline", "owner_name", "color"):
            if field in new_value:
                sets.append(f"{field}=?")
                vals.append(new_value[field])
        if sets:
            sets.append("updated_at=?")
            vals.append(now)
            vals.append(target_id)
            conn.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=?", vals)
        return {"updated_id": target_id, "type": "project"}

    elif change_type == "create_task":
        pid = new_value.get("project_id")
        if not pid:
            return {"error": "缺少 project_id"}
        # 兜底优先级：start_date > end_date（避免 start>end 颠倒） > 今天
        start_date = (
            new_value.get("start_date")
            or new_value.get("end_date")
            or date.today().isoformat()
        )
        collab_ids = ""
        if "collaborator_names" in new_value:
            collab_ids = _resolve_user_names_to_ids(conn, new_value.get("collaborator_names"))
        elif "collaborator_ids" in new_value:
            collab_ids = str(new_value.get("collaborator_ids") or "")
        cur = conn.execute(
            "INSERT INTO tasks (project_id, name, description, assignee_name, phase, "
            "priority, start_date, end_date, progress, collaborator_ids, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pid,
                new_value.get("name", "新任务"),
                new_value.get("description", ""),
                new_value.get("assignee_name", ""),
                new_value.get("phase", "concept"),
                new_value.get("priority", "medium"),
                start_date,
                new_value.get("end_date", ""),
                new_value.get("progress", 0),
                collab_ids,
                now, now,
            ),
        )
        return {"created_id": cur.lastrowid, "type": "task"}

    elif change_type == "modify_task":
        if not target_id:
            return {"error": "缺少 target_id"}
        sets, vals = [], []
        # Resolve collaborator_names to ids if present
        if "collaborator_names" in new_value and "collaborator_ids" not in new_value:
            new_value["collaborator_ids"] = _resolve_user_names_to_ids(conn, new_value.get("collaborator_names"))
        for field in ("name", "description", "assignee_name", "assignee_id",
                       "phase", "priority", "end_date", "start_date", "progress",
                       "collaborator_ids"):
            if field in new_value:
                sets.append(f"{field}=?")
                vals.append(new_value[field])
        if sets:
            sets.append("updated_at=?")
            vals.append(now)
            vals.append(target_id)
            conn.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals)
        return {"updated_id": target_id, "type": "task"}

    elif change_type == "complete_task":
        if not target_id:
            return {"error": "缺少 target_id"}
        conn.execute(
            "UPDATE tasks SET progress=100, updated_at=? WHERE id=?", (now, target_id)
        )
        return {"completed_id": target_id, "type": "task"}

    elif change_type == "create_subtask":
        tid = new_value.get("task_id")
        if not tid:
            return {"error": "缺少 task_id"}
        cur = conn.execute(
            "INSERT INTO subtasks (task_id, content, is_done, created_at) VALUES (?,?,?,?)",
            (tid, new_value.get("content", ""), 0, now),
        )
        return {"created_id": cur.lastrowid, "type": "subtask"}

    elif change_type == "add_comment":
        tid = new_value.get("task_id")
        if not tid:
            return {"error": "缺少 task_id"}
        cur = conn.execute(
            "INSERT INTO comments (task_id, user_id, user_name, content, created_at) VALUES (?,?,?,?,?)",
            (tid, g.user["id"], g.user["name"], new_value.get("content", ""), now),
        )
        return {"created_id": cur.lastrowid, "type": "comment"}

    return {"error": f"未知变更类型: {change_type}"}
