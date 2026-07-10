/** 对话区内的 Voice 工具卡片。 */
import { createToolCard, finishToolCard } from "./tool_card_factory.js";

const toolCards = new Map();

export function handleChatToolEvent(chatEl, data) {
  const id = data.tool_call_id;
  if (!id) return;

  if (data.event === "start") {
    if (toolCards.has(id)) return;
    const { wrap, entry } = createToolCard(data);
    const outer = document.createElement("div");
    outer.className = "msg assistant tool-chat-wrap";
    outer.appendChild(wrap);
    chatEl.appendChild(outer);
    chatEl.scrollTop = chatEl.scrollHeight;
    toolCards.set(id, entry);
    return;
  }

  if (data.event === "end") {
    const entry = toolCards.get(id);
    if (!entry) return;
    finishToolCard(entry, data);
    chatEl.scrollTop = chatEl.scrollHeight;
  }
}

export function resetChatToolCards() {
  toolCards.clear();
}
