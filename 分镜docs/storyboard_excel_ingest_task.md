# 分镜 Excel 统一入库 Tasks

## 分层原则

本功能按“薄 service、厚组件”的方式拆分。`service` 层只做流程编排，不直接堆字段兼容、数据库字段组装、向量文本拼接等业务细节。

具体分层：

- `parser`：只负责读 Excel、识别分镜 sheet、处理合并单元格和集数继承。
- `field_mapper`：只负责把不同 Excel 表头映射成统一字段。
- `record_builder`：只负责把统一分镜行转换成数据库可写入数据。
- `repository`：只负责查库、写库、更新。
- `vector_text_builder`：只负责拼接分镜向量文本。
- `vector_sync_service`：只负责 embedding + 写入 Milvus。
- `ingest_service`：只负责调用上面这些组件完成入库流程。
- `unified_ingest_service`：只负责统一调度资产入库和分镜入库。

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `app/core/config.py` | 增加分镜向量 collection 配置 |
| 新建 | `app/models/project_director_storyboard_prompt_model.py` | 映射 `common.project_director_storyboard_prompts` |
| 修改 | `app/models/__init__.py` | 导出分镜 ORM 模型 |
| 新建 | `app/repositories/project_director_storyboard_prompt_repository.py` | 写入/更新分镜记录 |
| 新建 | `app/services/storyboard_field_mapper.py` | 将不同 Excel 表头规范化为统一分镜字段 |
| 新建 | `app/services/storyboard_excel_parser.py` | 识别并解析 Excel 分镜 sheet |
| 新建 | `app/services/storyboard_record_builder.py` | 将标准分镜行转换成数据库写入数据 |
| 修改 | `app/services/vector/milvus_vector_store.py` | 支持指定 collection 名称 |
| 新建 | `app/services/vector/storyboard_vector_text_builder.py` | 单独构建分镜向量文本 |
| 新建 | `app/services/vector/storyboard_vector_sync_service.py` | 将分镜文本向量化并写入分镜向量库 |
| 新建 | `app/services/storyboard_ingest_service.py` | 编排分镜解析、结构化入库、向量同步 |
| 新建 | `app/services/excel_unified_ingest_service.py` | 编排资产入库和分镜入库 |
| 修改 | `app/schemas/asset_ingest.py` | 扩展统一入库响应字段 |
| 修改 | `app/api/v1/endpoints/asset_ingest_endpoint.py` | 保持路径不变，改为调用统一入库 service |
| 修改 | `docs/api_integration_guide.md` | 更新接口文档，说明同一份 Excel 支持资产 + 分镜 |

## T1: 确认数据库字段

**文件：** 无代码文件

**依赖：** 无

**步骤：**

1. 查询 `common.project_director_storyboard_prompts` 的真实字段。
2. 确认哪些字段可直接承载项目、集数、镜号、画面描述、台词、场景、音效等信息。
3. 确认是否存在 `metadata`、`prompt`、`content`、`shot_id`、`project_id` 等可用字段。
4. 如果字段和预期不一致，先调整 plan 和 task。

**验证：** 拿到表字段清单，并能明确每个 Excel 分镜字段写到哪里。

## T2: 增加分镜向量配置

**文件：** `app/core/config.py`

**依赖：** T1

**步骤：**

1. 在 `Settings` 中增加分镜向量 collection 配置字段。
2. 从环境变量读取 `MILVUS_COLLECTION_PROJECT_STORYBOARD`。
3. 默认值设置为 `project_storyboard_vectors`。
4. 确认不影响现有 `MILVUS_COLLECTION_ASSET_ENTITY`。

**验证：** 应用启动时能读取资产向量 collection 和分镜向量 collection 两个配置。

## T3: 新增分镜 ORM 模型

**文件：** `app/models/project_director_storyboard_prompt_model.py`、`app/models/__init__.py`

**依赖：** T1

**步骤：**

