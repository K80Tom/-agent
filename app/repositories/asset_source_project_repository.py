"""资产来源项目 repository。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo
from app.models.asset_source_project_model import AssetSourceProject


class AssetSourceProjectRepository:
    """负责 common.asset_source_projects 的数据库访问。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_name(self, name: str) -> AssetSourceProject | None:
        """根据项目名称查询来源项目。"""

        statement = select(AssetSourceProject).where(AssetSourceProject.name == name)
        return self.db.scalar(statement)

    def get_by_code(self, code: str) -> AssetSourceProject | None:
        """根据项目 code 查询来源项目。"""

        statement = select(AssetSourceProject).where(AssetSourceProject.code == code)
        return self.db.scalar(statement)
    


    def get_or_create(
        self,
        *,
        name: str,
        code: str | None = None,
        description: str | None = None,
        project_type: str | None = None,
        metadata: dict | None = None,
    ) -> AssetSourceProject:
        """根据项目名称获取来源项目，不存在则创建。"""

        existing = self.get_by_name(name)
        if existing is not None:
            return existing
        
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

        project = AssetSourceProject(
            name=name,
            code=code,
            description=description,
            project_type=project_type,
            metadata_=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.db.add(project)
        self.db.flush()
        self.db.refresh(project)
        return project
