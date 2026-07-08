import os

from fastapi import FastAPI
from a2wsgi import WSGIMiddleware

from config import URL_PREFIX
from routers import agent_chat

# 复用现有 Flask 应用(app.py 的 create_app 已在其内部完成 DB 初始化/迁移/蓝图注册)。
from app import app as flask_app


def create_app() -> FastAPI:
    app = FastAPI(
        title="奈娃咖啡项目管理",
        # 文档只描述 FastAPI 侧新写的路由；Flask 路由不进 OpenAPI。
        docs_url=f"{URL_PREFIX}/fastapi-docs" if URL_PREFIX else "/fastapi-docs",
        openapi_url=f"{URL_PREFIX}/fastapi-openapi.json" if URL_PREFIX else "/fastapi-openapi.json",
    )

    # 1) 先挂 FastAPI 原生 async 路由(带 URL_PREFIX，与 Flask 完整路径对齐)。
    app.include_router(agent_chat.router, prefix=URL_PREFIX)

    # 2) 再用整个 Flask app 兜底(挂根 '/'；它的 blueprint 自带 /pm 前缀)。
    #    所有未被上面精确匹配的路径 —— 页面、静态资源、其余 44 条 API —— 全部落到 Flask。
    app.mount("/", WSGIMiddleware(flask_app))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    # main:app 现在是完整服务(FastAPI async 路由 + Flask 兜底)，接管 Flask 原来的 8092。
    # 生产由 pm2 改跑 uvicorn 起本 app(见 ecosystem.config.js)。
    port = int(os.environ.get("PORT", 8092))
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=True)
