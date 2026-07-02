"""资产变体 repository。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset_variant_model import AssetVariant


class AssetVariantRepository:
    """负责 common.asset_variants 的数据库访问。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_unique_key(
        self,
        *,
        asset_entity_id: UUID | str,
        variant_kind: str,
        name: str,
    ) -> AssetVariant | None:
        """根据 asset_entity_id + variant_kind + name 查询变体。"""

        statement = select(AssetVariant).where(
            AssetVariant.asset_entity_id == self._to_uuid(asset_entity_id),
            AssetVariant.variant_kind == variant_kind,
            AssetVariant.name == name,
        )
        return self.db.scalar(statement)

    def save(self, variant: dict[str, Any]) -> AssetVariant:
        """保存资产变体，已存在则更新。"""

        entity = self.get_by_unique_key(
            asset_entity_id=variant["asset_entity_id"],
            variant_kind=variant["variant_kind"],
            name=variant["name"],
        )
        is_new = entity is None
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

        if entity is None:
            entity = AssetVariant(created_at=now, updated_at=now)
            self.db.add(entity)

        entity.asset_entity_id = self._to_uuid(variant["asset_entity_id"])
        entity.variant_kind = variant["variant_kind"]
        entity.name = variant["name"]
        entity.description = variant.get("description")
        entity.usage_context = variant.get("usage_context")
        entity.visual_prompt = variant.get("visual_prompt")
        entity.approved = variant.get("approved")
        entity.status = variant.get("status") or "pending_review"
        entity.is_primary = bool(variant.get("is_primary", False))
        entity.sort_order = int(variant.get("sort_order") or 0)
        entity.source_file_url = variant.get("source_file_url")
        entity.source_text = variant.get("source_text")
        entity.metadata_ = variant.get("metadata") or {}

        entity.updated_at = now

        self.db.flush()
        self.db.refresh(entity)
        return entity

    @staticmethod
    def _to_uuid(value: UUID | str) -> UUID:
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
