"""查询理解服务。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings


ASSET_KIND_HINTS = {
    "人像",
    "妆造",
    "服装",
    "场景概念",
    "场景四视图",
    "站位图",
    "道具",
    "参考图",
    "视频片段",
    "成片视频",
    "音色",
    "音乐",
    "选景/堪景图",
    "未知",
}

LEGACY_ASSET_KIND_HINTS = {
    "character": "人像",
    "scene": "场景概念",
    "prop": "道具",
    "variant": "妆造",
    "unknown": "未知",
}


class QueryUnderstandingService:
    """把用户自然语言 query 转成更适合检索的结构化意图。"""

    def __init__(self) -> None:
        if not settings.ark_api_key:
            raise ValueError("Missing ARK_API_KEY in .env")
        if not settings.llm_model:
            raise ValueError("Missing ARK_LLM_MODEL or DOUBAO_LLM_MODEL in .env")

        self.api_key = settings.ark_api_key
        self.model = settings.llm_model
        self.endpoint = f"{settings.ark_base_url.rstrip('/')}/chat/completions"

    def understand(self, query: str) -> dict[str, Any]:
        """调用豆包理解 query，并生成多条检索改写。"""

        prompt = f"""
                你是短剧资产检索系统的查询理解模块。

                用户会输入一句自然语言，用来找短剧生产资产。
                资产类型包括：人像、妆造、服装、场景概念、场景四视图、站位图、道具、参考图、视频片段、成片视频、音色、音乐、选景/堪景图等。
                请把 query 解析成结构化 JSON，并生成 2 条适合向量检索的中文 rewrite。

                要求：
                1. 只输出 JSON，不要 Markdown。
                2. 不要编造用户没说的信息。
                3. 如果没有明确资产名，name_hint 为 null。
                4. asset_kind_hint 只能是：人像、妆造、服装、场景概念、场景四视图、站位图、道具、参考图、视频片段、成片视频、音色、音乐、选景/堪景图、未知。
                5. rewrites 要保留用户核心视觉特征、身份、场景、风格词。
                6. 字段必须对应数据库 asset_entities 表，不要输出未列出的字段。

                用户 query：
                {query}

                输出格式：
                {{
                "source_project_name_hint": null,
                "asset_kind_hint": "未知",
                "name_hint": null,
                "display_name_hint": null,
                "intro_terms": [],
                "appearance_terms": [],
                "age_value_hint": null,
                "gender_hint": null,
                "height_cm_hint": null,
                "hair_description_terms": [],
                "outfit_description_terms": [],
                "category_terms": [],
                "style_tags": [],
                "approved_hint": null,
                "reuse_scope_hint": null,
                "status_hint": null,
                "negative_terms": [],
                "rewrites": [
                    "改写1",
                    "改写2"
                ]
                }}
            """.strip()

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Query understanding failed: "
                f"status={response.status_code}, body={response.text}"
            )

        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_json(content, fallback_query=query)

    def _parse_json(self, content: str, *, fallback_query: str) -> dict[str, Any]:
        """解析模型返回的 JSON，失败时给一个兜底结果。"""

        text = content.strip()

        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").strip()
            text = text.removesuffix("```").strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}

        rewrites = data.get("rewrites")
        if not isinstance(rewrites, list) or not rewrites:
            rewrites = [fallback_query]

        return {
           "source_project_name_hint": data.get("source_project_name_hint"),
            "asset_kind_hint": self._normalize_asset_kind_hint(data.get("asset_kind_hint")),
            "name_hint": data.get("name_hint"),
            "display_name_hint": data.get("display_name_hint"),
            "intro_terms": data.get("intro_terms") or [],
            "appearance_terms": data.get("appearance_terms") or [],
            "age_value_hint": data.get("age_value_hint"),
            "gender_hint": data.get("gender_hint"),
            "height_cm_hint": data.get("height_cm_hint"),
            "hair_description_terms": data.get("hair_description_terms") or [],
            "outfit_description_terms": data.get("outfit_description_terms") or [],
            "category_terms": data.get("category_terms") or [],
            "style_tags": data.get("style_tags") or [],
            "approved_hint": data.get("approved_hint"),
            "reuse_scope_hint": data.get("reuse_scope_hint"),
            "status_hint": data.get("status_hint"),
            "negative_terms": data.get("negative_terms") or [],
            "rewrites": [str(item) for item in rewrites[:2]],
        }

    def _normalize_asset_kind_hint(self, value: Any) -> str:
        """把模型返回的资产类型收敛到项目允许的中文枚举。"""

        if value is None:
            return "未知"

        text = str(value).strip()
        if text in ASSET_KIND_HINTS:
            return text

        return LEGACY_ASSET_KIND_HINTS.get(text.lower(), "未知")
