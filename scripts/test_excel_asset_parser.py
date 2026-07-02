"""测试 ExcelAssetParser 的解析结果。"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.excel_asset_parser import ExcelAssetParser


def main() -> None:
    """解析一个 Excel 文件，并打印解析出的资产行。"""

    if len(sys.argv) < 2:
        print("用法: python scripts/test_excel_asset_parser.py <excel_path> [limit]")
        return

    file_path = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) >= 3 else None

    parser = ExcelAssetParser()
    rows = parser.parse(
        file_name=file_path.name,
        content=file_path.read_bytes(),
    )

    display_rows = rows if limit is None else rows[:limit]

    print("文件:", file_path.name)
    print("解析出的资产行数量:", len(rows))
    print("本次打印数量:", len(display_rows))

    for row in display_rows:
        print("=" * 80)
        print("工作表:", row.sheet_name)
        print("行号:", row.row_number)
        print("字段:", row.fields)
        print("图片数量:", len(row.images))
        print("图片:", row.images)


if __name__ == "__main__":
    main()
