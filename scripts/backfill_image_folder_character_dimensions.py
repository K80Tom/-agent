"""回填图片文件夹入库角色的年龄和身高估值。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session
from app.models.asset_entity_model import AssetEntity
from app.models.asset_source_project_model import AssetSourceProject
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService
from scripts.ingest_image_folder_assets import infer_character_age, infer_character_height


def build_hint_text(entity: AssetEntity) -> str:
    """把当前资产字段拼成估算年龄和身高的线索。"""

    metadata = entity.metadata_ or {}
    parts = [
        entity.name,
        entity.display_name,
        entity.intro,
        entity.appearance,
        entity.hair_description,
        entity.outfit_description,
        entity.category,
        metadata.get("source_relative_path"),
        metadata.get("source_folder"),
        metadata.get("top_folder"),
    ]
    parts.extend(str(tag) for tag in (entity.style_tags or []))
    return " ".join(str(part) for part in parts if str(part or "").strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="回填图片文件夹角色年龄/身高估值。")
    parser.add_argument(
        "--source-project-name",
        required=True,
        help="来源项目名，例如 FF超能九组资产库_1783580494256。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要更新的记录，不写库、不同步向量。",
    )
    args = parser.parse_args()

    db = create_session()
    try:
        source_project = (
            db.query(AssetSourceProject)
            .filter(AssetSourceProject.name == args.source_project_name)
            .first()
        )
        if source_project is None:
            raise ValueError(f"source project not found: {args.source_project_name}")

        rows = (
            db.query(AssetEntity)
            .filter(
                AssetEntity.source_project_id == source_project.id,
                AssetEntity.asset_kind == "character",
            )
            .all()
        )

        vector_sync_service = None if args.dry_run else AssetVectorSyncService()
        updated_count = 0

        for entity in rows:
            if entity.age_value is not None and entity.height_cm is not None:
                continue

            hint_text = build_hint_text(entity)
            estimated_fields = dict((entity.metadata_ or {}).get("estimated_fields") or {})

            if entity.age_value is None:
                entity.age_value = infer_character_age(hint_text, entity.gender)
                estimated_fields["age_value"] = True

            if entity.height_cm is None:
                entity.height_cm = infer_character_height(hint_text, entity.gender)
                estimated_fields["height_cm"] = True

            metadata = dict(entity.metadata_ or {})
            metadata["estimated_fields"] = estimated_fields
            entity.metadata_ = metadata

            updated_count += 1
            print(
                f"[update] {entity.name}: "
                f"age={entity.age_value}, height_cm={entity.height_cm}"
            )

            if vector_sync_service is not None:
                vector_sync_service.sync_entity(entity)

        if args.dry_run:
            db.rollback()
        else:
            db.commit()

        print(f"updated_count={updated_count}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
