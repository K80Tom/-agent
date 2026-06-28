# 短剧制作智能体项目目录结构设计

本文档定义项目后续推荐的 Python 目录结构。当前阶段先设计结构，不一次性实现所有文件。

## 1. 推荐目录结构

```text
shortdrama-agent/
  app/
    __init__.py
    main.py

    api/
      __init__.py
      routers/
        __init__.py
        health.py
        ingest.py
        search.py
        recommend.py
      schemas/
        __init__.py
        ingest.py
        search.py
        recommend.py

    application/
      __init__.py
      ingest_service.py
      search_service.py
      recommendation_service.py
      answer_service.py

    domain/
      __init__.py
      models/
        __init__.py
        document.py
        chunk.py
        asset.py
        script.py
        scene.py
        role.py
        tag.py
        result.py
      interfaces/
        __init__.py
        document_parser.py
        embedder.py
        vector_store.py
        relational_store.py
        llm.py
        graph_store.py
      services/
        __init__.py
        chunker.py
        scoring.py

    infrastructure/
      __init__.py
      document_parsers/
        __init__.py
        local_parser.py
        commercial_parser.py
      embedders/
        __init__.py
        fake_embedder.py
        doubao_embedder.py
        qwen_embedder.py
      vectorstores/
        __init__.py
        local_vector_store.py
        milvus_vector_store.py
        vikingdb_vector_store.py
      relational/
        __init__.py
        postgres_store.py
        sqlalchemy_models.py
      llms/
        __init__.py
        fake_llm.py
        doubao_llm.py
        qwen_llm.py
      graph/
        __init__.py
        neo4j_store.py

    evaluation/
      __init__.py
      datasets/
      retrieval_eval.py
      recommendation_eval.py

    config/
      __init__.py
      settings.py

  scripts/
    ingest_local.py
    search_local.py
    evaluate_retrieval.py

  tests/
    test_chunker.py
    test_local_vector_store.py
    test_ingest_service.py
    test_search_service.py

  docs/
    ARCHITECTURE.md
    PROJECT_STRUCTURE.md

  README.md
  pyproject.toml
  .env.example
```

## 2. 每一层负责什么

### app/api

接口层。

负责：

```text
接收请求
校验请求体
调用 application service
返回响应
```

不负责：

```text
文档解析
chunk 切分
embedding
数据库 CRUD
向量库查询
推荐排序
```

示例接口：

```text
POST /api/ingest
POST /api/search
POST /api/recommend
GET  /api/health
```

### app/application

应用服务层。

负责把多个步骤串起来。

例如 IngestService：

```text
解析文档
切块
保存文档元数据
生成 embedding
写入向量库
```

例如 SearchService：

```text
query embedding
向量检索
回查 metadata
返回 SearchResult
```

application 层不应该写死某个具体 SDK。

### app/domain

核心业务层。

负责：

```text
定义业务对象
定义基础接口
定义核心规则
```

domain 层必须保持干净。

不允许直接依赖：

```text
FastAPI
LangChain
VikingDB
Milvus
PostgreSQL
Neo4j
```

### app/infrastructure

基础设施层。

负责对接真实外部系统：

```text
文档解析器
Embedding 服务
向量数据库
PostgreSQL
LLM
Neo4j
```

如果以后从 Milvus 换成 VikingDB，只应该改这一层，不应该影响 api、application、domain。

### app/evaluation

评估层。

负责：

```text
检索评估
推荐评估
测试集管理
效果对比
```

RAG 项目不能只看“接口能不能跑”，还要看“结果准不准”。

### app/config

配置层。

负责：

```text
读取 .env
管理数据库地址
管理模型配置
管理向量库配置
切换本地、测试、生产环境
```

## 3. 为什么不是简单 routers / services / repositories

普通 CRUD 项目用：

```text
routers
services
repositories
models
schemas
```

就够了。

但这个项目不是普通 CRUD。

它会涉及：

```text
文档解析
切块
embedding
向量库
LLM
推荐排序
GraphRAG
```

所以建议使用更清晰的分层：

```text
api
application
domain
infrastructure
```

这样做的好处是：

```text
业务对象清楚
外部服务可替换
后续 GraphRAG 容易扩展
测试更容易写
别人接手项目更容易看懂
```

## 4. MVP 阶段只需要实现哪些文件

第一版不要把目录写满。

MVP 只需要这些：

```text
app/main.py

app/domain/models/document.py
app/domain/models/chunk.py
app/domain/models/result.py

app/domain/interfaces/document_parser.py
app/domain/interfaces/embedder.py
app/domain/interfaces/vector_store.py

app/domain/services/chunker.py

app/infrastructure/document_parsers/local_parser.py
app/infrastructure/embedders/fake_embedder.py
app/infrastructure/vectorstores/local_vector_store.py

app/application/ingest_service.py
app/application/search_service.py

app/api/routers/health.py
app/api/routers/ingest.py
app/api/routers/search.py
app/api/schemas/ingest.py
app/api/schemas/search.py
```

先跑通：

```text
本地 txt/md 文档
固定窗口切块
fake embedding
本地内存向量检索
TopK 返回 chunk
```

这一步跑通后，再替换真实服务。

## 5. 真实服务替换顺序

推荐替换顺序：

```text
1. LocalDocumentParser → 商用文档解析器
2. FakeEmbedder → 真实 embedding 服务
3. LocalVectorStore → VikingDB 或 Milvus
4. 内存 metadata → PostgreSQL
5. 简单 TopK → metadata filter + rerank
6. SearchService → RecommendationService
7. 普通 RAG → GraphRAG
```

不要同时替换多个组件。

每替换一个组件，都要先验证：

```text
接口还能不能跑
结果格式有没有变
检索效果有没有变好
失败时错误是否清楚
```

## 6. 每次开发一个小步骤的格式

后续每次开发都按这个格式推进：

```text
1. 当前目标
2. 为什么先做这一步
3. 这一步涉及哪些文件
4. 代码实现
5. 如何运行
6. 如何验证是否成功
7. 下一步应该做什么
```

这样可以避免项目再次变成“想到哪里写到哪里”。
