"""FastAPI 应用入口。

这个文件只负责创建 FastAPI 应用、挂载路由。
不要在这里写入库、检索、推荐等业务逻辑。
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import health
from app.config.settings import settings


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()

