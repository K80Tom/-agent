"""测试插入一条 asset_media。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.models.asset_variant_model import AssetVariant  # noqa: F401
from app.db.session import create_session
from app.repositories.asset_media_repository import AssetMediaRepository


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/test_asset_media_insert.py <asset_entity_id>"
        )

    asset_entity_id = sys.argv[1]

    db = create_session()
    try:
        repository = AssetMediaRepository(db)
        media = repository.create(
            asset_entity_id=asset_entity_id,
            media_kind="character_final",
            view_angle="unknown",
            title="测试媒体",
            description="测试插入 asset_media",
            storage_bucket="drama-asset",
            storage_path="test/asset_media/test.jpg",
            storage_url="https://example.com/test.jpg",
            width_px=100,
            height_px=100,
            format="jpg",
            is_primary=True,
            approved=True,
            sort_order=0,
            metadata={
                "test": True,
            },
        )
        db.commit()

        print("inserted asset_media:")
        print("id:", media.id)
        print("asset_entity_id:", media.asset_entity_id)
        print("media_kind:", media.media_kind)
        print("storage_url:", media.storage_url)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()