"""创建 asset_entities 对应的 Milvus collection。"""

from __future__ import annotations

from pathlib import Path
import os
import sys

from dotenv import load_dotenv
from pymilvus import DataType, MilvusClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    load_dotenv(override=True)

    collection_name = os.getenv("MILVUS_COLLECTION_ASSET_ENTITY", "asset_entity_vectors")
    embedding_dim = int(os.getenv("EMBEDDING_DIM", "0"))

    if embedding_dim <= 0:
        raise ValueError("请先在 .env 里配置 EMBEDDING_DIM")

    client = MilvusClient(
        uri=os.getenv("MILVUS_URI"),
        user=os.getenv("MILVUS_USER"),
        password=os.getenv("MILVUS_PASSWORD"),
    )

    if client.has_collection(collection_name):
        print(f"collection already exists: {collection_name}")
        return

    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )

    schema.add_field(
        field_name="id",
        datatype=DataType.VARCHAR,
        is_primary=True,
        max_length=128,
    )
    
    schema.add_field(
        field_name="text",
        datatype=DataType.VARCHAR,
        max_length=8192,
    )
    
    schema.add_field(
        field_name="vector",
        datatype=DataType.FLOAT_VECTOR,
        dim=embedding_dim,
    )

    schema.add_field(
        field_name="metadata",
        datatype=DataType.JSON,
    )

    index_params = MilvusClient.prepare_index_params()

    index_params.add_index(
        field_name="vector",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )

    print(f"created collection: {collection_name}")


if __name__ == "__main__":
    main()