"""资产媒体 repository。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.asset_media_model import AssetMedia
from app.models.asset_variant_model import AssetVariant  # noqa: F401


class AssetMediaRepository:
    """负责 common.asset_media 的数据库写入。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        asset_entity_id: UUID,
        asset_variant_id: UUID | None = None,
        media_kind: str,
        view_angle: str | None = None,
        title: str | None = None,
        description: str | None = None,
        storage_bucket: str | None = None,
        storage_path: str | None = None,
        storage_url: str | None = None,
        width_px: int | None = None,
        height_px: int | None = None,
        format: str | None = None,
        sha256: str | None = None,
        is_primary: bool = False,
        approved: bool | None = None,
        sort_order: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> AssetMedia:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

        media = AssetMedia(
            asset_entity_id=asset_entity_id,
            asset_variant_id=asset_variant_id,
            media_kind=media_kind,
            view_angle=view_angle,
            title=title,
            description=description,
            storage_bucket=storage_bucket,
            storage_path=storage_path,
            storage_url=storage_url,
            width_px=width_px,
            height_px=height_px,
            format=format,
            sha256=sha256,
            is_primary=is_primary,
            approved=approved,
            sort_order=sort_order,
            metadata_=metadata or {},
            created_at=now,
        )

        self.db.add(media)
        self.db.flush()
        self.db.refresh(media)
        return media
