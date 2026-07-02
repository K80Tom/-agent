# 短剧资产入库与向量化上下文交接

## 目标

当前项目要做一条“文件资产入库”链路，主要处理 Excel 和图片：

1. 上传或指定一个 Excel 文件。
2. 把这个文件登记到 `common.asset_source_projects`。
3. 解析 Excel 每一行资产文字和图片。
4. 用模型把每一行文字字段提取成 `common.asset_entities` 字段。
5. 把每一行图片上传到火山云 TOS。
6. 主图 URL 回填到 `asset_entities.source_file_url`。
7. 所有图片逐张写入 `common.asset_media`，通过 `asset_entity_id` 关联资产主体。
8. 后续再处理 `asset_variants`：普通版入 `asset_entities`，心魔版、天尊版、升级版等放到 `asset_variants`，图片通过 `asset_variant_id` 关联。
9. 后续还要把结构化资产转 embedding，写入 Milvus 向量库。

当前优先级：先把 Excel -> `asset_source_projects` -> `asset_entities` -> TOS -> `asset_media` 跑通。暂时不做 `asset_variants` 和正式 MCP/API 包装。

## 数据库表理解

### asset_source_projects

表示一个来源文件或来源项目。

当前设计：

- `id`：UUID，代码侧用 `uuid4` 自动生成。
- `name`：来源文件主体名，例如 `《天尊》人设和场景表`。
- `code`：来源文件编码，例如 `file_xxxxxxxxxxxx`。
- `description`：原始文件名，例如 `《天尊》人设和场景表.xlsx`。
- `metadata`：文件来源信息，例如 `source_file_path`。
- `created_at / updated_at`：代码侧写入北京时间。
- `project_type`：暂时不处理，可后续人工传入，如 `现代/仙侠`。

### asset_entities

表示资产主体，比如一个角色或一个场景。

主要字段：

- `source_project_id`：关联 `asset_source_projects.id`。
- `source_project_name`：来源文件/项目名。
- `asset_kind`：`character` 或 `scene` 等。
- `name`：资产名称。
- `display_name`：展示名。
- `intro`：身份、性格、背景、经历、关系、动机、结局等介绍信息。
- `appearance`：整体外观、长相、面部特征、体态和气质。
- `age_value / gender / height_cm`：年龄、性别、身高。
- `hair_description`：发型，不重复写进 `appearance`。
- `outfit_description`：服装，不重复写进 `appearance`。
- `category`：角色/场景等。
- `style_tags`：标签。
- `approved`：来自 Excel 的“是否通过”。
- `source_file_url`：主图 URL，只放一张代表图。
- `metadata`：原始行号、图片信息、主图信息等。

### asset_media

表示媒体图片。每张图片单独一行。

主要字段：

- `asset_entity_id`：关联 `asset_entities.id`。
- `asset_variant_id`：暂时为 `null`，后续变体图片使用。
- `media_kind`：图片类型。
- `title / description`：图片标题和说明。
- `storage_bucket / storage_path / storage_url`：TOS 信息。
- `width_px / height_px / format / sha256`：图片基础信息。
- `is_primary`：是否主图。
- `approved`：继承 Excel 行的“是否通过”。
- `sort_order`：图片排序。
- `metadata`：Excel sheet、行号、列号、列名、image_index 等。

### asset_variants

表示资产变体，后续再做。

例如：

- `叶逍遥` 入 `asset_entities`。
- `天尊版叶逍遥` 入 `asset_variants`，关联 `叶逍遥.id`。
- `心魔叶婷` 入 `asset_variants`，关联 `叶婷.id`。
- 变体图片写入 `asset_media`，同时填 `asset_entity_id` 和 `asset_variant_id`。

当前只补了最小 ORM model，让 `asset_media.asset_variant_id` 外键能被 SQLAlchemy 识别。

## 当前代码分层

项目希望采用清晰分层：

- `endpoint`：HTTP 路由，不写业务逻辑。
- `service`：业务编排，不直接写 SQL。
- `repository`：数据库访问。
- `db`：数据库连接、Session、Base。
- `model`：SQLAlchemy ORM。
- `schema`：Pydantic 入参出参。
- `core/config`：配置。

目前主要相关文件：

