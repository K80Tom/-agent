"""测试 LLMExcelAssetExtractor 的 Excel 行字段抽取效果。"""

from __future__ import annotations

from pathlib import Path
import pprint
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.excel_asset_parser import ExcelAssetParser
from app.services.llm_excel_asset_extractor import LLMExcelAssetExtractor


def main() -> None:
    """解析 Excel 中的一行，并用大模型抽取资产字段。"""

    if len(sys.argv) < 2:
        print(
            "用法 1: python scripts/test_llm_excel_asset_extractor.py "
            "<excel_path> [source_project_id] [source_project_name] [row_index]"
        )
        print(
            "用法 2: python scripts/test_llm_excel_asset_extractor.py "
            "<excel_path> [source_project_id] [source_project_name] [sheet_name] [excel_row_number]"
        )
        return

    file_path = Path(sys.argv[1])
    source_project_id = sys.argv[2] if len(sys.argv) >= 3 else None
    source_project_name = sys.argv[3] if len(sys.argv) >= 4 else "天尊"

    parser = ExcelAssetParser()
    rows = parser.parse(
        file_name=file_path.name,
        content=file_path.read_bytes(),
    )

    if not rows:
        print("没有解析出资产行")
        return

    row = _select_row(rows, sys.argv[4:])
    if row is None:
        return

    print("原始 Excel 行:")
    print("sheet:", row.sheet_name)
    print("row_number:", row.row_number)
    pprint.pp(row.fields, width=120, sort_dicts=False)
    print("images:")
    pprint.pp(row.images, width=120, sort_dicts=False)

    extractor = LLMExcelAssetExtractor()
    asset = extractor.extract(
        row,
        source_project_id=source_project_id,
        source_project_name=source_project_name,
    )

    print("=" * 80)
    print("模型抽取后的 asset_entities 字段:")
    pprint.pp(asset, width=120, sort_dicts=False)


def _select_row(rows, args):
    """根据命令行参数选择一行资产。"""

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
