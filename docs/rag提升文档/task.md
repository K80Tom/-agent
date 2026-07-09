# 中文在线短剧 Agent RAG 检索提升 Tasks

> 本文是后续实现任务拆解，不代表本次已经改代码。

## 文件清单建议

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `docs/rag提升文档/` | 方案、计划、任务、验收文档 |
| 新建 | `docs/rag提升文档/rag检索评测集.md` | 人工可读的固定评测 query 集，包含 query、期望命中、期望排名、实际命中、实际排名、实际分数和是否通过 |
| 可选 | `scripts/evaluate_asset_search.py` | 后续把人工评测表自动化时使用，批量调用检索接口并生成报告 |
| 新建 | `app/services/search/query_understanding_service.py` | 查询理解与过滤条件抽取 |
| 新建 | `app/services/search/candidate_retrieval_service.py` | 多路候选召回 |
| 新建 | `app/services/search/rank_fusion_service.py` | RRF / 加权融合 |
| 新建 | `app/services/search/asset_rerank_service.py` | 规则重排和模型重排 |
| 修改 | `app/schemas/asset_search.py` | 增加可选过滤条件和 debug 字段 |
| 修改 | `app/api/v1/endpoints/asset_search_endpoint.py` | 接入新的检索编排服务 |
| 修改 | `app/services/vector/milvus_vector_store.py` | 支持更大 topN、过滤、后续 hybrid search |

## T1：建立评测 query 集

**依赖：** 无

**步骤：**

1. 从现有资产库整理 50-100 条 query。
2. 每条 query 写成 Markdown 表格行，先保证人能直接看懂和验收。
3. 每行必须包含：`Query`、`应命中资产`、`应命中 ID`、`资产类型`、`期望排名`、`实际命中`、`实际排名`、`实际分数`、`是否通过`、`问题判断`。
4. 覆盖角色精确检索、场景精确检索、角色语义检索、场景语义检索、变体视觉描述、负样本和边界样本。
5. 主文件保存为 `docs/rag提升文档/rag检索评测集.md`。

**验证：** 打开 `docs/rag提升文档/rag检索评测集.md`，能直接看到每条 query 应该命中谁、应该排第几，以及实际测试结果应该填在哪里。

## T2：增加检索日志

**依赖：** T1

**步骤：**

1. 每次检索记录 query、limit、候选 ID、score、vector_text。
2. 记录最终返回排序。
3. 可选记录用户点击、人工选择或 API 调用方反馈。

**验证：** 执行一次检索后，可以看到完整候选链路。

## T3：扩大向量召回并做基础规则重排

**依赖：** T2

**步骤：**

1. Milvus 内部召回 top 50。
2. 业务层重排后返回用户请求的 limit。
3. 加名称命中、资产类型命中、标签命中、主图可用、审核状态等规则分。
4. 同 parent entity 的 variant 做折叠或降权。

**验证：** 对精确名称 query，目标资产稳定进入 top 1 或 top 3。

## T4：增加查询过滤字段

**依赖：** T3

**步骤：**

1. 请求体增加可选字段：`asset_kind`、`source_project_name/source_project_id`、`status`、`approved`。
2. 检索时把过滤条件传入候选召回和回表阶段。
3. 保持原有 `query + limit` 调用兼容。

**验证：** 旧请求不受影响；传入 `asset_kind=scene` 时不返回 character。

## T5：实现关键词/精确匹配召回

**依赖：** T4

**步骤：**

1. PostgreSQL 中对 `name`、`display_name` 做精确匹配。
2. 对 `category`、`style_tags`、`intro`、`appearance` 做轻量模糊匹配。
3. 返回统一候选结构，保留召回来源和 rank。

**验证：** 输入完整角色名时，即使向量分不高，也能召回该角色。

## T6：实现 RRF 融合

**依赖：** T5

**步骤：**

1. 将 dense vector、exact、fuzzy、tag 多路结果转为 rank list。
2. 用 RRF 合并排名。
3. 保留每个候选的来源贡献，方便 debug。

**验证：** 多路召回中任一路高排名的正确资产，不会被单一路分数体系压掉。

## T7：接入二阶段模型重排

**依赖：** T6

**步骤：**

1. 从融合候选中取 top 20-50。
2. 构造候选摘要：名称、类型、简介、外观、标签、变体描述。
3. 调用 rerank 模型或 LLM scoring。
4. 将 rerank 分和原因写入 debug 字段。

**验证：** 描述性 query 的 top 5 人工可用率高于纯向量召回。

## T8：图片视觉语义入库

**依赖：** T6

**步骤：**

1. 对 `asset_media` 主图/参考图调用视觉模型。
2. 生成 `visual_summary`、`search_tags`、`composition`、`colors`、`quality_notes`。
3. 将视觉理解结果写入 metadata。
4. 将视觉文本写入独立图片向量 collection。

**验证：** 输入“蓝白长袍、高马尾、仙侠气质”能召回对应角色图。

## T9：分镜向量独立检索

**依赖：** T6

**步骤：**

1. 将分镜行转换为独立 vector_text。
2. 写入 `project_storyboard_vectors`。
3. 搜索时可选择搜索资产库、分镜库或两者。
4. 分镜命中后可扩展关联资产。

**验证：** 输入台词/镜头描述时能召回分镜，而不是污染资产主体结果。

## T10：离线评测脚本

**依赖：** T1-T7

**步骤：**

1. 后续如果需要自动化，再把 Markdown 评测表转成脚本可读格式，或者让脚本直接解析 Markdown 表格。
2. 调用本地或服务端 search API。
3. 计算 `Hit@K`、`Recall@K`、`MRR`、`Precision@K`。
4. 输出 Markdown 报告。

**验证：** 每次改检索逻辑后能生成可对比报告。

## 执行顺序

```text
T1 -> T2 -> T3 -> T4
              -> T5 -> T6 -> T7 -> T10
                    -> T8
                    -> T9
```
