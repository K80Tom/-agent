"""资产向量检索服务。"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.asset_entity_model import AssetEntity
from app.models.asset_media_model import AssetMedia
from app.models.asset_variant_model import AssetVariant
from app.services.vector.doubao_embedding_service import DoubaoEmbeddingService
from app.services.vector.milvus_vector_store import MilvusVectorStore
from app.services.search.query_understanding_service import QueryUnderstandingService
from sqlalchemy import desc, or_


class AssetVectorSearchService:
    """负责从向量库检索资产，并回结构库补全详情。"""

    RRF_K = 60
    RRF_SCALE = 100.0
    # 融合分里"余弦 : RRF"的占比。两者都归一化到 0~1 再加权。
    # 余弦（真实相似度）占大头，回答"到底多像"；RRF（排名）做鲁棒兜底。
    COSINE_WEIGHT = 0.6
    RRF_WEIGHT = 0.4
    # 把 0~1 的融合单元放大到跟旧版 RRF 量级接近，尽量少动 RELEVANCE_SCORE_TEMPERATURE。
    FUSION_SCALE = 2.0

    RELEVANCE_SCORE_TEMPERATURE = 2.75
    MIN_STRUCTURED_SQL_SCORE = 0.12
    # 相关性阈值：低于这个分的候选视为"没有足够相关"，直接丢弃，不硬凑 limit 条。
    # 这是 precision / recall 的调节旋钮：调高→更干净但可能漏；调低→更全但更多噪声。
    # 具体数值要用评测集（尤其负样本）定，先给个保守起点。
    MIN_RELEVANCE_SCORE = 0.45

    RECALL_SOURCE_WEIGHTS = {
        "vector_original": 1.00,
        "vector_rewrite": 0.97,
        "structured_sql": 0.4,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.embedding_service = DoubaoEmbeddingService()
        self.vector_store = MilvusVectorStore()
        self.query_understanding_service = QueryUnderstandingService()

    def search(self, *, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """执行多 query 向量召回。

        为什么这么做：
        - 原始 query 可能很长，embedding 会被很多细节稀释。
        - LLM rewrites 可以把 query 改写成更适合检索的短句。
        - 多条 query 都召回到同一资产，说明这个资产更稳定相关。
        """

        internal_limit = min(max(limit * 5, 20), 50)

        understanding = self.query_understanding_service.understand(query)

        # 原始 query 一定保留，LLM 改写只是增强，不替代用户原句。
        search_queries = [query]
        search_queries.extend(understanding.get("rewrites") or [])

        # 去重：避免相同 query 重复 embedding。
        search_queries = list(dict.fromkeys(item for item in search_queries if item))

        all_results: list[dict[str, Any]] = []

        for search_query in search_queries:
            vector = self.embedding_service.embed_text(search_query)
            hits = self.vector_store.search(vector=vector, limit=internal_limit)

            for rank, hit in enumerate(hits, start=1):
                item = self._build_result(hit)
                if item is None:
                    continue

                metadata = dict(item.get("metadata") or {})
                metadata.setdefault("search_debug", {})
                recall_source = (
                    "vector_original" if search_query == query else "vector_rewrite"
                )
                recall_signals = list(metadata.get("recall_signals") or [])
                recall_signals.append(
                    {
                        "source": recall_source,
                        "rank": rank,
                        "score": float(item.get("score") or 0),
                        "recall_query": search_query,
                    }
                )
                metadata["recall_signals"] = recall_signals
                metadata["search_debug"]["recall_query"] = search_query
                metadata["search_debug"]["vector_rank"] = rank
                metadata["search_debug"]["recall_source"] = recall_source
                metadata["search_debug"]["understanding"] = understanding
                item["metadata"] = metadata

                all_results.append(item)

        # 结构化 SQL 召回：使用 LLM 解析出的字段查 PostgreSQL。
        # 它补的是“字段命中”的候选，和向量召回互补。
        sql_results = self._structured_sql_recall(
            understanding=understanding,
            limit=20,
        )

        merged_results = self._merge_results(all_results + sql_results)

        reranked = self._rerank_results(
            query=query,
            understanding=understanding,
            items=merged_results,
        )
        # 先按阈值过滤，再截断。过滤在前保证：返回的每一条都过了相关性门槛，
        # 而不是"最多 limit 条里恰好有几条达标"。
        filtered = self._apply_relevance_threshold(reranked)

        return filtered[:limit]

    
    def _build_result(self, hit: dict[str, Any]) -> dict[str, Any] | None:
        metadata = hit.get("metadata") or {}
        source_table = metadata.get("source_table")
        source_id = metadata.get("source_id")

        if not source_table or not source_id:
            return None

        if source_table == "asset_entities":
            entity = self.db.get(AssetEntity, UUID(str(source_id)))
            if entity is None:
                return None

            media_image = self._primary_media_image(asset_entity_id=entity.id)
            metadata = self._metadata_with_primary_image(
                entity.metadata_,
                media_image=media_image,
            )

            return {
                "score": hit.get("score"),
                "source_table": source_table,
                "source_id": str(entity.id),
                "asset_kind": entity.asset_kind,
                "name": entity.name,
                "display_name": entity.display_name,
                "intro": entity.intro,
                "appearance": entity.appearance,
                "source_file_url": entity.source_file_url or self._media_url(media_image),
                "metadata": metadata,
                "vector_text": hit.get("text"),
            }

        if source_table == "asset_variants":
            variant = self.db.get(AssetVariant, UUID(str(source_id)))
            if variant is None:
                return None

            parent_entity = self.db.get(AssetEntity, variant.asset_entity_id)
            media_image = self._primary_media_image(
                asset_entity_id=variant.asset_entity_id,
                asset_variant_id=variant.id,
            )
            if media_image is None and parent_entity is not None:
                media_image = self._primary_media_image(asset_entity_id=parent_entity.id)
            metadata = self._metadata_with_primary_image(
                variant.metadata_,
                media_image=media_image,
            )

            return {
                "score": hit.get("score"),
                "source_table": source_table,
                "source_id": str(variant.id),
                "asset_kind": parent_entity.asset_kind if parent_entity else "variant",
                "name": variant.name,
                "display_name": variant.name,
                "parent_entity_id": str(parent_entity.id) if parent_entity else None,
                "parent_entity_name": parent_entity.name if parent_entity else None,
                "description": variant.description,
                "usage_context": variant.usage_context,
                "visual_prompt": variant.visual_prompt,
                "source_file_url": variant.source_file_url or self._media_url(media_image),
                "metadata": metadata,
                "vector_text": hit.get("text"),
            }

        return None

    def _primary_media_image(
        self,
        *,
        asset_entity_id: UUID,
        asset_variant_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """从 asset_media 里找可展示图片，优先主图。"""

        query = self.db.query(AssetMedia).filter(
            AssetMedia.asset_entity_id == asset_entity_id,
            AssetMedia.storage_url.isnot(None),
        )
        if asset_variant_id is not None:
            query = query.filter(AssetMedia.asset_variant_id == asset_variant_id)

        media = (
            query.order_by(
                desc(AssetMedia.is_primary),
                AssetMedia.sort_order.asc(),
                AssetMedia.created_at.asc(),
            )
            .first()
        )
        if media is None:
            return None

        return {
            "storage_bucket": media.storage_bucket,
            "storage_path": media.storage_path,
            "storage_url": media.storage_url,
            "media_kind": media.media_kind,
            "width": media.width_px,
            "height": media.height_px,
            "format": media.format,
            "sha256": media.sha256,
            "is_primary": media.is_primary,
        }

    @staticmethod
    def _media_url(media_image: dict[str, Any] | None) -> str | None:
        if not media_image:
            return None
        url = media_image.get("storage_url")
        return str(url) if url else None

    @staticmethod
    def _metadata_with_primary_image(
        metadata: dict[str, Any] | None,
        *,
        media_image: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = dict(metadata or {})
        if media_image is not None and not result.get("primary_image"):
            result["primary_image"] = media_image
        return result
    
    def _merge_results(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """合并多路召回结果，并按 source_table + source_id 去重。"""

        merged: dict[tuple[str, str], dict[str, Any]] = {}

        for item in items:
            key = (item["source_table"], item["source_id"])

            if key not in merged:
                metadata = dict(item.get("metadata") or {})
                recall_signals = list(metadata.get("recall_signals") or [])
                metadata["multi_query_hit_count"] = len(recall_signals) or 1
                item["metadata"] = metadata
                merged[key] = item
                continue

            old = merged[key]
            old_score = float(old.get("score") or 0)
            new_score = float(item.get("score") or 0)

            old_metadata = dict(old.get("metadata") or {})
            new_metadata = dict(item.get("metadata") or {})
            old_signals = list(old_metadata.get("recall_signals") or [])
            new_signals = list(new_metadata.get("recall_signals") or [])
            combined_signals = old_signals + new_signals

            # 同一个资产被多路召回时，展示字段保留原始分更高的那份；
            # 但排序信号必须合并，否则 RRF 会丢掉“多路命中”的信息。
            chosen = item if new_score > old_score else old
            chosen_metadata = dict(chosen.get("metadata") or {})

            merged_metadata = {
                **old_metadata,
                **new_metadata,
                **chosen_metadata,
            }
            merged_metadata["recall_signals"] = combined_signals
            merged_metadata["multi_query_hit_count"] = len(combined_signals) or 1
            chosen["metadata"] = merged_metadata
            merged[key] = chosen

        return list(merged.values())

    def _rerank_results(
        self,
        *,
        query: str,
        understanding: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """对多路召回结果做 RRF 融合排序。

        为什么要做：
        - 向量分、SQL 字段分不是同一个尺度，不能直接相加。
        - RRF 只看各路召回里的排名，天然适合融合不同召回通道。
        - 字段匹配、资产类型、有图等只做小幅辅助，不喧宾夺主。
        """

        scored_items = []

        for index, item in enumerate(items):
            fusion_score, reasons = self._compute_fusion_score(
                item=item,
                query=query,
                understanding=understanding,
            )
            metadata = dict(item.get("metadata") or {})
            search_debug = dict(metadata.get("search_debug") or {})
            search_debug.update(
                {
                    "fusion_score_before_diversity": fusion_score,
                    "final_score": fusion_score,
                    "fusion_reasons": reasons,
                    "recall_signals": metadata.get("recall_signals") or [],
                    "merged_rank_before_rerank": index + 1,
                }
            )
            metadata["search_debug"] = search_debug
            item["metadata"] = metadata

            scored_items.append((fusion_score, item))

        scored_items.sort(key=lambda pair: pair[0], reverse=True)

        # 排名前面如果已经出现同一个主体，后面的 variant 做轻微降权，减少刷屏。
        diversified_items = []
        seen_parent_ids: set[str] = set()
        for score, item in scored_items:
            final_score = score
            metadata = dict(item.get("metadata") or {})
            search_debug = dict(metadata.get("search_debug") or {})
            reasons = list(search_debug.get("fusion_reasons") or [])

            parent_id = item.get("parent_entity_id") or item.get("source_id")
            if parent_id in seen_parent_ids:
                final_score -= 0.20
                reasons.append("same_parent_penalty")
            else:
                seen_parent_ids.add(parent_id)

            search_debug["final_score"] = final_score
            search_debug["fusion_reasons"] = reasons
            metadata["search_debug"] = search_debug
            item["metadata"] = metadata
            diversified_items.append((final_score, item))

        diversified_items.sort(key=lambda pair: pair[0], reverse=True)
        return self._attach_relevance_scores(diversified_items)

    def _attach_relevance_scores(
        self,
        scored_items: list[tuple[float, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """把 RRF 原始融合分转换成 0-1 的相关性展示分。

        RRF 原始分只适合排序，不适合直接给用户看：
        - 原始分可能大于 1。
        - 不同 query 的候选数量和召回信号不同，原始分尺度会飘。

        这里做绝对分数校准：
        - 不再用 raw_score / max_score，因为那会导致第一名永远是 1.0。
        - 使用 1 - exp(-raw_score / temperature) 把融合分压到 0-1。
        - 多路高排名命中的结果会接近 0.9，弱结果会自然低于 0.6。
        """

        if not scored_items:
            return []

        results: list[dict[str, Any]] = []
        for raw_score, item in scored_items:
            if raw_score <= 0:
                relevance_score = 0.0
            else:
                relevance_score = 1 - math.exp(
                    -raw_score / self.RELEVANCE_SCORE_TEMPERATURE
                )
                relevance_score = max(0.0, min(relevance_score, 1.0))

            relevance_score = round(relevance_score, 4)

            metadata = dict(item.get("metadata") or {})
            search_debug = dict(metadata.get("search_debug") or {})
            search_debug["raw_fusion_score"] = raw_score
            search_debug["relevance_score"] = relevance_score
            metadata["search_debug"] = search_debug
            item["metadata"] = metadata

            # 对外返回 score 用校准后的相关性分数；原始 RRF 分保留在 metadata.search_debug。
            item["score"] = relevance_score
            results.append(item)

        return results
    
    def _apply_relevance_threshold(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按最低相关性阈值过滤结果。

        为什么要做：
        - 库里没有对应资产的 query，向量库仍会返回"最不差"的候选，
          分数不高但照样占满 limit，制造假阳性。
        - 与其硬返回 limit 条，不如把低于阈值的丢掉，允许返回更少甚至为空。
        - 返回空 = "我没找到足够相关的"，这对精度是正确行为。
        """

        kept: list[dict[str, Any]] = []
        for item in items:
            score = float(item.get("score") or 0.0)
            if score < self.MIN_RELEVANCE_SCORE:
                # items 已按分数降序，本可 break；用 continue 更稳，
                # 不依赖上游排序，以后改动也不会踩坑。
                continue
            kept.append(item)

        return kept


    def _compute_fusion_score(
        self,
        *,
        item: dict[str, Any],
        query: str,
        understanding: dict[str, Any],
    ) -> tuple[float, list[str]]:
        """计算一个候选的融合分：α·余弦 + β·RRF，再叠加多路命中/结构化/名称加分。"""

        metadata = dict(item.get("metadata") or {})
        recall_signals = metadata.get("recall_signals") or []
        score = 0.0
        reasons: list[str] = []

        for signal in recall_signals:
            source = signal.get("source")
            rank = signal.get("rank")
            if not isinstance(rank, int) or rank <= 0:
                continue

            weight = self.RECALL_SOURCE_WEIGHTS.get(str(source), 0.50)

            # RRF 项：只看排名，不看分数。天然鲁棒（不怕各通道分数尺度不一），
            # 但正因为丢了绝对分，才需要下面的余弦项来补。
            # 归一化到 0~1：rank 越小越接近 1，越大越衰减。
            rrf_term = self.RRF_K / (self.RRF_K + rank)

            # 余弦项：真实语义相似度，这才是"到底多像"的信号。
            # 只有向量召回的 score 是余弦；SQL 召回的 score 是字段匹配分，
            # 不是同一个尺度，所以这里给 0，让 SQL 只靠 RRF + structured_bonus。
            cosine = 0.0
            if str(source).startswith("vector_"):
                cosine = float(signal.get("score") or 0.0)
                # 夹到 0~1，挡住脏数据/负余弦，避免污染融合分。
                cosine = max(0.0, min(cosine, 1.0))

            # 融合：α·余弦 + β·RRF，两项都在 0~1，再乘通道权重和统一放大系数。
            blended = self.COSINE_WEIGHT * cosine + self.RRF_WEIGHT * rrf_term
            signal_score = weight * self.FUSION_SCALE * blended

            score += signal_score
            reasons.append(
                f"blend:{source}:rank={rank}:cos={cosine:.3f}:"
                f"rrf={rrf_term:.3f}:score={signal_score:.4f}"
            )


        if len(recall_signals) >= 2:
            multi_hit_bonus = 0.15 * min(len(recall_signals) - 1, 3)
            score += multi_hit_bonus
            reasons.append(f"multi_recall_hit_bonus:{multi_hit_bonus:.4f}")

        structured_score = float(metadata.get("structured_score") or 0)
        if structured_score > 0:
            structured_bonus = structured_score * 0.40
            score += structured_bonus
            reasons.append(f"structured_score_bonus:{structured_bonus:.4f}")

        name_bonus = self._name_match_bonus(item=item, query=query, understanding=understanding)
        if name_bonus:
            score += name_bonus
            reasons.append(f"name_match_bonus:{name_bonus:.4f}")

        
        return score, reasons

    def _name_match_bonus(
        self,
        *,
        item: dict[str, Any],
        query: str,
        understanding: dict[str, Any],
    ) -> float:
        """用 name_hint/display_name_hint 做名称加分，避免长 query 整句匹配。"""

        names = [
            item.get("name") or "",
            item.get("display_name") or "",
            item.get("parent_entity_name") or "",
        ]
        hints = [
            understanding.get("name_hint"),
            understanding.get("display_name_hint"),
        ]

        for hint in hints:
            if not hint:
                continue
            if any(self._normalize_text(str(hint)) == self._normalize_text(name) for name in names):
                return 0.35
            if any(self._contains(name, str(hint)) for name in names):
                return 0.25

        normalized_query = self._normalize_text(query)
        if any(normalized_query and normalized_query == self._normalize_text(name) for name in names):
            return 0.20

        return 0.0

    


    def _normalize_text(self, text: str) -> str:
        """统一文本格式，方便做名称匹配。"""

        return (
            text.lower()
            .replace("（", "(")
            .replace("）", ")")
            .replace(" ", "")
            .replace("_", "")
            .replace("-", "")
        )
    
    def _contains(self, value: str | None, term: str | None) -> bool:
        """判断字段文本是否包含 term，统一处理空值和格式。"""

        if not value or not term:
            return False

        return self._normalize_text(term) in self._normalize_text(value)

    def _score_structured_match(
        self,
        *,
        entity: AssetEntity,
        understanding: dict[str, Any],
    ) -> tuple[float, list[str]]:
        """计算 SQL 召回候选和结构化 query 的匹配分。

        分数不是向量相似度，而是结构化字段匹配度。
        后面 rerank 会把它当成候选信号之一，不应该直接写死 1.0。
        """

        score = 0.0
        matched_fields: list[str] = []

        name_hint = understanding.get("name_hint")
        if name_hint and (
            self._contains(entity.name, name_hint)
            or self._contains(entity.display_name, name_hint)
        ):
            score += 0.15
            matched_fields.append("name")


        source_project_name_hint = understanding.get("source_project_name_hint")
        if source_project_name_hint and self._contains(entity.source_project_name, source_project_name_hint):
            score += 0.08
            matched_fields.append("source_project_name")

        gender_hint = understanding.get("gender_hint")
        if gender_hint and entity.gender == gender_hint:
            score += 0.06
            matched_fields.append("gender")

        age_value_hint = understanding.get("age_value_hint")
        if isinstance(age_value_hint, int) and entity.age_value is not None:
            distance = abs(entity.age_value - age_value_hint)
            if distance <= 3:
                score += max(0.0, 0.08 - distance * 0.02)
                matched_fields.append("age_value")

        height_cm_hint = understanding.get("height_cm_hint")
        if isinstance(height_cm_hint, int) and entity.height_cm is not None:
            distance = abs(entity.height_cm - height_cm_hint)
            if distance <= 5:
                score += max(0.0, 0.05 - distance * 0.005)
                matched_fields.append("height_cm")

        # 自由文本语义（intro/appearance/发型/服装/分类）已由向量 cosine 表达，
        # 这里不再重复计分，避免和融合分里的余弦项双重计数。

        # style_tags 用精确元素匹配，和 @> 召回口径保持一致（不再子串模糊命中）。
        normalized_tags = {self._normalize_text(str(tag)) for tag in (entity.style_tags or [])}
        for term in understanding.get("style_tags") or []:
            if term and self._normalize_text(str(term)) in normalized_tags:
                score += 0.05
                matched_fields.append(f"style_tags:{term}")

        # 限制最高分，避免 SQL 分数绝对压过向量召回。
        return min(score, 0.75), matched_fields
    
    def _structured_sql_recall(
        self,
        *,
        understanding: dict[str, Any],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        # SQL 召回定位：高精度"身份/精确标签"锚定，不做模糊文本检索。
        # intro/appearance/发型/服装/分类/性别/年龄/身高 全部踢出 WHERE：
        # 它们是 OR 洪水的来源，且向量本来就更擅长，只留在打分里做加权。
        anchor_conditions = []

        # 名称：最强身份锚点。name_hint 同时匹配 name 和 display_name。
        name_hint = understanding.get("name_hint")
        if name_hint:
            like_name = f"%{name_hint}%"
            anchor_conditions.append(AssetEntity.name.ilike(like_name))
            anchor_conditions.append(AssetEntity.display_name.ilike(like_name))

        display_name_hint = understanding.get("display_name_hint")
        if display_name_hint:
            anchor_conditions.append(
                AssetEntity.display_name.ilike(f"%{display_name_hint}%")
            )

        source_project_name_hint = understanding.get("source_project_name_hint")
        if source_project_name_hint:
            anchor_conditions.append(
                AssetEntity.source_project_name.ilike(f"%{source_project_name_hint}%")
            )

        # style_tags 是 JSONB 数组，用 @>（contains）做"整个标签精确命中"。
        # 旧写法 cast(String).ilike 是在 JSON 序列化串里做子串匹配，
        # 会误命中别的 tag 片段甚至标点，这里换成精确元素包含。
        for term in understanding.get("style_tags") or []:
            if term:
                anchor_conditions.append(AssetEntity.style_tags.contains([term]))

        # 没有任何锚点就不做 SQL 召回，直接交给向量。
        # 这是杜绝"单个自由文本词/单个属性拉进半个库"的关键闸门。
        if not anchor_conditions:
            return []

        sql_fetch_limit = max(limit * 2, 40)
        rows = (
            self.db.query(AssetEntity)
            .filter(or_(*anchor_conditions))
            .order_by(AssetEntity.updated_at.desc())  # 加稳定排序，避免 limit 截断到随机行
            .limit(sql_fetch_limit)
            .all()
        )

        results: list[dict[str, Any]] = []

        for entity in rows:
            structured_score, matched_fields = self._score_structured_match(
                entity=entity,
                understanding=understanding,
            )
            if structured_score < self.MIN_STRUCTURED_SQL_SCORE:
                continue

            media_image = self._primary_media_image(asset_entity_id=entity.id)
            metadata = self._metadata_with_primary_image(
                entity.metadata_,
                media_image=media_image,
            )

            results.append(
                {
                    "score": structured_score,
                    "source_table": "asset_entities",
                    "source_id": str(entity.id),
                    "asset_kind": entity.asset_kind,
                    "name": entity.name,
                    "display_name": entity.display_name,
                    "intro": entity.intro,
                    "appearance": entity.appearance,
                    "source_file_url": entity.source_file_url or self._media_url(media_image),
                    "metadata": {
                    **metadata,
                    "recall_source": "structured_sql",
                    "structured_understanding": understanding,
                    "structured_score": structured_score,
                    "matched_fields": matched_fields,
                    },
                    "vector_text": None,
                }
            )

        results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        for rank, result in enumerate(results, start=1):
            metadata = dict(result.get("metadata") or {})
            recall_signals = list(metadata.get("recall_signals") or [])
            recall_signals.append(
                {
                    "source": "structured_sql",
                    "rank": rank,
                    "score": float(result.get("score") or 0),
                    "matched_fields": metadata.get("matched_fields") or [],
                }
            )
            metadata["recall_signals"] = recall_signals
            result["metadata"] = metadata

        return results[:limit]
    
