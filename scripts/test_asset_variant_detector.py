"""测试资产变体识别。"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.asset_variant_detector import detect_asset_variant


def main() -> None:
    names = sys.argv[1:] or [
        "叶逍遥",
        "天尊版叶逍遥",
        "心魔叶婷",
        "叶婷心魔版",
        "古装版沈晴雪",
    ]

    for name in names:
        result = detect_asset_variant(asset_kind="character", asset_name=name)
        print("=" * 80)
        print("name:", name)
        pprint(result)


if __name__ == "__main__":
    main()
