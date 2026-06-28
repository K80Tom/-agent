# 项目骨架中文说明

本文档解释当前项目每个目录和关键文件分别负责什么。

## 1. app

```text
app/
```

这是后端应用主目录。

所有真正的 Python 后端代码都应该放在这里。

## 2. app/main.py

```text
app/main.py
```

FastAPI 应用入口。

负责：

```text
创建 FastAPI app
挂载路由
读取基础配置
```

不负责：

```text
文档解析
切块
embedding
数据库操作
向量库操作
推荐逻辑
```

## 3. app/api

```text
app/api/
```

接口层。

负责接收 HTTP 请求，并把请求交给 services 层。

这一层以后放：

```text
POST /api/ingest
POST /api/search
POST /api/recommend
GET  /api/health
```

## 4. app/api/routes

```text
app/api/routes/
```

FastAPI router 放这里。

当前已有：

```text
health.py
```

后续会新增：

```text
ingest.py
search.py
recommend.py
```

router 的职责很简单：

```text
接收参数
调用 service
返回 response
```

router 不应该直接调用数据库或向量库。

## 5. app/schemas

```text
app/schemas/
```

请求体和响应体定义。

这一层使用 Pydantic。

后续会放：

```text
ingest.py
search.py
recommend.py
```

schemas 是给 API 用的，不是核心业务模型。

## 6. app/services

```text
app/services/
```

应用服务层。

负责把多个步骤串成完整流程。

例如后续的 IngestService：

```text
解析文档
切块
保存元数据
生成 embedding
写入向量库
```

例如后续的 SearchService：

```text
query embedding
向量检索
回查 metadata
返回 SearchResult
```

services 是业务流程编排层。

## 7. app/domain

```text
app/domain/
```

核心业务层。

这是项目地基。

domain 层不依赖：

```text
FastAPI
LangChain
VikingDB
Milvus
PostgreSQL
Neo4j
```

domain 只定义：

```text
业务对象
基础接口
核心规则
```

## 8. app/domain/models

```text
app/domain/models/
```

业务模型目录。

当前已有：

```text
document.py  原始文档
chunk.py     文档切块
asset.py     可推荐素材
script.py    短剧剧本
scene.py     剧情场景
role.py      角色
tag.py       标签
result.py    检索结果和推荐结果
```

这些对象是业务语言，不是数据库表。

## 9. app/domain/interfaces

```text
app/domain/interfaces/
```

基础接口目录。

当前已有：

```text
document_parser.py    文档解析器接口
embedder.py           embedding 接口
vector_store.py       向量库接口
relational_store.py   关系型数据库接口
llm.py                大模型接口
```

后续第三方工具都要实现这些接口。

例如：

```text
VikingDBVectorStore 实现 BaseVectorStore
MilvusVectorStore 实现 BaseVectorStore
DoubaoEmbedder 实现 BaseEmbedder
PostgresStore 实现 BaseRelationalStore
```

## 10. app/infrastructure

```text
app/infrastructure/
```

基础设施层。

这一层以后对接真实外部系统。

例如：

```text
火山文档解析
VikingDB
Milvus
PostgreSQL
豆包 embedding
通义千问
Neo4j
LangChain
```

外部 SDK 代码只应该出现在这一层。

## 11. app/config

```text
app/config/
```

配置层。

负责统一读取环境变量和项目配置。

后续数据库地址、向量库地址、模型名称、API Key 都应该从这里管理。

## 12. scripts

```text
scripts/
```

命令行脚本目录。

适合放：

```text
本地批量入库脚本
本地检索测试脚本
评估脚本
```

## 13. tests

```text
tests/
```

测试目录。

后续优先给这些模块写测试：

```text
chunker
local_vector_store
ingest_service
search_service
```

## 14. docs

```text
docs/
```

项目文档目录。

当前已有：

```text
ARCHITECTURE.md       架构设计
PROJECT_STRUCTURE.md  目录结构设计
SKELETON_GUIDE.md     当前骨架说明
```

## 15. 当前第一步完成标准

当前第一步完成后，项目应该满足：

```text
FastAPI 可以启动
domain 层已经有核心业务对象
domain 层已经有基础接口
没有接数据库
没有接向量库
没有接 LangChain
没有接第三方解析器
```

这样后面每接一个工具，都会有清晰的位置。

