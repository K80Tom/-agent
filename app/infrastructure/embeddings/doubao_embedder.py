"""Doubao multimodal embedding client.

This implementation uses Volcengine Ark's REST endpoint:
/api/v3/embeddings/multimodal
"""

from __future__ import annotations

from typing import Any
import os

from dotenv import load_dotenv
import httpx

from app.domain.interfaces.embedder import BaseEmbedder


class DoubaoEmbedder(BaseEmbedder):
    """Call Doubao multimodal embedding through Ark REST API."""

    def __init__(self) -> None:
        load_dotenv(override=True)

        api_key = os.getenv("ARK_API_KEY")
        base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        model = os.getenv("DOUBAO_EMBEDDING_MODEL")

        if not api_key:
            raise ValueError("Missing ARK_API_KEY in .env")
        if not model:
            raise ValueError("Missing DOUBAO_EMBEDDING_MODEL in .env")

        self.api_key = api_key
        self.model = model
        self.endpoint = f"{base_url.rstrip('/')}/embeddings/multimodal"

    def embed_text(self, text: str) -> list[float]:
        """Embed plain text with Doubao multimodal embedding."""

        if not text or not text.strip():
            raise ValueError("Embedding text cannot be empty")

        payload = {
            "model": self.model,
            "input": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }
        return self._request_embedding(payload)

    def embed_image_url(self, image_url: str) -> list[float]:
        """Embed an image URL with Doubao multimodal embedding."""

        if not image_url or not image_url.strip():
            raise ValueError("Image URL cannot be empty")

        payload = {
            "model": self.model,
            "input": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_url,
                    },
                }
            ],
        }
        return self._request_embedding(payload)

    def _request_embedding(self, payload: dict[str, Any]) -> list[float]:
        """Send a request to Ark and extract the embedding vector."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Doubao embedding request failed: "
                f"status={response.status_code}, body={response.text}"
            )

        return self._extract_embedding(response.json())

    @staticmethod
    def _extract_embedding(data: dict[str, Any]) -> list[float]:
        """Extract embedding from common Ark/OpenAI-like response shapes."""

        if isinstance(data.get("embedding"), list):
            return list(data["embedding"])

        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("embedding"), list):
            return list(result["embedding"])

        response_data = data.get("data")
        if isinstance(response_data, dict) and isinstance(response_data.get("embedding"), list):
            return list(response_data["embedding"])

        if isinstance(response_data, list) and response_data:
            first_item = response_data[0]
            if isinstance(first_item, dict) and isinstance(first_item.get("embedding"), list):
                return list(first_item["embedding"])

        raise RuntimeError(f"Cannot find embedding in response: {data}")
