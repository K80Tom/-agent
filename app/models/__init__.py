"""ORM 模型集中导入。"""

from __future__ import annotations

from app.models.asset_entity_model import AssetEntity
from app.models.asset_source_project_model import AssetSourceProject

__all__ = [
    "AssetEntity",
    "AssetSourceProject",
]