1. 根据真实表字段创建 ORM 模型。
2. 设置 `__tablename__ = "project_director_storyboard_prompts"`。
3. 设置 schema 为 `common`。
4. 为项目、集数、镜号、提示词/画面描述、metadata、创建时间、更新时间等字段建立映射。
5. 在 `app/models/__init__.py` 中导出模型。

**验证：** 通过 SQLAlchemy 可以导入模型，且不会报字段映射错误。

## T4: 新增分镜 repository

**文件：** `app/repositories/project_director_storyboard_prompt_repository.py`

**依赖：** T3

**步骤：**

1. 创建 repository 类。
2. 增加按“项目 + 集数 + 镜号”查询已有分镜的方法。
3. 增加保存方法：存在则更新，不存在则新增。
4. 写入时保留原始 sheet 名、行号和原始字段。

**验证：** 调用 repository 能新增一条分镜，再次用同一项目、集数、镜号写入时能更新同一条记录。

## T5: 新增分镜字段映射器

**文件：** `app/services/storyboard_field_mapper.py`

**依赖：** 无

**步骤：**

1. 定义 `StoryboardExcelRow` 数据结构。
2. 定义字段别名映射规则。
3. 将 `集数`、`镜号`、`画面描述`、`镜头运动`、`景别&视角`、`台词`、`场景`、`音效` 等字段规范化。
4. 将 `分镜图`、`参考画面`、`静态帧1`、`静态帧3` 合并为 `reference_image_note`。
5. 保留 `raw_fields`。

**验证：** 传入不同表头写法的原始字段后，能得到统一的 `StoryboardExcelRow`。

## T6: 新增分镜 Excel 解析器

**文件：** `app/services/storyboard_excel_parser.py`

**依赖：** T5

**步骤：**

1. 使用 `openpyxl` 读取 Excel。
2. 通过 sheet 名和表头字段识别分镜表。
3. 处理合并单元格。
4. 对空 `集数` 执行向下继承。
5. 调用 `StoryboardFieldMapper` 生成标准分镜行。
6. 跳过没有镜号且没有画面描述的空行。

**验证：** 用样例 Excel 能解析出分镜行，并正确填充集数、镜号和画面描述。

## T7: 新增分镜记录构建器

**文件：** `app/services/storyboard_record_builder.py`

**依赖：** T1、T5

**步骤：**

1. 接收标准化后的 `StoryboardExcelRow`、项目 ID、项目名。
2. 根据真实表字段组装数据库写入 dict。
3. 将 `episode` 写入 `episode_no`，将 `shot_no` 写入 `shot_no`。
4. 将 `scene` 写入 `scene_name`，将 `screen_description` 写入 `shot_description`。
5. 将 `camera_motion` 和 `shot_size_angle` 合并写入 `camera_movement`。如果两个字段同时存在，用分号拼接。
6. 将 `dialogue` 写入 `director_prompt_text`，将 `sound_effect` 写入 `sound_effect`。
7. 将 sheet 名、行号、原始字段放入 `metadata`，只用于追溯。

**验证：** 传入一条标准分镜行后，能输出 repository 可直接保存的数据结构。

## T8: 改造 MilvusVectorStore 支持指定 collection

**文件：** `app/services/vector/milvus_vector_store.py`

**依赖：** T2

**步骤：**

1. `MilvusVectorStore` 初始化时支持传入 `collection_name`。
2. 如果未传入，则继续使用资产向量 collection。
3. `ensure_collection`、`upsert`、`search` 继续使用当前实例的 collection。
4. 保持原有资产向量写入和检索行为不变。

**验证：** 资产向量服务不传 collection 仍写入 `asset_entity_vectors`；分镜向量服务传入 collection 后写入 `project_storyboard_vectors`。

## T9: 新增分镜向量文本构建器

**文件：** `app/services/vector/storyboard_vector_text_builder.py`

**依赖：** T3

**步骤：**

1. 创建分镜向量文本构建函数。
2. 拼接项目、集数、镜号、画面描述、景别视角、镜头运动、台词、场景、音效、参考画面说明。
3. 空字段不参与拼接。
4. 输出稳定、可读的多行文本。

