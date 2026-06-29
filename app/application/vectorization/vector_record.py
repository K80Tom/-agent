"""向量化记录模型。

表示一条准备写入向量数据库的数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VectorRecord:
    """准备写入向量数据库的一条记录。"""

    source_table: str
    source_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)