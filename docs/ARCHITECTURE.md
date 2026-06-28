# 短剧制作智能体 RAG 检索与推荐项目架构设计

本文档用于指导“短剧制作智能体”的知识底座建设。当前阶段只做架构设计，不急着堆代码。

项目目标是支持：

```text
文档入库
语义检索
RAG 问答
相似内容推荐
后续 GraphRAG 扩展
```

## 1. 项目整体目标

这个项目不是单纯做一个上传文件接口，也不是单纯做一个向量库 Demo。

它要成为短剧制作智能体背后的知识底座，负责把公司的短剧相关资料变成可以检索、推荐和推理的数据。

典型资料包括：

```text
短剧剧本
角色设定
分镜脚本
合同
会议纪要
制作规范
素材描述
运营反馈
爆款案例分析
```

最终系统应该支持三类能力：

```text
1. 入库能力
   把多模态文档解析、切块、向量化，并保存元数据。

2. 检索能力
   用户输入问题后，从知识库中找到相关片段。

3. 推荐能力
   用户输入需求、剧本片段、角色设定或素材描述后，推荐相似剧本、桥段、角色或素材。
```

后续 GraphRAG 的目标是：

```text
把角色、剧情事件、场景、冲突、关系、题材等信息结构化成图谱，
让系统不只会“搜相似文本”，还能理解故事结构和人物关系。
```

## 2. 核心业务对象

### Document

Document 表示一个原始文档。

示例：

```text
一份剧本 PDF
一份角色设定 Word
一份会议纪要
一份制作规范
```

建议字段：

```text
id
title
source
file_name
file_type
content_type
created_at
metadata
```

Document 只代表“文档本身”，不直接代表切块，也不直接代表向量。

### Chunk

Chunk 表示从 Document 中切出来的一段文本。

示例：

```text
剧本中的一场戏
角色设定中的一段描述
会议纪要中的一个议题
```

建议字段：

```text
id
document_id
chunk_index
text
start_offset
end_offset
metadata
```

Chunk 是 RAG 检索的核心单位。

### Asset

Asset 表示可被推荐的素材或资源。

示例：

```text
视频素材
图片素材
音频素材
短剧案例
可复用桥段
```

建议字段：

```text
id
asset_type
title
description
uri
tags
metadata
```

Asset 和 Document 不一定是一回事。Document 偏知识资料，Asset 偏可推荐资源。

### Script

Script 表示短剧剧本。

建议字段：

```text
id
title
genre
summary
target_audience
episodes
metadata
```

后续 GraphRAG 中，Script 可以连接 Scene、Role、Tag。

### Scene

Scene 表示一场戏或一个剧情片段。

建议字段：

```text
id
script_id
scene_index
location
time
summary
conflict
roles
metadata
```

Scene 是后续“相似桥段推荐”的重要对象。

### Role

Role 表示角色。

建议字段：

```text
id
name
age_range
gender
personality
motivation
relationship
metadata
```

Role 是后续角色相似推荐和人物关系图谱的基础。

### Tag

Tag 表示标签。

示例：

```text
甜宠
复仇
婆媳
霸总
中老年女性
反转
强冲突
低成本场景
```

建议字段：

```text
id
name
category
description
```

Tag 可以挂在 Document、Chunk、Asset、Script、Scene、Role 上。

### SearchResult

SearchResult 表示一次检索返回的结果。

建议字段：

```text
chunk_id
document_id
score
text
metadata
source
```

它回答的是：

```text
这个问题和哪些原文片段相关？
```

### RecommendationResult

RecommendationResult 表示一次推荐返回的结果。

建议字段：

```text
target_id
target_type
title
reason
score
metadata
```

它回答的是：

```text
我为什么推荐这个剧本、角色、桥段或素材？
```

## 3. RAG 入库流程设计

入库不是“上传文件就完了”，应该拆成多个明确步骤：

```text
上传文件
→ 文档解析
→ 文本清洗
→ 文本切块
→ 保存文档和 chunk 元数据
→ 生成 embedding
→ 写入向量库
→ 返回入库结果
```

推荐的应用服务：

```text
IngestService
```

IngestService 只负责编排流程，不应该直接写具体的 VikingDB、Milvus、PostgreSQL 调用细节。

推荐调用链路：

