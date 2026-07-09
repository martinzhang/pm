"""
AI 大脑·知识检索域（语义检索 / RAG）

把「一段话/一篇文章」形式的内容（本期：项目/任务附件正文）喂进向量库，让小鱼能
按语义检索到附件里写了什么——补上结构化只读工具摸不到的信息黑洞。

框架无关：不依赖 Flask、不依赖企业微信。三件事内聚在本模块：
  - build_knowledge()     装配 embedder + PgVector + Knowledge（懒加载单例）
  - index_attachments()   离线索引：把 uploads/ 下的文档类附件灌进向量库（带 project_id 归属）
  - visible_retriever()    自定义检索：可见性写死在代码里（复用只读工具同源口径），不交给 LLM

两个必须遵守的架构约束（都已从 agno 2.6.21 源码证实）：
  1. PgVector 用【同步】SQLAlchemy 引擎，db_url 必须 psycopg 驱动（config.AGENT_DB_URL_SYNC），
     不能用 asyncpg——asyncpg 是给 agno 会话库 AsyncPostgresDb 的，两者并存、各走各的。
  2. OllamaEmbedder.dimensions 必须 == 模型真实维度（bge-m3=1024），否则 get_embedding
     静默返回空向量、且建表向量列长度也会错。用 config.EMBED_DIM 统一。

可见性是硬约束：附件跟随所属项目的可见性。索引时把 project_id 打进 metadata，检索时按
「当前用户可见的 project_id 集合」过滤。集合口径复用 repositories.projects 的参与口径
（与 get_my_projects / get_project_status 完全同源），绝不让 LLM 自己选 filter（越权风险）。

离线冒烟（建表 + 索引 + 检索 + 可见性，不依赖企业微信）：
    uv run python -m agent.knowledge
"""
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agno.knowledge.knowledge import Knowledge
from agno.knowledge.embedder.ollama import OllamaEmbedder
from agno.vectordb.pgvector import PgVector
from agno.vectordb.search import SearchType
from agno.filters import IN

from config import (
    AGENT_DB_URL_SYNC, EMBED_HOST, EMBED_MODEL, EMBED_DIM, EMBED_SCORE_THRESHOLD,
    UPLOAD_DIR, IMAGE_EXTS,
)


# 向量表：agno schema 默认 "ai"，表名区分内容类型，未来会议纪要/评论各自建表或共表加 source。
_VECTOR_TABLE = "pm_attachments"
_VECTOR_SCHEMA = "ai"

_knowledge: Optional[Knowledge] = None


@dataclass
class SafeOllamaEmbedder(OllamaEmbedder):
    """给空文本兜底的 OllamaEmbedder。

    为什么需要：文档分块后常有空白页/图片页 chunk（content=''），bge-m3 对空文本返回 []。
    而 PgVector.insert 是【整批】写入——批里只要有一个空向量，pg 就报
    `vector must have at least 1 dimension`，导致【整份文件所有 chunk 一起回滚丢失】
    （亲测 D11 提案 16 页有效内容因第 17 页空页全没入库）。

    兜底策略：空文本 / 模型返空 → 返回合法维度的零向量。零向量与任何查询余弦相似度为 0，
    hybrid 检索也匹配不上空 content，天然不会被召回，无害地占一行，换取整批不炸。
    """

    def get_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * (self.dimensions or EMBED_DIM)
        v = super().get_embedding(text)
        return v if v else [0.0] * (self.dimensions or EMBED_DIM)


