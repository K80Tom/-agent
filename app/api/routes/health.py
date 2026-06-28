"""健康检查接口。

健康检查用于确认服务是否启动成功。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.health import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """返回服务健康状态。"""
    return HealthResponse(status="ok")

