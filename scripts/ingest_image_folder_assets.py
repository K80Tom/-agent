"""从图片文件夹抽样识别资产字段并入库。

适用场景：目录里只有图片，没有 Excel/JSON 字段。
流程：
1. 按包含图片的文件夹抽样。
2. 用豆包视觉模型识别 common.asset_entities 字段。
3. 上传被选中的图片到 TOS。
4. 写入 asset_entities / asset_media，并同步 Milvus 向量。
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import mimetypes
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, UnidentifiedImageError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import create_session
from app.models.asset_entity_model import AssetEntity
from app.repositories.asset_entity_repository import AssetEntityRepository
from app.repositories.asset_media_repository import AssetMediaRepository
from app.repositories.asset_source_project_repository import AssetSourceProjectRepository
from app.services.tos_uploader import TosUploader
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

TOP_FOLDER_ASSET_KIND_HINTS = {
    "人物资产": "character",
    "场景资产": "scene",
    "服装资产": "clothing",
    "生物资产": "character",
    "道具资产": "prop",
    "配乐资产": "voice",
}

ALLOWED_ASSET_KINDS = {"character", "scene", "prop", "clothing", "voice", "other"}


@dataclass(slots=True)
class ImageCandidate:
    """一张待识别、待入库的图片。"""

    path: Path
    relative_path: Path
    folder: Path
    top_folder: str
    asset_kind_hint: str


def read_env(path: Path) -> dict[str, str]:
    """读取 .env，兼容脚本里需要的自定义视觉模型变量名。"""

    data: dict[str, str] = {}
    if not path.exists():
        return data

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def clean_text(value: Any) -> str | None:
    """清理模型输出文本。"""

    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\r", " ").replace("\n", " ")).strip()
    return text or None


def list_image_groups(root: Path) -> dict[Path, list[Path]]:
    """按“直接包含图片的文件夹”分组。"""

    groups: dict[Path, list[Path]] = {}
    for image_path in root.rglob("*"):
        if not image_path.is_file():
            continue
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        relative_parts = image_path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        groups.setdefault(image_path.parent, []).append(image_path)

    for paths in groups.values():
        paths.sort(key=lambda item: item.name.lower())

    return dict(sorted(groups.items(), key=lambda item: str(item[0]).lower()))


def choose_images(paths: list[Path], limit: int) -> list[Path]:
    """从一个文件夹里选部分图片，默认均匀抽样。"""

    if limit <= 0 or len(paths) <= limit:
        return paths

    if limit == 1:
        return [paths[0]]

    last_index = len(paths) - 1
    indexes = sorted({round(index * last_index / (limit - 1)) for index in range(limit)})
    return [paths[index] for index in indexes]


def collect_candidates(
    *,
    root: Path,
    per_folder_limit: int,
    max_total: int | None,
) -> list[ImageCandidate]:
    """收集每个图片文件夹的抽样候选。"""

    candidates: list[ImageCandidate] = []
    groups = list_image_groups(root)

    for folder, image_paths in groups.items():
        relative_folder = folder.relative_to(root)
        if not relative_folder.parts:
            top_folder = root.name
        else:
            top_folder = relative_folder.parts[0]

        asset_kind_hint = TOP_FOLDER_ASSET_KIND_HINTS.get(top_folder, "other")
        for image_path in choose_images(image_paths, per_folder_limit):
            candidates.append(
                ImageCandidate(
                    path=image_path,
                    relative_path=image_path.relative_to(root),
                    folder=folder,
                    top_folder=top_folder,
                    asset_kind_hint=asset_kind_hint,
                )
            )

    if max_total is None or len(candidates) <= max_total:
        return candidates

    return limit_candidates_by_top_folder(candidates, max_total=max_total)


def limit_candidates_by_top_folder(
    candidates: list[ImageCandidate],
    *,
    max_total: int,
) -> list[ImageCandidate]:
    """按顶层分类轮询截断，避免小批量只覆盖排序靠前的类别。"""

    by_top_folder: dict[str, list[ImageCandidate]] = {}
    for candidate in candidates:
        by_top_folder.setdefault(candidate.top_folder, []).append(candidate)

    result: list[ImageCandidate] = []
    top_folders = list(by_top_folder)
    cursor = 0

    while len(result) < max_total and any(by_top_folder.values()):
        top_folder = top_folders[cursor % len(top_folders)]
        cursor += 1

        bucket = by_top_folder[top_folder]
        if not bucket:
            continue

        result.append(bucket.pop(0))

    return result


def build_prompt(candidate: ImageCandidate) -> str:
    """构造图片识别提示词。"""

    folder_text = " / ".join(candidate.relative_path.parent.parts)

    return f"""