def build_knowledge() -> Knowledge:
    """懒加载单例：装配 embedder + PgVector + Knowledge。

    首次调用时 Knowledge.__post_init__ 会自动建表（CREATE EXTENSION vector + 建 schema + 建表）。
    embedder / vector_db 都显式传，不能省——省了 PgVector 会默认 OpenAIEmbedder。
    """
    global _knowledge
    if _knowledge is None:
        embedder = SafeOllamaEmbedder(
            id=EMBED_MODEL,
            dimensions=EMBED_DIM,   # 必须 == bge-m3 真实维度 1024
            host=EMBED_HOST,        # 完整 URL，原样透传给 ollama.Client
        )
        vector_db = PgVector(
            table_name=_VECTOR_TABLE,
            schema=_VECTOR_SCHEMA,
            db_url=AGENT_DB_URL_SYNC,   # 同步 psycopg URL，不是 asyncpg
            embedder=embedder,
            search_type=SearchType.hybrid,  # 向量 + 关键词混合，中文短查询更稳
            # 相似度下限：编译成 SQL `WHERE hybrid_score >= 阈值`，不达标片段根本不出库，
            # 从源头挡住低相关噪声进 LLM 上下文。对所有走 kb.search() 的调用统一生效。
            # 注意：这挡不住空白页零向量行（其分数是 NaN，PG 里 `NaN >= 阈值` 为真）——
            # 那道防线仍靠 visible_retriever 的空内容过滤 + _clean_meta 清 NaN，两者正交。
            similarity_threshold=EMBED_SCORE_THRESHOLD,
        )
        _knowledge = Knowledge(vector_db=vector_db, max_results=5)
    return _knowledge


# ── 索引：把附件正文灌进向量库 ──

def _iter_document_attachments(conn):
    """从 SQLite 取所有【文档类】附件 + 归属信息，yield 统一结构。

    跟随 blueprints/ai.py 的 JOIN 口径拿到 project_id（可见性归属的 key）：
      - task 附件：tf JOIN tasks 拿 project_id，物理路径 uploads/{task_id}/{filename}
      - project 附件：pf JOIN projects，物理路径 uploads/project_{project_id}/{filename}
    图片扩展名跳过（agno reader 不解析图片，VLM 描述本期不做）。

    yield: dict(filepath, scope, project_id, task_id, file_name, stored_name)

    file_name 是 original_name（展示用，可重名）；stored_name 是磁盘唯一的 safe_name，
    单文件删除时按它精确定位，避免同任务重名文件被误删（见 sync_index_file / remove_file）。
    """
    # task 附件
    rows = conn.execute(
        "SELECT tf.task_id, tf.filename, tf.original_name, t.project_id "
        "FROM task_files tf JOIN tasks t ON tf.task_id = t.id"
    ).fetchall()
    for r in rows:
        ext = os.path.splitext(r["original_name"])[1].lower()
        if ext in IMAGE_EXTS:
            continue
        yield {
            "filepath": os.path.join(UPLOAD_DIR, str(r["task_id"]), r["filename"]),
            "scope": "task",
            "project_id": r["project_id"],
            "task_id": r["task_id"],
            "file_name": r["original_name"],
            "stored_name": r["filename"],
        }
    # project 附件
    rows = conn.execute(
        "SELECT pf.project_id, pf.filename, pf.original_name "
        "FROM project_files pf JOIN projects p ON pf.project_id = p.id"
    ).fetchall()
    for r in rows:
        ext = os.path.splitext(r["original_name"])[1].lower()
        if ext in IMAGE_EXTS:
            continue
        yield {
            "filepath": os.path.join(UPLOAD_DIR, f"project_{r['project_id']}", r["filename"]),
            "scope": "project",
            "project_id": r["project_id"],
            "task_id": None,
            "file_name": r["original_name"],
            "stored_name": r["filename"],
        }


def _build_metadata(scope: str, project_id, task_id, file_name: str, stored_name: str) -> Dict[str, str]:
    """索引/检索共用的 metadata 口径（单一事实源）。

    project_id 是检索期可见性过滤的命脉；stored_name 是磁盘唯一名，作单文件删除主键。
    全部转字符串——JSONB filter 与 delete_by_metadata 的 @> 都按字符串精确匹配。
    """
    return {
        "source": "attachment",
        "scope": scope,
        "project_id": str(project_id) if project_id is not None else "",
        "task_id": str(task_id) if task_id is not None else "",
        "file_name": file_name,
        "stored_name": stored_name,
    }


