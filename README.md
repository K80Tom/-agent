# 短剧资产智能体

这是一个面向短剧制作流程的资产入库与语义检索服务。当前版本已经跑通：

- Excel 资产表上传与解析
- 使用大模型从 Excel 行中提取结构化资产字段
- Excel 内嵌图片提取并上传到火山 TOS
- 结构化数据写入 PostgreSQL
- 资产文本生成 embedding 并写入 Milvus
- 通过自然语言进行资产语义检索
- 结构化 JSON 资产批量入库
- 分镜 Excel 解析基础能力

## 当前能力

### Excel 入库

接口接收 Excel 文件，后端自动解析工作表，不需要前端手动传 `sheet_name`。

流程：

```text
上传 Excel
-> 临时保存到 runtime/uploads
-> 解析全部有效工作表
-> 按行提取字段和图片位置
-> 调用大模型提取 asset_entities 字段
-> 上传 Excel 内嵌图片到 TOS
-> 写入 asset_source_projects
-> 写入 asset_entities / asset_variants
-> 写入 asset_media
-> 同步 entity / variant 到 Milvus 向量库
```

### JSON 资产入库

对接方可以绕过 Excel，直接提交结构化 JSON 资产数据。后端会写入 `asset_entities`，并同步到资产向量库。

```text
POST /api/v1/asset-ingest/json/assets
```

适合外部资产系统、标注系统或上游 Agent 已经产出结构化字段的场景。

### 分镜 Excel 解析

项目已加入分镜 Excel 解析模块，用于识别分镜 sheet、映射表头并标准化分镜行数据。当前分镜链路处于基础解析阶段，相关设计文档放在 `分镜docs/`。

### 向量检索

检索流程：

```text
用户 query
-> 豆包 embedding
-> Milvus 向量检索
-> 从 metadata 取 source_table / source_id
-> 回 PostgreSQL 查询完整资产信息
-> 返回资产详情和图片 URL
```

当前检索为混合检索，不强制区分 `character` / `scene`。返回结果中会包含 `asset_kind` 和 `source_table`，调用方可以据此展示或二次筛选。

## 项目结构

```text
app/
  main.py                         # FastAPI 入口
  api/
    v1/
      api.py                      # v1 路由聚合
      endpoints/
        health_endpoint.py
        asset_ingest_endpoint.py  # Excel / JSON 入库接口
        asset_search_endpoint.py  # 语义检索接口
  core/
    config.py                     # 环境变量和全局配置
  db/
    base.py                       # SQLAlchemy Base
    session.py                    # engine / Session 管理
  dependencies/
    db.py                         # FastAPI 数据库依赖
  models/                         # SQLAlchemy ORM 模型
    asset_source_project_model.py
    asset_entity_model.py
    asset_variant_model.py
    asset_media_model.py
    project_director_storyboard_prompt_model.py
  repositories/                   # 数据库访问层
    asset_source_project_repository.py
    asset_entity_repository.py
    asset_variant_repository.py
    asset_media_repository.py
    project_director_storyboard_prompt_repository.py
  schemas/                        # Pydantic 入参 / 出参
    asset_ingest.py
    asset_search.py
    health.py
  prompts/
    excel_asset_extraction_prompt.py
  services/                       # 业务编排和外部服务
    asset_entity_ingest_service.py
    excel_asset_parser.py
    excel_image_extractor.py
    excel_image_upload_service.py
    llm_excel_asset_extractor.py
    tos_uploader.py
    asset_media_mapping.py
    asset_variant_detector.py
    storyboard_excel_parser.py
    Mapping/
      storyboard_header_mapper.py
      storyboard_field_mapper.py
    json_ingest/
      json_asset_ingest_service.py
    vector/
      doubao_embedding_service.py
      milvus_vector_store.py
      asset_vector_sync_service.py
      asset_vector_search_service.py

scripts/                          # 本地调试脚本
docs/
分镜docs/                         # 分镜入库设计文档
runtime/                          # 上传临时文件，已忽略提交
```

## 分层约定

- `endpoint`：接收 HTTP 请求，做参数校验，调用 service，不直接写业务逻辑和 SQL。
- `service`：编排业务流程，例如 Excel 入库、图片上传、向量同步、语义检索。
- `repository`：封装数据库读写，不处理复杂业务。
- `model`：SQLAlchemy ORM 表结构。
- `schema`：Pydantic 请求体和响应体。
- `db`：数据库连接、Session、Base。
- `core/config`：集中读取环境变量。

## 环境变量

复制 `.env.example` 为 `.env`，并填入真实配置。

