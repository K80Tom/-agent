# 中文在线短剧 Agent RAG 检索提升方案

## 先看这里

本目录已经把第一阶段要用的文档写好：

| 文件 | 作用 |
|---|---|
| `spec.md` | RAG 提升目标、范围和验收口径 |
| `plan.md` | 从评测、召回、重排到视觉语义的整体实施计划 |
| `task.md` | 后续开发任务拆解 |
| `checklist.md` | 每个阶段的验收清单 |
| `step_01_评测集与评测脚本.md` | 第一步怎么用评测表验收接口 |
| `rag检索评测集.md` | 已经整理好的人工评测主表，包含 query、期望命中、期望排名、实际命中、实际排名、实际分数和是否通过 |

当前先以 `rag检索评测集.md` 为主，不要求你手写 JSON。后续如果要自动批量跑接口，再把这张表接到脚本里生成 Markdown 报告。

## 结论

当前系统已经跑通了基础 RAG 检索链路：

```text
资产结构化字段
-> 拼接 vector_text
-> 豆包 embedding
-> Milvus 单路向量召回
-> 根据 metadata.source_table / source_id 回 PostgreSQL 补详情
```

下一阶段最值得优先做的不是立刻换 embedding 模型，而是把“召回、排序、评测”补齐：

1. 先建立检索评测集和日志，让每次优化可量化。
2. 再做混合召回：向量召回 + 关键词/精确匹配召回。
3. 对候选结果做二阶段重排，解决“召回到了但排不前”的问题。
4. 把资产、变体、图片视觉语义、分镜分到不同向量链路，避免互相污染。
5. 最后引入查询改写、业务权重和资产关系扩展。

## 当前主要短板

| 问题 | 当前表现 | 影响 |
|---|---|---|
| 单路向量召回 | `AssetVectorSearchService` 只把 query embedding 后查 Milvus | 角色名、专有名词、短词、错别字、明确字段过滤容易不稳定 |
| 无混合检索 | 没有 BM25/关键词/数据库精确匹配召回 | “叶逍遥”“天尊版叶逍遥”这类精确名称不一定排第一 |
| 无重排 | Milvus topK 直接返回 | 语义相近但业务不合适的资产可能排前面 |
| 无查询理解 | query 只有一段自然语言 | 无法识别资产类型、项目、场景、风格、性别、年龄等过滤条件 |
| 无评测闭环 | 没有固定 query 集和指标 | 优化后无法判断是真的变好还是只是感觉变好 |
| 向量粒度偏粗 | entity / variant 文本统一拼接 | 名称、外观、标签、变体、图片视觉特征容易互相稀释 |

## 推荐路线

### P0：评测和日志先行

目标：先知道“搜得好不好”。

- 建 50-100 条短剧资产检索评测 query。
- 每条 query 标注期望命中资产 ID、资产类型、项目名和期望排名。
- 记录每次检索的 query、召回候选、score、vector_text、最终排序。
- 指标用 `Hit@K`、`MRR`、`Recall@K`、`Precision@K`。

### P1：不大改架构的快速提升

目标：在当前 Milvus 单 collection 基础上，提升首屏结果。

- 检索时扩大召回，例如 Milvus 先取 top 50，再业务重排后返回 top 5/10。
- 加资产类型、项目、状态过滤：`asset_kind`、`source_project_id`、`approved/status`。
- 结果重排时加规则：名称精确命中 > 别名命中 > 标签命中 > 语义相似。
- 对 entity 和 variant 做去重与合并展示，避免一个角色多个变体刷屏。

### P2：混合召回

目标：解决“向量擅长语义，关键词擅长精确”的互补问题。

推荐候选池：

```text
query
-> 向量召回 topN
-> 关键词/名称召回 topN
-> 元数据过滤召回 topN
-> RRF 或加权融合
-> 二阶段重排
-> 返回结果
```

优先实现方式：

- PostgreSQL 做名称、display_name、category、style_tags 的精确/模糊查询。
- Milvus 继续做语义向量召回。
- 用 RRF 合并多路结果，避免不同召回分数不可比较。

后续可以升级到 Milvus 多向量 / 稀疏向量混合检索。

### P3：二阶段重排

目标：让“最适合当前 query 的资产”排到前面。

重排输入不要只看 vector score，建议使用：

- query 原文
- 候选资产的 `name / display_name`
- `asset_kind`
- `intro / appearance / category / style_tags`
- 变体字段：`description / usage_context / visual_prompt`
- 是否有可用图片 `source_file_url`
- 审核状态、复用范围、项目匹配程度

先用规则重排，稳定后接入 rerank 模型或 LLM 评分。

### P4：多粒度向量和视觉语义

目标：让不同检索意图走不同索引。

建议拆成四类向量：

| 向量链路 | 数据来源 | 用途 |
|---|---|---|
| 资产主体向量 | `asset_entities` 核心字段 | 找角色、场景、道具 |
| 资产变体向量 | `asset_variants` | 找服装、状态、特殊形态 |
| 图片视觉语义向量 | `asset_media` 的视觉理解文本 | 按画面、颜色、构图、服饰找图 |
| 分镜向量 | `project_director_storyboard_prompts` / 分镜行 | 找镜头、台词、场景使用关系 |

图片不要直接向量化 URL。应先用视觉模型生成 `visual_summary / search_tags / composition / colors / quality_notes`，再向量化文本。

## 推荐实施顺序

```text
第 1 周：评测集 + 检索日志 + topN 扩召回 + 规则重排
第 2 周：关键词召回 + RRF 融合 + API 增加过滤条件
第 3 周：重排模型/LLM rerank + 结果解释字段
第 4 周：图片视觉语义入库 + 多向量 collection 设计
第 5 周：分镜向量和资产关系扩展
```

## 调研依据

- [Azure AI Search Hybrid Search](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview)：混合搜索将全文检索和向量检索并行执行，并用 RRF 融合结果。
- [Elasticsearch Reciprocal Rank Fusion](https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html)：RRF 适合融合不同检索器的排名，因为不要求不同分数体系可直接比较。
- [Milvus Hybrid Search](https://milvus.io/docs/hybrid_search_with_milvus.md)：Milvus 支持在一个检索流程中组合稠密向量、稀疏向量和多字段向量。
- [Milvus Reranking](https://milvus.io/docs/reranking.md)：Milvus 提供 WeightedRanker、RRFRanker 等候选融合/重排策略。
- [Cohere Rerank Docs](https://docs.cohere.com/docs/reranking)：rerank 模型接收 query 和候选文档，按相关性重新排序。
- [HyDE: Precise Zero-Shot Dense Retrieval without Relevance Labels](https://arxiv.org/abs/2212.10496)：用 LLM 生成 hypothetical document，再 embedding 检索，可改善短 query 或抽象 query 的召回。
- [Ragas Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)：评估检索结果中相关上下文是否排在更前面。

## mew-spec 文档

- [spec.md](./spec.md)：做什么，目标和边界。
- [plan.md](./plan.md)：怎么做，架构方案。
- [task.md](./task.md)：按什么顺序做。
- [checklist.md](./checklist.md)：怎么验收。
