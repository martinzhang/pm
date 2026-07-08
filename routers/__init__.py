"""
FastAPI routers 包（迁移期）

每个模块对应一个原 Flask blueprint 或一组相关路由。router 内部一律写相对路径，
URL_PREFIX 由 main.py 在 include_router 时统一加，避免前缀散落各处。
"""
