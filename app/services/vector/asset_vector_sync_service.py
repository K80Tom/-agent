"""资产向量同步服务。"""

from __future__ import annotations

from app.models.asset_entity_model import AssetEntity
from app.models.asset_variant_model import AssetVariant
from app.services.vector.doubao_embedding_service import DoubaoEmbeddingService
from app.services.vector.milvus_vector_store import MilvusVectorStore


def build_entity_vector_text(entity: AssetEntity) -> str:
    """把 asset_entities 资产主体转换成向量化文本。"""

    parts: list[str] = []

    def add(label: str, value) -> None:
        if value is None:
            return

        if isinstance(value, str) and not value.strip():
            return

        if isinstance(value, list) and not value:
            return

        parts.append(f"{label}：{value}")

    add("来源项目", entity.source_project_name)
    add("资产类型", entity.asset_kind)
    add("资产名称", entity.name)
    add("展示名称", entity.display_name)
    add("简介", entity.intro)
    add("外观描述", entity.appearance)
    add("年龄", entity.age_value)
    add("性别", entity.gender)
    add("身高厘米", entity.height_cm)
    add("发型或长相描述", entity.hair_description)
    add("服装描述", entity.outfit_description)
    add("资产分类", entity.category)
    add("风格标签", entity.style_tags)

    return "\n".join(parts)


def build_variant_vector_text(
    *,
    variant: AssetVariant,
    parent_entity: AssetEntity,
) -> str:
    """把 asset_variants 变体和父资产一起转换成向量化文本。"""

    parts: list[str] = []

    def add(label: str, value) -> None:
        if value is None:
            return

        if isinstance(value, str) and not value.strip():
            return

        if isinstance(value, list) and not value:
            return

        parts.append(f"{label}：{value}")

    add("来源项目", parent_entity.source_project_name)
    add("资产类型", parent_entity.asset_kind)
    add("主体名称", parent_entity.name)
    add("主体展示名称", parent_entity.display_name)
    add("主体简介", parent_entity.intro)
    add("主体外观描述", parent_entity.appearance)
    add("主体年龄", parent_entity.age_value)
    add("主体性别", parent_entity.gender)
    add("主体身高厘米", parent_entity.height_cm)
    add("主体发型或长相描述", parent_entity.hair_description)
    add("主体服装描述", parent_entity.outfit_description)
    add("主体分类", parent_entity.category)
    add("主体风格标签", parent_entity.style_tags)
    add("变体类型", variant.variant_kind)
    add("变体名称", variant.name)
    add("变体描述", variant.description)
    add("变体使用场景", variant.usage_context)
    add("变体视觉提示词", variant.visual_prompt)
    add("变体来源文本", variant.source_text)

    return "\n".join(parts)


class AssetVectorSyncService:
    """负责把结构化资产同步到向量数据库。"""

    def __init__(self) -> None:
        self.embedding_service = DoubaoEmbeddingService()
        self.vector_store = MilvusVectorStore()

    def sync_entity(self, entity: AssetEntity) -> None:
        """同步 asset_entities 资产主体到向量数据库。"""

        text = build_entity_vector_text(entity)
        vector = self.embedding_service.embed_text(text)
        metadata = {
            "source_table": "asset_entities",
            "source_id": str(entity.id),
            "asset_kind": entity.asset_kind,
            "source_project_id": str(entity.source_project_id) if entity.source_project_id else None,
            "name": entity.name,
        }

        self.vector_store.upsert(
            vector_id=str(entity.id),
            vector=vector,
            text=text,
            metadata=metadata,
        )

        print(text)
        print("vector dimension:", len(vector))
        print("vector first 5:", vector[:5])

    def sync_variant(self, variant: AssetVariant, parent_entity: AssetEntity) -> None:
        """同步 asset_variants 资产变体到向量数据库。"""

        text = build_variant_vector_text(
            variant=variant,
            parent_entity=parent_entity,
        )
        vector = self.embedding_service.embed_text(text)
        metadata = {
            "source_table": "asset_variants",
            "source_id": str(variant.id),
            "asset_kind": parent_entity.asset_kind,
            "source_project_id": str(parent_entity.source_project_id) if parent_entity.source_project_id else None,
            "name": variant.name,
            "parent_entity_id": str(parent_entity.id),
            "parent_entity_name": parent_entity.name,
        }

        self.vector_store.upsert(
            vector_id=str(variant.id),
            vector=vector,
            text=text,
            metadata=metadata,
        )

        print(text)
        print("vector dimension:", len(vector))
        print("vector first 5:", vector[:5])
