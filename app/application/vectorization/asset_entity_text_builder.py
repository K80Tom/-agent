"""资产主体向量化文本构造器。

负责把 common.asset_entities 的一行结构化数据，转换成适合 embedding 的自然语言文本。
"""

from app.application.vectorization.vector_record import VectorRecord

def build_asset_entity_text(row: dict) -> str:
    """把 asset_entities 的一行数据拼成 embedding_text。"""

    parts: list[str] = []

    def add(label: str, value) -> None:
        if value is None:
            return

        if isinstance(value, str) and not value.strip():
            return

        parts.append(f"{label}：{value}")

    add("来源项目", row.get("source_project_name"))
    add("资产类型", row.get("asset_kind"))
    add("资产名称", row.get("name"))
    add("展示名称", row.get("display_name"))
    add("简介", row.get("intro"))
    add("外观描述", row.get("appearance"))
    add("年龄", row.get("age_value"))
    add("性别", row.get("gender"))
    add("身高厘米", row.get("height_cm"))
    add("发型或长相描述", row.get("hair_description"))
    add("服装描述", row.get("outfit_description"))
    add("资产分类", row.get("category"))
    add("风格标签", row.get("style_tags"))

    return "\n".join(parts)

def build_asset_entity_vector_record(row: dict) -> VectorRecord:
    """把 asset_entities 的一行数据转换成 VectorRecord。"""

    text = build_asset_entity_text(row)

    return VectorRecord(
        source_table="asset_entities",
        source_id=str(row["id"]),
        text=text,
        metadata={
            "source_project_id": str(row["source_project_id"]) if row.get("source_project_id") else None,
            "source_project_name": row.get("source_project_name"),
            "asset_kind": row.get("asset_kind"),
            "name": row.get("name"),
            "display_name": row.get("display_name"),
            "category": row.get("category"),
            "status": row.get("status"),
            "source_file_url": row.get("source_file_url"),
        },
    )