```text
api
→ application/IngestService
→ infrastructure/document_parser
→ domain/chunker
→ infrastructure/relational_store
→ infrastructure/embedder
→ infrastructure/vector_store
```

### 入库阶段的关键原则

文档解析器必须可替换。

```text
今天可以用 LocalDocumentParser
明天可以换火山、阿里、Azure、LlamaParse、Unstructured
```

向量库也必须可替换。

```text
本地 Demo 用 LocalVectorStore
公司环境用 VikingDB
开发测试也可以用 Milvus
```

Embedding 模型也必须可替换。

```text
今天 mock
明天换 Doubao Embedding
后天换 Qwen Embedding
```

## 4. RAG 检索流程设计

检索流程是：

```text
用户输入 query
→ query 向量化
→ 向量库 TopK 检索
→ 回查 chunk 元数据
→ 可选 rerank
→ 返回 SearchResult
```

推荐的应用服务：

```text
SearchService
```

推荐调用链路：

```text
api
→ application/SearchService
→ infrastructure/embedder
→ infrastructure/vector_store
→ infrastructure/relational_store
→ application/rerank 可选
→ schema response
```

SearchService 返回的结果应该保留：

```text
原文片段
来源文档
score
metadata
```

不要只返回大模型答案。RAG 项目必须能看到“答案来自哪里”。

## 5. RAG 问答流程设计

问答是在检索的基础上多一步 LLM 生成。

流程：

```text
用户问题
→ SearchService 检索相关 chunk
→ 拼接上下文
→ 调用 LLM
→ 返回 answer + sources
```

推荐的应用服务：

```text
AnswerService
```

AnswerService 不应该自己重新写检索逻辑，而是复用 SearchService。

返回结果建议包含：

```text
answer
sources
used_chunks
```

## 6. 推荐流程设计

推荐和检索很像，但目标不同。

检索关注：

```text
哪些内容和用户问题最相关？
```

推荐关注：

```text
哪些剧本、桥段、角色、素材最适合用户需求？
为什么推荐？
```

推荐流程：

```text
用户输入需求
→ 需求向量化
→ 从向量库召回候选
→ 按 metadata 过滤
→ 业务规则打分
→ 可选 rerank
→ 生成推荐理由
→ 返回 RecommendationResult
```

推荐的应用服务：

```text
RecommendationService
```

推荐结果要尽量结构化：

```text
推荐对象
推荐理由
匹配点
score
source
```

这样 AgentKit 或前端才能稳定使用。

## 7. 后续 GraphRAG 扩展设计

GraphRAG 不应该从第一天就做。

第一阶段先把普通 RAG 跑通：

```text
Document
Chunk
Embedding
Vector Search
```

后续再增加图谱层：

```text
Script
Scene
Role
Event
Conflict
Relationship
Tag
```

GraphRAG 扩展流程：

```text
文档解析
→ 普通 chunk 入库
→ 实体抽取
→ 关系抽取
→ 写入图数据库
→ 检索时同时查向量库和图数据库
→ 合并上下文
→ LLM 生成回答或推荐
```

推荐新增接口：

```text
BaseGraphStore
GraphExtractionService
GraphSearchService
```

GraphRAG 适合解决这些问题：

```text
某个角色和谁有冲突？
某个剧本的主要反转在哪里？
哪些剧本有相似的人物关系？
哪些桥段属于同一种冲突类型？
```

## 8. 技术选型建议

### FastAPI

建议使用 FastAPI 做后端接口层。

原因：

```text
Python 生态友好
接口文档自动生成
适合快速开发 AI 后端服务
适合拆分 routers、schemas、services
```

FastAPI 只应该存在于 api 层，不应该污染 domain 层。

官方文档：https://fastapi.tiangolo.com/

### LangChain

LangChain 可以用，但不要让它成为项目架构核心。

建议：

```text
可以在 infrastructure 里封装 LangChain 的 Document、Retriever、LLMChain
不要让 domain 层直接依赖 LangChain
不要把全部业务流程写进 chain 里
```

原因是后续你可能换成自己写的检索、推荐、GraphRAG 流程。

官方文档：https://docs.langchain.com/oss/python/langchain/overview

### VikingDB / Milvus

如果公司已经明确使用火山云生态，生产环境优先考虑 VikingDB。

如果你本地开发或做开源可复现 Demo，可以用 Milvus。

架构上不要直接绑定某一个库，统一通过：

```text
BaseVectorStore
```

