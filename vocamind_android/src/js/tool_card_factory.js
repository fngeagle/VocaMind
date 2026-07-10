/** 工具卡片 DOM 工厂（对话区 / 后台面板共用）。 */

export const TOOL_LABELS = {
  web_search: "网页搜索",
  bash: "运行命令",
  read_file: "读取文件",
  write_file: "写入文件",
  edit_file: "编辑文件",
  list_dir: "列出目录",
  dispatch_task: "派发任务",
  list_tasks: "任务列表",
  get_task: "查看任务",
  query_status: "查询状态",
  core_memory_add: "添加记忆",
  core_memory_update: "更新记忆",
  core_memory_delete: "删除记忆",
  compact: "压缩上下文",
  complete_task: "完成任务",
};

export const STATUS_LABELS = {
  running: "执行中",
  success: "完成",
  error: "失败",
  blocked: "已阻止",
};

export function toolLabel(name) {
  return TOOL_LABELS[name] || name;
}

export function formatJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (_) {
    return String(value ?? "");
  }
}

export function argsSummary(args) {
  if (!args || typeof args !== "object") return "";
  const parts = [];
  for (const [key, val] of Object.entries(args)) {
    let text = typeof val === "string" ? val : JSON.stringify(val);
    if (text.length > 48) text = `${text.slice(0, 48)}…`;
    parts.push(`${key}: ${text}`);
  }
  return parts.join(" · ") || "无参数";
}

function bindTap(el, handler) {
  let lastTouchAt = 0;
  el.addEventListener(
    "touchend",
    (e) => {
      e.preventDefault();
      lastTouchAt = Date.now();
      handler();
    },
    { passive: false },
  );
  el.addEventListener("click", () => {
    if (Date.now() - lastTouchAt < 500) return;
    handler();
  });
}

/** @returns {{ wrap: HTMLElement, entry: object }} */
export function createToolCard(data) {
  const wrap = document.createElement("div");
  wrap.className = "tool-card-wrap";
  wrap.dataset.toolId = data.tool_call_id;

  const card = document.createElement("div");
  card.className = "tool-card running";

  const header = document.createElement("button");
  header.type = "button";
  header.className = "tool-card-header";
  header.setAttribute("aria-expanded", "false");

  const icon = document.createElement("span");
  icon.className = "tool-icon";
  icon.textContent = data.scope === "agent" ? "⚙️" : "🔧";

  const meta = document.createElement("div");
  meta.className = "tool-meta";

  const title = document.createElement("span");
  title.className = "tool-title";
  title.textContent = toolLabel(data.tool_name);

  const subtitle = document.createElement("span");
  subtitle.className = "tool-subtitle";
  subtitle.textContent = argsSummary(data.arguments);

  meta.appendChild(title);
  meta.appendChild(subtitle);

  const status = document.createElement("span");
  status.className = "tool-status running";
  status.textContent = STATUS_LABELS.running;

  const chevron = document.createElement("span");
  chevron.className = "tool-chevron";
  chevron.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`;

  header.append(icon, meta, status, chevron);

  const body = document.createElement("div");
  body.className = "tool-card-body";

  const argsSection = document.createElement("div");
  argsSection.className = "tool-section";
  argsSection.innerHTML = `<div class="tool-section-label">参数</div>`;
  const argsPre = document.createElement("pre");
  argsPre.className = "tool-pre";
  argsPre.textContent = formatJson(data.arguments);
  argsSection.appendChild(argsPre);

  const resultSection = document.createElement("div");
  resultSection.className = "tool-section tool-result-section hidden";
  resultSection.innerHTML = `<div class="tool-section-label">结果</div>`;
  const resultPre = document.createElement("pre");
  resultPre.className = "tool-pre tool-result-pre";
  resultSection.appendChild(resultPre);

  body.append(argsSection, resultSection);
  card.append(header, body);
  wrap.appendChild(card);

  bindTap(header, () => {
    const open = body.classList.toggle("open");
    header.setAttribute("aria-expanded", open ? "true" : "false");
    card.classList.toggle("expanded", open);
  });

  const entry = { wrap, card, statusEl: status, resultPre, resultSection };
  return { wrap, entry };
}

export function finishToolCard(entry, data) {
  const st = data.status || "success";
  entry.statusEl.className = `tool-status ${st}`;
  entry.statusEl.textContent = STATUS_LABELS[st] || st;
  entry.card.classList.remove("running");
  entry.card.classList.add(st);
  const text = data.content_preview || data.content || "";
  entry.resultPre.textContent = text;
  entry.resultSection.classList.remove("hidden");
}
