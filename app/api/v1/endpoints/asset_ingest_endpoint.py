"""资产入库 endpoint。"""

from __future__ import annotations
import shutil
import re
import time
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import create_session
from app.dependencies.db import get_db
from app.models.asset_entity_model import AssetEntity
from app.schemas.asset_ingest import (
    AssetUploadResponse,
    ExcelIngestResponse,
    JsonAssetIngestRequest,
    JsonAssetIngestResponse,
)
from app.services.json_ingest.json_asset_ingest_service import JsonAssetIngestService
from app.services.asset_entity_ingest_service import AssetEntityIngestService
from app.services.image_asset_ingest_service import IMAGE_SUFFIXES, ImageAssetIngestService
from app.services.vector.asset_vector_sync_service import AssetVectorSyncService


router = APIRouter()

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}


@router.post("/json/assets", response_model=JsonAssetIngestResponse)
def ingest_json_assets(
    request: JsonAssetIngestRequest,
    db: Session = Depends(get_db),
) -> JsonAssetIngestResponse:
    """接收 JSON 资产数据并写入资产库。"""

    if not request.assets:
        raise HTTPException(status_code=400, detail="assets cannot be empty")

    service = JsonAssetIngestService(db)
    items = service.ingest(request)

    db.commit()

    return JsonAssetIngestResponse(
        count=len(items),
        items=items,
    )


@router.post("/upload", response_model=AssetUploadResponse)
async def upload_and_ingest_assets(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_project_name: str | None = Form(default=None),
    batch_size: int = Form(default=5, ge=1, le=20),
    asset_kind_hint: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> AssetUploadResponse:
    """统一上传入口：Excel 自动解析入库，图片用豆包视觉识别入库。"""

    request_started = time.perf_counter()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded file name")

    suffix = Path(file.filename).suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        response = await _ingest_excel_upload(
            file=file,
            source_project_name=source_project_name,
            batch_size=batch_size,
            db=db,
        )
        return AssetUploadResponse(
            mode="excel",
            count=response.count,
            items=response.items,
            uploaded_file_path=response.uploaded_file_path,
            uploaded_file_deleted=response.uploaded_file_deleted,
        )

    if suffix in IMAGE_SUFFIXES:
        stage_started = time.perf_counter()
        content = await file.read()
        api_timing_ms = {
            "api_read_upload": _elapsed_ms(stage_started),
        }

        stage_started = time.perf_counter()
        service = ImageAssetIngestService(db)
        api_timing_ms["api_service_init"] = _elapsed_ms(stage_started)
        try:
            stage_started = time.perf_counter()
            item = service.ingest_image(
                file_name=file.filename,
                content=content,
                content_type=file.content_type,
                source_project_name=source_project_name,
                asset_kind_hint=asset_kind_hint,
                sync_vector=False,
            )
            api_timing_ms["api_service_ingest_image"] = _elapsed_ms(stage_started)

            stage_started = time.perf_counter()
            db.commit()
            api_timing_ms["api_db_commit"] = _elapsed_ms(stage_started)
            background_tasks.add_task(_sync_entity_vector_background, item["id"])
            api_timing_ms["api_total_before_response"] = _elapsed_ms(request_started)
            metadata = item.setdefault("metadata", {})
            timing_ms = metadata.setdefault("ingest_timing_ms", {})
            timing_ms.update(api_timing_ms)
            metadata["vector_sync_status"] = "queued_background_task"
            print(f"[image-ingest-timing] file={file.filename} timing_ms={timing_ms}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return AssetUploadResponse(
            mode="image",
            count=1,
            items=[item],
        )

    raise HTTPException(
        status_code=400,
        detail="Only .xlsx/.xlsm or image files (.jpg/.jpeg/.png/.webp/.bmp) are supported",
    )


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


def _sync_entity_vector_background(entity_id: str) -> None:
    """后台同步单个图片资产的向量，避免上传接口一直等待 embedding/Milvus。"""

    db = create_session()
    try:
        entity = db.query(AssetEntity).filter(AssetEntity.id == UUID(entity_id)).first()
        if entity is None:
            return
        AssetVectorSyncService().sync_entity(entity)
    finally:
        db.close()


@router.post("/excel/upload", response_model=ExcelIngestResponse)
async def upload_and_ingest_excel_assets(
    file: UploadFile = File(...),
    source_project_name: str | None = Form(default=None),
    batch_size: int = Form(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> ExcelIngestResponse:
    """上传 Excel 并自动入库后端解析到的全部工作表。"""

    return await _ingest_excel_upload(
        file=file,
        source_project_name=source_project_name,
        batch_size=batch_size,
        db=db,
    )


async def _ingest_excel_upload(
    *,
    file: UploadFile,
    source_project_name: str | None,
    batch_size: int,
    db: Session,
) -> ExcelIngestResponse:
    request_started = time.perf_counter()
    api_timing_ms: dict[str, int] = {}

    """处理 Excel 上传入库。"""

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded file name")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in EXCEL_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .xlsx or .xlsm files are supported")

    stage_started = time.perf_counter()
    uploaded_path = await _save_uploaded_excel(file)
    api_timing_ms["api_save_upload"] = _elapsed_ms(stage_started)
    project_name = source_project_name or _extract_project_name(uploaded_path.name)

    stage_started = time.perf_counter()
    service = AssetEntityIngestService(db)
    api_timing_ms["api_service_init"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    items = service.ingest_excel_path(
        excel_path=str(uploaded_path),
        source_project_name=project_name,
        batch_size=batch_size,
    )
    api_timing_ms["api_service_ingest_excel"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    uploaded_file_deleted = _cleanup_uploaded_excel(uploaded_path)
    api_timing_ms["api_cleanup_upload"] = _elapsed_ms(stage_started)
    api_timing_ms["api_total_before_response"] = _elapsed_ms(request_started)
    _attach_ingest_timing(items, api_timing_ms)
    print(f"[excel-ingest-api-timing] file={file.filename} timing_ms={api_timing_ms}")

    return ExcelIngestResponse(
        count=len(items),
        items=items,
        uploaded_file_path=str(uploaded_path),
        uploaded_file_deleted=uploaded_file_deleted,
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


def _attach_ingest_timing(items: list[dict], timing_ms: dict[str, int]) -> None:
    """Attach API timing to response metadata for the frontend timing badges."""

    for item in items:
        metadata = item.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            item["metadata"] = metadata

        item_timing = metadata.setdefault("ingest_timing_ms", {})
        if not isinstance(item_timing, dict):
            item_timing = {}
            metadata["ingest_timing_ms"] = item_timing

        item_timing.update(timing_ms)


def _extract_project_name(file_name: str) -> str:
    """从文件名提取项目名，优先取书名号里的内容。"""

    stem = Path(file_name).stem
    match = re.search(r"《(.+?)》", stem)
    if match:
        return match.group(1).strip()
    return stem


def _cleanup_uploaded_excel(uploaded_path: Path) -> bool:
    """入库成功后删除本次上传目录，避免长期保留 Excel 源文件。"""

    uploads_root = (Path("runtime") / "uploads").resolve()
    upload_dir = uploaded_path.parent.resolve()

    if not upload_dir.exists():
        return True

    if upload_dir.parent != uploads_root:
        return False

    shutil.rmtree(upload_dir)
    return True
