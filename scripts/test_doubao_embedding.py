"""Test Doubao multimodal embedding with one asset text."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.application.vectorization.asset_entity_text_builder import build_asset_entity_vector_record
from app.infrastructure.database.postgres import get_postgres_connection
from app.infrastructure.embeddings.doubao_embedder import DoubaoEmbedder
from app.infrastructure.repositories.asset_entity_repository import AssetEntityRepository


def main() -> None:
    with get_postgres_connection() as connection:
        repository = AssetEntityRepository(connection)
        rows = repository.list_vectorizable(limit=1)

    if not rows:
        print("No vectorizable asset entity found")
        return

    record = build_asset_entity_vector_record(rows[0])

    embedder = DoubaoEmbedder()
    vector = embedder.embed_text(record.text)

    print("source_id:", record.source_id)
    print("text:")
    print(record.text)
    print("=" * 80)
    print("vector dimension:", len(vector))
    print("vector first 5:", vector[:5])


if __name__ == "__main__":
    main()
