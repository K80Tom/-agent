"""资产主体 repository。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset_entity_model import AssetEntity


class AssetEntityRepository:
    """负责 common.asset_entities 的数据库访问。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, asset_id: UUID | str) -> AssetEntity | None:
        """根据 id 查询资产主体。"""

        statement = select(AssetEntity).where(AssetEntity.id == self._to_uuid(asset_id))
        return self.db.scalar(statement)

    def get_by_unique_key(
        self,
        *,
        source_project_id: UUID | str | None,
        asset_kind: str,
        name: str,
    ) -> AssetEntity | None:
        """根据唯一键查询资产主体。

        数据库唯一键是 source_project_id + asset_kind + name。
        """

        statement = select(AssetEntity).where(
            AssetEntity.source_project_id == self._to_uuid_or_none(source_project_id),
            AssetEntity.asset_kind == asset_kind,
            AssetEntity.name == name,
        )
        return self.db.scalar(statement)

    def save(self, asset: dict[str, Any]) -> AssetEntity:
        """保存资产主体。

        如果唯一键已经存在，则更新已有记录；否则插入新记录。
        """

        entity = self.get_by_unique_key(
            source_project_id=asset.get("source_project_id"),
            asset_kind=asset["asset_kind"],
            name=asset["name"],
        )
        is_new = entity is None

        if entity is None:
            entity = AssetEntity()
            self.db.add(entity)

        self._apply_asset(entity, asset, is_new=is_new)
        self.db.flush()
        self.db.refresh(entity)
        return entity

    def create(self, asset: dict[str, Any]) -> AssetEntity:
        """兼容旧调用：保存资产主体。"""

        return self.save(asset)

    def _apply_asset(self, entity: AssetEntity, asset: dict[str, Any], *, is_new: bool) -> None:
        """把入库字段应用到 ORM 对象。"""

        entity.source_project_id = self._to_uuid_or_none(asset.get("source_project_id"))
        entity.source_project_name = asset.get("source_project_name")
        entity.asset_kind = asset["asset_kind"]
        entity.name = asset["name"]
        entity.display_name = asset.get("display_name")
        entity.intro = asset.get("intro")
        entity.appearance = asset.get("appearance")
        entity.age_value = asset.get("age_value")
        entity.gender = asset.get("gender")
        entity.height_cm = asset.get("height_cm")
        entity.hair_description = asset.get("hair_description")
        entity.outfit_description = asset.get("outfit_description")
        entity.category = asset.get("category")
        entity.style_tags = asset.get("style_tags") or []
        entity.approved = asset.get("approved")
        entity.reuse_scope = asset.get("reuse_scope") or "all_projects"
        entity.status = asset.get("status") or "pending_review"
        entity.source_file_url = asset.get("source_file_url")
        entity.metadata_ = asset.get("metadata") or {}

        if not is_new:
            entity.updated_at = datetime.now()

    @staticmethod
    def _to_uuid(value: UUID | str) -> UUID:
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

    @classmethod
    def _to_uuid_or_none(cls, value: Any) -> UUID | None:
        if value is None:
            return None
        return cls._to_uuid(value)
