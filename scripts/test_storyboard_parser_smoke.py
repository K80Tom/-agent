"""分镜 Excel parser 冒烟测试。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from openpyxl import Workbook

from app.services.Mapping.storyboard_field_mapper import StoryboardFieldMapper
from app.services.Mapping.storyboard_header_mapper import StoryboardHeaderMap
from app.services.storyboard_excel_parser import StoryboardExcelParser


class FakeStoryboardHeaderMapper:
    """测试专用的假表头识别器。

    正式流程里，StoryboardHeaderMapper 会调用模型识别表头。
    这里为了先测试 parser，不调用模型，直接返回固定映射。
    """

    def map_headers(self, *, sheet_name: str, headers: list[str]) -> StoryboardHeaderMap:
        return StoryboardHeaderMap(
            episode="集数",
            shot_no="镜号",
            screen_description="画面描述",
            camera_motion="镜头运动",
            shot_size_angle="景别&视角",
            dialogue="台词",
            scene="场景",
            sound_effect="音效",
            reference_image_headers=["参考图"],
            storyboard_image_headers=["分镜图"],
        )


def main() -> None:
    excel_path = Path("runtime/storyboard_parser_smoke.xlsx")
    excel_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()

    # 第一个 sheet 故意叫“人物表”，应该被 parser 跳过。
    people_sheet = workbook.active
    people_sheet.title = "人物表"
    people_sheet.append(["角色名", "身份"])
    people_sheet.append(["叶逍遥", "男主"])

    # 第二个 sheet 叫“分镜表”，应该被 parser 解析。
    storyboard_sheet = workbook.create_sheet("分镜表")
        # 模拟真实 Excel：前两行不是表头，而是标题/说明。
    storyboard_sheet.append(["《天尊》分镜表"])
    storyboard_sheet.append(["这里是说明行，不是表头"])

    # 第 3 行才是真正表头。
    storyboard_sheet.append([
        "集数",
        "镜号",
        "画面描述",
        "镜头运动",
        "景别&视角",
        "台词",
        "场景",
        "音效",
        "参考图",
        "分镜图",
    ])

    # 第 4 行才是真正数据。
    storyboard_sheet.append([
        1,
        3,
        "叶逍遥推门",
        "推进",
        "中景",
        "你来了",
        "山中道台",
        "风声",
        "参考画面A",
        "分镜画面A",
    ])

    workbook.save(excel_path)

    parser = StoryboardExcelParser(
        header_mapper=FakeStoryboardHeaderMapper(),
        field_mapper=StoryboardFieldMapper(),
    )

    rows = parser.parse(excel_path)

    print(f"解析到 {len(rows)} 条分镜")
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()