```text
APP_NAME=Shortdrama Agent
APP_VERSION=0.1.0
DEBUG=false

POSTGRES_HOST=...
POSTGRES_PORT=5432
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_SCHEMA=common

ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_API_KEY=...
ARK_LLM_MODEL=...
DOUBAO_LLM_MODEL=...
DOUBAO_EMBEDDING_MODEL=...

TOS_BUCKET=...
TOS_SDK_ENDPOINT=https://tos-cn-beijing.volces.com
TOS_PUBLIC_BASE_URL=https://<bucket>.tos-cn-beijing.volces.com
TOS_REGION=cn-beijing
TOS_ACCESS_KEY=...
TOS_SECRET_KEY=...

MILVUS_URI=...
MILVUS_USER=...
MILVUS_PASSWORD=...
MILVUS_COLLECTION_ASSET_ENTITY=asset_entity_vectors
MILVUS_COLLECTION_PROJECT_STORYBOARD=project_storyboard_vectors
```

注意：不要提交 `.env`。仓库只提交 `.env.example`。

## 启动

安装依赖：

```powershell
pip install -r requirements.txt
```

启动 FastAPI：

```powershell
D:\Anaconda3\envs\shortdrama-agent\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开接口文档：

```text
http://127.0.0.1:8000/docs
```

## API

### 健康检查

```text
GET /api/v1/health
```

### 上传 Excel 并自动入库

```text
POST /api/v1/asset-ingest/excel/upload
```

表单参数：

- `file`：Excel 文件，支持 `.xlsx` / `.xlsm`
- `source_project_name`：可选，不传则从文件名提取，优先取 `《...》` 中的内容
- `batch_size`：每批调用大模型的行数，默认 `5`

示例：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/asset-ingest/excel/upload" `
  -F "file=@C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" `
  -F "batch_size=5"
```

### JSON 资产批量入库

```text
POST /api/v1/asset-ingest/json/assets
```

请求体示例：

```json
{
  "source_project_name": "天尊",
  "assets": [
    {
      "asset_kind": "character",
      "name": "叶逍遥",
      "display_name": "叶逍遥",
      "intro": "男主，天资卓绝，性格坚韧。",
      "appearance": "青年男性，五官清俊，气质沉稳。",
      "style_tags": ["古装", "仙侠"],
      "source_file_url": "https://example.com/images/ye-xiaoyao.png",
      "metadata": {
        "source": "external_json"
      }
    }
  ]
}
```

更完整的字段说明见 `docs/json_asset_ingest_api.md`。

### 资产语义检索

```text
POST /api/v1/asset-search/semantic
```

请求体：

```json
{
  "query": "老奸巨猾的某市龙头",
  "limit": 5
}
```

返回结果会包含：

- `score`：向量相似度分数
- `source_table`：`asset_entities` 或 `asset_variants`
- `source_id`：结构数据库中的主键 ID
- `asset_kind`：资产类型，如 `character` / `scene`
- `name` / `display_name`
- `source_file_url`：主图 URL，前端可直接用 `<img src="...">` 展示
- `metadata`
- `vector_text`：生成向量时使用的文本，便于调试

## 本地脚本

测试 Excel 解析：

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_excel_asset_parser.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx"
```

测试单条结构数据同步到 Milvus：

```powershell
D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_asset_vector_sync.py
```

指定某个 `asset_entity_id`：

```powershell
D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_asset_vector_sync.py "asset_entity_id"
```

按指定工作表批量入库：

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\ingest_excel_sheet_assets.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" "天尊" "人设表" --batch-size 5
```

测试分镜解析：

```powershell
D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_storyboard_parser_smoke.py
```

## 数据表关系

```text
asset_source_projects
  -> asset_entities.source_project_id

asset_entities
  -> asset_media.asset_entity_id
  -> asset_variants.asset_entity_id

asset_variants
  -> asset_media.asset_variant_id

Milvus metadata
  -> source_table
  -> source_id
```

结构库是资产真实数据源，Milvus 是语义检索索引。检索命中后，通过 `metadata.source_table` 和 `metadata.source_id` 回 PostgreSQL 查询完整资产。

## 当前注意事项

- Excel 会先保存到 `runtime/uploads`，用于后续 openpyxl 解析和图片抽取；该目录已被 `.gitignore` 忽略。
- 语义检索目前是混合检索，不做强制类型过滤。
- 如果旧数据存在乱码或早期错误向量，建议清空 Milvus collection 后重新同步。
- `asset_media` 当前未做严格防重复，重复入库时可能产生重复媒体记录，后续可按 `sha256` 或 `storage_path` 做去重。
- TOS 图片 URL 如果 bucket 非公开读，需要后续改为签名 URL。
