"""Document 业务模型。

Document 表示一份原始业务文档，例如剧本、角色设定、会议纪要、合同、制作规范。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Document:
    """原始文档对象。

    这里的 Document 是业务对象，不是数据库 ORM 模型。
    """

    id: str
    title: str
    file_name: str
    file_type: str
    text: str
    source: str | None = None
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