这样后面可以替换：

```text
LocalVectorStore
MilvusVectorStore
VikingDBVectorStore
```

Milvus 官方文档：https://milvus.io/docs

### PostgreSQL

PostgreSQL 用来保存结构化元数据。

例如：

```text
documents
chunks
assets
scripts
roles
tags
```

向量库负责相似度检索，PostgreSQL 负责可查、可过滤、可追溯的业务数据。

不要把所有 metadata 都只塞进向量库。

### Neo4j

Neo4j 建议放到 P2 阶段。

用途：

```text
角色关系图
剧情事件图
场景关系图
冲突类型图
题材标签图
```

GraphRAG 可以通过图数据库补足普通向量检索不擅长的关系推理。

Neo4j GraphRAG Python 文档：https://neo4j.com/docs/neo4j-graphrag-python/current/

### Embedding

Embedding 模型建议通过接口隔离：

```text
BaseEmbedder
```

本地开发先用 FakeEmbedder。

生产环境再换：

```text
Doubao Embedding
Qwen Embedding
BGE 系列
公司统一指定的 embedding 服务
```

选型重点：

```text
中文效果
长文本效果
向量维度
价格
稳定性
是否支持批量 embedding
是否和 VikingDB 维度匹配
```

### LLM

LLM 也必须通过接口隔离：

```text
BaseLLM
```

不要在业务代码里直接写死某个模型 SDK。

生产可选：

```text
豆包
通义千问
DeepSeek
公司内部模型服务
```

LLM 在项目里主要用于：

```text
RAG 答案生成
推荐理由生成
实体关系抽取
query 改写
```

## 9. 为什么这样分层

推荐使用分层架构：

```text
api
application
domain
infrastructure
evaluation
config
```

### api 层

负责：

```text
接收 HTTP 请求
参数校验
调用 application service
返回 response
```

不负责：

```text
业务流程
数据库操作
向量库操作
文档解析细节
```

### application 层

负责：

```text
编排业务流程
调用 parser、embedder、vector store、relational store
处理入库、检索、推荐的完整流程
```

这是项目的“大脑”，但它不直接依赖具体云厂商 SDK。

### domain 层

负责：

```text
核心业务对象
核心规则
基础接口定义
```

domain 层不应该依赖：

```text
FastAPI
LangChain
VikingDB
Milvus
PostgreSQL
Neo4j
```

这样后续换技术栈时，核心业务不会崩。

### infrastructure 层

负责：

```text
对接真实外部服务
文档解析器
Embedding 服务
向量数据库
关系数据库
LLM
图数据库
```

所有外部依赖都应该关在这一层。

### evaluation 层

负责：

```text
评估检索效果
评估推荐效果
记录测试集
计算召回率、命中率、人工评分
```

RAG 项目一定要有评估，否则很难判断“改动是不是变好了”。

### config 层

负责：

```text
读取环境变量
管理配置
切换本地、测试、生产环境
```

## 10. P0 / P1 / P2 开发路线

### P0：必须完成

P0 是最小可用版本。

```text
本地文档入库
chunk 切分
embedding
向量入库
TopK 检索
返回原文片段和 metadata
FastAPI 接口
README 和架构文档
```

P0 的目标不是效果完美，而是链路完整。

### P1：完成后项目更完整

```text
PostgreSQL 保存文档和 chunk 元数据
metadata 过滤
rerank
推荐接口
检索评估脚本
日志和异常处理
```

P1 的目标是让项目更像正式后端服务。

### P2：后续高级能力

```text
GraphRAG
实体关系抽取
图数据库
混合检索
多模态素材推荐
Agent 工具调用
```

P2 的目标是让系统从“能搜”升级成“能理解关系、能推荐、能辅助创作”。

## 11. 当前阶段结论

现在不要急着接 VikingDB，也不要急着写 GraphRAG。

建议执行顺序：

```text
1. 先搭 domain 模型和 base interface
2. 用 LocalDocumentParser + FakeEmbedder + LocalVectorStore 跑通本地 Demo
3. 再接 FastAPI
4. 再替换真实 VikingDB / Milvus
5. 再接 PostgreSQL
6. 再做推荐
7. 最后做 GraphRAG
```

架构的核心原则：

```text
先定义边界，再写实现。
先跑通本地 Demo，再接真实云服务。
先普通 RAG，再 GraphRAG。
```
