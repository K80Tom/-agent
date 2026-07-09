"""资产向量同步服务。"""

from __future__ import annotations

import re

from app.models.asset_entity_model import AssetEntity
from app.models.asset_variant_model import AssetVariant
from app.services.vector.doubao_embedding_service import DoubaoEmbeddingService
from app.services.vector.milvus_vector_store import MilvusVectorStore


EMPTY_TEXT_VALUES = {
    "",
    "-",
    "--",
    "/",
    "无",
    "暂无",
    "暂无信息",
    "未填",
    "未填写",
    "未提供",
    "未提及",
    "未知",
    "不详",
    "空",
    "none",
    "null",
    "n/a",
}


def _is_emptyish(value) -> bool:
    """判断一个字段值是否没有可检索语义。"""

    if value is None:
        return True

    text = str(value).strip()
    text = text.strip(" \t\r\n。；;，,、")
    return text.lower() in EMPTY_TEXT_VALUES


def _clean_vector_text(value) -> str | None:
    """清理向量文本，去掉“字段：无”这类无效片段。"""

    if _is_emptyish(value):
        return None

    text = str(value).strip()
    segments = re.split(r"[；;\n]+", text)
    kept: list[str] = []

    for segment in segments:
        segment = segment.strip()
        if _is_emptyish(segment):
            continue

        if "：" in segment:
            _label, content = segment.split("：", 1)
            if _is_emptyish(content):
                continue
        elif ":" in segment:
            _label, content = segment.split(":", 1)
            if _is_emptyish(content):
                continue

        kept.append(segment)

    return "；".join(kept) if kept else None


def _clean_tag(value) -> str | None:
    """清理 style_tags 里的空标签。"""

    if _is_emptyish(value):
        return None
    return str(value).strip()


def _strip_leading_label(text: str, labels: list[str]) -> str:
    """去掉字段文本里已有的前缀标签，避免“外观：外观：...”."""

    cleaned = text.strip()
    for label in labels:
        for delimiter in ("：", ":"):
            prefix = f"{label}{delimiter}"
            if cleaned.startswith(prefix):
                return cleaned[len(prefix) :].strip()
    return cleaned


def build_entity_vector_text(entity: AssetEntity) -> str:
    """把 asset_entities 资产主体转成向量化文本（路线A：单向量，按判别力排序）。

    排版原则：
    1. 高熵内容放前面：名称 → 简介 → 外观/发型/服装 → 风格。
       它们每条资产都不同，是区分资产的主力信号。
    2. 低熵字段（来源项目/资产类型/分类）不写入向量文本；
    这些字段 metadata / 数据库里已有，交给结构化召回或过滤。
    3. 裸标量（年龄/身高）必须带最小标签，否则 "28"、"175" 没有语义。
    """

    lines: list[str] = []

    # —— 名称：最高判别信号，放最前，尽量裸值 ——
    name = _clean_vector_text(entity.name) or ""
    display_name = _clean_vector_text(entity.display_name) or ""
    if name and display_name and display_name != name:
        lines.append(f"{name}（{display_name}）")
    elif name or display_name:
        lines.append(name or display_name)

    # —— 语义/视觉自由文本：内容自带含义，只用轻标签点明字段角色 ——
    intro = _clean_vector_text(entity.intro)
    if intro:
        lines.append(intro)
    appearance = _clean_vector_text(entity.appearance)
    if appearance:
        appearance = _strip_leading_label(appearance, ["外观", "外观描述", "视觉", "画面"])
        if appearance:
            lines.append(f"外观：{appearance}")
    hair_description = _clean_vector_text(entity.hair_description)
    if hair_description:
        hair_description = _strip_leading_label(
            hair_description,
            ["发型长相", "发型", "头发", "头部特征"],
        )
        if hair_description:
            lines.append(f"发型长相：{hair_description}")
    outfit_description = _clean_vector_text(entity.outfit_description)
    if outfit_description:
        outfit_description = _strip_leading_label(
            outfit_description,
            ["服装", "服装描述", "穿着", "配饰"],
        )
        if outfit_description:
            lines.append(f"服装：{outfit_description}")
    if entity.style_tags:
        tags = "、".join(
            tag for tag in (_clean_tag(item) for item in entity.style_tags) if tag
        )
        if tags:
            lines.append(f"风格：{tags}")

    # —— 裸标量：必须带标签，压成一行，放在语义内容之后 ——
    attrs: list[str] = []
    if not _is_emptyish(entity.gender):
        attrs.append(f"性别{entity.gender}")
    if entity.age_value is not None:
        attrs.append(f"年龄{entity.age_value}岁")
    if entity.height_cm is not None:
        attrs.append(f"身高{entity.height_cm}cm")
    if attrs:
        lines.append(" ".join(attrs))

    return "\n".join(lines)


def build_variant_vector_text(*, variant: AssetVariant, parent_entity: AssetEntity) -> str:
    """把 asset_variants 变体+父资产转成向量化文本（路线A：按判别力排序）。

    变体自身的名称/描述/视觉提示词放最前，父资产只留必要身份锚点，
    避免父资产"整段人生"稀释变体自己的信号。
    """

    lines: list[str] = []

    # —— 变体自身：最高判别信号 ——
    variant_name = _clean_vector_text(variant.name)
    if variant_name:
        lines.append(variant_name)
    description = _clean_vector_text(variant.description)
    if description:
        lines.append(description)
    visual_prompt = _clean_vector_text(variant.visual_prompt)
    if visual_prompt:
        lines.append(f"视觉：{visual_prompt}")
    usage_context = _clean_vector_text(variant.usage_context)
    if usage_context:
        lines.append(f"使用场景：{usage_context}")

    # —— 父资产身份锚点：让变体挂到正确主体，但不喧宾夺主 ——
    parent_name = _clean_vector_text(parent_entity.name)
    if parent_name:
        lines.append(f"这是{parent_name}的变体造型。")
    parent_intro = _clean_vector_text(parent_entity.intro)
    if parent_intro:
        lines.append(parent_intro)

    return "\n".join(lines)



class AssetVectorSyncService:
    """负责把结构化资产同步到向量数据库。"""

    def __init__(self) -> None:
        self.embedding_service = DoubaoEmbeddingService()
        self.vector_store = MilvusVectorStore()

    def sync_entity(self, entity: AssetEntity) -> None:
        """同步 asset_entities 资产主体到向量数据库。"""

        text = build_entity_vector_text(entity)
        if not text.strip():
            print(f"skip empty entity vector text: {entity.id}")
            return

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
        if not text.strip():
            print(f"skip empty variant vector text: {variant.id}")
            return

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
