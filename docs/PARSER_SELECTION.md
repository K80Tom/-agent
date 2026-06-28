# 多模态文档解析器选型指南

本文档用于指导短剧制作智能体项目选择第三方多模态文档解析服务。

当前结论：

```text
现在不要直接写死某一家解析器。
先做选型评测，再把胜出的解析器接入 BaseDocumentParser。
```

## 1. 为什么解析器选型很关键

RAG 项目的效果很大程度取决于文档解析质量。

如果解析出来的文本是乱的，后面这些都会跟着出问题：

```text
切块
embedding
向量检索
RAG 回答
推荐
GraphRAG 实体关系抽取
```

短剧制作场景的文档很可能不是纯文本，而是多模态资料：

```text
PDF 剧本
Word 角色设定
Excel 制作表
PPT 提案
图片分镜
扫描合同
网页资料
带表格的制作规范
带图片的会议纪要
```

所以解析器不仅要 OCR，还要尽量保留结构。

## 2. 现在应该先做什么

当前第一步不是接 VikingDB，也不是写推荐接口。

当前第一步是：

```text
收集真实样例文件
→ 用多个第三方解析器跑同一批文件
→ 对比解析结果
→ 选出主解析器和备用解析器
```

建议至少准备 20 个样例文件：

```text
3 个 PDF 剧本
3 个 Word 角色设定/制作规范
3 个 Excel 表格
3 个 PPT 提案/分镜
3 张图片或扫描件
3 个合同/会议纪要
2 个网页或 HTML
```

样例必须尽量接近公司真实业务，不要只用网上随便下载的干净文件。

## 3. 候选方案

### 方案 A：火山/豆包生态

如果公司已经要求使用火山云、VikingDB、AgentKit，那么优先评测火山生态里的文档解析、OCR、视觉理解或豆包多模态能力。

优点：

```text
和公司现有云资源更容易打通
和 VikingDB / AgentKit 生态一致
采购和合规阻力可能更小
国内访问稳定
```

风险：

```text
具体文件格式支持范围需要看你们公司开通的产品和控制台能力
复杂表格、PPT、分镜图片效果必须用真实样例测试
不要只听销售介绍，要看实际解析输出
```

建议定位：

```text
生产首选候选
但必须用真实文件评测后再定
```

### 方案 B：LlamaParse

LlamaParse 是面向 LLM/RAG 的文档解析服务，官方定位是把 PDF、扫描件、表格、图表等解析成 markdown、text 或 JSON。官方文档中提到支持 130+ 文件类型，包括 PDF、DOCX、PPTX、XLSX、HTML、JPEG、PNG、XML、EPUB 等。

适合：

```text
RAG 文档解析
复杂 PDF
表格和图表
需要 markdown 输出
希望快速验证效果
```

风险：

```text
海外服务合规需要公司确认
成本、数据出境、私有化能力要问清楚
```

建议定位：

```text
强力对照组
用于判断国内方案效果是否够好
```

官方资料：

```text
https://docs.cloud.llamaindex.ai/llamaparse
```

### 方案 C：Azure AI Document Intelligence

Azure Document Intelligence 是企业级文档智能服务。官方文档显示 Read/Layout 等模型支持 PDF、图片、Word DOCX、Excel XLSX、PowerPoint PPTX、HTML 等格式，并支持 OCR、段落、行、词、位置等信息提取。

适合：

```text
企业文档解析
Office 文档
PDF 和扫描件
需要稳定 API 和 SDK
```

风险：

```text
云区域、合规、费用需要公司确认
中文和复杂短剧业务文档要实测
```

建议定位：

```text
企业级对照组
```

官方资料：

```text
https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read
```

### 方案 D：Google Document AI

Google Document AI 官方支持 PDF、GIF、TIFF、JPEG、PNG、BMP、WebP、HTML、DOCX、PPTX、XLSX 等文件类型。

适合：

```text
海外云可用的团队
需要强文档 AI 能力
```

风险：

```text
国内访问和合规通常是主要问题
公司是否允许使用需要先确认
```

建议定位：

```text
技术对照组
不一定适合作为国内生产首选
```

官方资料：

```text
https://cloud.google.com/document-ai/docs/file-types
```

### 方案 E：Unstructured

Unstructured 提供开源库和商业服务。官方文档显示其 partition 能处理 PDF、图片、Word、PPT、Excel、HTML、Markdown、邮件、EPUB、XML 等多种格式，并能输出结构化 elements。

