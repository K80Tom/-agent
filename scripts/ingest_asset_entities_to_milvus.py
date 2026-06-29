"""Embed asset_entities rows and upsert them into Milvus."""

from __future__ import annotations

from pathlib import Path
import os
import sys

from dotenv import load_dotenv
from pymilvus import MilvusClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.application.vectorization.asset_entity_text_builder import build_asset_entity_vector_record
from app.infrastructure.database.postgres import get_postgres_connection
from app.infrastructure.embeddings.doubao_embedder import DoubaoEmbedder
from app.infrastructure.repositories.asset_entity_repository import AssetEntityRepository


def main() -> None:
    load_dotenv(override=True)

    collection_name = os.getenv("MILVUS_COLLECTION_ASSET_ENTITY", "asset_entity_vectors")

    client = MilvusClient(
        uri=os.getenv("MILVUS_URI"),
        user=os.getenv("MILVUS_USER"),
        password=os.getenv("MILVUS_PASSWORD"),
    )

    embedder = DoubaoEmbedder()

    with get_postgres_connection() as connection:
        repository = AssetEntityRepository(connection)
        rows = repository.list_vectorizable(limit=3)

    if not rows:
        print("No vectorizable asset_entities rows found")
        return

    milvus_rows = []

    for row in rows:
        record = build_asset_entity_vector_record(row)
        vector = embedder.embed_text(record.text)

        milvus_rows.append(
            {
                "id": record.source_id,
                "text": record.text,
                "metadata": record.metadata,
                "vector": vector,
            }
        )

        print(f"prepared: {record.source_id}")

    result = client.upsert(
        collection_name=collection_name,
        data=milvus_rows,
    )

    print(f"upserted rows: {len(milvus_rows)}")
    print("milvus result:", result)


if __name__ == "__main__":
    main()