你是短剧资产库的图片标注员。请只根据图片可见内容，结合目录名提示，把图片转换成 common.asset_entities 表可以入库的 JSON 字段。

目录信息：
- 顶层分类：{candidate.top_folder}
- 所在文件夹：{folder_text}
- 资产类型提示：{candidate.asset_kind_hint}

要求：
1. 只输出严格 JSON，不要 Markdown，不要解释。
2. 不要把 UUID 文件名当成资产名。
3. name/display_name 用中文短名称，优先结合目录语义和图片主体，例如“赛博女性战士”“现代医院走廊”“金色奖杯”。
4. asset_kind 只能是 character / scene / prop / clothing / voice / other。
5. 对 character 类型，age_value 和 height_cm 必须给合理估值，不要填 null：
   - 小女孩/小男孩按儿童估算，少年/少女按青少年估算，成年男女按青年/中年估算，老年角色按老年估算。
   - 机器人、魔物、外星生物等非真人角色，也按外观体型给“设定年龄/视觉高度”的近似整数。
   - 其他类型如 scene/prop/clothing 不适用时可以填 null。
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


def parse_json_object(text: str) -> dict[str, Any]:
    """尽量从模型输出中提取 JSON 对象。"""

    content = text.strip()
    content = re.sub(r"^```(?:json)?", "", content).strip()
    content = re.sub(r"```$", "", content).strip()

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, flags=re.S)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"Vision output is not a JSON object: {text[:500]}")


def image_for_vision(path: Path, *, max_side: int, jpeg_quality: int) -> tuple[str, str]:
    """把图片压缩成适合视觉模型的 data URL 内容。"""

    try:
        with Image.open(path) as image:
            image.thumbnail((max_side, max_side))
            if image.mode in {"RGBA", "LA", "P"}:
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                background.paste(image, mask=image.getchannel("A") if image.mode != "RGB" else None)
                image = background
            else:
                image = image.convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"
    except (UnidentifiedImageError, OSError):
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return base64.b64encode(path.read_bytes()).decode("ascii"), mime_type


def describe_image(
    *,
    candidate: ImageCandidate,
    model: str,
    api_key: str,
    base_url: str,
    timeout: float,
    max_side: int,
    jpeg_quality: int,
) -> dict[str, Any]:
    """调用豆包视觉模型，把图片识别成资产字段。"""

    image_b64, mime_type = image_for_vision(
        candidate.path,
        max_side=max_side,
        jpeg_quality=jpeg_quality,
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_prompt(candidate)},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                    },
                ],
            }
        ],
        "temperature": 0,
    }

    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Vision model failed for {candidate.relative_path}: "
            f"status={response.status_code}, body={response.text}"
        )

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    asset = parse_json_object(content)
    asset["_raw_content"] = content
    asset["_model"] = data.get("model", model)
    return asset


def normalize_style_tags(value: Any) -> list[str]:
    """把 style_tags 规整成字符串列表。"""

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text = clean_text(value)
    if not text:
        return []

    return [
        item.strip()
        for item in re.split(r"[、,，/|;；\s]+", text)
        if item.strip()
    ]


def normalize_gender(value: Any) -> str | None:
    """规整性别字段。"""

    text = clean_text(value)
    if text in {"男", "女", "未知"}:
        return text
    return None


def to_int_or_none(value: Any) -> int | None:
    """规整整数字段。"""

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        return int(match.group(0)) if match else None


def _asset_hint_text(
    *,
    raw_asset: dict[str, Any],
    candidate: ImageCandidate,
    name: str,
    display_name: str,
) -> str:
    """把可用于估算年龄/身高的线索拼成一段。"""

    parts: list[str] = [
        name,
        display_name,
        candidate.top_folder,
        str(candidate.relative_path.parent),
    ]
    for key in (
        "intro",
        "appearance",
        "hair_description",
        "outfit_description",
        "category",
    ):
        value = clean_text(raw_asset.get(key))
        if value:
            parts.append(value)
    parts.extend(normalize_style_tags(raw_asset.get("style_tags")))
    return " ".join(parts)


