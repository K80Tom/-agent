"""项目导演分镜提示词 repository。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project_director_storyboard_prompt_model import (
    ProjectDirectorStoryboardPrompt,
)


class ProjectDirectorStoryboardPromptRepository:
    """负责 common.project_director_storyboard_prompts 的数据库访问。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_project_episode_shot(
            self,
            *,
            project_id: UUID,
            episode_no: int | None,
            shot_no: int | None,
        ) -> ProjectDirectorStoryboardPrompt | None:
            """按项目 + 集数 + 镜号查找已有分镜。

            为什么这样查：
            同一项目里，一集的一个镜号应该对应一条分镜。
            后续重复上传 Excel 时，我们希望更新旧记录，而不是重复插入。
            """

            statement = select(ProjectDirectorStoryboardPrompt).where(
                ProjectDirectorStoryboardPrompt.project_id == project_id,
                ProjectDirectorStoryboardPrompt.episode_no == episode_no,
                ProjectDirectorStoryboardPrompt.shot_no == shot_no,
            )
            return self.db.scalar(statement)
    

    
    def save(self, data: dict[str, Any]) -> ProjectDirectorStoryboardPrompt:
        """保存分镜记录。

        如果同一项目 + 集数 + 镜号已经存在，就更新。
        如果不存在，就新增。
        """

        project_id = data["project_id"]
        episode_no = data.get("episode_no")
        shot_no = data.get("shot_no")

        existing = self.get_by_project_episode_shot(
            project_id=project_id,
            episode_no=episode_no,
            shot_no=shot_no,
        )

        if existing is None:
            entity = ProjectDirectorStoryboardPrompt()
            self.db.add(entity)
        else:
            entity = existing

        self._apply_data(entity, data)
        self.db.flush()
        self.db.refresh(entity)
        return entity
    

    
    @staticmethod
    def _apply_data(
        entity: ProjectDirectorStoryboardPrompt,
        data: dict[str, Any],
    ) -> None:
        """把 dict 数据写入 ORM 对象。

        这里不直接循环所有 key，是为了避免把不存在的字段误写进去。
        后面 Excel 字段再多，也应该先在 record_builder 里整理好。
        """

        entity.project_id = data["project_id"]
        entity.project_name = data.get("project_name")
        entity.episode_no = data.get("episode_no")
        entity.shot_no = data.get("shot_no")
        entity.scene_name = data.get("scene_name")
        entity.director_prompt_text = data.get("director_prompt_text")
        entity.shot_description = data.get("shot_description")
        entity.camera_movement = data.get("camera_movement")
        entity.lighting = data.get("lighting")
        entity.sound_instruction = data.get("sound_instruction")
        entity.sound_effect = data.get("sound_effect")
        entity.reference_file_url = data.get("reference_file_url")
        entity.storyboard_file_url = data.get("storyboard_file_url")
        entity.status = data.get("status") or "active"
        entity.metadata_ = data.get("metadata") or {}

    