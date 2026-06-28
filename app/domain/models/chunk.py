"""Chunk 业务模型。

Chunk 表示从 Document 中切分出来的一段文本，是 RAG 检索的基本单位。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Chunk:
    """文档切块对象。"""

    id: str
    document_id: str
    text: str
    chunk_index: int
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

