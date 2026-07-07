# JSON 资产入库接口对接方案

本文档用于说明对接方通过 JSON 方式向短剧资产库写入资产数据的接口格式。

当前接口只处理“资产库”入库，不处理 Excel，不处理分镜入库。

## 1. 接口地址

服务器环境：

```http
POST http://124.174.8.150:8000/api/v1/asset-ingest/json/assets
Content-Type: application/json; charset=utf-8
```

## 2. 对接边界

本接口由对接方直接提交结构化 JSON，后端收到后会：

1. 写入 `common.asset_entities`。
2. 保存 `source_file_url` 作为资产主图地址。
3. 将资产文本字段同步到向量库 `asset_entity_vectors`。
4. 前端检索结果可根据 `source_file_url` 展示图片。

图片由对接方负责上传并提供在线地址，本系统第一版不下载图片、不转存 TOS。

## 3. 请求示例

```json
{
  "source_project_name": "天尊",
  "assets": [
    {
      "asset_kind": "character",
      "name": "叶逍遥",
      "display_name": "叶逍遥",
      "intro": "男主，天赋异禀，性格坚韧。",
      "appearance": "青年男性，五官清俊，气质沉稳。",
      "age_value": 22,
      "gender": "male",
      "height_cm": 180,
      "hair_description": "黑色长发，半束发。",
      "outfit_description": "白色古装长袍，银色腰封。",
      "category": "主要角色",
      "style_tags": ["古装", "仙侠", "男主"],
      "approved": true,
      "reuse_scope": "needs_review",
      "status": "pending_review",
      "source_file_url": "https://example.com/images/ye-xiaoyao.png",
      "metadata": {
        "source": "external_json",
        "provider": "third_party_asset_system",
        "original_asset_id": "external-character-001",
        "remark": "来自对接方资产系统"
      }
    },
    {
      "asset_kind": "scene",
      "name": "山中道台",
      "display_name": "山中道台",
      "intro": "位于深山中的修炼道台，云雾缭绕。",
      "appearance": "石质平台，周围有松树、山雾和远山。",
      "category": "外景",
      "style_tags": ["古风", "山林", "修炼场景"],
      "approved": true,
      "reuse_scope": "needs_review",
      "status": "pending_review",
      "source_file_url": "https://example.com/images/mountain-platform.png",
      "metadata": {
        "source": "external_json",
        "original_asset_id": "external-scene-001"
      }
    }
  ]
}
```

## 4. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| source_project_id | uuid | 否 | 项目 ID。可不传。若传入，必须是 `common.asset_source_projects` 中真实存在的 ID，否则会触发外键错误。 |
| source_project_name | string | 推荐 | 项目名称，例如 `天尊`。第一版建议优先传项目名，不强制传项目 ID。 |
| assets | array | 是 | 资产列表，支持批量提交。 |

## 5. assets 字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| asset_kind | string | 是 | 资产类型，例如 `character`、`scene`。 |
| name | string | 是 | 资产名称。后端按 `source_project_id + asset_kind + name` 做 upsert。 |
| display_name | string | 否 | 展示名。不传时后端默认使用 `name`。 |
| intro | string | 推荐 | 简介。人物简介、场景简介、道具说明等。会参与向量化。 |
| appearance | string | 推荐 | 外观或画面描述。会参与向量化。 |
| age_value | integer | 否 | 年龄，主要用于人物。 |
| gender | string | 否 | 性别，主要用于人物。 |
| height_cm | integer | 否 | 身高，单位 cm，主要用于人物。 |
| hair_description | string | 否 | 发型、发色描述，主要用于人物。 |
| outfit_description | string | 否 | 服装描述，主要用于人物。 |
| category | string | 推荐 | 资产分类，例如 `主要角色`、`外景`、`道具`。会参与向量化。 |
| style_tags | array[string] | 推荐 | 风格标签，例如 `["古装", "仙侠"]`。会参与向量化。 |
| approved | boolean | 否 | 是否已审核。 |
| reuse_scope | string | 否 | 复用范围。当前建议传 `needs_review`。 |
| status | string | 否 | 状态。当前建议传 `pending_review`。 |
| source_file_url | string | 否 | 资产主图或参考图在线地址。由对接方提供，本系统直接保存，不转存。 |
| metadata | object | 否 | 扩展信息，用于保存来源系统、原始资产 ID、备注等。 |

## 6. 枚举说明

### asset_kind

| 值 | 说明 |
| --- | --- |
| character | 人物 |
| scene | 场景 |
| prop | 道具 |
| other | 其他 |

### gender

| 值 | 说明 |
| --- | --- |
| male | 男 |
| female | 女 |
| unknown | 未知 |

### status

| 值 | 说明 |
| --- | --- |
| pending_review | 待审核 |
| active | 可用 |
| disabled | 停用 |

### reuse_scope

当前系统中该字段用于标记复用/审核范围。第一版对接建议传：

```text
needs_review
```

如后续需要更严格枚举，可再统一约定。

## 7. 图片地址要求

`source_file_url` 由对接方提供。要求：

1. 必须是完整 URL，例如 `https://example.com/image.png`。
2. 必须长期有效。
3. 必须能被后端和浏览器直接访问。
4. 不应依赖登录态、临时 Cookie 或仅内网可访问地址。

如果 `source_file_url` 无法被浏览器访问，前端检索结果会显示图片加载失败。

## 8. 响应示例

```json
{
  "count": 2,
  "items": [
    {
      "id": "3b6f7f4e-8c2a-4f6b-ae83-2ddc6e6a1f11",
      "asset_kind": "character",
      "name": "叶逍遥"
    },
    {
      "id": "b5b7a25f-00d3-4db5-9f33-3c4f5b8b32a1",
      "asset_kind": "scene",
      "name": "山中道台"
    }
  ]
}
```

## 9. 向量化字段

接口入库成功后，后端会将以下字段拼接成文本并写入向量库：

```text
来源项目
资产类型
资产名称
展示名称
简介
外观描述
年龄
性别
身高厘米
发型或长相描述
服装描述
资产分类
风格标签
```

示例向量化文本：

```text
来源项目：天尊
资产类型：character
资产名称：叶逍遥
展示名称：叶逍遥
简介：男主，天赋异禀，性格坚韧。
外观描述：青年男性，五官清俊，气质沉稳。
资产分类：主要角色
风格标签：['古装', '仙侠', '男主']
```

## 10. PowerShell 测试方式

建议将请求体保存为 UTF-8 JSON 文件后再发送，避免 PowerShell 中文字符串编码导致中文变成问号。

服务器测试命令：

```powershell
curl.exe -X POST "http://124.174.8.150:8000/api/v1/asset-ingest/json/assets" `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-binary "@runtime/json_asset_test.json"
```

## 11. 注意事项

1. `assets` 不能为空。
2. 每条资产必须提供 `asset_kind` 和 `name`。
3. `source_project_id` 不建议第一版强制传；如果传，必须是数据库中已存在的项目 ID。
4. `source_file_url` 只保存对接方提供的在线地址，本系统不转存图片。
5. 同名资产会走 upsert 逻辑，可能更新已有记录，不一定新增一条。
6. 入库成功后会同步向量库，供后续 RAG 检索使用。

