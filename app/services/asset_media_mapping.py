"""asset_media 字段映射。"""

from __future__ import annotations

from typing import Any
from uuid import UUID


def detect_media_kind(*, asset_kind: str, column_header: str | None) -> str:
    """根据资产类型和 Excel 图片列名判断 media_kind。"""

    header = column_header or ""

    if asset_kind == "character":
        if "人设图" in header or "定稿" in header:
            return "character_final"
        if "三视图" in header or "多视图" in header:
            return "character_turnaround"
        if "服饰" in header or "服装" in header:
            return "costume_reference"
        return "other"

    if asset_kind == "scene":
        if "定稿" in header:
            return "scene_final"
        if "多视图" in header or "三视图" in header:
            return "scene_multi_view"
        if "参考" in header:
            return "scene_reference"
        return "other"

    if "服饰" in header or "服装" in header:
        return "costume_reference"

    return "other"


def build_sort_order(*, media_kind: str, current_order: int) -> int:
    """按媒体类型生成排序号，让主图排在前面。"""

    if media_kind in {"character_final", "scene_final"}:
        return 100 + current_order

    if media_kind in {"character_turnaround", "scene_multi_view"}:
        return 200 + current_order

    if media_kind == "costume_reference":
        return 300 + current_order

    if media_kind == "scene_reference":
        return 400 + current_order

    return 900 + current_order


def normalize_project_name(source_project_name: str) -> str:
    """把项目名规范成描述里使用的格式。"""

    name = source_project_name.strip()
    if not name:
        return "未知项目"
    if name.startswith("《") and name.endswith("》"):
        return name
    return f"《{name}》"


def normalize_media_label(column_header: str | None) -> str:
    """把 Excel 图片列名规范成标题里使用的图片类型。"""

    label = (column_header or "图片").strip()
    return (
        label.replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
        .replace("按需", "")
        .strip()
    ) or "图片"


def build_asset_media_data(
    *,
    asset_entity_id: UUID,
    uploaded_image: dict[str, Any],
    asset_kind: str,
    asset_name: str,
    source_project_name: str,
    asset_variant_id: UUID | None = None,
    approved: bool | None = None,
) -> dict[str, Any]:
    """把上传后的图片信息转换成 AssetMediaRepository.create 需要的参数。"""

    column_header = uploaded_image.get("column_header")
    media_kind = detect_media_kind(
        asset_kind=asset_kind,
        column_header=column_header,
    )
    media_label = normalize_media_label(column_header)
    project_name = normalize_project_name(source_project_name)
    sheet_name = uploaded_image.get("sheet_name") or "未知表"
    current_order = int(uploaded_image.get("sort_order") or 0)

    title = f"{asset_name}{media_label}"
    description = f"来自{project_name}{sheet_name}的{asset_name}{media_label}"

    return {
        "asset_entity_id": asset_entity_id,
        "asset_variant_id": asset_variant_id,
        "media_kind": media_kind,
        "view_angle": "unknown",
        "title": title,
        "description": description,
        "storage_bucket": uploaded_image.get("storage_bucket"),
        "storage_path": uploaded_image.get("storage_path"),
        "storage_url": uploaded_image.get("storage_url"),
        "width_px": uploaded_image.get("width"),
        "height_px": uploaded_image.get("height"),
        "format": uploaded_image.get("format"),
        "sha256": uploaded_image.get("sha256"),
        "is_primary": bool(uploaded_image.get("is_primary")),
        "approved": approved,
        "sort_order": build_sort_order(
            media_kind=media_kind,
            current_order=current_order,
        ),
        "metadata": {
            "source_project_name": source_project_name,
            "source_sheet_name": sheet_name,
            "source_row_number": uploaded_image.get("row"),
            "source_col_number": uploaded_image.get("col"),
            "column_header": column_header,
            "image_index": uploaded_image.get("image_index"),
        },
    }
