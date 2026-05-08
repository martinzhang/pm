"""
Projects -- configuration & constants
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

# ── AI ──
MINIMAX_API_KEY = os.environ.get(
    "MINIMAX_API_KEY",
    "sk-cp-JY_0qjYL8Y8qebUixGtghTwToFERGsd9o3S8O9CiGBaBqs0UnxV-2HRHkOAvllOJ_b0RORGRdrkGKAu4gY0-f4lL9q6qEkzSdWONwSW90AYzwvlt4exfe8o",
)
MINIMAX_BASE = "https://api.minimaxi.com/v1"
MINIMAX_MODEL = "MiniMax-M2.7"
PHASE_ORDER = [p[0] for p in PHASES]
FILE_CONTENT_PER_FILE = 50000
FILE_CONTENT_TOTAL = 500000
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VLM_MAX_PER_REQUEST = 5
