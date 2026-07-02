"""Excel 图片上传编排服务。"""

from __future__ import annotations

import re
from typing import Any
import hashlib
from app.services.excel_asset_parser import ExcelAssetRow
from app.services.excel_image_extractor import ExcelImageExtractor
from app.services.tos_uploader import TosUploader


class ExcelImageUploadService:
    """选择 Excel 行主图，上传到 TOS，并返回图片 URL 信息。"""

    def __init__(self) -> None:
        self.image_extractor = ExcelImageExtractor()
        self.tos_uploader = TosUploader()

    def upload_primary_image(
        self,
        *,
        excel_path: str,
        row: ExcelAssetRow,
        source_project_name: str,
        asset_name: str,
    ) -> dict[str, Any] | None:
        """上传一行资产的主图。

        当前策略：
        1. 优先选择表头包含“人设图”和“定稿”的图片。
        2. 其次选择表头包含“定稿”的图片。
        3. 最后回退到这一行的第一张图片。
        """

        image_info = self._choose_primary_image(row.images)
        if image_info is None:
            return None

        image_file = self.image_extractor.extract_one(
            excel_path=excel_path,
            sheet_name=image_info["sheet_name"],
            image_index=image_info["image_index"],
        )
        storage_path = self._build_storage_path(
            source_project_name=source_project_name,
            asset_name=asset_name,
            row=row,
            image_info=image_info,
            extension=image_file.extension,
        )
        uploaded = self.tos_uploader.upload_bytes(
            content=image_file.content,
            storage_path=storage_path,
            content_type=image_file.content_type,
        )

        return {
            **image_info,
            "storage_bucket": uploaded.bucket,
            "storage_path": uploaded.storage_path,
            "storage_url": uploaded.storage_url,
        }

    @staticmethod
    def _choose_primary_image(images: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not images:
            return None

        def header(image: dict[str, Any]) -> str:
            return str(image.get("column_header") or "")

        for image in images:
            text = header(image)
            if "人设图" in text and "定稿" in text:
                return image

        for image in images:
            if "定稿" in header(image):
                return image

        return images[0]

    def _build_storage_path(
        self,
        *,
        source_project_name: str,
        asset_name: str,
        row: ExcelAssetRow,
        image_info: dict[str, Any],
        extension: str,
    ) -> str:
        project = self._safe_path_part(source_project_name)
        asset = self._safe_path_part(asset_name)
        sheet = self._safe_path_part(row.sheet_name)
        header = self._safe_path_part(str(image_info.get("column_header") or "image"))
        image_index = image_info["image_index"]
        row_number = row.row_number

        return (
            f"prod/asset/{project}/{asset}/"
            f"{sheet}_row_{row_number}_{header}_image_{image_index}.{extension}"
        )

    @staticmethod
    def _safe_path_part(value: str) -> str:
        text = value.strip()
        text = re.sub(r"[\\/:*?\"<>|\\s]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "unknown"
    

    def upload_row_images(
        self,
        *,
        excel_path: str,
        row: ExcelAssetRow,
        source_project_name: str,
        asset_name: str,
    ) -> list[dict]:
        """上传这一行的全部图片。"""

        results: list[dict] = []
        primary_image = self._choose_primary_image(row.images)

        for sort_order, image_info in enumerate(row.images):
            image_file = self.image_extractor.extract_one(
                excel_path=excel_path,
                sheet_name=image_info["sheet_name"],
                image_index=image_info["image_index"],
            )

            storage_path = self._build_storage_path(
                source_project_name=source_project_name,
                asset_name=asset_name,
                row=row,
                image_info=image_info,
                extension=image_file.extension,
            )

            uploaded = self.tos_uploader.upload_bytes(
                content=image_file.content,
                storage_path=storage_path,
                content_type=image_file.content_type,
            )

            results.append(
                {
                    **image_info,
                    "storage_bucket": uploaded.bucket,
                    "storage_path": uploaded.storage_path,
                    "storage_url": uploaded.storage_url,
                    "sha256": hashlib.sha256(image_file.content).hexdigest(),
                    "is_primary": image_info == primary_image,
                    "sort_order": sort_order,
                }
            )

        return results