```text
app/core/config.py
app/db/base.py
app/db/session.py

app/models/asset_entity_model.py
app/models/asset_source_project_model.py
app/models/asset_media_model.py
app/models/asset_variant_model.py

app/repositories/asset_entity_repository.py
app/repositories/asset_source_project_repository.py
app/repositories/asset_media_repository.py

app/services/asset_entity_ingest_service.py
app/services/excel_asset_parser.py
app/services/excel_image_extractor.py
app/services/excel_image_upload_service.py
app/services/llm_excel_asset_extractor.py
app/services/asset_media_mapping.py
app/prompts/excel_asset_extraction_prompt.py

scripts/ingest_excel_sheet_assets.py
scripts/test_excel_asset_parser.py
scripts/test_llm_excel_asset_extractor.py
scripts/test_excel_row_images_upload.py
scripts/test_excel_row_images_to_asset_media.py
scripts/test_asset_media_insert.py
```

## 已经跑通的链路

### 1. Excel 原始解析

`ExcelAssetParser` 可以把 Excel 行解析成：

```text
ExcelAssetRow.fields
ExcelAssetRow.images
```

其中 `fields` 包含：

- 姓名/场景名
- 简介
- 形象参考
- 外观
- 是否通过
- 首次出现集数
- 其他 Excel 表头字段

`images` 包含：

- `sheet_name`
- `image_index`
- `row`
- `col`
- `column_header`
- `format`
- `width`
- `height`

注意：Excel 解析阶段不直接生成数据库字段，只保留原始结构。

### 2. 模型提取 asset_entities 字段

`LLMExcelAssetExtractor` 读取 Excel 行的 `fields`，调用火山方舟 LLM，把原始字段提取为 `asset_entities` 字段。

模型目标字段：

```text
source_project_id
source_project_name
asset_kind
name
display_name
intro
appearance
age_value
gender
height_cm
hair_description
outfit_description
category
style_tags
approved
reuse_scope
status
source_file_url
metadata
```

提示词要求：

- `age_value / gender / height_cm` 必须单独提取，不写进 `intro`。
- `intro` 写身份、性格、背景、经历、关系、动机、结局等。
- `appearance` 写整体外观、长相、面部特征、体态、气质。
- `hair_description` 只写发型，头发颜色和发型不要重复进 `appearance`。
- `outfit_description` 只写服装。
- `权重分级` 不写入。
- 不做过多兜底，不强行补字段。

### 3. 文件登记到 asset_source_projects

`AssetEntityIngestService.ingest_sheet_excel_path()` 里会根据 `excel_path` 生成来源项：

```python
source_file = Path(excel_path)
source_project_name = source_file.stem
source_file_name = source_file.name
source_project_code = "file_" + hashlib.md5(str(source_file).encode("utf-8")).hexdigest()[:12]
```

然后调用：

```python
source_project_repository.get_or_create(
    name=source_project_name,
    code=source_project_code,
    description=source_file_name,
    metadata={
        "source_file_path": str(source_file),
    },
)
```

### 4. asset_entities 入库

`AssetEntityRepository.save(...)` 已经支持按唯一键保存。

唯一键：

```text
source_project_id + asset_kind + name
```

重复测试时可以更新已有记录，而不是每次都插入新行。

### 5. Excel 图片上传 TOS

`ExcelImageUploadService.upload_row_images(...)` 已经可以上传某一行全部图片。

返回结果包括：

- `storage_bucket`
- `storage_path`
- `storage_url`
- `sha256`
- `is_primary`
- `sort_order`
- 原始 `image_info`

主图选择逻辑：

1. 优先表头包含 `人设图` 和 `定稿`。
2. 其次表头包含 `定稿`。
3. 最后取该行第一张图片。

### 6. 上传图片写入 asset_media

`AssetMediaRepository.create(...)` 已经可写入 `asset_media`。

`asset_media_mapping.py` 负责把上传图片信息映射成 repository 参数。

当前媒体类型规则：

```text
character + 人设图/定稿 -> character_final
character + 三视图/多视图 -> character_turnaround
character + 服饰/服装 -> costume_reference

scene + 定稿 -> scene_final
scene + 多视图/三视图 -> scene_multi_view
scene + 参考 -> scene_reference

其他 -> other
```

排序规则：

```text
主图/定稿：100 段
三视图/多视图：200 段
服饰参考：300 段
场景参考图：400 段
其他：900 段
```

`approved` 来自 Excel 的 `是否通过`。

测试脚本 `scripts/test_excel_row_images_to_asset_media.py` 已跑通。

## 常用测试命令

### 看 Excel 原始解析

