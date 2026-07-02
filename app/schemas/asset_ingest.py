"""资产入库接口 schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ExcelIngestResponse(BaseModel):
    """Excel 资产入库响应。"""

    count: int
    items: list[dict[str, Any]]
    uploaded_file_path: str
