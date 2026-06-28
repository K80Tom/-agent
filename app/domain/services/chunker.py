"""文档切块服务。

Chunker 负责把 ParsedDocument 切成适合 embedding 和向量检索的 Chunk。
"""

from __future__ import annotations

from app.domain.models.chunk import Chunk
from app.domain.models.parsed_document import ParsedDocument

class FixedWindowChunker:
    """固定窗口切块器。

    第一版先用最简单稳定的策略：固定长度 + 重叠。
    """

    def __init__(self, *, chunk_size: int = 800, chunk_overlap: int = 150) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap 不能小于 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def split(self, *, document_id: str, parsed_document: ParsedDocument) -> list[Chunk]:
        """把 ParsedDocument 切成 Chunk 列表。"""

        text = parsed_document.to_markdown()

        if not text.strip():
            return []

        chunks: list[Chunk] = []
        start = 0
        chunk_index = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(
                    Chunk(  
                        id=f"{document_id}_chunk_{chunk_index}",
                        document_id=document_id,
                        text=chunk_text,
                        chunk_index=chunk_index,
                        metadata={
                            "source_file": parsed_document.file_name,
                            "parser": parsed_document.parser_name,
                            "chunk_size": self.chunk_size,
                            "chunk_overlap": self.chunk_overlap,
                        },
                    )
                )
                chunk_index += 1
            start += self.chunk_size - self.chunk_overlap

        return chunks
    

