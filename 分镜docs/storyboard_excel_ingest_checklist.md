# 分镜 Excel 统一入库 Checklist

> 每一项都需要通过运行代码、查看响应、查询数据库或查看向量库来验证。

## 实现完整性

- [ ] 配置中已支持分镜向量 collection。
  验证：应用启动后能读取 `MILVUS_COLLECTION_PROJECT_STORYBOARD`，默认值为 `project_storyboard_vectors`。

- [ ] 已新增 `common.project_director_storyboard_prompts` ORM 映射。
  验证：项目启动时模型可正常导入，不出现 SQLAlchemy 字段映射错误。

- [ ] 已新增分镜 repository。
  验证：同一项目、同一集数、同一镜号重复写入时更新同一条记录，不重复新增。

- [ ] 已新增分镜字段映射器。
  验证：不同表头写法能被规范化为统一字段，例如 `景别&视角` 先进入 `shot_size_angle`，后续落库时拼入 `camera_movement`。

- [ ] 已新增分镜 Excel 解析器。
  验证：包含 `分镜1-10`、`分镜11-19` 这类 sheet 的 Excel 能解析出分镜行。

- [ ] 分镜解析支持集数向下继承。
  验证：Excel 中某些行 `集数` 为空时，能继承上一条非空集数。

- [ ] 已新增分镜记录构建器。
  验证：标准分镜行能转换成 repository 可保存的数据结构，`台词` 写入 `director_prompt_text`，`景别&视角` 拼入 `camera_movement`，并保留 sheet 名、行号、原始字段。

- [ ] 已新增分镜向量文本构建器。
  验证：生成的向量文本包含项目、集数、镜号、画面描述、台词、场景等核心语义。

- [ ] 已新增分镜向量同步服务。
  验证：分镜入库后能向 `project_storyboard_vectors` 写入向量。

- [ ] 已新增统一 Excel 入库 service。
  验证：同一份 Excel 能同时触发资产入库和分镜入库。

## 接口行为

- [ ] 入库接口路径保持不变。
  验证：仍然使用 `POST /api/v1/asset-ingest/excel/upload`。

- [ ] 上传只包含资产的 Excel 时，原有资产入库能力不受影响。
  验证：响应中 `asset_count` 大于 0，`storyboard_count` 为 0。

- [ ] 上传只包含分镜的 Excel 时，可以只完成分镜入库。
  验证：响应中 `asset_count` 为 0，`storyboard_count` 大于 0。

- [ ] 上传同时包含人物、场景、分镜的 Excel 时，可以同时完成两类入库。
  验证：响应中 `asset_count` 和 `storyboard_count` 都大于 0。

- [ ] 接口响应保留旧字段。
  验证：响应仍包含 `count`、`items`、`uploaded_file_path`、`uploaded_file_deleted`。

- [ ] 接口响应新增统一统计字段。
  验证：响应包含 `asset_count`、`storyboard_count`、`total_count`、`storyboard_items`。

- [ ] 入库成功后删除上传源文件。
  验证：响应中 `uploaded_file_deleted` 为 `true`，运行目录下对应上传目录不存在。

## 数据库检查

- [ ] 分镜记录写入 `common.project_director_storyboard_prompts`。
  验证：上传分镜 Excel 后，数据库中能查到对应项目、集数、镜号的记录。

- [ ] 分镜记录保留原始来源信息。
  验证：数据库记录中能追溯原始 sheet 名、Excel 行号和原始字段。

- [ ] 重复上传同一份分镜 Excel 不产生重复分镜。
  验证：同项目、同集数、同镜号只保留一条有效记录。

## 向量库检查

- [ ] 资产向量仍写入 `asset_entity_vectors`。
  验证：资产入库后，资产检索仍能返回资产结果。

- [ ] 分镜向量写入 `project_storyboard_vectors`。
  验证：分镜入库后，向量库中能按分镜记录 ID 查到对应向量。

- [ ] 分镜向量不污染资产检索。
  验证：调用现有资产语义检索接口时，不返回分镜记录作为资产结果。

## 编译与启动

- [ ] 后端应用可以正常启动。
  验证：启动服务后访问 `/api/v1/health` 返回 `status = ok`。

- [ ] 现有资产检索接口仍可使用。
  验证：调用 `/api/v1/asset-search/semantic` 能正常返回资产检索结果。

- [ ] Docker 镜像可以重新构建。
  验证：运行 `docker build` 可以成功完成。

## 端到端场景

- [ ] 场景 1：上传只含资产的 Excel。
  验证：资产入库成功，分镜数量为 0，资产检索可用。

- [ ] 场景 2：上传只含分镜的 Excel。
  验证：分镜入库成功，分镜结构化表有记录，分镜向量库有记录。

- [ ] 场景 3：上传同时包含人物、场景、分镜的 Excel。
  验证：资产和分镜都入库成功，响应能分别看到资产数量和分镜数量。

- [ ] 场景 4：重复上传同一份 Excel。
  验证：同项目、同集数、同镜号的分镜被更新，不重复新增。

- [ ] 场景 5：Excel 中某些分镜行缺少集数。
  验证：系统能向下继承集数，并写入正确的集数信息。

## 文档检查

- [ ] 接口文档已更新。
  验证：`docs/api_integration_guide.md` 中说明同一份 Excel 支持资产 + 分镜统一入库。

- [ ] 对接方仍只需要调用一个入库接口。
  验证：文档中没有要求对接方新增单独的分镜上传接口。
