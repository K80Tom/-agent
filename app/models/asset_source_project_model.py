"""资产来源项目 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetSourceProject(Base):
    """对应 common.asset_source_projects。"""

    __tablename__ = "asset_source_projects"
    __table_args__ = {"schema": "common"}

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str | None] = mapped_column(String(128))
    code: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(512))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    project_type: Mapped[str | None] = mapped_column(String(64))
