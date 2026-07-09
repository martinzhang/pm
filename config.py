"""
Projects -- configuration & constants
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path):
    """极简 .env 加载：KEY=VALUE，忽略注释/空行；已存在的环境变量优先，不覆盖。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


# 环境配置（endpoint / key 等）：dev 机读 .env.dev，prod 机读 .env.prod。
# 两者都尝试，_load_env_file 不覆盖已存在变量（pm2 直接注入的优先）。
_load_env_file(os.path.join(BASE_DIR, ".env.dev"))
_load_env_file(os.path.join(BASE_DIR, ".env.prod"))

DB_PATH = os.path.join(BASE_DIR, "projects.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
URL_PREFIX = os.environ.get("URL_PREFIX", "")
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".txt", ".md", ".csv",
    ".ai", ".psd", ".sketch", ".fig",
}

os.makedirs(UPLOAD_DIR, exist_ok=True)

GATEWAY_USERS_FILE = os.path.join(os.path.dirname(BASE_DIR), "nmc-auth-gateway", "data", "users.json")
GATEWAY_ORG_FILE = os.path.join(os.path.dirname(BASE_DIR), "nmc-auth-gateway", "data", "org.json")

PHASES = [
    ("concept", "概念"), ("design", "设计"), ("prototype", "打样"),
    ("review", "评审"), ("production", "量产"), ("qc", "质检"), ("shipped", "交付"),
]
PHASE_MAP = dict(PHASES)
PHASE_COLORS = {
    "concept": "#95A3B3", "design": "#C89D9F", "prototype": "#D4A574",
    "review": "#A594C4", "production": "#82B89C", "qc": "#D4956A", "shipped": "#7CB5B3",
}
PRIORITIES = [("urgent", "紧急"), ("high", "高"), ("medium", "中"), ("low", "低")]
PROJECT_STATUS = [("active", "进行中"), ("paused", "暂停"), ("completed", "已完成"), ("archived", "已归档")]
PROJECT_COLORS = ["#95A3B3", "#C89D9F", "#82B89C", "#A594C4", "#D4A574", "#7CB5B3", "#D4956A", "#8BA3C7"]

# ── Agent DB ──
AGENT_DB_URL = os.environ.get(
    "AGENT_DB_URL",
    "postgresql+asyncpg://postgres:nmCafe1503@192.168.0.239:15432/pm_agent",
)
# PgVector（agno 向量库）用同步 SQLAlchemy 引擎，驱动必须是 psycopg，不能用 asyncpg。
# 默认从 AGENT_DB_URL 派生（只换驱动），保证与会话库同库；也可用 AGENT_DB_URL_SYNC 单独覆盖。
AGENT_DB_URL_SYNC = os.environ.get(
    "AGENT_DB_URL_SYNC",
    AGENT_DB_URL.replace("+asyncpg", "+psycopg"),
)

# ── Embedding（ollama / bge-m3，向量维度 1024）──
EMBED_HOST = os.environ.get("EMBED_HOST", "http://192.168.0.239:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
# 检索相似度下限（hybrid_score，0~1）：低于此分的片段不召回，避免噪声进上下文。
# 实测 bge-m3 中文 hybrid 分整体偏低——强相关约 0.30~0.40、噪声约 0.17~0.23，
# 0.25 卡在两者之间的 gap。生产可用 EMBED_SCORE_THRESHOLD 覆盖再调。
EMBED_SCORE_THRESHOLD = float(os.environ.get("EMBED_SCORE_THRESHOLD", "0.25"))

# ── AI（经 litellm 网关；配置见 .env.prod，由 pm2 env_file 注入）──
MINIMAX_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE = os.environ.get("LLM_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7-highspeed")
PHASE_ORDER = [p[0] for p in PHASES]
FILE_CONTENT_PER_FILE = 50000
FILE_CONTENT_TOTAL = 500000
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VLM_MAX_PER_REQUEST = 5