def index_attachments() -> Dict[str, int]:
    """离线索引：遍历文档类附件，逐个 add_content(path=...) 灌进向量库。

    agno 按扩展名自动选 reader（pdf/docx/xlsx/pptx/md/txt…）+ 分块 + 向量化，我们只负责
    把物理路径和归属 metadata 交给它。metadata 口径见 _build_metadata（与增量钩子同源）。

    返回 {"indexed": n, "skipped_missing": m}。物理文件缺失的静默跳过（本地快照可能缺文件）。
    """
    from models import get_db

    kb = build_knowledge()
    indexed = 0
    skipped = 0
    conn = get_db()
    try:
        for att in _iter_document_attachments(conn):
            if not os.path.exists(att["filepath"]):
                skipped += 1
                continue
            metadata = _build_metadata(
                att["scope"], att["project_id"], att["task_id"],
                att["file_name"], att["stored_name"],
            )
            kb.add_content(path=att["filepath"], metadata=metadata)
            indexed += 1
    finally:
        conn.close()
    return {"indexed": indexed, "skipped_missing": skipped}


# ── 增量同步：跟随文件生命周期，让向量库与附件增删保持一致 ──
#
# 设计（高内聚）：所有"文件变动 → 向量库同步"的逻辑收在这里，Flask 端点只调一行、
# 不碰 agno/pgvector。四个钩子都【自带 try/except 兜底】——知识库同步是对 agent 检索的
# 增强，不是文件增删的核心事务，同步失败绝不能让用户的上传/删除失败（dev 机常连不上
# 本地 pgvector / 远程 ollama，必须静默降级）。
#
# 删除类同步、即时执行：纯 SQL DELETE 很快，且"已删文件仍被检索到"是泄漏，不容窗口。
# 新增类走后台线程：add_content 要解析 + embedding（秒级），不能阻塞上传 HTTP 响应。

_IMG_EXTS = IMAGE_EXTS


def _attachment_path(scope: str, project_id, task_id, stored_name: str) -> str:
    """按 scope 拼物理路径，与 _iter_document_attachments 的落盘规则严格一致。

    task 附件：uploads/{task_id}/{stored_name}
    project 附件：uploads/project_{project_id}/{stored_name}
    """
    if scope == "task":
        return os.path.join(UPLOAD_DIR, str(task_id), stored_name)
    return os.path.join(UPLOAD_DIR, f"project_{project_id}", stored_name)


def _do_index_file(scope: str, project_id, task_id, stored_name: str, original_name: str) -> None:
    """真正把单个文件灌进向量库（在后台线程里跑）。图片跳过、缺文件跳过。"""
    from loguru import logger

    log = logger.bind(scope=scope, stored=stored_name)
    try:
        ext = os.path.splitext(original_name)[1].lower()
        if ext in _IMG_EXTS:
            return  # 图片不解析（与全量索引口径一致）
        path = _attachment_path(scope, project_id, task_id, stored_name)
        if not os.path.exists(path):
            log.warning("知识库增量索引：物理文件不存在，跳过 {}", path)
            return
        kb = build_knowledge()
        metadata = _build_metadata(scope, project_id, task_id, original_name, stored_name)
        kb.add_content(path=path, metadata=metadata, upsert=True)  # upsert 幂等，重灌不重复
        log.info("知识库增量索引完成：{}", original_name)
    except Exception:  # noqa: BLE001 -- 增强性质，绝不影响上传主流程
        log.exception("知识库增量索引失败（已忽略，不影响文件上传）")


