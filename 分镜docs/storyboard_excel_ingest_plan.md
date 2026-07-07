# 分镜 Excel 统一入库 Plan

## 架构概览

本次改造保持现有入库入口不变，在 `POST /api/v1/asset-ingest/excel/upload` 内部增加“统一 Excel 编排层”。上传文件保存后，编排层负责同时调度资产入库与分镜入库。

资产入库继续复用现有链路：Excel 解析、LLM 字段抽取、图片上传、结构化入库、资产向量同步。分镜入库新增独立链路：分镜 sheet 识别、分镜行解析、写入 `common.project_director_storyboard_prompts`、同步到分镜向量库。

向量库拆成两个 collection：

- `asset_entity_vectors`：继续用于人物、场景、变体等资产检索。
- `project_storyboard_vectors`：新增，用于分镜语义检索和后续按分镜匹配资产。

## 核心数据结构

### StoryboardExcelRow

用于表示 Excel 中解析出的单条分镜行。

| 字段 | 类型 | 说明 |
|---|---|---|
| `sheet_name` | string | 原始 sheet 名 |
| `row_number` | integer | 原始 Excel 行号 |
| `episode` | string/null | 集数 |
| `shot_no` | string/null | 镜号 |
| `screen_description` | string/null | 画面描述 |
| `camera_motion` | string/null | 镜头运动 |
| `shot_size_angle` | string/null | 景别与视角 |
| `dialogue` | string/null | 台词 |
| `scene` | string/null | 场景 |
| `sound_effect` | string/null | 音效 |
| `reference_image_note` | string/null | 参考画面、分镜图、静态帧等文本信息 |
| `raw_fields` | object | 原始 Excel 字段 |

### StoryboardIngestResult

用于表示分镜入库结果。

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 分镜入库数量 |
| `items` | array | 已入库分镜摘要 |
| `vector_count` | integer | 分镜向量同步数量 |

### ExcelIngestResponse

现有响应结构需要向后兼容，并补充统一入库统计。

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 兼容旧字段，仍表示资产入库数量 |
| `items` | array | 兼容旧字段，仍表示资产入库明细 |
| `uploaded_file_path` | string | 上传文件临时路径 |
| `uploaded_file_deleted` | boolean | 源 Excel 是否已删除 |
| `asset_count` | integer | 资产入库数量 |
| `storyboard_count` | integer | 分镜入库数量 |
| `total_count` | integer | 资产 + 分镜总数量 |
| `storyboard_items` | array | 分镜入库明细摘要 |

## 模块设计

### ExcelUnifiedIngestService

**职责：** 统一编排一份 Excel 中的资产入库和分镜入库。

**对外接口：**

- 接收 Excel 路径、项目名、批处理大小。
- 返回资产入库结果、分镜入库结果和总统计。

**依赖：**

- `AssetEntityIngestService`
- `StoryboardIngestService`

### StoryboardExcelParser

**职责：** 从 Excel 中识别分镜 sheet，并解析为标准分镜行。

**识别规则：**

- sheet 名包含“分镜”时优先识别为分镜表。
- 表头包含 `镜号`、`画面描述`、`台词`、`场景` 中的多个字段时，也识别为分镜表。
- `集数` 允许为空，解析时继承上一条非空集数。

**字段兼容：**

- `镜头运动` 和 `景别&视角` 都进入分镜语义文本。
- `分镜图`、`参考画面`、`静态帧1`、`静态帧3` 第一版先作为文本/元数据记录，不做视觉理解。

### StoryboardFieldMapper

**职责：** 将不同分镜 Excel 表头规范化为统一字段，避免把字段兼容逻辑塞进入库 service。

**处理内容：**

- 将 `画面描述`、`镜头画面` 等同义字段统一为 `screen_description`。
- 将 `镜头运动` 统一为 `camera_motion`。
- 将 `景别&视角`、`景别视角`、`景别` 等统一为 `shot_size_angle`。
- 将 `分镜图`、`参考画面`、`静态帧1`、`静态帧3` 汇总为 `reference_image_note`。
- 保留 `raw_fields`，避免原始 Excel 信息丢失。

### StoryboardRecordBuilder

**职责：** 将标准化后的 `StoryboardExcelRow` 转换成可写入 `common.project_director_storyboard_prompts` 的结构化数据。

**处理内容：**

- 组装项目、集数、镜号、画面描述、台词、场景、音效等结构化字段。
- 将 `画面描述` 写入 `shot_description`。
- 将 `镜头运动` 和 `景别&视角` 合并写入 `camera_movement`。如果两个字段同时存在，用分号拼接。
- 将 `台词` 写入 `director_prompt_text`。
- 将 `场景` 写入 `scene_name`。
- 将 `音效` 写入 `sound_effect`。
- 只把原始 sheet 名、Excel 行号、原始字段等追溯信息写入 `metadata`。

### ProjectDirectorStoryboardPrompt

**职责：** 映射 `common.project_director_storyboard_prompts` 表。

第一版以数据库已有字段为准进行映射。已确认的核心落库规则：