def infer_character_age(hint_text: str, gender: str | None) -> int:
    """为角色类资产估算年龄，避免角色年龄为空。"""

    text = hint_text.lower()

    if any(keyword in hint_text for keyword in ("婴儿", "宝宝", "幼儿", "新生儿")):
        return 1
    if any(keyword in hint_text for keyword in ("小女孩", "女童", "儿童女孩")):
        return 8
    if any(keyword in hint_text for keyword in ("小男孩", "男童", "儿童男孩")):
        return 9
    if any(keyword in hint_text for keyword in ("儿童", "孩子", "孩童")):
        return 9
    if any(keyword in hint_text for keyword in ("少女", "少年", "青少年", "高中生", "学生")):
        return 17
    if any(keyword in hint_text for keyword in ("老年", "老人", "老太", "老爷爷", "老奶奶")):
        return 68
    if any(keyword in hint_text for keyword in ("中年", "父亲", "母亲", "叔叔", "阿姨")):
        return 45
    if any(keyword in hint_text for keyword in ("机器人", "机甲", "仿生人", "机械")):
        return 3
    if any(keyword in hint_text for keyword in ("魔物", "怪物", "恶魔", "异兽", "外星生物", "狼形")):
        return 5

    if gender == "男":
        return 30
    if gender == "女":
        return 25
    if "robot" in text or "mecha" in text:
        return 3
    return 25


def infer_character_height(hint_text: str, gender: str | None) -> int:
    """为角色类资产估算身高厘米，避免角色身高为空。"""

    text = hint_text.lower()

    if any(keyword in hint_text for keyword in ("婴儿", "宝宝", "幼儿", "新生儿")):
        return 75
    if any(keyword in hint_text for keyword in ("小女孩", "女童", "儿童女孩")):
        return 125
    if any(keyword in hint_text for keyword in ("小男孩", "男童", "儿童男孩")):
        return 132
    if any(keyword in hint_text for keyword in ("儿童", "孩子", "孩童")):
        return 130
    if any(keyword in hint_text for keyword in ("少女", "青少年", "高中生", "学生")):
        return 160 if gender == "女" else 170
    if any(keyword in hint_text for keyword in ("少年",)):
        return 170 if gender == "男" else 160
    if any(keyword in hint_text for keyword in ("老年", "老人", "老太", "老爷爷", "老奶奶")):
        return 160 if gender == "女" else 168
    if any(keyword in hint_text for keyword in ("高大", "魁梧", "壮硕", "巨型", "大型")):
        return 190
    if any(keyword in hint_text for keyword in ("矮小", "娇小", "小型")):
        return 150
    if any(keyword in hint_text for keyword in ("机器人", "机甲", "仿生人", "机械")):
        return 180
    if any(keyword in hint_text for keyword in ("魔物", "怪物", "恶魔", "异兽", "狼形")):
        return 180
    if "robot" in text or "mecha" in text:
        return 180

    if gender == "男":
        return 176
    if gender == "女":
        return 165
    return 170


def fill_character_age_height(
    *,
    asset_kind: str,
    raw_asset: dict[str, Any],
    candidate: ImageCandidate,
    name: str,
    display_name: str,
    gender: str | None,
) -> tuple[int | None, int | None, dict[str, bool]]:
    """角色类资产补齐年龄和身高估值。"""

    age_value = to_int_or_none(raw_asset.get("age_value"))
    height_cm = to_int_or_none(raw_asset.get("height_cm"))
    estimated = {
        "age_value": False,
        "height_cm": False,
    }

    if asset_kind != "character":
        return age_value, height_cm, estimated

    hint_text = _asset_hint_text(
        raw_asset=raw_asset,
        candidate=candidate,
        name=name,
        display_name=display_name,
    )

    if age_value is None:
        age_value = infer_character_age(hint_text, gender)
        estimated["age_value"] = True

    if height_cm is None:
        height_cm = infer_character_height(hint_text, gender)
        estimated["height_cm"] = True

    return age_value, height_cm, estimated