def sync_index_file(scope: str, project_id, task_id, stored_name: str, original_name: str) -> None:
    """【新增钩子】文件上传后调用：起后台 daemon 线程异步灌库，立即返回、不阻塞上传响应。

    :param scope: "task" | "project"
    :param project_id: 归属项目 id（可见性过滤的命脉；task 附件也要传其所属项目）
    :param task_id: task 附件传 task id，project 附件传 None
    :param stored_name: 磁盘唯一名（DB 的 filename / safe_name），删除主键
    :param original_name: 原始文件名（判扩展名 + 展示）

    进程重启可能丢未完成线程，但 upsert 幂等、下次全量重灌能补，对当前体量可接受。
    """
    import threading

    threading.Thread(
        target=_do_index_file,
        args=(scope, project_id, task_id, stored_name, original_name),
        daemon=True,
    ).start()


def _delete_by(meta: Dict[str, str]) -> None:
    """按 metadata 从向量库删 chunk 的共用兜底封装（同步、即时）。"""
    from loguru import logger

    try:
        build_knowledge().vector_db.delete_by_metadata(meta)
        logger.bind(meta=meta).info("知识库删除同步完成")
    except Exception:  # noqa: BLE001 -- 增强性质，绝不影响删除主流程
        logger.bind(meta=meta).exception("知识库删除同步失败（已忽略，不影响文件删除）")


def remove_file(project_id, task_id, stored_name: str) -> None:
    """【删单文件钩子】按 stored_name + 归属精确删。

    stored_name 磁盘唯一，即使同任务重名（original_name 相同）也不会误删另一个。
    带上 project_id/task_id 收窄匹配范围（@> 多键 AND），更稳。
    """
    meta = {"stored_name": stored_name}
    if task_id is not None:
        meta["task_id"] = str(task_id)
    if project_id is not None:
        meta["project_id"] = str(project_id)
    _delete_by(meta)


def remove_task(task_id) -> None:
    """【级联删任务钩子】一条 SQL 清掉该 task 名下所有 chunk，天然覆盖多文件。"""
    _delete_by({"task_id": str(task_id)})


def remove_project(project_id) -> None:
    """【级联删项目钩子】清掉该 project 名下所有 chunk（含其下 task 附件——它们 metadata 也带 project_id）。"""
    _delete_by({"project_id": str(project_id)})


# ── 实体档案：把结构化实体里「人写的文字」聚合成一份可语义检索的档案文档 ──
#
# 为什么要这层：附件正文进了向量库，但「决策 / 讨论 / 描述」这类人写的文字散落在
# tasks.description、subtasks.content、comments.content 里——结构化只读工具要先知道
# 任务名再线性翻，语义问题（「D11 老板选了哪个提案」）根本够不到。把一个实体名下所有
# 人写的文字聚合成一份「档案卡」灌进同一向量库（用 metadata.source 区分），让那一次语义
# 检索同时覆盖【附件正文 + 实体讨论】。爱写评论的团队信息在评论、不爱写的在描述/子任务，
# 聚合成卡就一网打尽，解决的是一类问题而非单个字段。
#
# 只收【非结构化文本】(名 / 描述 / 子任务 / 评论 / 附件名)，绝不收【结构化标量】(状态 /
# 进度 / 日期 / 计数)：后者要精确 + 实时，归 6 个 SQL 只读工具，一 embed 就召回不准、还要
# 随高频变动不断重嵌。档案是「快照叙事」，状态是「实时事实」，两条路正交（边界见 core.py）。
#
# 幂等靠【先按 metadata 删旧、再灌新】，不能靠 add_content(upsert=True)：agno 的 upsert 按
# content_hash 去重，档案内容一变(加一条评论)hash 就变，旧档案不会被覆盖而是越堆越多。所以
# 每次同步先 delete_by_metadata({source, task_id}) 精确清掉这个实体的旧档案(带 source 收窄，
# 绝不误删同 task_id 的附件 chunk)，再 add_content 灌新。粒度是「两级实体档案」：一 task 一份、
# 一 project 一份，各自是天然的叙事边界，不拍平成项目级巨型文档(那样 embedding 被稀释、召回掉)。

