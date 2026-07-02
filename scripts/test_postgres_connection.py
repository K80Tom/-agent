"""测试 PostgreSQL 连接。"""

from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session


def main() -> None:
    """连接 PostgreSQL，并查询 asset_entities 数量。"""

    db = create_session()
    try:
        count = db.execute(text("select count(*) from common.asset_entities")).scalar_one()
    finally:
        db.close()

    print("连接成功")
    print("asset_entities count:", count)


if __name__ == "__main__":
    main()
