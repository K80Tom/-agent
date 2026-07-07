"""应用配置管理。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from sqlalchemy.engine import URL


def _load_dotenv_if_exists() -> None:
    """读取项目根目录下的 .env，已有环境变量不覆盖。"""

    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    """应用全局配置。

    所有环境变量都集中在这里读取，业务代码不要直接散落使用 os.getenv。
    """

    app_name: str
    app_version: str
    debug: bool

    database_url: str | None
    postgres_host: str | None
    postgres_port: int
    postgres_db: str | None
    postgres_user: str | None
    postgres_password: str | None
    postgres_schema: str

    ark_base_url: str
    ark_api_key: str | None
    ark_llm_model: str | None
    doubao_llm_model: str | None
    doubao_embedding_model: str | None

    tos_bucket: str | None
    tos_sdk_endpoint: str | None
    tos_public_base_url: str | None
    tos_region: str
    tos_access_key: str | None
    tos_secret_key: str | None
    milvus_uri: str | None
    milvus_user: str | None
    milvus_password: str | None
    milvus_collection_asset_entity: str

    # 分镜单独使用一个 Milvus collection，避免污染资产检索结果。
    milvus_collection_project_storyboard: str

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量创建配置对象。"""

        _load_dotenv_if_exists()
        return cls(
            app_name=os.getenv("APP_NAME", "Shortdrama Agent"),
            app_version=os.getenv("APP_VERSION", "0.1.0"),
            debug=_get_bool("DEBUG", False),
            database_url=os.getenv("DATABASE_URL"),
            postgres_host=os.getenv("POSTGRES_HOST"),
            postgres_port=_get_int("POSTGRES_PORT", 5432),
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            postgres_schema=os.getenv("POSTGRES_SCHEMA", "common"),
            ark_base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            ark_api_key=os.getenv("ARK_API_KEY"),
            ark_llm_model=os.getenv("ARK_LLM_MODEL"),
            doubao_llm_model=os.getenv("DOUBAO_LLM_MODEL"),
            doubao_embedding_model=os.getenv("DOUBAO_EMBEDDING_MODEL"),
            tos_bucket=os.getenv("TOS_BUCKET"),
            tos_sdk_endpoint=os.getenv("TOS_SDK_ENDPOINT") or os.getenv("TOS_ENDPOINT"),
            tos_public_base_url=os.getenv("TOS_PUBLIC_BASE_URL") or os.getenv("TOS_ENDPOINT"),
            tos_region=os.getenv("TOS_REGION", "cn-beijing"),
            tos_access_key=os.getenv("TOS_ACCESS_KEY"),
            tos_secret_key=os.getenv("TOS_SECRET_KEY"),
            milvus_uri=os.getenv("MILVUS_URI"),
            milvus_user=os.getenv("MILVUS_USER"),
            milvus_password=os.getenv("MILVUS_PASSWORD"),
            milvus_collection_asset_entity=os.getenv(
                "MILVUS_COLLECTION_ASSET_ENTITY",
                "asset_entity_vectors",
            ),

            # 分镜向量库：用于按画面描述、台词、场景等检索分镜。
            milvus_collection_project_storyboard=os.getenv(
                "MILVUS_COLLECTION_PROJECT_STORYBOARD",
                "project_storyboard_vectors",
            ),
        )

    @property
    def sqlalchemy_database_url(self) -> str | URL:
        """返回 SQLAlchemy 可用的数据库连接地址。"""

        if self.database_url:
            return self.database_url

        if not all(
            [
                self.postgres_host,
                self.postgres_db,
                self.postgres_user,
                self.postgres_password,
            ]
        ):
            return "sqlite:///./local.db"

        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def llm_model(self) -> str | None:
        """返回用于字段抽取的大模型接入点。"""

        return self.ark_llm_model or self.doubao_llm_model


settings = Settings.from_env()
