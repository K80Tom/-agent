"""资产主体入库 service。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
import hashlib
import time
from app.models.asset_entity_model import AssetEntity
from app.repositories.asset_entity_repository import AssetEntityRepository
from app.repositories.asset_variant_repository import AssetVariantRepository
from app.repositories.asset_source_project_repository import AssetSourceProjectRepository
from app.services.excel_asset_parser import ExcelAssetParser, ExcelAssetRow
from app.services.excel_image_upload_service import ExcelImageUploadService
from app.services.llm_excel_asset_extractor import LLMExcelAssetExtractor
from app.repositories.asset_media_repository import AssetMediaRepository
from app.services.asset_media_mapping import build_asset_media_data
from app.services.asset_variant_detector import AssetVariantInfo, detect_asset_variant
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService

class AssetEntityIngestService:
    """编排 Excel -> LLM 抽取 -> 主图上传 -> asset_entities 入库流程。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.source_project_repository = AssetSourceProjectRepository(db)
        self.asset_entity_repository = AssetEntityRepository(db)
        self.asset_variant_repository = AssetVariantRepository(db)
        self.asset_media_repository = AssetMediaRepository(db)
        self.excel_parser = ExcelAssetParser()
        self.image_upload_service = ExcelImageUploadService()
        self.llm_extractor = LLMExcelAssetExtractor()
        self.asset_vector_sync_service=AssetVectorSyncService()

    def preview_excel_path(
        self,
        *,
        excel_path: str,
        source_project_name: str,
        limit: int = 5,
        sheet_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """预览 Excel 资产字段抽取结果，不写数据库，不上传图片。"""

        rows = self._load_rows_from_path(excel_path)
        rows = self._filter_rows(rows, sheet_name=sheet_name)[:limit]
        return self.llm_extractor.extract_many(
            rows,
            source_project_id=None,
            source_project_name=source_project_name,
        )

    def ingest_sheet_excel_path(
        self,
        *,
        excel_path: str,
        source_project_name: str,
        sheet_name: str,
        batch_size: int = 5,
    ) -> list[dict[str, Any]]:
        """批量入库某个 Excel 工作表的全部资产行。"""

        rows = self._load_rows_from_path(excel_path)
        rows = self._filter_rows(rows, sheet_name=sheet_name)
        if not rows:
            raise ValueError(f"No asset rows found for sheet: {sheet_name}")

        return self._ingest_rows(
            excel_path=excel_path,
            rows=rows,
            source_project_name=source_project_name,
            batch_size=batch_size,
        )

    def ingest_excel_path(
        self,
        *,
        excel_path: str,
        source_project_name: str,
        batch_size: int = 5,
    ) -> list[dict[str, Any]]:
        """批量入库整个 Excel 文件中解析到的全部资产行。"""

        rows = self._load_rows_from_path(excel_path)
        if not rows:
            raise ValueError(f"No asset rows parsed from Excel: {excel_path}")

        return self._ingest_rows(
            excel_path=excel_path,
            rows=rows,
            source_project_name=source_project_name,
            batch_size=batch_size,
        )

    def _ingest_rows(
        self,
        *,
        excel_path: str,
        rows: list[ExcelAssetRow],
        source_project_name: str,
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """批量入库已经解析好的 Excel 资产行。"""

        ingest_started = time.perf_counter()
        media_source_project_name = source_project_name
        source_file = Path(excel_path)
        source_file_name = source_file.name
        source_project_code = "file_" + hashlib.md5(str(source_file).encode("utf-8")).hexdigest()[:12]

        stage_started = time.perf_counter()
        source_project = self.source_project_repository.get_or_create(
            name=source_project_name,
            code=source_project_code,
            description=source_file_name,
            metadata={
                "source_file_path": str(source_file),
            },
        )
        source_project_ms = self._elapsed_ms(stage_started)
        source_project_id = str(source_project.id)
        actual_project_name = source_project.name or source_project_name

        results: list[dict[str, Any]] = []

        print(
            "[excel-ingest-timing] "
            f"scope=start file={source_file_name} row_count={len(rows)} batch_size={batch_size} "
            f"source_project_get_or_create={source_project_ms}"
        )

        for batch_index, batch_rows in enumerate(self._iter_batches(rows, batch_size=batch_size), start=1):
            batch_started = time.perf_counter()
            batch_timing_ms: dict[str, int] = {}
            try:
                stage_started = time.perf_counter()
                assets = self.llm_extractor.extract_many(
                    batch_rows,
                    source_project_id=source_project_id,
                    source_project_name=actual_project_name,
                )
                batch_timing_ms["llm_extract"] = self._elapsed_ms(stage_started)

                stage_started = time.perf_counter()
                batch_items = [
                    (
                        row,
                        asset_data,
                        detect_asset_variant(
                            asset_kind=asset_data["asset_kind"],
                            asset_name=asset_data.get("name"),
                        ),
                    )
                    for row, asset_data in zip(batch_rows, assets)
                ]
                batch_timing_ms["variant_detect"] = self._elapsed_ms(stage_started)

                entity_count = 0
                stage_started = time.perf_counter()
                for row, asset_data, variant_info in batch_items:
                    if variant_info is not None:
                        continue
                    entity = self._save_entity_with_media(
                        excel_path=excel_path,
                        row=row,
                        asset_data=asset_data,
                        actual_project_name=actual_project_name,
                        media_source_project_name=media_source_project_name,
                    )
                    results.append(self._serialize_entity(entity))
                    entity_count += 1
                batch_timing_ms["save_entities_media_vector"] = self._elapsed_ms(stage_started)

                variant_count = 0
                stage_started = time.perf_counter()
                for row, asset_data, variant_info in batch_items:
                    if variant_info is None:
                        continue
                    result = self._save_variant_with_media(
                        excel_path=excel_path,
                        row=row,
                        asset_data=asset_data,
                        variant_info=variant_info,
                        source_project_id=source_project_id,
                        actual_project_name=actual_project_name,
                        media_source_project_name=media_source_project_name,
                    )
                    results.append(result)
                    variant_count += 1
                batch_timing_ms["save_variants_media_vector"] = self._elapsed_ms(stage_started)

                stage_started = time.perf_counter()
                self.db.commit()
                batch_timing_ms["db_commit"] = self._elapsed_ms(stage_started)
                batch_timing_ms["batch_total"] = self._elapsed_ms(batch_started)
                row_keys = ",".join(f"{row.sheet_name}:{row.row_number}" for row in batch_rows[:5])
                if len(batch_rows) > 5:
                    row_keys += ",..."
                print(
                    "[excel-ingest-batch-timing] "
                    f"file={source_file_name} batch={batch_index} rows={row_keys} "
                    f"row_count={len(batch_rows)} entity_count={entity_count} variant_count={variant_count} "
                    f"timing_ms={batch_timing_ms}"
                )
            except Exception:
                self.db.rollback()
                raise

        print(
            "[excel-ingest-timing] "
            f"scope=total file={source_file_name} row_count={len(rows)} "
            f"result_count={len(results)} total_ms={self._elapsed_ms(ingest_started)}"
        )
        return results

    def _save_entity_with_media(
        self,
        *,
        excel_path: str,
        row: ExcelAssetRow,
        asset_data: dict[str, Any],
        actual_project_name: str,
        media_source_project_name: str,
    ) -> AssetEntity:
        """保存普通资产主体，并把这一行全部图片写入 asset_media。"""

        media_asset_name = self._media_asset_name(asset_data, row)
        uploaded_images = self.image_upload_service.upload_row_images(
            excel_path=excel_path,
            row=row,
            source_project_name=actual_project_name,
            asset_name=media_asset_name,
        )

        primary_image = self._primary_image(uploaded_images)
        if primary_image is not None:
            asset_data["source_file_url"] = primary_image["storage_url"]
            asset_data.setdefault("metadata", {})["primary_image"] = primary_image

        entity = self.asset_entity_repository.save(asset_data)
        self._save_media_records(
            uploaded_images=uploaded_images,
            asset_entity_id=entity.id,
            asset_variant_id=None,
            asset_kind=asset_data["asset_kind"],
            asset_name=media_asset_name,
            source_project_name=media_source_project_name,
            approved=asset_data.get("approved"),
        )
        self.asset_vector_sync_service.sync_entity(entity)
        return entity

    def _save_variant_with_media(
        self,
        *,
        excel_path: str,
        row: ExcelAssetRow,
        asset_data: dict[str, Any],
        variant_info: AssetVariantInfo,
        source_project_id: str,
        actual_project_name: str,
        media_source_project_name: str,
    ) -> dict[str, Any]:
        """保存变体，并把这一行图片挂到父主体和变体。"""

        parent_entity = self.asset_entity_repository.get_by_unique_key(
            source_project_id=source_project_id,
            asset_kind="character",
            name=variant_info.parent_name,
        )
        if parent_entity is None:
            asset_data.setdefault("metadata", {})["variant_detection_failed"] = {
                "parent_name": variant_info.parent_name,
                "variant_name": variant_info.variant_name,
                "reason": "parent_entity_not_found",
            }
            entity = self._save_entity_with_media(
                excel_path=excel_path,
                row=row,
                asset_data=asset_data,
                actual_project_name=actual_project_name,
                media_source_project_name=media_source_project_name,
            )
            return self._serialize_entity(entity)

        media_asset_name = variant_info.source_name
        uploaded_images = self.image_upload_service.upload_row_images(
            excel_path=excel_path,
            row=row,
            source_project_name=actual_project_name,
            asset_name=media_asset_name,
        )

        primary_image = self._primary_image(uploaded_images)
        variant = self.asset_variant_repository.save(
            self._build_variant_data(
                parent_entity=parent_entity,
                asset_data=asset_data,
                variant_info=variant_info,
                row=row,
                primary_image=primary_image,
            )
        )
        self._save_media_records(
            uploaded_images=uploaded_images,
            asset_entity_id=parent_entity.id,
            asset_variant_id=variant.id,
            asset_kind=asset_data["asset_kind"],
            asset_name=media_asset_name,
            source_project_name=media_source_project_name,
            approved=asset_data.get("approved"),
        )
        self.asset_vector_sync_service.sync_variant(variant, parent_entity)
        return self._serialize_variant(variant, parent_entity)

    def _save_media_records(
        self,
        *,
        uploaded_images: list[dict[str, Any]],
        asset_entity_id,
        asset_variant_id,
        asset_kind: str,
        asset_name: str,
        source_project_name: str,
        approved: bool | None,
    ) -> None:
        """把上传后的图片逐张写入 asset_media。"""

        for uploaded_image in uploaded_images:
            media_data = build_asset_media_data(
                asset_entity_id=asset_entity_id,
                asset_variant_id=asset_variant_id,
                uploaded_image=uploaded_image,
                asset_kind=asset_kind,
                asset_name=asset_name,
                source_project_name=source_project_name,
                approved=approved,
            )
            self.asset_media_repository.create(**media_data)

    @staticmethod
    def _primary_image(uploaded_images: list[dict[str, Any]]) -> dict[str, Any] | None:
        """从上传结果中找主图。"""

        return next((image for image in uploaded_images if image.get("is_primary")), None)

    def _build_variant_data(
        self,
        *,
        parent_entity: AssetEntity,
        asset_data: dict[str, Any],
        variant_info: AssetVariantInfo,
        row: ExcelAssetRow,
        primary_image: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """组装 asset_variants 入库字段。"""

        metadata = {
            "row_key": f"{row.sheet_name}:{row.row_number}",
            "source_sheet_name": row.sheet_name,
            "source_row_number": row.row_number,
            "images": row.images,
            "parent_name": variant_info.parent_name,
            "source_name": variant_info.source_name,
            "extractor": "llm_excel_asset_extractor",
        }
        if primary_image is not None:
            metadata["primary_image"] = primary_image

        return {
            "asset_entity_id": parent_entity.id,
            "variant_kind": variant_info.variant_kind,
            "name": variant_info.variant_name,
            "description": asset_data.get("intro") or asset_data.get("appearance"),
            "usage_context": variant_info.variant_name,
            "visual_prompt": self._build_visual_prompt(asset_data),
            "approved": asset_data.get("approved"),
            "status": asset_data.get("status") or "pending_review",
            "is_primary": False,
            "sort_order": 0,
            "source_file_url": primary_image.get("storage_url") if primary_image else None,
            "source_text": asset_data.get("intro"),
            "metadata": metadata,
        }

    @staticmethod
    def _build_visual_prompt(asset_data: dict[str, Any]) -> str | None:
        """把变体视觉相关字段合并成 visual_prompt。"""

        parts = [
            asset_data.get("appearance"),
            asset_data.get("hair_description"),
            asset_data.get("outfit_description"),
        ]
        text = "；".join(str(part).strip() for part in parts if str(part or "").strip())
        return text or None

    def _upload_primary_image_if_present(
        self,
        *,
        excel_path: str,
        row: ExcelAssetRow,
        source_project_name: str,
        asset_data: dict[str, Any],
    ) -> None:
        """如果这一行有图片，则上传主图并回填 source_file_url。"""

        primary_image = ExcelImageUploadService().upload_primary_image(
            excel_path=excel_path,
            row=row,
            source_project_name=source_project_name,
            asset_name=asset_data["name"],
        )
        if primary_image is None:
            return

        asset_data["source_file_url"] = primary_image["storage_url"]
        metadata = asset_data.setdefault("metadata", {})
        metadata["primary_image"] = primary_image

    def _load_rows_from_path(self, excel_path: str) -> list[ExcelAssetRow]:
        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {excel_path}")

        rows = self.excel_parser.parse(
            file_name=path.name,
            content=path.read_bytes(),
        )
        if not rows:
            raise ValueError(f"No asset rows parsed from Excel: {excel_path}")
        return rows

    @staticmethod
    def _filter_rows(rows: list[ExcelAssetRow], *, sheet_name: str | None) -> list[ExcelAssetRow]:
        if sheet_name is None:
            return rows
        return [row for row in rows if row.sheet_name == sheet_name]

    @staticmethod
    def _iter_batches(rows: list[ExcelAssetRow], *, batch_size: int) -> list[list[ExcelAssetRow]]:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")
        return [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return round((time.perf_counter() - started_at) * 1000)

    @staticmethod
    def _media_asset_name(asset_data: dict[str, Any], row: ExcelAssetRow) -> str:
        """生成媒体标题和存储路径里使用的资产名，避免场景序号变成标题。"""

        if asset_data.get("asset_kind") == "scene":
            for key in ("简介", "场景名", "名称"):
                value = str(row.fields.get(key) or "").strip()
                if value and not value.isdigit():
                    return value

        if asset_data.get("asset_kind") == "character":
            value = str(row.fields.get("姓名") or "").strip()
            if value and not value.isdigit():
                return value

        for key in ("display_name", "name"):
            value = str(asset_data.get(key) or "").strip()
            if value and not value.isdigit():
                return value

        if asset_data.get("asset_kind") == "scene":
            intro = str(asset_data.get("intro") or "").strip()
            if intro:
                return intro.splitlines()[0].split("；")[0].strip()

        return f"{row.sheet_name}第{row.row_number}行"

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

    @staticmethod
    def _serialize_variant(variant, parent_entity: AssetEntity) -> dict[str, Any]:
        return {
            "id": str(variant.id),
            "source_project_id": str(parent_entity.source_project_id)
            if parent_entity.source_project_id
            else None,
            "source_project_name": parent_entity.source_project_name,
            "asset_kind": "variant",
            "name": variant.name,
            "display_name": variant.name,
            "parent_entity_id": str(parent_entity.id),
            "parent_entity_name": parent_entity.name,
            "variant_kind": variant.variant_kind,
            "source_file_url": variant.source_file_url,
            "metadata": variant.metadata_,
        }
