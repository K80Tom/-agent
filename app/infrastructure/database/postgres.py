"""PostgreSQL 数据库连接。

这里负责创建 PostgreSQL 连接。
业务代码不要直接到处写 psycopg.connect。
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg import Connection


load_dotenv(override=True)


def get_postgres_connection() -> Connection:
    """创建 PostgreSQL 连接。"""

    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )