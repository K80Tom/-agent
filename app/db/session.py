"""数据库 engine 和 Session 管理。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

# 导入模型，让 Base.metadata 可以发现表定义。
import app.models  # noqa: F401,E402


connect_args = {}
if str(settings.sqlalchemy_database_url).startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.sqlalchemy_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def create_session() -> Session:
    """创建一个数据库 Session。"""

    return SessionLocal()


def init_db() -> None:
    """初始化数据库表。

    生产环境建议使用 Alembic 迁移，不建议启动时自动 create_all。
    """

    Base.metadata.create_all(bind=engine)
