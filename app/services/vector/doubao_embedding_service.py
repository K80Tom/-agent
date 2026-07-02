"""豆包多模态 embedding 服务。"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class DoubaoEmbeddingService:
    """调用火山方舟 embedding 接口生成向量。"""

    def __init__(self) -> None:
        if not settings.ark_api_key:
            raise ValueError("Missing ARK_API_KEY in .env")
        if not settings.doubao_embedding_model:
            raise ValueError("Missing DOUBAO_EMBEDDING_MODEL in .env")

        self.api_key = settings.ark_api_key
        self.model = settings.doubao_embedding_model
        self.endpoint = f"{settings.ark_base_url.rstrip('/')}/embeddings/multimodal"

    def embed_text(self, text: str) -> list[float]:
        """把文本转成 embedding 向量。"""

        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Doubao embedding failed: "
                f"status={response.status_code}, body={response.text}"
            )

        data = response.json()
        return data["data"]["embedding"]