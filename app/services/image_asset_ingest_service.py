"""图片资产入库 service。"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asset_entity_model import AssetEntity
from app.repositories.asset_entity_repository import AssetEntityRepository
from app.repositories.asset_media_repository import AssetMediaRepository
from app.repositories.asset_source_project_repository import AssetSourceProjectRepository
from app.services.tos_uploader import TosUploader
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ALLOWED_ASSET_KINDS = {"character", "scene", "prop", "clothing", "voice", "other"}


@dataclass(slots=True)
class ImageUploadContext:
    """图片识别上下文。"""

    file_name: str
    source_project_name: str
    asset_kind_hint: str | None


class ImageAssetIngestService:
    """编排图片 -> 豆包识别 -> TOS 上传 -> PG 入库 -> Milvus 同步。"""

    def __init__(self, db: Session) -> None:
        if not settings.ark_api_key:
            raise ValueError("Missing ARK_API_KEY in .env")
        if not settings.vision_model:
            raise ValueError("Missing DOUBAO_LLM_MODEL_2_0_LITE or DOUBAO_VISION_MODEL in .env")

        self.db = db
        self.api_key = settings.ark_api_key
        self.model = settings.vision_model
        self.endpoint = f"{settings.ark_base_url.rstrip('/')}/chat/completions"
        self.source_project_repository = AssetSourceProjectRepository(db)
        self.asset_entity_repository = AssetEntityRepository(db)
        self.asset_media_repository = AssetMediaRepository(db)
        self.tos_uploader = TosUploader()

    def ingest_image(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None,
        source_project_name: str | None,
        asset_kind_hint: str | None = None,
        sync_vector: bool = True,
    ) -> dict[str, Any]:
        """识别并入库单张图片。"""

        total_started = time.perf_counter()
        timing_ms: dict[str, int] = {}

        safe_file_name = Path(file_name).name
        suffix = Path(safe_file_name).suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError("Only image files are supported: .jpg/.jpeg/.png/.webp/.bmp")
        if not content:
            raise ValueError("Uploaded image is empty")

        project_name = source_project_name or Path(safe_file_name).stem
        normalized_kind_hint = self._normalize_asset_kind(asset_kind_hint)
        context = ImageUploadContext(
            file_name=safe_file_name,
            source_project_name=project_name,
            asset_kind_hint=normalized_kind_hint,
        )

        stage_started = time.perf_counter()
        source_project = self.source_project_repository.get_or_create(
            name=project_name,
            code="image_api_" + hashlib.md5(project_name.encode("utf-8")).hexdigest()[:12],
            description=safe_file_name,
            project_type="image_upload",
            metadata={
                "ingest_api": "asset-ingest/upload",
                "source_file_name": safe_file_name,
            },
        )
        timing_ms["source_project_get_or_create"] = self._elapsed_ms(stage_started)
        source_project_id = str(source_project.id)

        stage_started = time.perf_counter()
        image_sha256 = hashlib.sha256(content).hexdigest()
        timing_ms["image_sha256"] = self._elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        raw_asset = self._describe_image(
            content=content,
            content_type=content_type,
            context=context,
            timing_ms=timing_ms,
        )
        timing_ms["doubao_vision"] = self._elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        asset_data = self._normalize_asset(
            raw_asset=raw_asset,
            context=context,
            image_sha256=image_sha256,
        )
        timing_ms["normalize_asset"] = self._elapsed_ms(stage_started)
        asset_data["source_project_id"] = source_project_id
        asset_data["source_project_name"] = source_project.name or project_name

        stage_started = time.perf_counter()
        upload_content_type = content_type or mimetypes.guess_type(safe_file_name)[0] or "application/octet-stream"
        storage_path = self._storage_path_for(
            source_project_name=source_project.name or project_name,
            asset_kind=asset_data["asset_kind"],
            asset_name=asset_data["name"],
            file_name=safe_file_name,
            image_sha256=image_sha256,
        )
        timing_ms["build_storage_path"] = self._elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        uploaded = self.tos_uploader.upload_bytes(
            content=content,
            storage_path=storage_path,
            content_type=upload_content_type,
        )
        timing_ms["tos_upload"] = self._elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        width, height, image_format = self._image_info(content)
        timing_ms["image_info"] = self._elapsed_ms(stage_started)
        primary_image = {
            "storage_bucket": uploaded.bucket,
            "storage_path": uploaded.storage_path,
            "storage_url": uploaded.storage_url,
            "sha256": image_sha256,
            "width": width,
            "height": height,
            "format": image_format or suffix.lstrip("."),
            "is_primary": True,
            "sort_order": 0,
        }
        asset_data["source_file_url"] = uploaded.storage_url
        metadata = asset_data.setdefault("metadata", {})
        metadata["primary_image"] = primary_image
        metadata["source_file_name"] = safe_file_name
        metadata["content_type"] = upload_content_type
        metadata["ingest_timing_ms"] = timing_ms

        stage_started = time.perf_counter()
        entity = self.asset_entity_repository.save(asset_data)
        self.asset_media_repository.create(
            asset_entity_id=entity.id,
            asset_variant_id=None,
            media_kind=self._media_kind_for(entity.asset_kind),
            view_angle="unknown",
            title=entity.display_name or entity.name,
            description=entity.appearance or entity.intro,
            storage_bucket=uploaded.bucket,
            storage_path=uploaded.storage_path,
            storage_url=uploaded.storage_url,
            width_px=width,
            height_px=height,
            format=image_format or suffix.lstrip("."),
            sha256=image_sha256,
            is_primary=True,
            approved=entity.approved,
            sort_order=100,
            metadata={
                "source_project_name": entity.source_project_name,
                "source_file_name": safe_file_name,
                "extractor": "doubao_lite_image_upload_api",
            },
        )
        timing_ms["pg_write"] = self._elapsed_ms(stage_started)
        if sync_vector:
            stage_started = time.perf_counter()
            AssetVectorSyncService().sync_entity(entity)
            timing_ms["vector_sync"] = self._elapsed_ms(stage_started)
        else:
            timing_ms["vector_sync"] = 0

        timing_ms["service_total_before_commit"] = self._elapsed_ms(total_started)
        entity_metadata = dict(entity.metadata_ or {})
        entity_metadata["ingest_timing_ms"] = dict(timing_ms)
        entity.metadata_ = entity_metadata
        return self._serialize_entity(entity)

    def _describe_image(
        self,
        *,
        content: bytes,
        content_type: str | None,
        context: ImageUploadContext,
        timing_ms: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """调用豆包视觉模型识别资产字段。"""

        stage_started = time.perf_counter()
        image_b64, mime_type = self._image_for_vision(content, content_type=content_type)
        if timing_ms is not None:
            timing_ms["vision_image_prepare"] = self._elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._build_prompt(context)},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }
        if timing_ms is not None:
            timing_ms["vision_payload_build"] = self._elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if timing_ms is not None:
            timing_ms["vision_http"] = self._elapsed_ms(stage_started)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Image asset extraction failed: "
                f"status={response.status_code}, body={response.text}"
            )

        stage_started = time.perf_counter()
        data = response.json()
        content_text = data["choices"][0]["message"]["content"]
        asset = self._parse_json_object(content_text)
        asset["_raw_content"] = content_text
        asset["_model"] = data.get("model", self.model)
        if timing_ms is not None:
            timing_ms["vision_response_parse"] = self._elapsed_ms(stage_started)
        return asset

    def _build_prompt(self, context: ImageUploadContext) -> str:
        """构造图片识别提示词。"""

        asset_kind_hint_line = (
            f"\n- 资产类型提示：{context.asset_kind_hint}"
            if context.asset_kind_hint
            else ""
        )
        return f"""
