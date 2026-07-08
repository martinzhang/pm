from typing import Annotated

from fastapi import Depends, Request

# 复用 auth.py 里已有、且与 HTTP 框架无关的纯逻辑，避免重复实现。
from auth import _load_env_dev, _dev_user_from_db
from models import get_db
from datetime import datetime, timezone
import urllib.parse


def get_current_user(request: Request) -> dict:
    """FastAPI 依赖：从 nginx 认证头解析当前用户；开发环境按 .env.dev 回退。

    等价于 Flask 的 auth.load_user + g.user，但以返回值形式交给路由（Depends 注入）。
    """
    uid = request.headers.get("X-Auth-UserId", "")
    uname = request.headers.get("X-Auth-User", "")
    dname = urllib.parse.unquote(request.headers.get("X-Auth-Name", "") or "")
    role = request.headers.get("X-Auth-Role", "member")

    if not uid:
        # 开发模式：优先读 .env.dev 中的 DEV_USER（逻辑照搬 auth.load_user）
        dev_username = _load_env_dev().get("DEV_USER", "").strip()
        if dev_username:
            found = _dev_user_from_db(dev_username)
            if found:
                uid, uname, dname, role = found
            else:
                uid, uname, dname, role = "local", dev_username, dev_username, "member"
        else:
            uid, uname, dname, role = "local", "local", "本地用户", "admin"

    user = {"id": uid, "username": uname, "name": dname or uname, "role": role}

    # upsert users（覆盖式更新 display_name/role），与 Flask 版一致；失败静默。
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (id,username,display_name,role,created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,role=excluded.role",
            (uid, uname, dname or uname, role, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return user


# 类型别名：路由签名里写 `user: CurrentUser` 即可拿到当前用户。
CurrentUser = Annotated[dict, Depends(get_current_user)]
