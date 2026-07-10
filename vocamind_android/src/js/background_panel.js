/** 页顶后台 Agent 活动面板：默认显示状态，下拉查看工具调用。 */
import { createToolCard, finishToolCard, toolLabel } from "./tool_card_factory.js";

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

export class BackgroundPanel {
  constructor(rootEl) {
    this.root = rootEl;
    this.bar = rootEl.querySelector(".bg-panel-bar");
    this.statusEl = rootEl.querySelector(".bg-panel-status");
    this.hintEl = rootEl.querySelector(".bg-panel-hint");
    this.bodyEl = rootEl.querySelector(".bg-panel-body");
    this.scrollEl = rootEl.querySelector(".bg-panel-scroll");
    this.dotEl = rootEl.querySelector(".bg-panel-dot");

    this.toolCards = new Map();
    this.taskSections = new Map();
    this.runningCount = 0;
    this.currentTool = null;
    this.activeTaskId = null;
    this.expanded = false;
    this.hasActivity = false;

    bindTap(this.bar, () => this.toggle());
    this.updateStatus();
  }

  toggle(force) {
    this.expanded = force !== undefined ? force : !this.expanded;
    this.root.classList.toggle("expanded", this.expanded);
    this.bar.setAttribute("aria-expanded", this.expanded ? "true" : "false");
  }

  ensureTaskSection(taskId, title) {
    const key = taskId || "_default";
    if (this.taskSections.has(key)) {
      const { section } = this.taskSections.get(key);
      if (title) {
        const titleEl = section.querySelector(".bg-task-title");
        if (titleEl) titleEl.textContent = title;
      }
      return this.taskSections.get(key).tools;
    }

    const section = document.createElement("div");
    section.className = "bg-task-section";
    section.dataset.taskId = key;

    const head = document.createElement("div");
    head.className = "bg-task-head";
    head.innerHTML = `
      <span class="bg-task-icon">📋</span>
      <div class="bg-task-meta">
        <span class="bg-task-title">${title || "后台任务"}</span>
        <span class="bg-task-id">${taskId ? taskId.slice(0, 12) : ""}</span>
      </div>
      <span class="bg-task-state">进行中</span>
    `;

    const tools = document.createElement("div");
    tools.className = "bg-task-tools";

    section.append(head, tools);
    this.scrollEl.prepend(section);
    this.taskSections.set(key, { section, tools });

    this.root.classList.add("has-activity");
    this.hasActivity = true;
    this.hideEmptyHint();
    return tools;
  }

  hideEmptyHint() {
    const empty = this.scrollEl.querySelector(".bg-panel-empty");
    if (empty) empty.remove();
  }

  noteTaskDispatched(data) {
    const subject = data.arguments?.subject || "新任务";
    const taskId = data.task_id || `pending-${data.tool_call_id}`;
    this.activeTaskId = taskId;
    this.ensureTaskSection(taskId, subject);
    this.updateStatus();
  }

  handleToolEvent(data) {
    const id = data.tool_call_id;
    if (!id) return;

    if (data.event === "start") {
      if (this.toolCards.has(id)) return;
      this.runningCount += 1;
      this.currentTool = data.tool_name;
      if (data.task_id) this.activeTaskId = data.task_id;

      const container = this.ensureTaskSection(
        data.task_id,
        data.arguments?.subject,
      );
      const { wrap, entry } = createToolCard({ ...data, scope: "agent" });
      container.appendChild(wrap);
      this.toolCards.set(id, entry);
      this.updateStatus();
      return;
    }

    if (data.event === "end") {
      const entry = this.toolCards.get(id);
      if (entry) finishToolCard(entry, data);
      this.runningCount = Math.max(0, this.runningCount - 1);
      if (this.runningCount === 0) {
        this.currentTool = null;
        if (data.task_id) {
          const stored = this.taskSections.get(data.task_id);
          const stateEl = stored?.section?.querySelector(".bg-task-state");
          if (stateEl) {
            stateEl.textContent = data.status === "error" ? "失败" : "已完成";
            stateEl.classList.add(data.status === "error" ? "err" : "done");
          }
        }
      } else {
        this.currentTool = data.tool_name;
      }
      this.updateStatus();
    }
  }

  updateStatus() {
    if (this.runningCount > 0) {
      this.statusEl.textContent = `执行中 · ${toolLabel(this.currentTool)}`;
      this.hintEl.textContent = `${this.runningCount} 个工具运行中，下拉查看`;
      this.dotEl.className = "bg-panel-dot busy";
      this.root.classList.add("active");
    } else if (this.hasActivity) {
      this.statusEl.textContent = "空闲";
      this.hintEl.textContent = "下拉查看后台记录";
      this.dotEl.className = "bg-panel-dot ok";
      this.root.classList.remove("active");
    } else {
      this.statusEl.textContent = "空闲";
      this.hintEl.textContent = "暂无后台任务";
      this.dotEl.className = "bg-panel-dot";
      this.root.classList.remove("active");
    }
  }

  reset() {
    this.toolCards.clear();
    this.taskSections.clear();
    this.runningCount = 0;
    this.currentTool = null;
    this.activeTaskId = null;
    this.hasActivity = false;
    this.scrollEl.innerHTML = `<p class="bg-panel-empty">后台 Agent 的工具调用会显示在这里</p>`;
    this.updateStatus();
  }
}

let panelInstance = null;

export function initBackgroundPanel(rootEl) {
  panelInstance = new BackgroundPanel(rootEl);
  return panelInstance;
}

export function getBackgroundPanel() {
  return panelInstance;
}
