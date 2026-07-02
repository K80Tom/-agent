"""测试 Excel 单行主图上传到 TOS。"""

from __future__ import annotations

from pathlib import Path
import pprint
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.excel_asset_parser import ExcelAssetParser
from app.services.excel_image_upload_service import ExcelImageUploadService


def main() -> None:
    """选择一行 Excel 资产，上传这一行的主图，并打印 URL。"""

    if len(sys.argv) < 2:
        print("用法 1: python scripts/test_excel_primary_image_upload.py <excel_path> [source_project_name] [asset_name] [row_index]")
        print(
            "用法 2: python scripts/test_excel_primary_image_upload.py "
            "<excel_path> [source_project_name] [asset_name] [sheet_name] [excel_row_number]"
        )
        return

    file_path = Path(sys.argv[1])
    source_project_name = sys.argv[2] if len(sys.argv) >= 3 else "天尊"
    asset_name = sys.argv[3] if len(sys.argv) >= 4 else "preview"
    select_args = sys.argv[4:]

    parser = ExcelAssetParser()
    rows = parser.parse(
        file_name=file_path.name,
        content=file_path.read_bytes(),
    )
    row = _select_row(rows, select_args)
    if row is None:
        return

    print("准备上传主图:")
    print("sheet:", row.sheet_name)
    print("row_number:", row.row_number)
    print("images:")
    pprint.pp(row.images, width=120, sort_dicts=False)

    uploader = ExcelImageUploadService()
    result = uploader.upload_primary_image(
        excel_path=str(file_path),
        row=row,
        source_project_name=source_project_name,
        asset_name=asset_name,
    )

    print("=" * 80)
    print("上传结果:")
    pprint.pp(result, width=120, sort_dicts=False)


def _select_row(rows, args):
    if not rows:
        print("没有解析出资产行")
        return None

    if not args:
        return rows[0]

    if len(args) == 1:
        row_index = int(args[0])
        if row_index < 0 or row_index >= len(rows):
            print(f"row_index 超出范围: {row_index}, 当前范围: 0 - {len(rows) - 1}")
            return None
        return rows[row_index]

    sheet_name = args[0]
    excel_row_number = int(args[1])

    for row in rows:
        if row.sheet_name == sheet_name and row.row_number == excel_row_number:
            return row

    print(f"没有找到工作表 {sheet_name} 第 {excel_row_number} 行")
    return None


if __name__ == "__main__":
    main()
