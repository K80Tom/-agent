"""文档解析器接口。

任何第三方文档解析服务都应该实现 BaseDocumentParser。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models.parsed_document import ParsedDocument


class BaseDocumentParser(ABC):
    """文档解析器基础接口。"""

    @abstractmethod
    def parse(self, *, file_name: str, content: bytes) -> ParsedDocument:
        """把上传的文件内容解析成统一的ParsedDocument。"""

