"""本地文本解析器。

这个解析器只用于开发阶段模拟第三方文档解析服务。
它把 txt 文本按空行拆成多个 ParsedBlock。
"""

from __future__ import annotations
from app.domain.interfaces.document_parser import BaseDocumentParser
from app.domain.models.parsed_document import ParsedBlock, ParsedDocument

class LocalTextParser(BaseDocumentParser):
    """本地文本解析器。 """
    parser_name = "local_text"

    def parse(self, *, file_name: str, content: bytes) -> ParsedDocument:
        """把txt文件内容解析成ParsedDocument。"""

        text = content.decode("utf-8")

        pargraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        blocks = [
            ParsedBlock(
                content=paragraph,
                page_num=None,
                block_index=index,
                content_type="text",
                metadata={},
            )
            for index, paragraph in enumerate(pargraphs)
        ]

        return ParsedDocument(
            file_name=file_name,
            parser_name=self.parser_name,
            blocks=blocks,
            metadata={
                "source_file": file_name,
                "parser": self.parser_name,
            },
        )