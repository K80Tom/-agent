"""Embedding 模型基础接口。

domain 层只定义项目需要的能力，不依赖具体云厂商 SDK。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """文本向量化模型接口。"""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """把一段文本转换成向量。"""
        raise NotImplementedError
