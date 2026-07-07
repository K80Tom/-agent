"""资产入库接口 schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import Field
from uuid import UUID


class ExcelIngestResponse(BaseModel):
    """Excel 资产入库响应。"""

    count: int
    items: list[dict[str, Any]]
    uploaded_file_path: str
    uploaded_file_deleted: bool = False


class JsonAssetItem(BaseModel):
    """JSON 资产入库的单条资产。

    这份结构对应 common.asset_entities 的主体字段。
    对接方按这个结构传，后端可以直接入资产库。
    """

    # 资产类型：character / scene / prop / other
    asset_kind: str

    # 资产唯一名称，入库去重会用到 asset_kind + name。
    name: str

    # 展示名，不传时后端可以默认用 name。
    display_name: str | None = None

    # 简介：人物简介、场景简介、道具说明等。
    intro: str | None = None

    # 视觉描述：人物外观、场景画面、道具外观等。
    appearance: str | None = None

    # 人物类字段。场景/道具可以不传。
    age_value: int | None = None
    gender: str | None = None
    height_cm: int | None = None
    hair_description: str | None = None
    outfit_description: str | None = None

    # 分类和标签，用于检索和筛选。
    category: str | None = None
    style_tags: list[str] = Field(default_factory=list)

    # 审核、复用、状态字段。
    approved: bool | None = None
    reuse_scope: str = "needs_review"
    status: str = "pending_review"

    # 主图/参考图 URL。如果对方已经上传图片，就直接传这个。
    source_file_url: str | None = None

    # 扩展字段，保存对接来源、原始字段、备注等。
    metadata: dict[str, Any] = Field(default_factory=dict)



class JsonAssetIngestRequest(BaseModel):
    """JSON 资产批量入库请求。"""

    # 项目 ID 可选；如果后面要严格按项目去重，可以让对方传。
    source_project_id: UUID | None = None

    # 项目名推荐传，比如“天尊”。
    source_project_name: str | None = None

    # 批量资产列表。
    assets: list[JsonAssetItem]
    
class JsonAssetIngestItemResponse(BaseModel):
    """JSON 资产入库后返回给调用方的单条结果。"""

    id: UUID
    asset_kind: str
    name: str

class JsonAssetIngestResponse(BaseModel):
    """JSON 资产入库响应。"""

    count: int
    items: list[JsonAssetIngestItemResponse]