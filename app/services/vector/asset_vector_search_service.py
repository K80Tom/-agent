"""资产向量检索服务。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.asset_entity_model import AssetEntity
from app.models.asset_variant_model import AssetVariant
from app.services.vector.doubao_embedding_service import DoubaoEmbeddingService
from app.services.vector.milvus_vector_store import MilvusVectorStore


class AssetVectorSearchService:
    """负责从向量库检索资产，并回结构库补全详情。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.embedding_service = DoubaoEmbeddingService()
        self.vector_store = MilvusVectorStore()

    def search(self, *, query: str, limit: int = 10) -> list[dict[str, Any]]:
        vector = self.embedding_service.embed_text(query)
        hits = self.vector_store.search(vector=vector, limit=limit)

        results: list[dict[str, Any]] = []
        for hit in hits:
            item = self._build_result(hit)
            if item is not None:
                results.append(item)

        return results
    
    def _build_result(self, hit: dict[str, Any]) -> dict[str, Any] | None:
        metadata = hit.get("metadata") or {}
        source_table = metadata.get("source_table")
        source_id = metadata.get("source_id")

        if not source_table or not source_id:
            return None

        if source_table == "asset_entities":
            entity = self.db.get(AssetEntity, UUID(str(source_id)))
            if entity is None:
                return None

            return {
                "score": hit.get("score"),
                "source_table": source_table,
                "source_id": str(entity.id),
                "asset_kind": entity.asset_kind,
                "name": entity.name,
                "display_name": entity.display_name,
                "intro": entity.intro,
                "appearance": entity.appearance,
                "source_file_url": entity.source_file_url,
                "metadata": entity.metadata_,
                "vector_text": hit.get("text"),
            }

        if source_table == "asset_variants":
            variant = self.db.get(AssetVariant, UUID(str(source_id)))
            if variant is None:
                return None

            parent_entity = self.db.get(AssetEntity, variant.asset_entity_id)

            return {
                "score": hit.get("score"),
                "source_table": source_table,
                "source_id": str(variant.id),
                "asset_kind": parent_entity.asset_kind if parent_entity else "variant",
                "name": variant.name,
                "display_name": variant.name,
                "parent_entity_id": str(parent_entity.id) if parent_entity else None,
                "parent_entity_name": parent_entity.name if parent_entity else None,
                "description": variant.description,
                "usage_context": variant.usage_context,
                "visual_prompt": variant.visual_prompt,
                "source_file_url": variant.source_file_url,
                "metadata": variant.metadata_,
                "vector_text": hit.get("text"),
            }

        return None