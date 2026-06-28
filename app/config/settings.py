"""项目配置。

后续所有环境变量都从这里统一读取，避免散落在业务代码中。
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    """应用配置对象。"""

    app_name: str = os.getenv("APP_NAME", "Shortdrama Agent RAG")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")


settings = Settings()