def normalize_asset(
    *,
    raw_asset: dict[str, Any],
    candidate: ImageCandidate,
    image_sha256: str,
    uploaded_url: str | None,
) -> dict[str, Any]:
    """把模型结果转换成 AssetEntityRepository.save() 可用字段。"""

    asset_kind = clean_text(raw_asset.get("asset_kind")) or candidate.asset_kind_hint
    if asset_kind not in ALLOWED_ASSET_KINDS:
        asset_kind = candidate.asset_kind_hint if candidate.asset_kind_hint in ALLOWED_ASSET_KINDS else "other"

    fallback_name = candidate.relative_path.parent.name or candidate.path.stem
    name = clean_text(raw_asset.get("name")) or clean_text(raw_asset.get("display_name")) or fallback_name
    display_name = clean_text(raw_asset.get("display_name")) or name
    gender = normalize_gender(raw_asset.get("gender"))
    age_value, height_cm, estimated_fields = fill_character_age_height(
        asset_kind=asset_kind,
        raw_asset=raw_asset,
        candidate=candidate,
        name=name,
        display_name=display_name,
        gender=gender,
    )

    return {
        "asset_kind": asset_kind,
        "name": name,
        "display_name": display_name,
        "intro": clean_text(raw_asset.get("intro")),
        "appearance": clean_text(raw_asset.get("appearance")),
        "age_value": age_value,
        "gender": gender,
        "height_cm": height_cm,
        "hair_description": clean_text(raw_asset.get("hair_description")),
        "outfit_description": clean_text(raw_asset.get("outfit_description")),
        "category": clean_text(raw_asset.get("category")) or candidate.top_folder,
        "style_tags": normalize_style_tags(raw_asset.get("style_tags")),
        "approved": None,
        "reuse_scope": "all_projects",
        "status": "pending_review",
        "source_file_url": uploaded_url,
        "metadata": {
            "extractor": "doubao_vision_image_folder_ingest",
            "vision_model": raw_asset.get("_model"),
            "source_local_path": str(candidate.path),
            "source_relative_path": str(candidate.relative_path),
            "source_folder": str(candidate.relative_path.parent),
            "top_folder": candidate.top_folder,
            "image_sha256": image_sha256,
            "estimated_fields": estimated_fields,
            "raw_vision_asset": {
                key: value
                for key, value in raw_asset.items()
                if not key.startswith("_")
            },
        },
    }


def safe_path_part(value: str) -> str:
    """把中文/空格路径片段转换成 TOS key 里稳定的片段。"""

    text = re.sub(r"[\\/:*?\"<>|]+", "_", value).strip().strip(".")
    text = re.sub(r"\s+", "_", text)
    return text or "unknown"


def storage_path_for(
    *,
    source_project_code: str,
    candidate: ImageCandidate,
    image_sha256: str,
) -> str:
    """生成 TOS 存储路径。"""

    folder_parts = [safe_path_part(part) for part in candidate.relative_path.parent.parts]
    suffix = candidate.path.suffix.lower() or ".jpg"
    file_name = f"{image_sha256[:12]}_{safe_path_part(candidate.path.stem)[:80]}{suffix}"
    return "/".join(
        ["asset-images", "image-folder-ingest", source_project_code, *folder_parts, file_name]
    )


def image_info(path: Path) -> tuple[int | None, int | None, str | None]:
    """读取图片宽高和格式。"""

    try:
        with Image.open(path) as image:
            return image.width, image.height, image.format
    except (UnidentifiedImageError, OSError):
        return None, None, None


def media_kind_for(asset_kind: str) -> str:
    """给图片文件夹入库的媒体类型。"""

    if asset_kind == "character":
        return "character_final"
    if asset_kind == "scene":
        return "scene_final"
    if asset_kind == "clothing":
        return "costume_reference"
    return "other"


def write_jsonl(path: Path | None, item: dict[str, Any]) -> None:
    """追加写入 JSONL 结果。"""

    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def existing_relative_paths(db, source_project_id) -> set[str]:
    """读取当前来源项目已处理过的本地相对路径。"""

    rows = (
        db.query(AssetEntity.metadata_)
        .filter(AssetEntity.source_project_id == source_project_id)
        .all()
    )
    paths: set[str] = set()
    for (metadata,) in rows:
        relative_path = (metadata or {}).get("source_relative_path")
        if relative_path:
            paths.add(str(relative_path))
    return paths