你是短剧资产库的图片标注员。请只根据图片可见内容，结合文件信息，把图片转换成 common.asset_entities 表可以入库的 JSON 字段。

文件信息：
- 文件名：{context.file_name}
- 来源项目：{context.source_project_name}{asset_kind_hint_line}

要求：
1. 只输出严格 JSON，不要 Markdown，不要解释。
2. 不要把 UUID 文件名当成资产名。
3. name/display_name 用中文短名称，优先描述图片主体。
4. asset_kind 只能是 character / scene / prop / clothing / voice / other。
5. 对 character 类型，age_value 和 height_cm 必须给合理估值，不要填 null。
6. appearance 写整体视觉描述；hair_description 只写头发/头部特征；outfit_description 只写服装配饰。
7. style_tags 写适合检索的中文标签，避免太泛的“图片”“素材”。

输出 JSON 形状：
{{
  "asset_kind": "character",
  "name": "中文资产名",
  "display_name": "中文展示名",
  "intro": "一句话说明这个资产是什么，适合什么用途",
  "appearance": "主体外观、画面构成、关键视觉特征",
  "age_value": 25,
  "gender": "男/女/未知/null",
  "height_cm": 168,
  "hair_description": null,
  "outfit_description": null,
  "category": "角色/场景/道具/服装/生物/配乐/其他中的一个或更具体分类",
  "style_tags": ["标签1", "标签2"]
}}
""".strip()

    def _normalize_asset(
        self,
        *,
        raw_asset: dict[str, Any],
        context: ImageUploadContext,
        image_sha256: str,
    ) -> dict[str, Any]:
        """规整模型输出为 asset_entities 字段。"""

        asset_kind = self._normalize_asset_kind(raw_asset.get("asset_kind")) or context.asset_kind_hint or "other"
        if asset_kind not in ALLOWED_ASSET_KINDS:
            asset_kind = "other"

        name = self._clean_text(raw_asset.get("name")) or self._clean_text(raw_asset.get("display_name"))
        if not name:
            name = Path(context.file_name).stem
        display_name = self._clean_text(raw_asset.get("display_name")) or name
        gender = self._normalize_gender(raw_asset.get("gender"))
        age_value = self._to_int_or_none(raw_asset.get("age_value"))
        height_cm = self._to_int_or_none(raw_asset.get("height_cm"))

        if asset_kind == "character":
            hint_text = " ".join(
                str(item)
                for item in [
                    name,
                    display_name,
                    raw_asset.get("intro"),
                    raw_asset.get("appearance"),
                    raw_asset.get("category"),
                ]
                if str(item or "").strip()
            )
            if age_value is None:
                age_value = self._infer_character_age(hint_text, gender)
            if height_cm is None:
                height_cm = self._infer_character_height(hint_text, gender)

        return {
            "asset_kind": asset_kind,
            "name": name,
            "display_name": display_name,
            "intro": self._clean_text(raw_asset.get("intro")),
            "appearance": self._clean_text(raw_asset.get("appearance")),
            "age_value": age_value,
            "gender": gender,
            "height_cm": height_cm,
            "hair_description": self._clean_text(raw_asset.get("hair_description")),
            "outfit_description": self._clean_text(raw_asset.get("outfit_description")),
            "category": self._clean_text(raw_asset.get("category")) or self._default_category(asset_kind),
            "style_tags": self._normalize_style_tags(raw_asset.get("style_tags")),
            "approved": None,
            "reuse_scope": "all_projects",
            "status": "pending_review",
            "source_file_url": None,
            "metadata": {
                "extractor": "doubao_lite_image_upload_api",
                "vision_model": raw_asset.get("_model"),
                "image_sha256": image_sha256,
                "raw_vision_asset": {
                    key: value
                    for key, value in raw_asset.items()
                    if not key.startswith("_")
                },
            },
        }

    @staticmethod
    def _image_for_vision(content: bytes, *, content_type: str | None) -> tuple[str, str]:
        """把图片压缩成视觉模型输入。"""

        try:
            with Image.open(BytesIO(content)) as image:
                image.thumbnail((1536, 1536))
                if image.mode in {"RGBA", "LA", "P"}:
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=85, optimize=True)
                return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"
        except (UnidentifiedImageError, OSError):
            return base64.b64encode(content).decode("ascii"), content_type or "application/octet-stream"

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        content = text.strip()
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.S)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError(f"Vision output must be a JSON object: {text[:300]}")
        return parsed

    @staticmethod
    def _storage_path_for(
        *,
        source_project_name: str,
        asset_kind: str,
        asset_name: str,
        file_name: str,
        image_sha256: str,
    ) -> str:
        suffix = Path(file_name).suffix.lower() or ".jpg"
        return "/".join(
            [
                "prod",
                "asset",
                ImageAssetIngestService._safe_path_part(source_project_name),
                ImageAssetIngestService._safe_path_part(asset_kind),
                ImageAssetIngestService._safe_path_part(asset_name),
                f"{image_sha256[:12]}_{ImageAssetIngestService._safe_path_part(Path(file_name).stem)[:80]}{suffix}",
            ]
        )

    @staticmethod
    def _safe_path_part(value: str) -> str:
        text = re.sub(r"[\\/:*?\"<>|\s]+", "_", str(value)).strip("_").strip(".")
        return text or "unknown"

    @staticmethod
    def _image_info(content: bytes) -> tuple[int | None, int | None, str | None]:
        try:
            with Image.open(BytesIO(content)) as image:
                return image.width, image.height, image.format
        except (UnidentifiedImageError, OSError):
            return None, None, None

    @staticmethod
    def _media_kind_for(asset_kind: str) -> str:
        if asset_kind == "character":
            return "character_final"
        if asset_kind == "scene":
            return "scene_final"
        if asset_kind == "clothing":
            return "costume_reference"
        return "other"

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return round((time.perf_counter() - started_at) * 1000)

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = re.sub(r"\s+", " ", str(value).replace("\r", " ").replace("\n", " ")).strip()
        return text or None

    @staticmethod
    def _normalize_asset_kind(value: Any) -> str | None:
        text = ImageAssetIngestService._clean_text(value)
        if not text:
            return None
        mapping = {
            "人物": "character",
            "角色": "character",
            "人像": "character",
            "生物": "character",
            "场景": "scene",
            "道具": "prop",
            "服装": "clothing",
            "服饰": "clothing",
            "配乐": "voice",
            "音色": "voice",
        }
        return mapping.get(text, text if text in ALLOWED_ASSET_KINDS else None)

    @staticmethod
    def _normalize_gender(value: Any) -> str | None:
        text = ImageAssetIngestService._clean_text(value)
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
    def _normalize_style_tags(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = ImageAssetIngestService._clean_text(value)
        if not text:
            return []
        return [item for item in re.split(r"[、,，/|;；\s]+", text) if item.strip()]

    @staticmethod
    def _default_category(asset_kind: str) -> str:
        return {
            "character": "角色",
            "scene": "场景",
            "prop": "道具",
            "clothing": "服装",
            "voice": "配乐",
        }.get(asset_kind, "其他")

    @staticmethod
    def _infer_character_age(hint_text: str, gender: str | None) -> int:
        if any(keyword in hint_text for keyword in ("儿童", "小女孩", "小男孩", "孩子", "孩童")):
            return 9
        if any(keyword in hint_text for keyword in ("少女", "少年", "学生", "青少年")):
            return 17
        if any(keyword in hint_text for keyword in ("老年", "老人", "老太", "老爷爷", "老奶奶")):
            return 68
        if any(keyword in hint_text for keyword in ("中年", "父亲", "母亲", "叔叔", "阿姨")):
            return 45
        if any(keyword in hint_text for keyword in ("机器人", "机甲", "魔物", "怪物", "外星")):
            return 5
        return 30 if gender == "男" else 25

    @staticmethod
    def _infer_character_height(hint_text: str, gender: str | None) -> int:
        if any(keyword in hint_text for keyword in ("儿童", "小女孩", "小男孩", "孩子", "孩童")):
            return 130
        if any(keyword in hint_text for keyword in ("高大", "魁梧", "壮硕", "巨型", "大型")):
            return 190
        if any(keyword in hint_text for keyword in ("娇小", "矮小", "小型")):
            return 150
        if any(keyword in hint_text for keyword in ("机器人", "机甲", "魔物", "怪物", "外星")):
            return 180
        return 176 if gender == "男" else 165

    @staticmethod
    def _serialize_entity(entity: AssetEntity) -> dict[str, Any]:
        return {
            "id": str(entity.id),
            "source_project_id": str(entity.source_project_id) if entity.source_project_id else None,
            "source_project_name": entity.source_project_name,
            "asset_kind": entity.asset_kind,
            "name": entity.name,
            "display_name": entity.display_name,
            "intro": entity.intro,
            "appearance": entity.appearance,
            "age_value": entity.age_value,
            "gender": entity.gender,
            "height_cm": entity.height_cm,
            "hair_description": entity.hair_description,
            "outfit_description": entity.outfit_description,
            "category": entity.category,
            "style_tags": entity.style_tags,
            "approved": entity.approved,
            "reuse_scope": entity.reuse_scope,
            "status": entity.status,
            "source_file_url": entity.source_file_url,
            "metadata": entity.metadata_,
        }
