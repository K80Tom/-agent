"""批量预览 Excel 行的 LLM 资产字段抽取结果。"""

from __future__ import annotations

from pathlib import Path
import pprint
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.excel_asset_parser import ExcelAssetParser
from app.services.llm_excel_asset_extractor import LLMExcelAssetExtractor


def main() -> None:
    """批量预览 LLM 对 Excel 资产行的字段抽取结果，不写数据库。"""

    if len(sys.argv) < 2:
        print(
            "用法: python scripts/preview_llm_excel_asset_entities.py "
            "<excel_path> [source_project_name] [limit] [sheet_name]"
        )
        return

    file_path = Path(sys.argv[1])
    source_project_name = sys.argv[2] if len(sys.argv) >= 3 else "天尊"
    limit = int(sys.argv[3]) if len(sys.argv) >= 4 else 5
    sheet_name = sys.argv[4] if len(sys.argv) >= 5 else None

    parser = ExcelAssetParser()
    rows = parser.parse(
        file_name=file_path.name,
        content=file_path.read_bytes(),
    )

    if sheet_name:
        rows = [row for row in rows if row.sheet_name == sheet_name]

    rows = rows[:limit]

    print("文件:", file_path.name)
    print("项目:", source_project_name)
    print("筛选工作表:", sheet_name or "全部")
    print("本次预览行数:", len(rows))

    if not rows:
        print("没有可预览的资产行")
        return

    extractor = LLMExcelAssetExtractor()
    assets = extractor.extract_many(
        rows,
        source_project_id=None,
        source_project_name=source_project_name,
    )

    for index, (row, asset) in enumerate(zip(rows, assets), start=1):
        print("=" * 100)
        print(f"预览 {index}/{len(rows)}")
        print("sheet:", row.sheet_name)
        print("row_number:", row.row_number)
        print("原始字段:")
        pprint.pp(row.fields, width=120, sort_dicts=False)
        print("图片数量:", len(row.images))
        print("LLM 抽取结果:")
        pprint.pp(asset, width=120, sort_dicts=False)


if __name__ == "__main__":
    main()
