"""测试资产向量文本构造。"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session
from app.models.asset_entity_model import AssetEntity
from app.models.asset_variant_model import AssetVariant
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService


def main() -> None:
    """从数据库取一条 entity 和一条 variant，打印向量化文本。"""

    db = create_session()
    try:
        service = AssetVectorSyncService()

        entity = db.query(AssetEntity).first()
        if entity is None:
            print("没有 asset_entities 数据")
        else:
            print("=" * 80)
            print("asset_entities vector text:")
            service.sync_entity(entity)

        variant = db.query(AssetVariant).first()
        if variant is None:
            print("没有 asset_variants 数据")
        else:
            parent_entity = (
                db.query(AssetEntity)
                .filter(AssetEntity.id == variant.asset_entity_id)
                .first()
            )
            if parent_entity is None:
                print("variant 找不到父 entity")
            else:
                print("=" * 80)
                print("asset_variants vector text:")
                service.sync_variant(variant, parent_entity)
    finally:
        db.close()


if __name__ == "__main__":
    main()