"""分镜 Excel 表头识别服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.services.llm_excel_asset_extractor import LLMExcelAssetExtractor


@dataclass(slots=True)
class StoryboardHeaderMap:
    """一个分镜 sheet 的表头映射结果。

    注意：
    这里只保存“需要从 Excel 表头识别出来的字段”。
    数据库字段里的 project_id、status、metadata、created_at 等，
    由后续 StoryboardRecordBuilder 或数据库默认值补齐。

    图片字段这里只保存对应的 Excel 表头名。
    真正上传 TOS、生成 URL 的动作放到后续图片上传服务里。
    """

    episode: str | None = None
    shot_no: str | None = None
    screen_description: str | None = None
    camera_motion: str | None = None
    shot_size_angle: str | None = None
    dialogue: str | None = None
    scene: str | None = None
    sound_effect: str | None = None

    # 参考画面/参考图/静态帧等，后续上传后写 reference_file_url。
    reference_image_headers: list[str] = field(default_factory=list)

    # 分镜图/故事板图等，后续上传后写 storyboard_file_url。
    storyboard_image_headers: list[str] = field(default_factory=list)


class StoryboardHeaderMapper:
    """使用模型识别分镜 Excel 表头。"""

    def __init__(self) -> None:
        # 复用当前项目里已有的 LLM 调用封装，避免重新写一套模型客户端。
        self.llm_extractor = LLMExcelAssetExtractor()

    def map_headers(
        self,
        *,
        sheet_name: str,
        headers: list[str],
    ) -> StoryboardHeaderMap:
        """让模型识别一个 sheet 的表头映射。"""

        cleaned_headers = [
            header.strip()
            for header in headers
            if header and header.strip()
        ]
        if not cleaned_headers:
            return StoryboardHeaderMap()

        prompt = self._build_prompt(sheet_name=sheet_name, headers=cleaned_headers)

        # 复用资产抽取里已经写好的 LLM 请求方法。
        # 这样不用重新写 httpx、鉴权、模型名这些重复代码。
        raw_result = self.llm_extractor._call_llm(prompt)

        # 复用资产抽取里的 JSON 修复逻辑。
        # 如果模型偶尔返回了 markdown 代码块或不标准 JSON，这里会尝试修复一次。
        data = self.llm_extractor._parse_json_object_with_repair(raw_result)

        return StoryboardHeaderMap(
            episode=self._valid_header(data.get("episode"), cleaned_headers),
            shot_no=self._valid_header(data.get("shot_no"), cleaned_headers),
            screen_description=self._valid_header(
                data.get("screen_description"),
                cleaned_headers,
            ),
            camera_motion=self._valid_header(data.get("camera_motion"), cleaned_headers),
            shot_size_angle=self._valid_header(data.get("shot_size_angle"), cleaned_headers),
            dialogue=self._valid_header(data.get("dialogue"), cleaned_headers),
            scene=self._valid_header(data.get("scene"), cleaned_headers),
            sound_effect=self._valid_header(data.get("sound_effect"), cleaned_headers),
            reference_image_headers=self._valid_header_list(
                data.get("reference_image_headers"),
                cleaned_headers,
            ),
            storyboard_image_headers=self._valid_header_list(
                data.get("storyboard_image_headers"),
                cleaned_headers,
            ),
        )

    @staticmethod
    def _build_prompt(*, sheet_name: str, headers: list[str]) -> str:
            """构造表头识别提示词。"""

            return f"""
                你是短剧分镜 Excel 表头识别助手。

                请根据 sheet 名和表头列表，判断每个标准字段对应哪个 Excel 原始表头。

                sheet 名：
                {sheet_name}

                Excel 表头：
                {json.dumps(headers, ensure_ascii=False)}

                字段含义说明：
                - episode：集数、剧集编号、集
                - shot_no：镜号、镜头号、分镜号
                - screen_description：画面描述、镜头画面、画面内容
                - camera_motion：镜头运动、运镜、推拉摇移、拍摄运动
                - shot_size_angle：景别、视角、景别&视角、画面角度
                - dialogue：台词、对白、角色说话内容
                - scene：场景、场景名、地点
                - sound_effect：音效、声音、环境声
                - reference_image_headers：参考画面、参考图、静态帧、静态帧1、静态帧3
                - storyboard_image_headers：分镜图、故事板图、分镜画面、分镜图片

                请只返回 JSON，不要返回解释。

                JSON 格式如下：
                {{
                "episode": "集数字段对应的原始表头，没有则为 null",
                "shot_no": "镜号字段对应的原始表头，没有则为 null",
                "screen_description": "画面描述字段对应的原始表头，没有则为 null",
                "camera_motion": "镜头运动字段对应的原始表头，没有则为 null",
                "shot_size_angle": "景别/视角字段对应的原始表头，没有则为 null",
                "dialogue": "台词/对白字段对应的原始表头，没有则为 null",
                "scene": "场景字段对应的原始表头，没有则为 null",
                "sound_effect": "音效/声音字段对应的原始表头，没有则为 null",
                "reference_image_headers": ["参考画面、参考图、静态帧等字段对应的原始表头"],
                "storyboard_image_headers": ["分镜图、故事板图等字段对应的原始表头"]
                }}
                """.strip()

    @staticmethod
    def _valid_header(value, headers: list[str]) -> str | None:
        """只接受真实存在于 Excel 里的表头，防止模型编造。"""

        if not isinstance(value, str):
            return None

        value = value.strip()
        if value in headers:
            return value

        return None

    def _valid_header_list(self, value, headers: list[str]) -> list[str]:
        """校验模型返回的多表头字段。"""

        if not isinstance(value, list):
            return []

        valid_headers: list[str] = []
        for item in value:
            header = self._valid_header(item, headers)
            if header is not None:
                valid_headers.append(header)

        return valid_headers