**验证：** 传入一条分镜记录后，能输出包含核心语义字段的向量文本。

## T10: 新增分镜向量同步服务

**文件：** `app/services/vector/storyboard_vector_sync_service.py`

**依赖：** T2、T3、T8、T9

**步骤：**

1. 调用 `StoryboardVectorTextBuilder` 构建向量文本。
2. 使用现有 `DoubaoEmbeddingService` 生成向量。
3. 使用 `MilvusVectorStore(collection_name=settings.milvus_collection_project_storyboard)` 写入。
4. metadata 中记录来源表、来源 ID、项目 ID、项目名、集数、镜号、sheet 名和行号。

**验证：** 传入一条分镜记录后，能向 `project_storyboard_vectors` 写入一条向量。

## T11: 新增分镜入库 service

**文件：** `app/services/storyboard_ingest_service.py`

**依赖：** T4、T6、T7、T10

**步骤：**

1. 接收 Excel 路径、项目名、批处理大小。
2. 获取或创建 `asset_source_projects` 项目记录。
3. 使用 `StoryboardExcelParser` 解析分镜行。
4. 使用 `StoryboardRecordBuilder` 生成数据库写入数据。
5. 调用 repository 写入或更新分镜记录。
6. 每条成功写入后同步分镜向量。
7. 返回分镜入库数量、向量数量和摘要列表。

**验证：** 上传只包含分镜的 Excel 时，能写入结构化表并同步向量。

## T12: 新增统一 Excel 入库 service

**文件：** `app/services/excel_unified_ingest_service.py`

**依赖：** T11

**步骤：**

1. 接收 Excel 路径、项目名、批处理大小。
2. 调用现有 `AssetEntityIngestService` 入库资产。
3. 调用新增 `StoryboardIngestService` 入库分镜。
4. 如果某一类数据不存在，不视为失败。
5. 汇总资产结果、分镜结果、总数量。
6. 对确实异常的失败保留清晰错误信息。

**验证：** 同一份 Excel 中既有资产又有分镜时，能分别得到资产数量和分镜数量。

## T13: 扩展接口响应 schema

**文件：** `app/schemas/asset_ingest.py`

**依赖：** T12

**步骤：**

1. 保留 `count`、`items`、`uploaded_file_path`、`uploaded_file_deleted`。
2. 新增 `asset_count`、`storyboard_count`、`total_count`。
3. 新增 `storyboard_items`。
4. 新增可选错误摘要字段，用于定位资产或分镜入库失败原因。

**验证：** 老调用方仍能读取 `count` 和 `items`；新调用方能读取分镜数量。

## T14: 接入现有上传 endpoint

**文件：** `app/api/v1/endpoints/asset_ingest_endpoint.py`

**依赖：** T12、T13

**步骤：**

1. 保持接口路径不变。
2. 保存上传 Excel 的逻辑保持不变。
3. 将 service 从 `AssetEntityIngestService` 替换为 `ExcelUnifiedIngestService`。
4. 响应中返回资产数量、分镜数量、总数量。
5. 入库成功后继续删除上传目录。

**验证：** `POST /api/v1/asset-ingest/excel/upload` 仍可调用，响应包含新增统计字段。

## T15: 更新接口文档

**文件：** `docs/api_integration_guide.md`

**依赖：** T13、T14

**步骤：**

1. 将入库接口说明从“资产 Excel 入库”更新为“统一 Excel 入库”。
2. 说明同一份 Excel 可包含人物、场景、分镜。
3. 补充响应中的 `asset_count`、`storyboard_count`、`total_count`、`storyboard_items`。
4. 补充分镜向量库说明。

**验证：** 对接方阅读文档后能知道仍然只调用一个上传接口。

## 执行顺序

```text
T1
├─ T2
├─ T3 → T4
├─ T5 → T6
└─ T8

T1 + T5 → T7
T2 + T3 + T8 → T9 → T10
T4 + T6 + T7 + T10 → T11
T11 → T12 → T13 → T14 → T15
```
