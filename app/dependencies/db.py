"""FastAPI 数据库依赖。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import create_session


def get_db() -> Generator[Session, None, None]:
    """为每个 HTTP 请求提供独立数据库 Session。"""

    db = create_session()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
