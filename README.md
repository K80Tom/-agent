# 短剧制作智能体 RAG 项目

这是一个从 0 开始搭建的短剧制作智能体知识底座项目。

当前阶段只完成 FastAPI 分层骨架和 domain 层基础定义。

## 当前目录

```text
app/
  main.py
  api/
  schemas/
  services/
  domain/
  infrastructure/
  config/

docs/
scripts/
tests/
```

## 当前可运行接口

```text
GET /api/health
```

## 启动方式

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000/docs
```

