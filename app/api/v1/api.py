"""v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import asset_ingest_endpoint, asset_search_endpoint, health_endpoint

api_router = APIRouter()

api_router.include_router(
    health_endpoint.router,
    prefix="/health",
    tags=["Health"],
)
api_router.include_router(
    asset_ingest_endpoint.router,
    prefix="/asset-ingest",
    tags=["Asset Ingest"],
)


api_router.include_router(
    asset_search_endpoint.router,
    prefix="/asset-search",
    tags=["Asset Search"],
)