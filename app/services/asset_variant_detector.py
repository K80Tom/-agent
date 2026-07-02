"""资产变体识别。"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class AssetVariantInfo:
    """从资产名称中识别出的变体信息。"""

    parent_name: str
    variant_name: str
    variant_kind: str
    source_name: str


PREFIX_VARIANTS: tuple[tuple[str, str], ...] = (
    ("心魔版", "心魔版"),
    ("心魔", "心魔版"),
    ("天尊版", "天尊版"),
    ("升级版", "升级版"),
    ("古装版", "古装版"),
    ("现代版", "现代版"),
    ("礼服版", "礼服版"),
    ("战斗版", "战斗版"),
)

SUFFIX_VARIANTS: tuple[tuple[str, str], ...] = (
    ("心魔版", "心魔版"),
    ("天尊版", "天尊版"),
    ("升级版", "升级版"),
    ("古装版", "古装版"),
    ("现代版", "现代版"),
    ("礼服版", "礼服版"),
    ("战斗版", "战斗版"),
)


def detect_asset_variant(*, asset_kind: str, asset_name: str | None) -> AssetVariantInfo | None:
    """判断资产名是否表示主体变体。

    例如：
    心魔叶婷 -> parent_name=叶婷, variant_name=心魔版
    天尊版叶逍遥 -> parent_name=叶逍遥, variant_name=天尊版
    """

    if asset_kind != "character":
        return None

    source_name = _clean_name(asset_name)
    if not source_name:
        return None

    for marker, variant_name in PREFIX_VARIANTS:
        if source_name.startswith(marker):
            parent_name = source_name.removeprefix(marker).strip()
            if parent_name:
                return AssetVariantInfo(
                    parent_name=parent_name,
                    variant_name=variant_name,
                    variant_kind="look",
                    source_name=source_name,
                )

    for marker, variant_name in SUFFIX_VARIANTS:
        if source_name.endswith(marker):
            parent_name = source_name.removesuffix(marker).strip()
            if parent_name:
                return AssetVariantInfo(
                    parent_name=parent_name,
                    variant_name=variant_name,
                    variant_kind="look",
                    source_name=source_name,
                )

    return None


def _clean_name(value: str | None) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "", text)
    return text
