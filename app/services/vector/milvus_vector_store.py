"""Milvus 向量库写入服务。"""

from __future__ import annotations

from typing import Any

from pymilvus import DataType, MilvusClient

from app.core.config import settings


class MilvusVectorStore:
    def __init__(self) -> None:
        self.collection_name = settings.milvus_collection_asset_entity
        self.vector_dim = 2048
        self.client = MilvusClient(
            uri=settings.milvus_uri,
            token=f"{settings.milvus_user}:{settings.milvus_password}",
        )

    def ensure_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.load_collection(self.collection_name)
            return

        schema = self.client.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )

        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.vector_dim)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("metadata", DataType.JSON)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self.client.load_collection(self.collection_name)

    
    def upsert(
        self,
        *,
        vector_id: str,
        vector: list[float],
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        self.ensure_collection()
        self.client.upsert(
            collection_name=self.collection_name,
            data=[
                {
                    "id": vector_id,
                    "vector": vector,
                    "text": text,
                    "metadata": metadata,
                }
            ],
    )
        
    def search(
        self,
        *,
        vector: list[float],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.ensure_collection()
        results = self.client.search(
            collection_name=self.collection_name,
            data=[vector],
            limit=limit,
            output_fields=["id", "text", "metadata"],
            search_params={
                "metric_type": "COSINE",
                "params": {"ef": 64},
            },
        )

        hits = results[0] if results else []
        return [
            {
                "id": hit["id"],
                "score": hit["distance"],
                "text": hit["entity"].get("text"),
                "metadata": hit["entity"].get("metadata") or {},
            }
            for hit in hits
        ]

