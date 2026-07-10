const state = {
  view: "ingest",
  file: null,
};

const nodes = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  pageKicker: document.querySelector("#pageKicker"),
  pageTitle: document.querySelector("#pageTitle"),
  viewButtons: document.querySelectorAll("[data-view-button]"),
  ingestView: document.querySelector("#ingestView"),
  searchView: document.querySelector("#searchView"),
  ingestForm: document.querySelector("#ingestForm"),
  searchForm: document.querySelector("#searchForm"),
  excelInput: document.querySelector("#excelInput"),
  dropZone: document.querySelector("#dropZone"),
  fileGlyph: document.querySelector("#fileGlyph"),
  fileTitle: document.querySelector("#fileTitle"),
  fileHint: document.querySelector("#fileHint"),
  projectNameInput: document.querySelector("#projectNameInput"),
  batchSizeInput: document.querySelector("#batchSizeInput"),
  ingestButton: document.querySelector("#ingestButton"),
  searchButton: document.querySelector("#searchButton"),
  ingestStatus: document.querySelector("#ingestStatus"),
  searchStatus: document.querySelector("#searchStatus"),
  ingestEmpty: document.querySelector("#ingestEmpty"),
  ingestResultPanel: document.querySelector("#ingestResultPanel"),
  ingestCount: document.querySelector("#ingestCount"),
  uploadedPath: document.querySelector("#uploadedPath"),
  ingestItems: document.querySelector("#ingestItems"),
  queryInput: document.querySelector("#queryInput"),
  limitInput: document.querySelector("#limitInput"),
  searchEmpty: document.querySelector("#searchEmpty"),
  resultsGrid: document.querySelector("#resultsGrid"),
};

function apiBaseUrl() {
  return nodes.apiBaseInput.value.trim().replace(/\/$/, "") || window.location.origin;
}

const EXCEL_EXTENSIONS = [".xlsx", ".xlsm"];
const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".bmp"];

function fileExtension(fileName) {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex).toLowerCase() : "";
}

function fileMode(file) {
  if (!file) return "";
  const extension = fileExtension(file.name);
  if (EXCEL_EXTENSIONS.includes(extension)) return "excel";
  if (IMAGE_EXTENSIONS.includes(extension) || file.type.startsWith("image/")) return "image";
  return "";
}

function setView(view) {
  state.view = view;
  nodes.ingestView.classList.toggle("hidden", view !== "ingest");
  nodes.searchView.classList.toggle("hidden", view !== "search");
  nodes.pageKicker.textContent = view === "ingest" ? "Asset Ingest" : "Semantic Asset Search";
  nodes.pageTitle.textContent = view === "ingest" ? "智能入库" : "素材检索";
  nodes.viewButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.viewButton === view);
  });
}

function setStatus(node, kind, message) {
  node.className = `inlineStatus ${kind}`;
  node.textContent = message;
}

