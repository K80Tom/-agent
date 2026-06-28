"""文档解析结果模型。

这里定义的是第三方解析器解析后的统一结果。
不管底层用阿里云、火山、TextIn 还是 MinerU，最后都要转成 ParsedDocument。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class ParsedBlock:
    """解析后的一个内容块。

    一个 block 可以来自阿里云的一个 layout，也可以来自其他解析器的一段文本、一个表格或一个图片说明。
    """
    content: str
    page_num: int | None = None
    block_index: int | None = None
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ParsedDocument:
    """解析后的文档。

    这个类是所有第三方解析器的统一结果。
    """
    file_name: str
    parser_name: str
    blocks: list[ParsedBlock]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """把所有的block内容拼接成一个 Markdown 文档。"""
        return "\n\n".join(block.content for block in self.blocks if block.content.strip())


