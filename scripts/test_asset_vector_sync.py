"""测试单条 asset_entities 同步到 Milvus。"""

from __future__ import annotations

from pathlib import Path
import sys
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session
from app.models.asset_entity_model import AssetEntity
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService


def main() -> None:
    """从 PostgreSQL 取一条资产主体，生成向量并写入 Milvus。"""

    entity_id = sys.argv[1] if len(sys.argv) >= 2 else None

    db = create_session()
    try:
        query = db.query(AssetEntity)
        if entity_id:
            entity = query.filter(AssetEntity.id == UUID(entity_id)).first()
        else:
            entity = query.order_by(AssetEntity.updated_at.desc()).first()

        if entity is None:
            print("没有找到 asset_entities 数据")
            return

        print("sync entity:")
        print("id:", entity.id)
        print("name:", entity.name)
        print("asset_kind:", entity.asset_kind)

        service = AssetVectorSyncService()
        service.sync_entity(entity)
        print("Milvus sync ok")
    finally:
        db.close()


if __name__ == "__main__":
    main()
