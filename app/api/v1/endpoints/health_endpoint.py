"""健康检查 endpoint。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse


router = APIRouter()


@router.get("", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """返回服务健康状态。"""

    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        version=settings.app_version,
    )
