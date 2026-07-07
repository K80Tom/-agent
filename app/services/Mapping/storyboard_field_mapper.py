"""分镜 Excel 行字段映射器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.Mapping.storyboard_header_mapper import StoryboardHeaderMap


@dataclass(slots=True)
class StoryboardExcelRow:
    """标准化后的单条分镜行。

    这个结构只保存从 Excel 每一行提取出来的业务字段。
    表头怎么识别，由 StoryboardHeaderMapper 负责。
    这一层只根据 header_map 去取值。
    """

    sheet_name: str
    row_number: int
    episode: str | None = None
    shot_no: str | None = None
    screen_description: str | None = None
    camera_motion: str | None = None
    shot_size_angle: str | None = None
    dialogue: str | None = None
    scene: str | None = None
    sound_effect: str | None = None

    # 这些字段保存“图片列里的文本值”。
    # 真正的 Excel 内嵌图片上传 TOS，后面由图片提取/上传服务处理。
    reference_image_note: str | None = None
    storyboard_image_note: str | None = None

    # 原始字段全部保留，方便排查和回溯。
    raw_fields: dict[str, str] = field(default_factory=dict)


class StoryboardFieldMapper:
    """根据模型识别出的表头映射，把 Excel 行转换成标准分镜行。"""

    def map_fields(
        self,
        *,
        sheet_name: str,
        row_number: int,
        fields: dict[str, Any],
        header_map: StoryboardHeaderMap,
    ) -> StoryboardExcelRow:
        """把一行 Excel 原始字段转换成标准分镜行。"""

        normalized_fields = {
            self._normalize_key(key): self._normalize_value(value)
            for key, value in fields.items()
            if self._normalize_key(key)
        }

        return StoryboardExcelRow(
            sheet_name=sheet_name,
            row_number=row_number,
            episode=self._value_by_header(normalized_fields, header_map.episode),
            shot_no=self._value_by_header(normalized_fields, header_map.shot_no),
            screen_description=self._value_by_header(
                normalized_fields,
                header_map.screen_description,
            ),
            camera_motion=self._value_by_header(
                normalized_fields,
                header_map.camera_motion,
            ),
            shot_size_angle=self._value_by_header(
                normalized_fields,
                header_map.shot_size_angle,
            ),
            dialogue=self._value_by_header(normalized_fields, header_map.dialogue),
            scene=self._value_by_header(normalized_fields, header_map.scene),
            sound_effect=self._value_by_header(
                normalized_fields,
                header_map.sound_effect,
            ),
            reference_image_note=self._join_values_by_headers(
                normalized_fields,
                header_map.reference_image_headers,
            ),
            storyboard_image_note=self._join_values_by_headers(
                normalized_fields,
                header_map.storyboard_image_headers,
            ),
            raw_fields=normalized_fields,
        )

    @staticmethod
    def _normalize_key(value: Any) -> str:
        """统一表头文本，避免空格导致匹配失败。"""

        return str(value or "").strip()

    @staticmethod
    def _normalize_value(value: Any) -> str:
        """统一单元格文本，空值返回空字符串。"""

        return str(value or "").strip()

    @staticmethod
    def _value_by_header(
        fields: dict[str, str],
        header: str | None,
    ) -> str | None:
        """根据模型识别出的原始表头取值。"""

        if not header:
            return None

        value = fields.get(header)
        if value:
            return value

        return None

    def _join_values_by_headers(
        self,
        fields: dict[str, str],
        headers: list[str],
    ) -> str | None:
        """把多个图片相关列里的文本合并起来。

        注意：
        这里处理的是单元格文本，不是 Excel 内嵌图片。
        真正的图片上传 TOS，后面单独做。
        """

        values: list[str] = []

        for header in headers:
            value = self._value_by_header(fields, header)
            if value:
                values.append(f"{header}：{value}")

        if not values:
            return None

        return "\n".join(values)