function asText(value) {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number") return String(value);
  return "";
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function findImageUrl(item) {
  if (!isRecord(item)) return "";
  const directKeys = ["source_file_url", "storage_url", "image_url", "url", "thumbnail_url", "cover_url"];
  for (const key of directKeys) {
    const value = asText(item[key]);
    if (value.startsWith("http://") || value.startsWith("https://")) return value;
  }

  const metadata = item.metadata;
  if (isRecord(metadata)) {
    const metadataUrl = findImageUrl(metadata);
    if (metadataUrl) return metadataUrl;

    if (isRecord(metadata.primary_image)) {
      const primaryUrl = findImageUrl(metadata.primary_image);
      if (primaryUrl) return primaryUrl;
    }

    if (Array.isArray(metadata.images)) {
      for (const image of metadata.images) {
        const imageUrl = findImageUrl(image);
        if (imageUrl) return imageUrl;
      }
    }
  }

  return "";
}

function displayName(item) {
  return (
    asText(item.display_name) ||
    asText(item.name) ||
    asText(item.parent_entity_name) ||
    asText(item.source_id) ||
    "未命名资产"
  );
}

function summaryText(item) {
  return (
    asText(item.intro) ||
    asText(item.description) ||
    asText(item.appearance) ||
    asText(item.usage_context) ||
    asText(item.visual_prompt) ||
    asText(item.vector_text) ||
    "暂无文本摘要"
  );
}

function compactKind(kind) {
  const value = asText(kind);
  if (value === "character") return "角色";
  if (value === "scene") return "场景";
  if (value === "prop") return "道具";
  if (value === "variant") return "变体";
  return value || "资产";
}

function scoreText(score) {
  return typeof score === "number" ? score.toFixed(4) : "无分数";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function imageMarkup(item, title) {
  const url = findImageUrl(item);
  if (!url) {
    return `<div class="imageFallback"><span>暂无图片</span></div>`;
  }
  return `<a class="imageLink" href="${escapeHtml(url)}" target="_blank" rel="noreferrer"><img class="assetImage" src="${escapeHtml(url)}" alt="${escapeHtml(title)}" loading="lazy" onerror="this.closest('.imageLink').outerHTML='<div class=&quot;imageFallback&quot;><span>图片无法加载</span></div>'" /></a>`;
}

function textBlock(label, value) {
  const text = asText(value);
  if (!text) return "";
  return `<div class="textBlock"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(text)}</dd></div>`;
}

function formatMs(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number >= 1000 ? `${(number / 1000).toFixed(2)}s` : `${Math.round(number)}ms`;
}

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function timingBadges(item) {
  const timing = item?.metadata?.ingest_timing_ms;
  if (!isRecord(timing)) return "";

  const cleanFields = [
    ["总耗时", firstPresent(timing.api_total_before_response, timing.service_total_before_commit)],
    ["Excel入库", timing.api_service_ingest_excel],
    ["保存上传", timing.api_save_upload],
    ["模型HTTP", timing.vision_http],
    ["模型总", firstPresent(timing.doubao_vision, timing.llm_extract)],
    ["TOS", timing.tos_upload],
    ["PG", timing.pg_write],
    ["读取", timing.api_read_upload],
    ["提交", timing.api_db_commit],
    ["清理", timing.api_cleanup_upload],
  ];
  const cleanBadges = cleanFields
    .map(([label, value]) => {
      const text = formatMs(value);
      return text ? `<span>${escapeHtml(label)} ${escapeHtml(text)}</span>` : "";
    })
    .filter(Boolean)
    .join("");

  return cleanBadges ? `<div class="timingBadges">${cleanBadges}</div>` : "";

  const fields = [
    ["总耗时", firstPresent(timing.api_total_before_response, timing.service_total_before_commit)],
    ["Excel入库", timing.api_service_ingest_excel],
    ["保存上传", timing.api_save_upload],
    ["清理", timing.api_cleanup_upload],
    ["总耗时", timing.api_total_before_response],
    ["模型HTTP", timing.vision_http],
    ["模型总", timing.doubao_vision],
    ["TOS", timing.tos_upload],
    ["PG", timing.pg_write],
    ["读取", timing.api_read_upload],
    ["提交", timing.api_db_commit],
  ];
  const badges = fields
    .map(([label, value]) => {
      const text = formatMs(value);
      return text ? `<span>${escapeHtml(label)} ${escapeHtml(text)}</span>` : "";
    })
    .filter(Boolean)
    .join("");

  return badges ? `<div class="timingBadges">${badges}</div>` : "";
}

function renderMiniItem(item) {
  const title = displayName(item);
  return `
    <article class="miniCard">
      <div class="miniImageWrap">${imageMarkup(item, title)}</div>
      <div>
        <span>${escapeHtml(compactKind(item.asset_kind))}</span>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(summaryText(item))}</p>
        ${timingBadges(item)}
      </div>
    </article>
  `;
}

function renderSearchItem(item) {
  const title = displayName(item);
  return `
    <article class="resultCard">
      <div class="resultImageWrap">${imageMarkup(item, title)}</div>
      <div class="resultBody">
        <div class="resultTopline">
          <span>${escapeHtml(compactKind(item.asset_kind))}</span>
          <strong>${escapeHtml(scoreText(item.score))}</strong>
        </div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(summaryText(item))}</p>
        <dl class="fieldList">
          ${textBlock("来源", item.source_table)}
          ${textBlock("父级", item.parent_entity_name)}
          ${textBlock("外观", item.appearance)}
          ${textBlock("用途", item.usage_context)}
          ${textBlock("视觉提示", item.visual_prompt)}
          ${textBlock("向量文本", item.vector_text)}
        </dl>
      </div>
    </article>
  `;
}

async function parseApiError(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((item) => item.msg || JSON.stringify(item)).join("；");
    }
    return JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

async function uploadAssetFile(event) {
  event.preventDefault();
  if (!state.file) {
    setStatus(nodes.ingestStatus, "error", "请先选择 Excel 或图片文件");
    return;
  }

  const mode = fileMode(state.file);
  if (!mode) {
    setStatus(nodes.ingestStatus, "error", "仅支持 .xlsx/.xlsm 或 .jpg/.jpeg/.png/.webp/.bmp");
    return;
  }

  const formData = new FormData();
  formData.append("file", state.file);
  const projectName = nodes.projectNameInput.value.trim();
  if (projectName) formData.append("source_project_name", projectName);
  formData.append("batch_size", nodes.batchSizeInput.value || "5");

  nodes.ingestButton.disabled = true;
  setStatus(
    nodes.ingestStatus,
    "loading",
    mode === "image" ? "正在识别图片、上传 TOS 并入库" : "正在解析 Excel 并入库",
  );

  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/asset-ingest/upload`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error(await parseApiError(response));

    const result = await response.json();
    nodes.ingestEmpty.classList.add("hidden");
    nodes.ingestResultPanel.classList.remove("hidden");
    nodes.ingestCount.textContent = `${result.count || 0} 条`;
    nodes.uploadedPath.textContent =
      result.mode === "image"
        ? "图片已上传 TOS，source_file_url 已写入资产主图地址"
        : `上传路径：${result.uploaded_file_path || ""}`;
    nodes.ingestItems.innerHTML = (result.items || []).slice(0, 8).map(renderMiniItem).join("");
    setStatus(
      nodes.ingestStatus,
      "success",
      `${result.mode === "image" ? "图片" : "Excel"} 入库完成，共写入 ${result.count || 0} 条资产`,
    );
  } catch (error) {
    setStatus(nodes.ingestStatus, "error", error instanceof Error ? error.message : "入库失败");
  } finally {
    nodes.ingestButton.disabled = false;
  }
}

async function searchAssets(event) {
  event.preventDefault();
  const query = nodes.queryInput.value.trim();
  if (!query) {
    setStatus(nodes.searchStatus, "error", "请输入检索内容");
    return;
  }

  nodes.searchButton.disabled = true;
  setStatus(nodes.searchStatus, "loading", "正在检索语义相近素材");

  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/asset-search/semantic`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        limit: Number(nodes.limitInput.value || 10),
      }),
    });
    if (!response.ok) throw new Error(await parseApiError(response));

    const result = await response.json();
    const items = result.items || [];
    nodes.resultsGrid.innerHTML = items.map(renderSearchItem).join("");
    nodes.resultsGrid.classList.toggle("hidden", items.length === 0);
    nodes.searchEmpty.classList.toggle("hidden", items.length > 0);
    nodes.searchEmpty.querySelector("h2").textContent = items.length ? "" : "没有匹配结果";
    setStatus(nodes.searchStatus, "success", `找到 ${result.count || 0} 条结果`);
  } catch (error) {
    setStatus(nodes.searchStatus, "error", error instanceof Error ? error.message : "检索失败");
  } finally {
    nodes.searchButton.disabled = false;
  }
}

