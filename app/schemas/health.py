"""健康检查接口的响应模型。"""
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str