def build_arg_parser() -> argparse.ArgumentParser:
    """创建命令行参数。"""

    parser = argparse.ArgumentParser(
        description="按文件夹抽样图片，用豆包视觉模型识别资产字段并入库。"
    )
    parser.add_argument(
        "--root",
        required=True,
        help="图片资产库根目录。",
    )
    parser.add_argument(
        "--source-project-name",
        default=None,
        help="入库来源项目名；不传则使用根目录名。",
    )
    parser.add_argument(
        "--per-folder-limit",
        type=int,
        default=1,
        help="每个直接包含图片的文件夹最多处理几张，默认 1。",
    )
    parser.add_argument(
        "--max-total",
        type=int,
        default=30,
        help="本次最多处理多少张；设为 0 表示不限制。默认 30。",
    )
    parser.add_argument(
        "--vision-model",
        default=None,
        help="豆包视觉模型 endpoint id；不传则从 .env 读取 DOUBAO_LLM_MODEL_2_0_LITE 等变量。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只枚举图片并调用视觉识别预览，不上传、不写库、不同步向量。",
    )
    parser.add_argument(
        "--selection-only",
        action="store_true",
        help="只打印抽样图片列表，不调用模型。",
    )
    parser.add_argument(
        "--show-selection",
        action="store_true",
        help="正式处理前打印全部选中的图片列表；全量跑时默认不打印。",
    )
    parser.add_argument(
        "--verbose-vector",
        action="store_true",
        help="打印向量同步服务的调试输出；默认静默同步。",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="默认跳过已入库的 source_relative_path；传这个参数会允许重复处理。",
    )
    parser.add_argument(
        "--output-jsonl",
        default=None,
        help="把每张图片的识别/入库结果写入 JSONL；不传则写入 runtime/image_folder_ingest_时间戳.jsonl。",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="视觉模型请求超时时间，默认 120 秒。",
    )
    parser.add_argument(
        "--vision-max-side",
        type=int,
        default=1536,
        help="发给视觉模型前的最长边压缩尺寸，默认 1536。",
    )
    parser.add_argument(
        "--vision-jpeg-quality",
        type=int,
        default=85,
        help="发给视觉模型前的 JPEG 质量，默认 85。",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="遇到单张图片失败时立即停止；默认记录错误后继续。",
    )
    return parser


def resolve_model(args: argparse.Namespace, env: dict[str, str]) -> str:
    """解析视觉模型 endpoint id。"""

    model = (
        args.vision_model
        or env.get("DOUBAO_LLM_MODEL_2_0_LITE")
        or env.get("DOUBAO_LLM_MODE_2.0lite")
        or env.get("DOUBAO_VISION_MODEL")
        or env.get("DOUBAO_LLM_MODEL")
        or env.get("ARK_LLM_MODEL")
    )
    if not model:
        raise ValueError("Missing vision model: set DOUBAO_LLM_MODEL_2_0_LITE or pass --vision-model")
    return model


