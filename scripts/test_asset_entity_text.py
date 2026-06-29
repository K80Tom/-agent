"""测试 asset_entities 转 embedding_text。"""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.application.vectorization.asset_entity_text_builder import build_asset_entity_vector_record
from app.application.vectorization.asset_entity_text_builder import build_asset_entity_text
from app.infrastructure.database.postgres import get_postgres_connection
from app.infrastructure.repositories.asset_entity_repository import AssetEntityRepository


def main() -> None:
    with get_postgres_connection() as connection:
        repository = AssetEntityRepository(connection)
        rows = repository.list_vectorizable(limit=3)

    print("rows:", len(rows))

    for row in rows:
        record = build_asset_entity_vector_record(row)

        print("=" * 80)
        print("source_table:", record.source_table)
        print("source_id:", record.source_id)
        print("metadata:", record.metadata)
        print("text:")
        print(record.text)


if __name__ == "__main__":
    main()