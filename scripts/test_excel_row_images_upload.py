"""测试上传 Excel 某一行的全部图片。"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.excel_asset_parser import ExcelAssetParser
from app.services.excel_image_upload_service import ExcelImageUploadService


def main() -> None:
    if len(sys.argv) < 5:
        raise SystemExit(
            "Usage: python scripts/test_excel_row_images_upload.py "
            "<excel_path> <sheet_name> <row_number> <asset_name>"
        )

    excel_path = sys.argv[1]
    sheet_name = sys.argv[2]
    row_number = int(sys.argv[3])
    asset_name = sys.argv[4]

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

    print("row fields:")
    pprint(target_row.fields)
    print("row images:")
    pprint(target_row.images)
    print("=" * 80)

    uploader = ExcelImageUploadService()
    uploaded_images = uploader.upload_row_images(
        excel_path=excel_path,
        row=target_row,
        source_project_name=path.stem,
        asset_name=asset_name,
    )

    print("uploaded images:")
    pprint(uploaded_images)


if __name__ == "__main__":
    main()