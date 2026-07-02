"""批量入库 Excel 工作表中的资产行。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session
from app.services.asset_entity_ingest_service import AssetEntityIngestService


def main() -> None:
    """批量抽取并入库某个工作表的资产。"""

    parser = argparse.ArgumentParser(description="批量入库 Excel 工作表资产")
    parser.add_argument("excel_path", help="Excel 文件路径")
    parser.add_argument("source_project_name", help="来源项目名称")
    parser.add_argument("sheet_name", help="工作表名称")
    parser.add_argument("--batch-size", type=int, default=10, help="每批调用模型的行数")
    args = parser.parse_args()

    db = create_session()
    try:
        service = AssetEntityIngestService(db)
        assets = service.ingest_sheet_excel_path(
            excel_path=args.excel_path,
            source_project_name=args.source_project_name,
            sheet_name=args.sheet_name,
            batch_size=args.batch_size,
        )
    finally:
        db.close()

    print("批量入库完成")
    print("sheet:", args.sheet_name)
    print("count:", len(assets))
    for asset in assets:
        print(asset["id"], asset["asset_kind"], asset["name"])


if __name__ == "__main__":
    main()