_ENTITY_SOURCE_TASK = "task"
_ENTITY_SOURCE_PROJECT = "project"


def _entity_meta(source: str, project_id, task_id=None) -> Dict[str, str]:
    """实体档案的 metadata 口径（单一事实源）。

    source 区分 task / project 档案；project_id 是 visible_retriever 可见性过滤的命脉；
    task_id 供「先删旧档案」精确定位。全部转字符串，对齐 JSONB @> 的字符串精确匹配。
    """
    return {
        "source": source,
        "project_id": str(project_id) if project_id is not None else "",
        "task_id": str(task_id) if task_id is not None else "",
    }


def _build_task_card(conn, task_id):
    """把一个任务名下所有【人写的文字】聚合成一份档案卡文本。

    收：任务名 + 描述 + 子任务 content + 评论(谁/哪天/正文) + 附件文件名。
    不收：状态 / 进度 / 日期 / 计数——那些高频变动且要精确，归 SQL 只读工具。
    返回 (card_text, project_id)；任务不存在返回 (None, None)。
    """
    t = conn.execute(
        "SELECT id, project_id, name, description FROM tasks WHERE id=?", (task_id,)
    ).fetchone()
    if not t:
        return None, None
    lines = [f"任务：{t['name']}"]
    if (t["description"] or "").strip():
        lines.append(f"描述：{t['description'].strip()}")

    subs = conn.execute(
        "SELECT content FROM subtasks WHERE task_id=? ORDER BY id", (task_id,)
    ).fetchall()
    sub_lines = [f"- {s['content'].strip()}" for s in subs if (s["content"] or "").strip()]
    if sub_lines:
        lines.append("子任务：")
        lines.extend(sub_lines)

    cmts = conn.execute(
        "SELECT user_name, content, created_at FROM comments WHERE task_id=? ORDER BY created_at",
        (task_id,),
    ).fetchall()
    cmt_lines = []
    for c in cmts:
        if not (c["content"] or "").strip():
            continue
        who = c["user_name"] or "某同事"
        when = (c["created_at"] or "")[:10]
        when_str = f"（{when}）" if when else ""
        cmt_lines.append(f"- {who}{when_str}：{c['content'].strip()}")
    if cmt_lines:
        lines.append("评论：")
        lines.extend(cmt_lines)

    files = conn.execute(
        "SELECT original_name FROM task_files WHERE task_id=? ORDER BY created_at", (task_id,)
    ).fetchall()
    fnames = [f["original_name"] for f in files if (f["original_name"] or "").strip()]
    if fnames:
        lines.append("附件：" + "、".join(fnames))

    return "\n".join(lines), t["project_id"]


def _build_project_card(conn, project_id):
    """把一个项目的【人写的文字】聚合成档案卡：项目名 + 描述 + 项目附件名。

    接住「XX 项目当初为什么做」这类藏在项目描述里的语义问题。任务级的讨论各自成
    task 档案，不在这里重复（避免项目卡膨胀 + 稀释召回）。返回 card_text；项目不存在返回 None。
    """
    p = conn.execute(
        "SELECT id, name, description FROM projects WHERE id=?", (project_id,)
    ).fetchone()
    if not p:
        return None
    lines = [f"项目：{p['name']}"]
    if (p["description"] or "").strip():
        lines.append(f"描述：{p['description'].strip()}")
    files = conn.execute(
        "SELECT original_name FROM project_files WHERE project_id=? ORDER BY created_at", (project_id,)
    ).fetchall()
    fnames = [f["original_name"] for f in files if (f["original_name"] or "").strip()]
    if fnames:
        lines.append("附件：" + "、".join(fnames))
    return "\n".join(lines)


