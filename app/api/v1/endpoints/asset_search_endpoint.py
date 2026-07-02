"""资产语义检索 endpoint。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.db import get_db
from app.schemas.asset_search import AssetSearchRequest, AssetSearchResponse
from app.services.vector.asset_vector_search_service import AssetVectorSearchService


router = APIRouter()


@router.post("/semantic", response_model=AssetSearchResponse)
def search_assets(
    request: AssetSearchRequest,
    db: Session = Depends(get_db),
) -> AssetSearchResponse:
    """根据自然语言检索资产。"""

    service = AssetVectorSearchService(db)
    items = service.search(
        query=request.query,
        limit=request.limit,
    )

    return AssetSearchResponse(
        count=len(items),
        items=items,
    )