适合：

```text
本地快速开发
需要开源可控
想先跑通解析流程
对接 RAG pipeline
```

风险：

```text
本地部署依赖可能比较多
复杂版式、图表、扫描件质量需要实测
商用服务和开源能力边界要分清
```

建议定位：

```text
本地开发和开源备选
```

官方资料：

```text
https://docs.unstructured.io/open-source/core-functionality/partitioning
```

### 方案 F：AWS Textract

AWS Textract 更偏 OCR 和表单/表格抽取。官方文档显示支持 JPEG、PNG、PDF、TIFF，但语言支持和中文场景不一定适合你的业务。

适合：

```text
英文文档
表单和票据类文档
AWS 生态内项目
```

风险：

```text
不是短剧中文多模态文档的优先候选
Office 文档支持不如其他方案直接
中文效果需要特别谨慎
```

建议定位：

```text
不是当前优先推荐
```

官方资料：

```text
https://docs.aws.amazon.com/textract/latest/dg/limits-document.html
```

## 4. 推荐选型路线

我建议当前选型分三组：

```text
主候选：火山/豆包生态
强对照：LlamaParse
企业对照：Azure Document Intelligence 或 Google Document AI
本地备选：Unstructured
```

如果公司明确要求火山云：

```text
优先评测火山方案
但必须拿 LlamaParse 或 Azure 做效果对照
```

原因是：

```text
只测一家，你不知道它到底好不好。
测两到三家，才能跟领导说清楚为什么选它。
```

## 5. 评测维度

建议用 100 分制。

```text
文件格式覆盖：15 分
中文 OCR 准确率：15 分
标题和层级结构：10 分
表格解析：15 分
图片/扫描件/分镜解析：10 分
页码、坐标、来源 metadata：10 分
输出格式是否适合 RAG：10 分
API 稳定性和批处理能力：5 分
成本和速度：5 分
合规、私有化、数据安全：5 分
```

最关键的不是“能不能识别文字”，而是：

```text
解析结果能不能直接进入 RAG pipeline。
```

## 6. 评测输出格式

每个解析器都应该输出统一结构。

建议统一为：

```json
{
  "parser_name": "xxx",
  "file_name": "demo.pdf",
  "file_type": "pdf",
  "text": "解析后的正文",
  "elements": [
    {
      "type": "title",
      "text": "第一章",
      "page": 1
    },
    {
      "type": "paragraph",
      "text": "正文内容",
      "page": 1
    },
    {
      "type": "table",
      "text": "|字段|值|",
      "page": 2
    }
  ],
  "metadata": {
    "page_count": 10,
    "has_table": true,
    "has_image": true
  }
}
```

后续不管接哪家，都要转成这个内部统一结构。

## 7. 为什么还要保留 BaseDocumentParser

即使你们最终选择某一个第三方，也不要让业务代码直接依赖它的 SDK。

正确方式：

```text
BaseDocumentParser
  ↑
VolcanoDocumentParser
LlamaParseDocumentParser
AzureDocumentParser
UnstructuredDocumentParser
```

业务流程只依赖：

```text
BaseDocumentParser
```

这样以后换解析器，不需要重写入库、切块、检索、推荐代码。

## 8. 当前项目下一步

下一步不要直接写某家 SDK。

下一步应该做：

```text
1. 新建 docs/parser_eval_matrix.xlsx 或 markdown 表格
2. 收集 20 个真实样例文件
3. 设计统一 ParsedDocument 输出结构
4. 为 BaseDocumentParser 增加更适合多模态解析的返回模型
5. 先实现 ParserEvaluation 评测脚本骨架
```

等评测结果出来后，再决定：

```text
主解析器是谁
备用解析器是谁
哪些文件类型走哪个解析器
```

## 9. 暂定建议

在没有真实样例评测前，不应该拍板。

但从当前业务和公司环境看，暂定路线可以是：

```text
生产优先：火山/豆包生态
效果对照：LlamaParse
企业对照：Azure Document Intelligence
本地备选：Unstructured
```

如果火山方案在你们真实文件上效果足够好，并且公司已经采购火山云，那就优先用火山。

如果火山解析复杂 PDF、表格、PPT、扫描件效果不稳定，就需要考虑：

```text
火山为主 + LlamaParse/Unstructured 兜底
```

或者按文件类型路由：

```text
普通 Office 文档 → 火山/企业云解析
复杂 PDF/图表 → LlamaParse
本地开发测试 → Unstructured
```