def _sync_entity(source: str, key_meta: Dict[str, str], card, full_meta: Dict[str, str], name: str) -> None:
    """实体档案同步的共用内核（先按 metadata 删旧、再灌新），同步执行。

    key_meta：精确定位这个实体旧档案的最小键（带 source，绝不误删附件 chunk）。
    card 为 None（实体已删）时只删不灌。调用方负责起线程 + 兜底 try/except。
    """
    kb = build_knowledge()
    kb.vector_db.delete_by_metadata(key_meta)   # 先清旧档案（含上一版的多个 chunk）
    if card and card.strip():
        kb.add_content(text_content=card, name=name, metadata=full_meta)


def _do_sync_task_doc(task_id) -> None:
    """重建单个任务档案（后台线程里跑）。任务已删则只清旧档案。"""
    from loguru import logger
    from models import get_db

    log = logger.bind(entity="task", id=task_id)
    try:
        conn = get_db()
        try:
            card, project_id = _build_task_card(conn, task_id)
        finally:
            conn.close()
        _sync_entity(
            _ENTITY_SOURCE_TASK,
            {"source": _ENTITY_SOURCE_TASK, "task_id": str(task_id)},
            card,
            _entity_meta(_ENTITY_SOURCE_TASK, project_id, task_id),
            name=f"task-{task_id}",
        )
        log.info("任务档案同步完成")
    except Exception:  # noqa: BLE001 -- 增强性质，绝不影响主流程
        log.exception("任务档案同步失败（已忽略，不影响主流程）")


def _do_sync_project_doc(project_id) -> None:
    """重建单个项目档案（后台线程里跑）。项目已删则只清旧档案。"""
    from loguru import logger
    from models import get_db

    log = logger.bind(entity="project", id=project_id)
    try:
        conn = get_db()
        try:
            card = _build_project_card(conn, project_id)
        finally:
            conn.close()
        _sync_entity(
            _ENTITY_SOURCE_PROJECT,
            {"source": _ENTITY_SOURCE_PROJECT, "project_id": str(project_id)},
            card,
            _entity_meta(_ENTITY_SOURCE_PROJECT, project_id),
            name=f"project-{project_id}",
        )
        log.info("项目档案同步完成")
    except Exception:  # noqa: BLE001 -- 增强性质，绝不影响主流程
        log.exception("项目档案同步失败（已忽略，不影响主流程）")


def sync_task_doc(task_id) -> None:
    """【任务档案钩子】任务 / 子任务 / 评论 增删改后调用：起后台线程重建该任务档案。

    立即返回、不阻塞请求。task 被整体删除时用现有 remove_task 即可（按 task_id 连档案带附件
    一起清），无需再调本钩子。进程重启可能丢未完成线程，但下次全量 index_entities 能补齐。
    """
    import threading

    threading.Thread(target=_do_sync_task_doc, args=(task_id,), daemon=True).start()


def sync_project_doc(project_id) -> None:
    """【项目档案钩子】项目名 / 描述 / 项目附件变动后调用：起后台线程重建该项目档案。

    项目被整体删除时用现有 remove_project 即可（按 project_id 连档案带其下所有 chunk 一起清）。
    """
    import threading

    threading.Thread(target=_do_sync_project_doc, args=(project_id,), daemon=True).start()


def index_entities() -> Dict[str, int]:
    """离线全量：为所有任务 / 项目重建档案文档（先删旧、再灌新，幂等可重跑）。

    与 index_attachments 正交：那个灌附件正文(source=attachment)，这个灌实体档案
    (source=task/project)，同一张向量表靠 source 区分。返回 {"tasks": n, "projects": m}。
    """
    from models import get_db

    conn = get_db()
    try:
        tids = [r["id"] for r in conn.execute("SELECT id FROM tasks").fetchall()]
        pids = [r["id"] for r in conn.execute("SELECT id FROM projects").fetchall()]
        for tid in tids:
            card, project_id = _build_task_card(conn, tid)
            _sync_entity(
                _ENTITY_SOURCE_TASK,
                {"source": _ENTITY_SOURCE_TASK, "task_id": str(tid)},
                card,
                _entity_meta(_ENTITY_SOURCE_TASK, project_id, tid),
                name=f"task-{tid}",
            )
        for pid in pids:
            card = _build_project_card(conn, pid)
            _sync_entity(
                _ENTITY_SOURCE_PROJECT,
                {"source": _ENTITY_SOURCE_PROJECT, "project_id": str(pid)},
                card,
                _entity_meta(_ENTITY_SOURCE_PROJECT, pid),
                name=f"project-{pid}",
            )
    finally:
        conn.close()
    return {"tasks": len(tids), "projects": len(pids)}


