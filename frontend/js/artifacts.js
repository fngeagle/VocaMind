/** 任务文档附件：卡片展示与 Markdown 渲染。 */
import { renderMarkdown } from "./markdown_render.js";

export function artifactBaseUrlFromWs(wsUrl) {
  const u = new URL(wsUrl);
  const wsPort = parseInt(u.port, 10) || 9001;
  u.protocol = u.protocol === "wss:" ? "https:" : "http:";
  u.port = String(wsPort + 1);
  u.pathname = "";
  u.search = "";
  u.hash = "";
  return u.origin;
}

export function buildArtifactUrl(baseUrl, artifact) {
  const path = encodeURIComponent(artifact.path).replace(/%2F/g, "/");
  return `${baseUrl}/api/artifacts/${artifact.task_id}/${path}`;
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

export function appendAttachmentCards(chatEl, attachments, { onOpen }) {
  const seen = appendAttachmentCards._seen || (appendAttachmentCards._seen = new Set());
  for (const att of attachments) {
    const key = `${att.task_id}:${att.path}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const wrap = document.createElement("div");
    wrap.className = "msg assistant artifact-card";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "artifact-btn";
    btn.textContent = att.kind === "html" ? `📄 ${att.title}` : `📝 ${att.title}`;
    bindTap(btn, () => onOpen(att));
    wrap.appendChild(btn);

    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
  }
}

export function ensureDocModal() {
  let modal = document.getElementById("docModal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "docModal";
  modal.className = "doc-modal hidden";
  modal.innerHTML = `
    <div class="doc-modal-backdrop"></div>
    <div class="doc-modal-panel" role="dialog" aria-modal="true">
      <header class="doc-modal-header">
        <h2 id="docModalTitle"></h2>
        <button type="button" id="docModalClose" aria-label="关闭">×</button>
      </header>
      <article id="docModalBody" class="doc-modal-body"></article>
    </div>
  `;
  document.body.appendChild(modal);

  const close = () => modal.classList.add("hidden");
  bindTap(modal.querySelector(".doc-modal-backdrop"), close);
  bindTap(modal.querySelector("#docModalClose"), close);
  return modal;
}

export async function openArtifactModal(artifact, baseUrl) {
  const modal = ensureDocModal();
  const titleEl = modal.querySelector("#docModalTitle");
  const bodyEl = modal.querySelector("#docModalBody");
  titleEl.textContent = artifact.title;
  bodyEl.textContent = "加载中…";
  modal.classList.remove("hidden");

  const url = buildArtifactUrl(baseUrl, artifact);
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const text = await resp.text();
    if (artifact.kind === "html") {
      bodyEl.textContent = "";
      const frame = document.createElement("iframe");
      frame.className = "doc-html-frame";
      frame.setAttribute("sandbox", "allow-same-origin");
      frame.srcdoc = text;
      bodyEl.appendChild(frame);
    } else {
      bodyEl.innerHTML = renderMarkdown(text);
    }
  } catch (err) {
    bodyEl.textContent = `无法加载文档：${err.message}\n\n请确认文档服务已启动（HTTP 端口一般为 WebSocket 端口 +1，如 9002）。`;
    console.error("openArtifactModal failed", url, err);
  }
}
