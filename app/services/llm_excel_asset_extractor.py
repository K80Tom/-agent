"""基于大模型的 Excel 资产字段抽取服务。"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.prompts.excel_asset_extraction_prompt import build_excel_asset_extraction_prompt
from app.services.excel_asset_parser import ExcelAssetRow


class LLMExcelAssetExtractor:
    """把 Excel 资产行解析成 asset_entities 可入库字段。"""

    def __init__(self) -> None:
        if not settings.ark_api_key:
            raise ValueError("Missing ARK_API_KEY in .env")
        if not settings.llm_model:
            raise ValueError("Missing ARK_LLM_MODEL or DOUBAO_LLM_MODEL in .env")

        self.api_key = settings.ark_api_key
        self.model = settings.llm_model
        self.endpoint = f"{settings.ark_base_url.rstrip('/')}/chat/completions"

    def extract(
        self,
        row: ExcelAssetRow,
        *,
        source_project_id: str | None,
        source_project_name: str,
    ) -> dict[str, Any]:
        """抽取单行资产字段。"""

        prompt = self._build_single_prompt(row)
        raw_result = self._call_llm(prompt)
        asset = self._parse_json_object_with_repair(raw_result)
        return self._normalize_asset(
            asset,
            row=row,
            source_project_id=source_project_id,
            source_project_name=source_project_name,
        )

    def extract_many(
        self,
        rows: list[ExcelAssetRow],
        *,
        source_project_id: str | None,
        source_project_name: str,
    ) -> list[dict[str, Any]]:
        """批量抽取多行资产字段。"""

        if not rows:
            return []

        prompt = self._build_batch_prompt(rows)
        raw_result = self._call_llm(prompt)
        assets = self._parse_json_array_with_repair(raw_result)
        assets_by_key = self._index_assets_by_row_key(assets)

        normalized_assets: list[dict[str, Any]] = []
        for row in rows:
            row_key = self._row_key(row)
            asset = assets_by_key.get(row_key)
            if asset is None:
                normalized_assets.append(
                    self.extract(
                        row,
                        source_project_id=source_project_id,
                        source_project_name=source_project_name,
                    )
                )
                continue

            normalized_assets.append(
                self._normalize_asset(
                    asset,
                    row=row,
                    source_project_id=source_project_id,
                    source_project_name=source_project_name,
                )
            )

        return normalized_assets

    def _build_single_prompt(self, row: ExcelAssetRow) -> str:
        fields_text = json.dumps(row.fields, ensure_ascii=False, indent=2)

        return build_excel_asset_extraction_prompt(
            task="请把下面这一行 Excel 资产数据转换成 common.asset_entities 表需要的标准 JSON 对象。",
            output_shape="object",
            rows_text=f"""
                工作表名称：{row.sheet_name}
                Excel 行号：{row.row_number}
                Excel 字段：
                {fields_text}
                """.strip(),
            )

    def _build_batch_prompt(self, rows: list[ExcelAssetRow]) -> str:
        input_rows = [
            {
                "row_key": self._row_key(row),
                "sheet_name": row.sheet_name,
                "row_number": row.row_number,
                "fields": row.fields,
            }
            for row in rows
        ]
        rows_text = json.dumps(input_rows, ensure_ascii=False, indent=2)

        return build_excel_asset_extraction_prompt(
            task="请把下面多行 Excel 资产数据分别转换成 common.asset_entities 表需要的标准 JSON 数组。",
            output_shape="array",
            rows_text=f"Excel 行数据：\n{rows_text}",
        )

    def _call_llm(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "你只输出严格 JSON，不输出 Markdown，不输出解释。",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.endpoint, headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM asset extraction failed: "
                f"status={response.status_code}, body={response.text}"
            )

        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _parse_json_object_with_repair(self, text: str) -> dict[str, Any]:
        try:
            return self._parse_json_object(text)
        except (ValueError, json.JSONDecodeError):
            repaired_text = self._repair_json(text, expected_shape="JSON object")
            return self._parse_json_object(repaired_text)

    def _parse_json_array_with_repair(self, text: str) -> list[dict[str, Any]]:
        try:
            return self._parse_json_array(text)
        except (ValueError, json.JSONDecodeError):
            repaired_text = self._repair_json(text, expected_shape="JSON array")
            return self._parse_json_array(repaired_text)

    def _repair_json(self, text: str, *, expected_shape: str) -> str:
        """让模型修复一次非法 JSON 输出。"""

        prompt = f"""
下面内容原本应该是严格的 {expected_shape}，但是它不是合法 JSON。
请你只修复 JSON 语法问题，不要新增字段，不要删除字段，不要改写字段含义。
重点处理：
1. 字符串里的引号必须正确转义。
2. 对象之间、字段之间必须有逗号。
3. 删除 Markdown 代码块标记和解释文字。
4. 只输出修复后的严格 JSON。