# ── 检索：可见性写死的自定义 retriever ──

def _visible_project_ids(uid: str, is_admin: bool) -> List[str]:
    """算「当前用户可见的 project_id 集合」，与只读工具完全同源的参与口径。

    复用 repositories.projects.find_participating_by_name（name 传空 = 不加名字过滤），
    admin 放宽到全部活跃项目。返回字符串列表（对齐 metadata 里的 str(project_id)）。
    """
    from models import get_db
    from repositories import projects as projects_repo

    conn = get_db()
    try:
        projs = projects_repo.find_participating_by_name(conn, uid, is_admin, name="", limit=200)
    finally:
        conn.close()
    return [str(p["id"]) for p in projs]


def _identity(run_context) -> Dict[str, Any]:
    """从 run_context.dependencies 取「当前对话者」身份（与 agent.tools._shared 同一契约）。"""
    deps = getattr(run_context, "dependencies", None) or {}
    ident = deps.get("当前对话者") or {}
    return ident if isinstance(ident, dict) else {}


def _clean_meta(meta: Any) -> Dict[str, Any]:
    """清洗 meta_data 里 PostgreSQL JSON 不接受的值（主要是 NaN）。

    agno 检索会在 meta_data 塞 `similarity_score`，命中零向量行时其值为 float('nan')。
    json.dumps 能过，但 agno 会话历史落库走 asyncpg 的 JSON 类型，PG 标准 JSON 不接受 NaN，
    会报 InvalidTextRepresentationError。这里把 NaN/inf 一律剔除，避免污染会话写库。
    """
    import math

    if not isinstance(meta, dict):
        return {}
    out = {}
    for k, v in meta.items():
        if isinstance(v, float) and not math.isfinite(v):  # NaN / inf
            continue
        out[k] = v
    return out


def visible_retriever(query: str, num_documents: Optional[int] = None,
                      run_context=None, **kwargs) -> List[Dict[str, Any]]:
    """自定义知识检索：只返回「当前对话者有权看的项目」下的附件片段。

    形参名是 agno 的注入契约（inspect.signature 按名注入，必须精确叫 query / num_documents /
    run_context），拼错就不会被注入。可见性在这里用代码写死：先算可见 project_id 集合，再用
    IN filter 交给向量检索——绝不把 filter 选择权交给 LLM。

    返回 [{"name", "meta_data", "content"}, ...]（带 content 键，与 agno 默认路径一致）。
    未绑定 / 无可见项目 → 返回 []，不查库。空 content 片段（分块出的空白页）直接丢弃——
    对回答无价值，还会带 NaN similarity_score 污染会话写库。
    """
    ident = _identity(run_context)
    uid = ident.get("id")
    if not uid:
        return []
    is_admin = (ident.get("role") == "admin")
    pids = _visible_project_ids(uid, is_admin)
    if not pids:
        return []

    kb = build_knowledge()
    docs = kb.search(
        query=query,
        max_results=num_documents or 5,
        filters=[IN("project_id", pids)],
    )
    return [
        {"name": d.name, "meta_data": _clean_meta(d.meta_data), "content": d.content}
        for d in docs
        if (d.content or "").strip()   # 丢弃空白页片段
    ]


