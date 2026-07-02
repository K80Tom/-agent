"""资产向量检索接口 schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssetSearchRequest(BaseModel):
    """资产语义检索请求。"""

    query: str = Field(..., min_length=1, description="检索文本")
    limit: int = Field(default=10, ge=1, le=50, description="返回数量")


class AssetSearchItem(BaseModel):
    """资产语义检索结果项。"""

    score: float | None = None
    source_table: str
    source_id: str
    asset_kind: str | None = None
    name: str | None = None
    display_name: str | None = None
    parent_entity_id: str | None = None
    parent_entity_name: str | None = None
    intro: str | None = None
    appearance: str | None = None
    description: str | None = None
    usage_context: str | None = None
    visual_prompt: str | None = None
    source_file_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    vector_text: str | None = None


class AssetSearchResponse(BaseModel):
    """资产语义检索响应。"""

    count: int
    items: list[AssetSearchItem]