待修复内容：
{text}
""".strip()
        return self._call_llm(prompt)

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        data = self._parse_json_value(text)
        if not isinstance(data, dict):
            raise ValueError(f"LLM output must be a JSON object: {data}")
        return data

    def _parse_json_array(self, text: str) -> list[dict[str, Any]]:
        data = self._parse_json_value(text)
        if isinstance(data, dict) and isinstance(data.get("assets"), list):
            data = data["assets"]
        if not isinstance(data, list):
            raise ValueError(f"LLM output must be a JSON array: {data}")
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(f"LLM array item must be an object: {item}")
        return data

    def _parse_json_value(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned_text = text.strip()
            cleaned_text = re.sub(r"^```json\s*", "", cleaned_text)
            cleaned_text = re.sub(r"^```\s*", "", cleaned_text)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

            try:
                return json.loads(cleaned_text)
            except json.JSONDecodeError:
                array_match = re.search(r"\[.*\]", cleaned_text, re.S)
                if array_match:
                    try:
                        return json.loads(array_match.group(0))
                    except json.JSONDecodeError:
                        pass

                object_match = re.search(r"\{.*\}", cleaned_text, re.S)
                if object_match:
                    try:
                        return json.loads(object_match.group(0))
                    except json.JSONDecodeError:
                        pass

        snippet = text[:1000]
        raise ValueError(f"LLM output is not valid JSON. First 1000 chars: {snippet}") from None

    def _index_assets_by_row_key(self, assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for asset in assets:
            row_key = self._clean_text(self._get_asset_value(asset, "row_key"))
            if not row_key:
                raise ValueError(f"LLM batch output missing row_key: {asset}")
            if row_key in result:
                raise ValueError(f"LLM batch output duplicated row_key: {row_key}")
            result[row_key] = asset
        return result

    @staticmethod
    def _get_asset_value(asset: dict[str, Any], key: str) -> Any:
        """读取模型字段，兼容字段名首尾多空格的情况。"""

        if key in asset:
            return asset[key]

        for raw_key, value in asset.items():
            if str(raw_key).strip() == key:
                return value

        return None

    def _normalize_asset(
        self,
        asset: dict[str, Any],
        *,
        row: ExcelAssetRow,
        source_project_id: str | None,
        source_project_name: str,
    ) -> dict[str, Any]:
        asset_kind = self._normalize_asset_kind(asset.get("asset_kind"))
        name = self._clean_text(asset.get("name"))
        if not name:
            name = self._fallback_name(row) or "无"

        style_tags = asset.get("style_tags")
        if not isinstance(style_tags, list):
            style_tags = []

        appearance = self._clean_text(asset.get("appearance"))
        hair_description = self._clean_text(asset.get("hair_description"))
        appearance, hair_description = self._fix_hair_and_appearance(
            appearance=appearance,
            hair_description=hair_description,
        )

        return {
            "source_project_id": source_project_id,
            "source_project_name": source_project_name,
            "asset_kind": asset_kind,
            "name": name,
            "display_name": self._clean_text(asset.get("display_name")) or name,
            "intro": self._clean_text(asset.get("intro")),
            "appearance": appearance,
            "age_value": self._to_int_or_none(asset.get("age_value")),
            "gender": self._normalize_gender(asset.get("gender")),
            "height_cm": self._to_int_or_none(asset.get("height_cm")),
            "hair_description": hair_description,
            "outfit_description": self._clean_text(asset.get("outfit_description")),
            "category": self._clean_text(asset.get("category")) or self._default_category(asset_kind),
            "style_tags": [str(tag).strip() for tag in style_tags if str(tag).strip()],
            "approved": self._to_bool_or_none(asset.get("approved")),
            "reuse_scope": "all_projects",
            "status": "pending_review",
            "source_file_url": None,
            "metadata": {
                "row_key": self._row_key(row),
                "source_sheet_name": row.sheet_name,
                "source_row_number": row.row_number,
                "images": row.images,
                "extractor": "llm_excel_asset_extractor",
            },
        }

    @staticmethod
    def _row_key(row: ExcelAssetRow) -> str:
        return f"{row.sheet_name}:{row.row_number}"

    @staticmethod
    def _fallback_name(row: ExcelAssetRow) -> str | None:
        """模型没抽到 name 时，从 Excel 原始字段里取一个名字。"""

        for key in ("姓名", "场景名", "资产名称", "名称", "name"):
            value = row.fields.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text.replace("\n", "")
        return None

    @staticmethod
    def _fix_hair_and_appearance(
        *,
        appearance: str | None,
        hair_description: str | None,
    ) -> tuple[str | None, str | None]:
        """修正模型把非头发信息误放到 hair_description 的情况。"""

        if not hair_description:
            return appearance, hair_description

        non_hair_keywords = [
            "伤疤",
            "疤",
            "肌肉",
            "虬结",
            "壮硕",
            "魁梧",
            "身材",
            "体态",
            "面有",
            "面部",
            "五官",
            "眼神",
            "气质",
            "表情",
            "脸",
            "轮廓",
        ]
        if not any(keyword in hair_description for keyword in non_hair_keywords):
            return appearance, hair_description

        merged_appearance = hair_description
        if appearance:
            merged_appearance = f"{appearance}；{hair_description}"

        return merged_appearance, None

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_asset_kind(value: Any) -> str:
        allowed = {"character", "scene", "prop", "clothing", "voice", "other"}
        kind = str(value or "").strip()
        return kind if kind in allowed else "other"

    @staticmethod
    def _normalize_gender(value: Any) -> str | None:
        text = str(value or "").strip()
        if text in {"男", "女", "未知"}:
            return text
        return None

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            match = re.search(r"\d+", str(value))
            return int(match.group(0)) if match else None

    @staticmethod
    def _to_bool_or_none(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"true", "1", "yes", "是", "通过", "已通过"}:
            return True
        if text in {"false", "0", "no", "否", "不通过", "未通过"}:
            return False
        return None

    @staticmethod
    def _default_category(asset_kind: str) -> str:
        mapping = {
            "character": "角色",
            "scene": "场景",
            "prop": "道具",
            "clothing": "服装",
            "voice": "音色",
        }
        return mapping.get(asset_kind, "其他")