# ── 离线冒烟：建表 + 索引 + 裸检索 + 可见性 ──
if __name__ == "__main__":
    print("\033[35m===== agent.knowledge 冒烟 =====\033[0m")

    print("\n[1] 建表 + 装配 ...")
    kb = build_knowledge()
    print("    Knowledge 就绪，表 =", f"{_VECTOR_SCHEMA}.{_VECTOR_TABLE}")

    print("\n[2] 索引附件 ...")
    stat = index_attachments()
    print("    ", stat)

    print("\n[2b] 索引实体档案（任务/项目：描述+子任务+评论+附件名）...")
    stat_e = index_entities()
    print("    ", stat_e)

    print("\n[3] 裸检索（无可见性，直接问向量库）...")
    q = "咖啡车 包装 提案"
    docs = kb.search(query=q, max_results=3)
    print(f"    query={q!r} 命中 {len(docs)} 片段")
    for i, d in enumerate(docs, 1):
        pid = (d.meta_data or {}).get("project_id")
        fn = (d.meta_data or {}).get("file_name")
        print(f"    #{i} [proj={pid}] {fn}: {(d.content or '')[:80]}...")

    print("\n[4] 可见性检索（两个身份验越权）...")

    class _Ctx:
        def __init__(self, ident):
            self.dependencies = {"当前对话者": ident}

    admin = {"bound": True, "id": "admin_probe", "role": "admin"}
    got_admin = visible_retriever(q, num_documents=3, run_context=_Ctx(admin))
    print(f"    admin 检索到 {len(got_admin)} 片段（应 > 0）")

    outsider = {"bound": True, "id": "user_no_access_probe", "role": "user"}
    got_out = visible_retriever(q, num_documents=3, run_context=_Ctx(outsider))
    print(f"    无权用户检索到 {len(got_out)} 片段（应 == 0，证明不越权）")

    print("\n[5] Agent 端到端（真实小鱼 + knowledge，问附件内容）...")
    import asyncio
    from agno.agent import Agent
    from agno.models.minimax import MiniMax
    from agno.run.agent import RunEvent
    from config import MINIMAX_API_KEY, MINIMAX_BASE, MINIMAX_MODEL

    # 临时 Agent：只验证 knowledge 检索链路，不动 core.py 生产单例。
    # knowledge_retriever=visible_retriever → 可见性写死；search_knowledge=True → agent 自主检索。
    probe_agent = Agent(
        model=MiniMax(id=MINIMAX_MODEL, api_key=MINIMAX_API_KEY, base_url=MINIMAX_BASE),
        knowledge=build_knowledge(),
        knowledge_retriever=visible_retriever,
        search_knowledge=True,
        instructions="你是奈娃咖啡小助手小鱼。同事问附件/文档内容时，检索知识库并基于检索到的正文回答，不要编造。",
        markdown=True,
        telemetry=False,
        add_datetime_to_context=True,
        timezone_identifier="Asia/Shanghai",
    )

    async def _ask(ident, msg):
        tag = ident.get("display_name") or ident.get("id")
        print(f"\n\033[36m[{tag}]\033[0m {msg}")
        print("\033[32m[小鱼]\033[0m ", end="", flush=True)
        got = []
        async for ev in probe_agent.arun(
            msg, stream=True,
            session_id=f"kb-smoke-{ident['id']}", user_id=ident["id"],
            dependencies={"当前对话者": ident},
        ):
            if ev.event == RunEvent.run_content and ev.content:
                got.append(ev.content)
                print(ev.content, end="", flush=True)
        print()
        return "".join(got)

    async def _run():
        # Finn 是 D11 项目(37) owner，应能检索到包装提案内容
        finn = {"bound": True, "id": "user_1775808580706_fcmow",
                "display_name": "叶飞(Finn)", "username": "yefei", "role": "user"}
        ans = await _ask(finn, "D11 那个浓缩咖啡液包装提案里都提了哪些包装盒型？")
        hit = any(k in ans for k in ("翻盖", "飞机盒", "PP", "盒型", "包装"))
        print(f"\033[90m  (提到具体盒型={hit}，len={len(ans)})\033[0m")

    asyncio.run(_run())