| Excel 字段 | 数据库字段 | 说明 |
|---|---|---|
| 项目名 | `project_name` | 同时写入对应项目 ID |
| 集数 | `episode_no` | 转成整数 |
| 镜号 | `shot_no` | 转成整数 |
| 场景 | `scene_name` | 直接写入 |
| 画面描述 | `shot_description` | 分镜核心文本 |
| 镜头运动 | `camera_movement` | 与景别视角合并 |
| 景别&视角 | `camera_movement` | 与镜头运动用分号拼接 |
| 台词 | `director_prompt_text` | 直接写入台词文本 |
| 音效 | `sound_effect` | 直接写入 |
| 分镜图/参考画面 | `reference_file_url` / `storyboard_file_url` | 第一版先写 URL 或文本来源 |
| sheet 名、行号、原始字段 | `metadata` | 只用于追溯 |

### ProjectDirectorStoryboardPromptRepository

**职责：** 负责分镜记录的写入和更新。

**写入策略：**

- 同一项目、同一集数、同一镜号视为同一条分镜。
- 如果已存在，则更新该分镜内容。
- 如果不存在，则新增分镜。

### StoryboardVectorSyncService

**职责：** 将分镜记录同步到独立向量库。

**向量 collection：**

```text
project_storyboard_vectors
```

**向量文本：**

```text
项目：{项目名}
集数：{集数}
镜号：{镜号}
画面描述：{画面描述}
景别视角：{景别与视角}
镜头运动：{镜头运动}
台词：{台词}
场景：{场景}
音效：{音效}
参考画面：{参考画面说明}
```

**metadata：**

```json
{
  "source_table": "project_director_storyboard_prompts",
  "source_id": "分镜记录ID",
  "source_project_id": "项目ID",
  "source_project_name": "项目名",
  "episode": "集数",
  "shot_no": "镜号",
  "sheet_name": "原始sheet名",
  "row_number": 12
}
```

### StoryboardVectorTextBuilder

**职责：** 单独负责分镜向量文本拼接，避免向量同步 service 内部堆业务字段规则。

**输出内容：**

- 项目
- 集数
- 镜号
- 画面描述
- 景别视角
- 镜头运动
- 台词
- 场景
- 音效
- 参考画面说明

### MilvusVectorStore

**职责：** 继续作为通用 Milvus 写入/检索底层能力。

**改造点：**

- 支持传入 collection 名称。
- 默认仍使用资产 collection，避免影响现有资产检索。
- 新增分镜同步服务时传入 `project_storyboard_vectors`。

## 模块交互

```text
API: /api/v1/asset-ingest/excel/upload
  ↓
保存上传 Excel 到 runtime/uploads
  ↓
ExcelUnifiedIngestService
  ├─ AssetEntityIngestService
  │   ├─ ExcelAssetParser
  │   ├─ LLMExcelAssetExtractor
  │   ├─ AssetEntityRepository
  │   ├─ AssetMediaRepository
  │   └─ AssetVectorSyncService -> asset_entity_vectors
  │
  └─ StoryboardIngestService
      ├─ StoryboardExcelParser
      ├─ StoryboardFieldMapper
      ├─ StoryboardRecordBuilder
      ├─ ProjectDirectorStoryboardPromptRepository
      └─ StoryboardVectorSyncService
          ├─ StoryboardVectorTextBuilder
          └─ MilvusVectorStore -> project_storyboard_vectors
  ↓
删除上传 Excel
  ↓
返回统一入库响应
```

## 文件组织

```text
app/
├── api/v1/endpoints/
│   └── asset_ingest_endpoint.py              # 保持接口路径，改为调用统一入库编排
├── core/
│   └── config.py                             # 增加分镜向量 collection 配置
├── models/
│   ├── __init__.py
│   └── project_director_storyboard_prompt_model.py
├── repositories/
│   └── project_director_storyboard_prompt_repository.py
├── schemas/
│   └── asset_ingest.py                       # 扩展入库响应字段
├── services/
│   ├── excel_unified_ingest_service.py
│   ├── storyboard_excel_parser.py
│   ├── storyboard_field_mapper.py
│   ├── storyboard_record_builder.py
│   ├── storyboard_ingest_service.py
│   └── vector/
│       ├── milvus_vector_store.py            # 支持指定 collection
│       ├── storyboard_vector_text_builder.py
│       └── storyboard_vector_sync_service.py
└── ...
```

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 入库接口 | 继续使用现有 `/api/v1/asset-ingest/excel/upload` | 对接方只需要调一个接口，符合实际“一份 Excel 全量入库”的业务方式 |
| 分镜结构化表 | 写入 `common.project_director_storyboard_prompts` | 复用现有项目协同表，方便后续关联审核、生成和项目流程 |
| 分镜向量库 | 新建 `project_storyboard_vectors` | 避免污染资产检索结果，分镜检索和资产检索职责分离 |
| sheet 识别 | sheet 名 + 表头字段双规则 | 兼容“分镜1-10”“分镜11-19”等不同命名方式 |
| 集数继承 | 空集数继承上一条非空集数 | 符合现有分镜 Excel 的填写习惯 |
| 图片理解 | 第一版不做视觉模型理解 | 先打通入库和文本向量闭环，降低复杂度 |
| 写入策略 | 同项目 + 集数 + 镜号更新，否则新增 | 支持重复上传修正同一份 Excel |
