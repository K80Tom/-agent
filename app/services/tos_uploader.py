"""火山 TOS 上传服务。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote

import tos

from app.core.config import settings


@dataclass(slots=True)
class UploadedObject:
    """TOS 上传结果。"""

    bucket: str
    storage_path: str
    storage_url: str


class TosUploader:
    """负责把二进制文件上传到火山 TOS。"""

    def __init__(self) -> None:
        required = {
            "TOS_BUCKET": settings.tos_bucket,
            "TOS_SDK_ENDPOINT": settings.tos_sdk_endpoint,
            "TOS_PUBLIC_BASE_URL": settings.tos_public_base_url,
            "TOS_ACCESS_KEY": settings.tos_access_key,
            "TOS_SECRET_KEY": settings.tos_secret_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing TOS config: {', '.join(missing)}")

        self.bucket = settings.tos_bucket or ""
        self.public_base_url = (settings.tos_public_base_url or "").rstrip("/")
        self.client = tos.TosClientV2(
            ak=settings.tos_access_key or "",
            sk=settings.tos_secret_key or "",
            endpoint=settings.tos_sdk_endpoint or "",
            region=settings.tos_region,
        )

    def upload_bytes(
        self,
        *,
        content: bytes,
        storage_path: str,
        content_type: str,
    ) -> UploadedObject:
        """上传 bytes 并返回可访问 URL。"""

        self.client.put_object(
            bucket=self.bucket,
            key=storage_path,
            content=BytesIO(content),
            content_length=len(content),
            content_type=content_type,
        )

        quoted_path = quote(storage_path, safe="/")
        return UploadedObject(
            bucket=self.bucket,
            storage_path=storage_path,
            storage_url=f"{self.public_base_url}/{quoted_path}",
        )
