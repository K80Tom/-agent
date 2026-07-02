"""测试把 Excel 某一行图片上传并写入 asset_media。"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session
from app.models.asset_variant_model import AssetVariant  # noqa: F401
from app.repositories.asset_media_repository import AssetMediaRepository
from app.services.asset_media_mapping import build_asset_media_data
from app.services.excel_asset_parser import ExcelAssetParser
from app.services.excel_image_upload_service import ExcelImageUploadService


def main() -> None:
    if len(sys.argv) < 7:
        raise SystemExit(
            "Usage: python scripts/test_excel_row_images_to_asset_media.py "
            "<excel_path> <sheet_name> <row_number> <asset_entity_id> <asset_kind> <asset_name>"
        )

    excel_path = sys.argv[1]
    sheet_name = sys.argv[2]
    row_number = int(sys.argv[3])
    asset_entity_id = UUID(sys.argv[4])
    asset_kind = sys.argv[5]
    asset_name = sys.argv[6]

    path = Path(excel_path)

    parser = ExcelAssetParser()
    rows = parser.parse(
        file_name=path.name,
        content=path.read_bytes(),
    )

    target_row = next(
        (
            row
            for row in rows
            if row.sheet_name == sheet_name and row.row_number == row_number
        ),
        None,
    )
    if target_row is None:
        raise SystemExit(f"Row not found: sheet={sheet_name}, row={row_number}")

    raw_approved = target_row.fields.get("是否通过")
    approved = True if raw_approved == "是" else None

    uploaded_images = ExcelImageUploadService().upload_row_images(
        excel_path=excel_path,
        row=target_row,
        source_project_name=path.stem,
        asset_name=asset_name,
    )

    db = create_session()
    try:
        repository = AssetMediaRepository(db)
        inserted = []

        for uploaded_image in uploaded_images:
            media_data = build_asset_media_data(
                asset_entity_id=asset_entity_id,
                uploaded_image=uploaded_image,
                asset_kind=asset_kind,
                asset_name=asset_name,
                source_project_name=path.stem,
                approved=approved,
            )
            media = repository.create(**media_data)
            inserted.append(
                {
                    "id": str(media.id),
                    "asset_entity_id": str(media.asset_entity_id),
                    "asset_variant_id": str(media.asset_variant_id)
                    if media.asset_variant_id
                    else None,
                    "media_kind": media.media_kind,
                    "title": media.title,
                    "storage_url": media.storage_url,
                    "is_primary": media.is_primary,
                    "sort_order": media.sort_order,
                }
            )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("inserted asset_media:")
    pprint(inserted)


if __name__ == "__main__":
    main()
