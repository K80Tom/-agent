"""资产入库 endpoint。"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.dependencies.db import get_db
from app.schemas.asset_ingest import (
    ExcelIngestResponse,
)
from app.services.asset_entity_ingest_service import AssetEntityIngestService


router = APIRouter()


@router.post("/excel/upload", response_model=ExcelIngestResponse)
async def upload_and_ingest_excel_assets(
    file: UploadFile = File(...),
    source_project_name: str | None = Form(default=None),
    batch_size: int = Form(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> ExcelIngestResponse:
    """上传 Excel 并自动入库后端解析到的全部工作表。"""

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded file name")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=400, detail="Only .xlsx or .xlsm files are supported")

    uploaded_path = await _save_uploaded_excel(file)
    project_name = source_project_name or _extract_project_name(uploaded_path.name)

    service = AssetEntityIngestService(db)
    items = service.ingest_excel_path(
        excel_path=str(uploaded_path),
        source_project_name=project_name,
        batch_size=batch_size,
    )

    return ExcelIngestResponse(
        count=len(items),
        items=items,
        uploaded_file_path=str(uploaded_path),
    )


async def _save_uploaded_excel(file: UploadFile) -> Path:
    """把上传的 Excel 保存到本地运行目录，供后续解析和图片抽取使用。"""

    safe_file_name = Path(file.filename or "upload.xlsx").name
    file_id = uuid4().hex
    upload_dir = Path("runtime") / "uploads" / file_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    uploaded_path = upload_dir / safe_file_name

    with uploaded_path.open("wb") as target:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)

    return uploaded_path


def _extract_project_name(file_name: str) -> str:
    """从文件名提取项目名，优先取书名号里的内容。"""

    stem = Path(file_name).stem
    match = re.search(r"《(.+?)》", stem)
    if match:
        return match.group(1).strip()
    return stem
