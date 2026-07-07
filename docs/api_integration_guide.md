# 短剧资产智能体接口对接文档

本文档用于说明短剧资产智能体当前已开放的入库与检索接口。

## 基础信息

### 服务地址

```text
http://124.174.8.150:8000
```

如果后续绑定正式域名，只需要把上述服务地址替换成正式域名即可。

### 接口前缀

```text
/api/v1
```

### 当前接口清单

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 健康检查 | GET | `/api/v1/health` | 检查服务是否正常 |
| 资产入库 | POST | `/api/v1/asset-ingest/excel/upload` | 上传 Excel 并自动解析入库 |
| 语义检索 | POST | `/api/v1/asset-search/semantic` | 根据自然语言检索资产 |

## 1. 健康检查

### 接口说明

用于判断后端服务是否正常运行。

### 请求方式

```text
GET /api/v1/health
```

### 请求示例

```bash
curl "http://124.174.8.150:8000/api/v1/health"
```

### 成功响应示例

```json
{
  "status": "ok",
  "app_name": "Shortdrama Agent",
  "version": "0.1.0"
}
```

## 2. Excel 资产入库接口

### 接口说明

用于上传短剧资产 Excel 表。服务端会解析 Excel 内容，并完成资产入库、向量化写入等处理。

当前适用于资产、人设、场景等资产表入库。分镜入库后续会单独扩展接口或在现有入库流程中增加分镜解析能力。

### 请求方式

```text
POST /api/v1/asset-ingest/excel/upload
```

### Content-Type

```text
multipart/form-data
```

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `file` | file | 是 | - | 需要上传的 Excel 文件，支持 `.xlsx`、`.xlsm` |
| `source_project_name` | string | 否 | 文件名自动提取 | 项目名称，例如 `天尊`、`测试项目` |
| `batch_size` | integer | 否 | `5` | 批处理大小，范围 `1-20` |

### 请求示例

```bash
curl -X POST "http://124.174.8.150:8000/api/v1/asset-ingest/excel/upload" \
  -F "file=@test.xlsx" \
  -F "source_project_name=测试项目" \
  -F "batch_size=2"
```

### 成功响应示例

```json
{
  "count": 10,
  "items": [
    {
      "id": "示例资产ID",
      "name": "示例资产名"
    }
  ],
  "uploaded_file_path": "runtime/uploads/xxx/test.xlsx",
  "uploaded_file_deleted": true
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 本次成功解析/入库的资产数量 |
| `items` | array | 入库后的资产明细，具体字段会随解析出的资产类型变化 |
| `uploaded_file_path` | string | 本次上传文件的临时路径 |
| `uploaded_file_deleted` | boolean | 入库成功后是否已删除源 Excel 文件 |

### 常见错误

| HTTP 状态码 | 可能原因 | 处理方式 |
|---:|---|---|
| 400 | 未上传文件名 | 检查 `file` 字段是否正确传入 |
| 400 | 文件格式不支持 | 仅上传 `.xlsx` 或 `.xlsm` |
| 404 | 使用浏览器 GET 访问上传接口 | 该接口必须使用 POST + multipart/form-data |
| 500 | 数据库、Milvus 或向量化服务异常 | 查看服务端日志，并检查数据库/Milvus 网络连通性 |

## 3. 资产语义检索接口

### 接口说明

用于根据自然语言查询短剧资产。接口会将查询文本向量化，然后从向量库中召回相关资产，并返回资产基础信息与匹配分数。

### 请求方式

```text
POST /api/v1/asset-search/semantic
```

### Content-Type

```text
application/json
```

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `query` | string | 是 | - | 检索文本，不能为空 |
| `limit` | integer | 否 | `10` | 返回数量，范围 `1-50` |

### 请求示例

```bash
curl -X POST "http://124.174.8.150:8000/api/v1/asset-search/semantic" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"白衣仙尊，清冷，古风男性角色\",\"limit\":5}"
```

### 成功响应示例

```json
{
  "count": 2,
  "items": [
    {
      "score": 0.873,
      "source_table": "asset_entities",
      "source_id": "资产ID",
      "asset_kind": "character",
      "name": "角色名",
      "display_name": "展示名称",
      "parent_entity_id": null,
      "parent_entity_name": null,
      "intro": "角色简介",
      "appearance": "外观描述",
      "description": "资产描述",
      "usage_context": "使用场景",
      "visual_prompt": "视觉提示词",
      "source_file_url": "https://example.com/image.png",
      "metadata": {},
      "vector_text": "参与向量化的文本内容"
    }
  ]
}
```

### 响应字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 本次返回的检索结果数量 |
| `items` | array | 检索结果列表 |
| `items[].score` | number/null | 匹配分数，分数越高代表越相关 |
| `items[].source_table` | string | 来源数据表 |
| `items[].source_id` | string | 来源数据 ID |
| `items[].asset_kind` | string/null | 资产类型，例如角色、场景、道具等 |
| `items[].name` | string/null | 资产名称 |
| `items[].display_name` | string/null | 展示名称 |
| `items[].parent_entity_id` | string/null | 父级资产 ID |
| `items[].parent_entity_name` | string/null | 父级资产名称 |
| `items[].intro` | string/null | 简介 |
| `items[].appearance` | string/null | 外观描述 |
| `items[].description` | string/null | 详细描述 |
| `items[].usage_context` | string/null | 使用上下文 |
| `items[].visual_prompt` | string/null | 视觉生成提示词 |
| `items[].source_file_url` | string/null | 关联图片或文件地址 |
| `items[].metadata` | object | 扩展元数据 |
| `items[].vector_text` | string/null | 实际参与向量化/检索的文本 |

### 常见错误

| HTTP 状态码 | 可能原因 | 处理方式 |
|---:|---|---|
| 422 | `query` 为空或参数类型错误 | 检查 JSON 参数 |
| 422 | `limit` 超出范围 | `limit` 需要在 `1-50` 之间 |
| 500 | 向量库或模型服务异常 | 查看服务端日志，并检查 Milvus/模型服务连通性 |

## 4. 对接建议

### 入库流程

1. 对接方先调用健康检查接口确认服务可用。
2. 使用 `POST /api/v1/asset-ingest/excel/upload` 上传 Excel。
3. 根据响应中的 `count` 判断本次入库数量。
4. 如果返回 500，需要由服务端排查数据库、Milvus 或模型服务连通性。

### 检索流程

1. 对接方将自然语言检索词传入 `query`。
2. 根据业务场景设置 `limit`，建议先使用 `5-10`。
3. 根据返回的 `score` 和资产字段进行展示、引用或后续 Agent 编排。

### 当前限制

1. 当前接口暂未加入鉴权，对公网开放时建议后续增加 `X-API-Key` 或其他鉴权方式。
2. 当前入库接口主要面向资产 Excel，分镜入库需要后续补充。
3. 入库成功后会删除上传的 Excel 源文件，不长期保留源文件。
4. 图片语义理解与图片向量化可作为后续增强能力接入。