def main() -> None:
    """脚本入口。"""

    parser = build_arg_parser()
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Root folder not found: {root}")

    max_total = None if args.max_total == 0 else args.max_total
    candidates = collect_candidates(
        root=root,
        per_folder_limit=args.per_folder_limit,
        max_total=max_total,
    )
    if not candidates:
        print("No image candidates found.")
        return

    print(f"selected images: {len(candidates)}")
    if args.selection_only or args.show_selection:
        for index, candidate in enumerate(candidates, start=1):
            print(f"[select] {index}/{len(candidates)} {candidate.relative_path}")

    if args.selection_only:
        return

    env = read_env(PROJECT_ROOT / ".env")
    api_key = env.get("ARK_API_KEY") or os.getenv("ARK_API_KEY")
    if not api_key:
        raise ValueError("Missing ARK_API_KEY in .env")

    model = resolve_model(args, env)
    base_url = env.get("ARK_BASE_URL") or os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3"
    source_project_name = args.source_project_name or root.name
    source_project_code = "folder_" + hashlib.md5(str(root).encode("utf-8")).hexdigest()[:12]

    default_output = (
        PROJECT_ROOT
        / "runtime"
        / f"image_folder_ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    output_jsonl = Path(args.output_jsonl).resolve() if args.output_jsonl else default_output

    db = None
    tos_uploader = None
    source_project_id = None
    entity_repository = None
    media_repository = None
    vector_sync_service = None
    existing_paths: set[str] = set()

    if not args.dry_run:
        db = create_session()
        source_project_repository = AssetSourceProjectRepository(db)
        source_project = source_project_repository.get_or_create(
            name=source_project_name,
            code=source_project_code,
            description=root.name,
            project_type="image_folder",
            metadata={"source_root": str(root), "ingest_script": Path(__file__).name},
        )
        db.commit()
        source_project_id = source_project.id
        if not args.include_existing:
            existing_paths = existing_relative_paths(db, source_project_id)
        tos_uploader = TosUploader()
        entity_repository = AssetEntityRepository(db)
        media_repository = AssetMediaRepository(db)
        vector_sync_service = AssetVectorSyncService()

    try:
        for index, candidate in enumerate(candidates, start=1):
            candidate_key = str(candidate.relative_path)
            if candidate_key in existing_paths:
                print(f"[skip-existing] {candidate.relative_path}")
                write_jsonl(
                    output_jsonl,
                    {
                        "status": "skipped_existing",
                        "source_relative_path": candidate_key,
                    },
                )
                continue

            print(f"[vision] {index}/{len(candidates)} {candidate.relative_path}")
            try:
                content = candidate.path.read_bytes()
                image_sha256 = hashlib.sha256(content).hexdigest()
                raw_asset = describe_image(
                    candidate=candidate,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    timeout=args.timeout,
                    max_side=args.vision_max_side,
                    jpeg_quality=args.vision_jpeg_quality,
                )

                uploaded = None
                if not args.dry_run:
                    assert tos_uploader is not None
                    storage_path = storage_path_for(
                        source_project_code=source_project_code,
                        candidate=candidate,
                        image_sha256=image_sha256,
                    )
                    uploaded = tos_uploader.upload_bytes(
                        content=content,
                        storage_path=storage_path,
                        content_type=mimetypes.guess_type(candidate.path.name)[0] or "application/octet-stream",
                    )

                asset_data = normalize_asset(
                    raw_asset=raw_asset,
                    candidate=candidate,
                    image_sha256=image_sha256,
                    uploaded_url=uploaded.storage_url if uploaded else None,
                )
                asset_data["source_project_id"] = source_project_id
                asset_data["source_project_name"] = source_project_name

                result: dict[str, Any] = {
                    "status": "dry_run" if args.dry_run else "ingested",
                    "source_relative_path": str(candidate.relative_path),
                    "asset": asset_data,
                }

                if not args.dry_run:
                    assert db is not None
                    assert entity_repository is not None
                    assert media_repository is not None
                    assert vector_sync_service is not None
                    assert uploaded is not None

                    entity = entity_repository.save(asset_data)
                    width, height, image_format = image_info(candidate.path)
                    media_repository.create(
                        asset_entity_id=entity.id,
                        asset_variant_id=None,
                        media_kind=media_kind_for(entity.asset_kind),
                        view_angle="unknown",
                        title=entity.display_name or entity.name,
                        description=asset_data.get("appearance") or asset_data.get("intro"),
                        storage_bucket=uploaded.bucket,
                        storage_path=uploaded.storage_path,
                        storage_url=uploaded.storage_url,
                        width_px=width,
                        height_px=height,
                        format=image_format,
                        sha256=image_sha256,
                        is_primary=True,
                        approved=None,
                        sort_order=100,
                        metadata={
                            "source_project_name": source_project_name,
                            "source_local_path": str(candidate.path),
                            "source_relative_path": str(candidate.relative_path),
                            "top_folder": candidate.top_folder,
                            "extractor": "doubao_vision_image_folder_ingest",
                        },
                    )
                    if args.verbose_vector:
                        vector_sync_service.sync_entity(entity)
                    else:
                        with contextlib.redirect_stdout(io.StringIO()):
                            vector_sync_service.sync_entity(entity)
                    db.commit()
                    result["entity_id"] = str(entity.id)
                    result["source_file_url"] = uploaded.storage_url

                write_jsonl(output_jsonl, result)
                print(
                    f"[ok] {candidate.relative_path} -> "
                    f"{asset_data['asset_kind']} / {asset_data['display_name']}"
                )
            except Exception as exc:
                if db is not None:
                    db.rollback()
                error = {
                    "status": "error",
                    "source_relative_path": str(candidate.relative_path),
                    "error": repr(exc),
                }
                write_jsonl(output_jsonl, error)
                print(f"[error] {candidate.relative_path}: {exc}")
                if args.stop_on_error:
                    raise
    finally:
        if db is not None:
            db.close()

    print(f"result jsonl: {output_jsonl}")


if __name__ == "__main__":
    main()
