"""JSON 资产入库服务。

职责：
1. 接收已经校验过的 JSON 资产数据。
2. 转成 common.asset_entities 可保存的字段。
3. 复用 AssetEntityRepository.save() 做 upsert。
4. 入库后同步向量库。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.asset_entity_repository import AssetEntityRepository
from app.schemas.asset_ingest import JsonAssetIngestRequest
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService


class JsonAssetIngestService:
    """处理 JSON -> asset_entities 的入库流程。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.asset_entity_repository = AssetEntityRepository(db)
        self.asset_vector_sync_service = AssetVectorSyncService()

    def ingest(self, request: JsonAssetIngestRequest) -> list[dict[str, Any]]:
        """批量入库 JSON 资产。"""

        saved_items: list[dict[str, Any]] = []

        for asset_item in request.assets:
            asset_data = self._build_asset_data(request, asset_item)

            # save() 已经封装了 upsert：
            # 如果 source_project_id + asset_kind + name 存在，就更新；
            # 否则新增。
            entity = self.asset_entity_repository.save(asset_data)

            # 入库后同步到向量库，保证检索可以搜到。
            self.asset_vector_sync_service.sync_entity(entity)

            saved_items.append(
                {
                    "id": entity.id,
                    "asset_kind": entity.asset_kind,
                    "name": entity.name,
                }
            )

        return saved_items

    def _build_asset_data(
        self,
        request: JsonAssetIngestRequest,
        asset_item,
    ) -> dict[str, Any]:
        """把请求里的单条资产转换成 repository.save() 需要的 dict。"""

        asset_data = asset_item.model_dump()

        # 顶层项目字段补到每条资产里，方便 repository 直接保存。
        asset_data["source_project_id"] = request.source_project_id
        asset_data["source_project_name"] = request.source_project_name

        # display_name 如果没传，默认用 name，避免展示时为空。
        asset_data["display_name"] = asset_data.get("display_name") or asset_data["name"]

        return asset_data