当前 `test_excel_asset_parser.py` 原本只支持 `excel_path` 和 `limit`。如果已升级参数，则可用 `--sheet-name`。

旧版命令：

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_excel_asset_parser.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" 10
```

### 看单行模型提取结果

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_llm_excel_asset_extractor.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" "00000000-0000-0000-0000-000000000001" "天尊" "人设表" 4
```

### 测试某一行全部图片上传

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_excel_row_images_upload.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" "人设表" 4 "叶婷"
```

### 测试某一行图片写入 asset_media

先查 `asset_entities.id`：

```sql
SELECT id, name, asset_kind
FROM common.asset_entities
WHERE name = '叶婷'
ORDER BY updated_at DESC;
```

再执行：

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\test_excel_row_images_to_asset_media.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" "人设表" 4 "这里换成叶婷的asset_entities_id" "character" "叶婷"
```

### 正式批量入库某个 sheet

```powershell
$env:PYTHONIOENCODING="utf-8"; D:\Anaconda3\envs\shortdrama-agent\python.exe scripts\ingest_excel_sheet_assets.py "C:\Users\Firebat\Desktop\《天尊》人设和场景表.xlsx" "天尊" "场景表" --batch-size 5
```

当前这个正式流程已经能写 `asset_source_projects` 和 `asset_entities`，但还没有完全接入 `asset_media` 批量写入。

## 当前下一步

下一步要把图片写入 `asset_media` 接进正式批量流程。

目标文件：

```text
app/services/asset_entity_ingest_service.py
```

当前循环大概是：

```python
for row, asset_data in zip(batch_rows, assets):
    self._upload_primary_image_if_present(...)
    entity = self.asset_entity_repository.save(asset_data)
    results.append(...)
```

要改成：

```text
1. 上传这一行全部图片 upload_row_images
2. 找 primary_image，回填 asset_data["source_file_url"]
3. 保存 asset_entity
4. 遍历 uploaded_images，写入 asset_media
```

伪代码：

```python
uploaded_images = self.image_upload_service.upload_row_images(
    excel_path=excel_path,
    row=row,
    source_project_name=actual_project_name,
    asset_name=asset_data["name"],
)

primary_image = next((image for image in uploaded_images if image.get("is_primary")), None)
if primary_image:
    asset_data["source_file_url"] = primary_image["storage_url"]
    asset_data.setdefault("metadata", {})["primary_image"] = primary_image

entity = self.asset_entity_repository.save(asset_data)

for uploaded_image in uploaded_images:
    media_data = build_asset_media_data(
        asset_entity_id=entity.id,
        uploaded_image=uploaded_image,
        asset_kind=asset_data["asset_kind"],
        asset_name=asset_data["name"],
        approved=asset_data.get("approved"),
    )
    self.asset_media_repository.create(**media_data)
```

需要新增：

```python
from app.repositories.asset_media_repository import AssetMediaRepository
from app.services.asset_media_mapping import build_asset_media_data
```

`__init__` 增加：

```python
self.asset_media_repository = AssetMediaRepository(db)
self.image_upload_service = ExcelImageUploadService()
```

旧的 `_upload_primary_image_if_present()` 可以先保留，确认新流程跑通后再删除。

## 后续待做

### 1. 处理 asset_variants

普通版入 `asset_entities`，心魔版、天尊版、升级版入 `asset_variants`。

难点：

- 同一个 Excel sheet 中普通版和变体版混在一起。
- 需要判断 `心魔叶婷` 应该挂到 `叶婷`。
- 需要判断 `天尊版叶逍遥` 应该挂到 `叶逍遥`。

建议后续让模型输出：

```text
row_type: entity | variant
parent_name
variant_name
variant_kind
```

再根据 `parent_name` 查找或创建主体。

### 2. 写入向量库

已有方向：

- `asset_entities` 结构化字段转 embedding text。
- 使用 Doubao embedding vision 的 multimodal embedding 接口。
- Milvus collection 已经建过，向量维度为 2048。
- 后续要把新入库的资产同步写入 Milvus。

### 3. 包装成接口或 MCP

团队说“包成一个 MCP 或接口给它”，意思是：

- 如果给普通后端/前端调用，用 HTTP API。
- 如果给智能体调用，建议做 MCP tool。

短剧智能体场景更适合 MCP：

```text
tool: ingest_excel_assets
input: file_path / file_url / sheet_name / batch_size
output: source_project_id / inserted_entities / inserted_media
```

但在包装前，要先把入库链路稳定跑通。