function selectFile(file) {
  state.file = file;
  if (!file) {
    nodes.fileGlyph.textContent = "FILE";
    nodes.fileTitle.textContent = "选择或拖入资产表 / 图片";
    nodes.fileHint.textContent = "支持 .xlsx / .xlsm / .jpg / .png / .webp / .bmp";
    return;
  }

  const mode = fileMode(file);
  nodes.fileGlyph.textContent = mode === "image" ? "IMG" : mode === "excel" ? "XLS" : "???";
  nodes.fileTitle.textContent = file.name;
  nodes.fileHint.textContent = `${mode === "image" ? "图片识别入库" : mode === "excel" ? "Excel 批量入库" : "暂不支持的文件"} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  nodes.ingestResultPanel.classList.add("hidden");
  nodes.ingestEmpty.classList.remove("hidden");
}

nodes.viewButtons.forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.viewButton));
});

nodes.excelInput.addEventListener("change", (event) => {
  selectFile(event.target.files?.[0] || null);
});

nodes.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  nodes.dropZone.classList.add("dragging");
});

nodes.dropZone.addEventListener("dragleave", () => {
  nodes.dropZone.classList.remove("dragging");
});

nodes.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  nodes.dropZone.classList.remove("dragging");
  selectFile(event.dataTransfer.files?.[0] || null);
});

nodes.ingestForm.addEventListener("submit", uploadAssetFile);
nodes.searchForm.addEventListener("submit", searchAssets);

if (nodes.apiBaseInput.value === "http://127.0.0.1:8000") {
  nodes.apiBaseInput.value = window.location.origin;
}
