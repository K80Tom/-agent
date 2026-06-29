"""资产主体 PostgreSQL 查询仓储。

负责从 common.asset_entities 查询需要向量化的资产主体数据。
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row


class AssetEntityRepository:
    """资产主体查询仓储。"""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        
    def list_vectorizable(self, *, limit: int | None = None) -> list[dict]:
        """查询需要向量化的资产主体数据。"""

        sql = """
            SELECT
                id,
                source_project_id,
                source_project_name,
                asset_kind,
                name,
                display_name,
                intro,
                appearance,
                age_value,
                gender,
                height_cm,
                hair_description,
                outfit_description,
                category,
                style_tags,
                approved,
                reuse_scope,
                status,
                source_file_url,
                metadata,
                updated_at
            FROM common.asset_entities
            WHERE status IN ('approved', 'pending_review')
            ORDER BY updated_at DESC
        """

        params = ()

        if limit is not None:
            sql += " LIMIT %s"
            params = (limit,)

        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    