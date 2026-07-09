# 中文在线短剧 Agent RAG 检索提升 Plan

## 架构概览

推荐把现有检索链路从“单路向量召回”升级为“查询理解 + 多路召回 + 融合排序 + 二阶段重排 + 回表补全 + 评测闭环”。

```text
用户 query
-> Query Understanding
   -> 识别项目、资产类型、角色名、场景名、风格词、过滤条件
-> Candidate Retrieval
   -> Milvus dense vector topN
   -> PostgreSQL exact / fuzzy / tag topN
   -> 后续 sparse vector / BM25 topN
-> Fusion
   -> RRF 或加权融合
-> Rerank
   -> 规则重排
   -> rerank 模型或 LLM 评分
-> Hydration
   -> 回 PostgreSQL 补资产详情、图片、metadata
-> Evaluation Logging
   -> 记录 query、候选、排序、点击/人工反馈
```

## 核心模块

### 1. 检索评测集

职责：给每次优化提供固定评测基准。

建议覆盖：

- 精确名称：`叶逍遥`、`天尊版叶逍遥`
- 自然语言：`清冷古风男性角色`
- 视觉描述：`蓝白长袍 高马尾 仙侠气质`
- 场景描述：`山中道台 云雾 古风`
- 变体检索：`心魔版角色`
- 分镜关联：`第 3 集病房重生场景里出现的资产`
- 负样本：不存在的人名或错误组合

指标：

- `Hit@1 / Hit@5`
- `Recall@10 / Recall@50`
- `MRR`
- `Precision@5`
- 人工标注的“是否可用”

### 2. 查询理解

职责：从自然语言中抽取可用于过滤和重排的结构化意图。

输出建议：

```json
{
  "raw_query": "清冷古风白衣男性角色",
  "normalized_query": "清冷 古风 白衣 男性 角色",
  "asset_kind_hint": "character",
  "project_hint": null,
  "must_terms": ["白衣", "男性"],
  "soft_terms": ["清冷", "古风"],
  "exclude_terms": [],
  "filter": {
    "asset_kind": "character",
    "status": "active"
  }
}
```

短期可以用规则和词典实现；中期再接入 LLM 做 query rewrite。

### 3. 多路候选召回

职责：尽量把正确资产召回进候选池。

候选来源：

| 来源 | 解决的问题 |
|---|---|
| Dense vector | 语义相似、描述性 query |
| PostgreSQL exact | 名称、别名、项目名精确匹配 |
| PostgreSQL fuzzy | 错别字、简称、部分名称 |
| Tag/category match | 风格标签、资产类型 |
| Sparse/BM25 | 关键词、专有名词、短词 |
| Storyboard link | 分镜上下文和资产使用关系 |

### 4. 融合排序

职责：合并不同召回路径，避免不同分数直接相加造成偏差。

推荐用 RRF：

```text
final_score = sum(1 / (k + rank_i))
```

其中 `rank_i` 是候选在第 i 路召回中的排名。RRF 的好处是只依赖排名，不依赖不同检索器的原始分数可比。

### 5. 二阶段重排

职责：从候选池中选出最适合当前 query 的结果。

第一阶段规则重排：

- 名称精确命中加权。
- `asset_kind` 匹配加权。
- `style_tags` 命中加权。
- 有主图 `source_file_url` 加权。
- `approved=true` 或 `status=active` 加权。
- 同一个 parent entity 的多个 variant 做折叠或惩罚。

第二阶段模型重排：

- 输入 query 和候选资产摘要。
- 输出 0-100 相关性分。
- 保留评分原因，方便调试和人工校验。

### 6. 多粒度向量

职责：避免所有字段拼成一段文本后语义互相稀释。

建议拆分：

| collection 或字段 | 内容 | 用途 |
|---|---|---|
| `asset_entity_vectors` | 资产主体核心字段 | 找角色/场景/道具 |
| `asset_variant_vectors` | 变体描述、使用场景、视觉提示词 | 找服装/状态/特殊形态 |
| `asset_media_visual_vectors` | 图片视觉理解文本 | 按画面找图 |
| `project_storyboard_vectors` | 分镜画面、台词、场景、音效 | 找镜头和资产使用上下文 |

当前已有 `asset_entity_vectors` 和 `MILVUS_COLLECTION_PROJECT_STORYBOARD` 配置，可以在此基础上渐进扩展。

### 7. 结果解释和调试

职责：让检索结果可追踪。

建议响应中逐步增加调试字段：

```json
{
  "score": 0.87,
  "rank_reason": [
    "dense_vector_rank=3",
    "exact_name_match=false",
    "style_tag_match=古风",
    "asset_kind_match=character",
    "rerank_score=91"
  ],
  "vector_text": "..."
}
```

生产环境可以默认隐藏，调试模式打开。

## 技术决策

| 决策点 | 推荐选择 | 理由 |
|---|---|---|
| 第一阶段优化 | 评测 + 日志 + topN 扩召回 + 规则重排 | 成本最低，最快能看到收益 |
| 混合召回融合 | RRF | 不依赖不同召回分数可比，适合 dense / keyword / exact 多路召回 |
| 关键词召回起步 | PostgreSQL exact/fuzzy | 不需要立刻引入新搜索服务 |
| 中期检索增强 | Milvus sparse / multi-vector hybrid | 与现有 Milvus 技术栈一致 |
| 重排起步 | 规则重排 | 可解释、稳定、易调参 |
| 重排升级 | rerank 模型或 LLM scoring | 能更好处理复杂自然语言意图 |
| 图片检索 | 视觉模型生成文本后再向量化 | URL 本身没有语义，文本便于审查和调试 |
| 分镜数据 | 独立 collection | 分镜是使用数据，不应污染资产主数据 |

## 来源映射

- Azure AI Search 的 hybrid search 思路，对应本项目的 dense vector + keyword/exact 并行召回。
- Elasticsearch / Milvus 的 RRF 思路，对应本项目的多路候选融合。
- Cohere rerank 文档对应本项目的二阶段候选重排。
- HyDE 论文对应本项目的长尾 query / 抽象 query 改写，例如“压迫感强的反派老板”。
- Ragas context precision 对应本项目的检索评测指标，尤其是“正确资产是否排在前面”。
