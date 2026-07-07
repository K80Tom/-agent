"""项目导演分镜提示词 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


SHANGHAI_NOW = text("(now() AT TIME ZONE 'Asia/Shanghai')")


class ProjectDirectorStoryboardPrompt(Base):
    """对应 common.project_director_storyboard_prompts。"""
    __tablename__ = "project_director_storyboard_prompts"
    __table_args__ = {"schema": "common"}

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # 关联项目。这个字段不能为空，所以入库前必须先找到或创建项目。
    project_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    # Excel 的“集数”和“镜号”，数据库里是 integer，所以入库时要转成 int。
    episode_no: Mapped[int | None] = mapped_column(Integer)
    shot_no: Mapped[int | None] = mapped_column(Integer)
    # Excel 的“场景”。
    scene_name: Mapped[str | None] = mapped_column(String)
    # Excel 的“台词”。你刚确认了，台词直接写这里。
    director_prompt_text: Mapped[str | None] = mapped_column(Text)
     # Excel 的“画面描述”。
    shot_description: Mapped[str | None] = mapped_column(Text)
     # Excel 的“镜头运动”和“景别&视角”会合并写这里。
    camera_movement: Mapped[str | None] = mapped_column(String)
    # 画面灯光，目前 Excel 不一定有，先映射出来。
    lighting: Mapped[str | None] = mapped_column(String)
    # 声音指导/音效。表里两个字段都有，Excel 的“音效”先写 sound_effect。
    sound_instruction: Mapped[str | None] = mapped_column(Text)
    sound_effect: Mapped[str | None] = mapped_column(String)
    # 用户和结果媒体字段，第一版分镜入库暂时不主动写。
    user_id: Mapped[str | None] = mapped_column(String)
    user_name: Mapped[str | None] = mapped_column(String)
    result_media_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    # 默认 active，和数据库默认值保持一致。
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'active'::character varying"),
    )
    # metadata 只放追溯信息：sheet 名、行号、原始字段。
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=SHANGHAI_NOW,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=SHANGHAI_NOW,
    )
    # 图片/参考文件地址。第一版如果只是 Excel 文本，可以先不写。
    reference_file_url: Mapped[str | None] = mapped_column(String)
    storyboard_file_url: Mapped[str | None] = mapped_column(String)


