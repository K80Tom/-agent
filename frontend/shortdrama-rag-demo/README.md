# Shortdrama Frontend

这是一个零依赖静态前端，直接接入当前后端的两个接口：

- `POST /api/v1/asset-ingest/excel/upload`
- `POST /api/v1/asset-search/semantic`

## 使用

直接用浏览器打开 `index.html`。

默认后端地址是：

```text
http://127.0.0.1:8000
```

页面左下角可以修改后端地址。检索结果会优先展示 `source_file_url`，也会尝试从 `metadata.primary_image.storage_url`、`metadata.images` 等字段里识别图片 URL。
