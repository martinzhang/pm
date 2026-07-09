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
    AGENT_DB_URL_SYNC, EMBED_HOST, EMBED_MODEL, EMBED_DIM,
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

    yield: dict(filepath, scope, project_id, task_id, file_name)
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
        }


def index_attachments() -> Dict[str, int]:
    """离线索引：遍历文档类附件，逐个 add_content(path=...) 灌进向量库。

    agno 按扩展名自动选 reader（pdf/docx/xlsx/pptx/md/txt…）+ 分块 + 向量化，我们只负责
    把物理路径和归属 metadata 交给它。metadata 的 project_id 是检索期可见性过滤的命脉，
    统一转字符串（JSONB filter 按字符串精确匹配）。

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
            metadata = {
                "source": "attachment",
                "scope": att["scope"],
                "project_id": str(att["project_id"]) if att["project_id"] is not None else "",
                "task_id": str(att["task_id"]) if att["task_id"] is not None else "",
                "file_name": att["file_name"],
            }
            kb.add_content(path=att["filepath"], metadata=metadata)
            indexed += 1
    finally:
        conn.close()
    return {"indexed": indexed, "skipped_missing": skipped}


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
