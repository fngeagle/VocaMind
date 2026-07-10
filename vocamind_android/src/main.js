import { VoiceConnection } from "./js/voice_connection.js";
import { defaultWsUrl } from "./js/ws_config.js";
import { requestMicStream } from "./js/mic_session.js";
import { PcmFrameBuffer, resampleTo16k } from "./js/audio_resample.js";
import { ClientVAD } from "./js/client_vad.js";
import { transcribeAudio, DEFAULT_ASR_URL, DEFAULT_ASR_MODEL } from "./js/client_asr.js";
import {
  artifactBaseUrlFromWs,
  appendAttachmentCards,
  openArtifactModal,
} from "./js/artifacts.js";
import { renderMarkdown } from "./js/markdown_render.js";
import { handleChatToolEvent, resetChatToolCards } from "./js/tool_cards.js";
import { initBackgroundPanel, getBackgroundPanel } from "./js/background_panel.js";

const SAMPLE_RATE = 16000;
const ASR_KEY_STORAGE = "vocamind_asr_api_key";
const ASR_URL_STORAGE = "vocamind_asr_api_url";
const ASR_MODEL_STORAGE = "vocamind_asr_model";
const UID_STORAGE = "vocamind_uid";
const THEME_STORAGE = "vocamind_theme";
const VOICE_PLAYBACK_STORAGE = "vocamind_voice_playback";
const THEME_COLORS = { light: "#f5f7fb", dark: "#0a0a0f" };

function getOrCreateUid() {
  let id = localStorage.getItem(UID_STORAGE);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(UID_STORAGE, id);
  }
  return id;
}

const uid = getOrCreateUid();

let connection = null;
let userInputCount = 0;
let busy = false;
let historySynced = false;
let syncRetryTimer = null;
let syncAttempts = 0;
const MAX_SYNC_ATTEMPTS = 10;
const SYNC_RETRY_MS = 600;
let assistantEl = null;
let lastUserEl = null;

let micOn = false;
let micStream = null;
let micContext = null;
let micProcessor = null;
let pcmFrameBuffer = null;
let clientVad = null;

const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
const audioQueue = [];
let audioPlaying = false;
let currentAudioSource = null;

const $ = (id) => document.getElementById(id);
const chat = $("chat");
const statusEl = $("status");
const statusDot = $("statusDot");
const inputEl = $("input");
const sendBtn = $("sendBtn");
const connectBtn = $("connectBtn");
const micBtn = $("micBtn");
const viewSettings = $("viewSettings");
const settingsBtn = $("settingsBtn");
const backBtn = $("backBtn");
const themeSegment = $("themeSegment");
const voicePlaybackToggle = $("voicePlaybackToggle");

function isVoicePlaybackEnabled() {
  const stored = localStorage.getItem(VOICE_PLAYBACK_STORAGE);
  if (stored === null) return true;
  return stored === "true";
}

function persistVoicePlayback(enabled) {
  localStorage.setItem(VOICE_PLAYBACK_STORAGE, enabled ? "true" : "false");
  if (!enabled) stopPlayback();
}

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem(THEME_STORAGE, next);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", THEME_COLORS[next]);
  themeSegment?.querySelectorAll(".segmented-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.theme === next);
  });
}

function initPreferences() {
  const theme = localStorage.getItem(THEME_STORAGE) || "light";
  applyTheme(theme);
  if (voicePlaybackToggle) {
    voicePlaybackToggle.checked = isVoicePlaybackEnabled();
  }
}

function getAsrConfig() {
  return {
    apiKey: $("asrKey")?.value?.trim() || localStorage.getItem(ASR_KEY_STORAGE) || "",
    apiUrl: $("asrUrl")?.value?.trim() || localStorage.getItem(ASR_URL_STORAGE) || DEFAULT_ASR_URL,
    model: $("asrModel")?.value?.trim() || localStorage.getItem(ASR_MODEL_STORAGE) || DEFAULT_ASR_MODEL,
  };
}

function persistAsrConfig() {
  const cfg = getAsrConfig();
  localStorage.setItem(ASR_KEY_STORAGE, cfg.apiKey);
  localStorage.setItem(ASR_URL_STORAGE, cfg.apiUrl);
  localStorage.setItem(ASR_MODEL_STORAGE, cfg.model);
}

function stopPlayback() {
  audioQueue.length = 0;
  if (currentAudioSource) {
    try {
      currentAudioSource.stop();
    } catch (_) {}
    currentAudioSource = null;
  }
  audioPlaying = false;
  notifyPlaying(false);
}

function onSpeechStart() {
  if (audioPlaying) {
    stopPlayback();
  }
}

function resetConnectionState() {
  busy = false;
  finishAssistantBubble();
  lastUserEl = null;
  stopPlayback();
}

function resetTurnState() {
  userInputCount = 0;
  resetConnectionState();
}

async function onSpeechSegment(segment) {
  if (!connection?.isOpen || busy || !historySynced) return;

  busy = true;
  sendBtn.disabled = true;
  finishAssistantBubble();
  lastUserEl = appendMsg("user", "🎤 识别中…");
  setStatus("识别中…", "busy");

  try {
    const text = await transcribeAudio(segment, {
      ...getAsrConfig(),
      sampleRate: SAMPLE_RATE,
    });
    if (!text) {
      throw new Error("未识别到语音内容");
    }
    if (lastUserEl) {
      lastUserEl.textContent = text;
    }
    userInputCount += 1;
    connection.send({ uid, text, audio_input: true });
  } catch (err) {
    busy = false;
    sendBtn.disabled = false;
    lastUserEl = null;
    setStatus(err.message || "语音识别失败", "err");
    console.error(err);
  }
}

function processMicFrame(frame) {
  clientVad?.pushFrame(frame);
}

function handleSocketMessage(data) {
  if (data.type === "ready") {
    tryRequestHistorySync();
    return;
  }
  if (data.type === "history_sync") {
    handleHistorySync(data);
    return;
  }
  if (data.type === "tool_event") {
    handleToolOutbound(data);
    return;
  }
  if (data.stop_playback) {
    if (!data.uid || data.uid === uid) {
      stopPlayback();
    }
    return;
  }
  const hasPayload =
    data.question_text ||
    data.answer_text ||
    data.answer_audio ||
    data.attachments?.length ||
    data.end_flag;
  if (data.placeholder !== undefined || !hasPayload) {
    return;
  }
  handleOutbound(data);
}

async function startMic() {
  if (micOn) return;
  if (!connection?.isOpen) {
    setStatus("请先连接", "err");
    openSettings();
    return;
  }
  persistAsrConfig();
  if (!getAsrConfig().apiKey) {
    setStatus("请先填写 ASR API Key", "err");
    openSettings();
    return;
  }
  try {
    await audioCtx.resume();
    micStream = await requestMicStream();
    micContext = new AudioContext();
    const captureRate = micContext.sampleRate;
    pcmFrameBuffer = new PcmFrameBuffer();
    clientVad = new ClientVAD({
      sampleRate: SAMPLE_RATE,
      onSpeechStart,
      onSpeechSegment,
    });
    const source = micContext.createMediaStreamSource(micStream);
    micProcessor = micContext.createScriptProcessor(4096, 1, 1);
    micProcessor.onaudioprocess = (ev) => {
      if (!micOn) return;
      const raw = ev.inputBuffer.getChannelData(0);
      const pcm16k = resampleTo16k(raw, captureRate);
      pcmFrameBuffer.push(pcm16k, processMicFrame);
    };
    source.connect(micProcessor);
    micProcessor.connect(micContext.destination);
    micOn = true;
    micBtn.classList.add("active");
    setStatus("麦克风已开", "ok");
  } catch (err) {
    setStatus(err.message || "麦克风打开失败", "err");
    console.error(err);
  }
}

function stopMic() {
  micOn = false;
  clientVad?.reset();
  clientVad = null;
  pcmFrameBuffer?.reset();
  pcmFrameBuffer = null;
  micProcessor?.disconnect();
  micProcessor = null;
  micStream?.getTracks().forEach((t) => t.stop());
  micStream = null;
  if (micContext) {
    micContext.close().catch(() => {});
    micContext = null;
  }
  micBtn.classList.remove("active");
}

async function toggleMic() {
  if (micOn) stopMic();
  else await startMic();
}

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  if (statusDot) {
    statusDot.className = "status-dot" + (kind ? " " + kind : "");
  }
}

function openSettings() {
  viewSettings?.classList.add("open");
  viewSettings?.setAttribute("aria-hidden", "false");
}

function closeSettings() {
  viewSettings?.classList.remove("open");
  viewSettings?.setAttribute("aria-hidden", "true");
}

function updateEmptyState() {
  const hasMessages = chat.querySelector(".msg, .artifact-card");
  chat.classList.toggle("has-messages", !!hasMessages);
}

function handleToolOutbound(data) {
  if (data.uid && data.uid !== uid) return;
  if (!historySynced && !data.proactive) return;

  const bgPanel = getBackgroundPanel();

  if (data.scope === "agent") {
    bgPanel?.handleToolEvent(data);
    return;
  }

  handleChatToolEvent(chat, data);

  if (data.tool_name === "dispatch_task") {
    if (data.event === "start") {
      bgPanel?.noteTaskDispatched(data);
    } else if (data.event === "end" && data.task_id) {
      bgPanel?.ensureTaskSection(data.task_id, data.arguments?.subject);
    }
  }

  updateEmptyState();
  chat.scrollTop = chat.scrollHeight;
}

function clearChatMessages() {
  chat.querySelectorAll(".msg, .artifact-card, .history-notice").forEach((el) => el.remove());
  resetChatToolCards();
  updateEmptyState();
}

function clearSyncRetry() {
  if (syncRetryTimer) {
    clearTimeout(syncRetryTimer);
    syncRetryTimer = null;
  }
}

function finishHistorySync() {
  historySynced = true;
  clearSyncRetry();
  if (connection?.isOpen && !busy) {
    sendBtn.disabled = false;
    micBtn.disabled = false;
  }
  setStatus(micOn ? "麦克风已开" : "已连接", "ok");
}

function scheduleHistorySyncRetry() {
  clearSyncRetry();
  syncRetryTimer = setTimeout(() => {
    if (historySynced) return;
    if (syncAttempts >= MAX_SYNC_ATTEMPTS) {
      console.warn("历史同步超时，已允许继续对话");
      finishHistorySync();
      return;
    }
    syncAttempts += 1;
    tryRequestHistorySync();
    scheduleHistorySyncRetry();
  }, SYNC_RETRY_MS);
}

function beginHistorySync() {
  historySynced = false;
  syncAttempts = 0;
  sendBtn.disabled = true;
  setStatus("同步历史中…", "busy");
  scheduleHistorySyncRetry();
}

function tryRequestHistorySync() {
  if (!connection?.isOpen) return;
  try {
    connection.send({ type: "sync_history", uid });
  } catch (err) {
    console.warn("发送历史同步请求失败", err);
  }
}

function requestHistorySync() {
  beginHistorySync();
  tryRequestHistorySync();
}

function handleHistorySync(data) {
  if (data.uid && data.uid !== uid) return;

  clearChatMessages();
  userInputCount = data.user_input_count || 0;
  resetConnectionState();

  if (data.has_summary) {
    const notice = document.createElement("div");
    notice.className = "history-notice";
    notice.textContent = "更早的对话已压缩，助手仍保留上下文记忆";
    chat.appendChild(notice);
  }

  for (const turn of data.turns || []) {
    const role = turn.role === "user" ? "user" : "assistant";
    appendMsg(role, turn.content || "");
  }

  finishHistorySync();
  updateEmptyState();
  chat.scrollTop = chat.scrollHeight;
}

function setAssistantContent(el, rawText) {
  el._rawText = rawText;
  el.innerHTML = renderMarkdown(rawText);
}

function appendMsg(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  if (role === "assistant") {
    setAssistantContent(el, text);
  } else {
    el.textContent = text;
  }
  chat.appendChild(el);
  updateEmptyState();
  chat.scrollTop = chat.scrollHeight;
  return el;
}

function ensureAssistantBubble() {
  if (!assistantEl) {
    assistantEl = appendMsg("assistant", "");
    assistantEl.classList.add("streaming");
  }
  return assistantEl;
}

function finishAssistantBubble() {
  if (assistantEl) {
    assistantEl.classList.remove("streaming");
    assistantEl = null;
  }
}

function notifyPlaying(isPlaying) {
  if (connection?.isOpen) {
    connection.send({ uid, is_playing: isPlaying ? "true" : "false" });
  }
}

function pcmBase64ToBuffer(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const int16 = new Int16Array(bytes.buffer);
  const buf = audioCtx.createBuffer(1, int16.length, SAMPLE_RATE);
  const channel = buf.getChannelData(0);
  for (let i = 0; i < int16.length; i++) channel[i] = int16[i] / 32768;
  return buf;
}

function enqueueAudio(b64) {
  if (!b64 || !isVoicePlaybackEnabled()) return;
  audioQueue.push(pcmBase64ToBuffer(b64));
  if (!audioPlaying) playNextAudio();
}

function playNextAudio() {
  if (audioQueue.length === 0) {
    audioPlaying = false;
    notifyPlaying(false);
    return;
  }
  if (!audioPlaying) {
    audioPlaying = true;
    notifyPlaying(true);
  }
  const buffer = audioQueue.shift();
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);
  currentAudioSource = source;
  source.onended = () => {
    currentAudioSource = null;
    playNextAudio();
  };
  source.start(0);
}

function onConnectionStateChange(state) {
  if (state === VoiceConnection.State.CONNECTED) {
    resetConnectionState();
    beginHistorySync();
    tryRequestHistorySync();
    micBtn.disabled = false;
    connectBtn.textContent = "已连接";
    connectBtn.disabled = true;
    closeSettings();
  } else if (state === VoiceConnection.State.CONNECTING) {
    setStatus("连接中…", "busy");
    sendBtn.disabled = true;
    micBtn.disabled = true;
    connectBtn.textContent = "连接中…";
    connectBtn.disabled = true;
  } else {
    stopMic();
    micBtn.disabled = true;
    clearSyncRetry();
    historySynced = false;
    if (!busy) {
      setStatus("未连接", "");
      sendBtn.disabled = true;
    } else {
      setStatus("思考中…", "busy");
    }
    connectBtn.textContent = "重新连接";
    connectBtn.disabled = false;
  }
}

function finishTurn() {
  finishAssistantBubble();
  busy = false;
  sendBtn.disabled = false;
  lastUserEl = null;
  inputEl.focus();
  if (connection?.isOpen) {
    setStatus(micOn ? "麦克风已开" : "已连接", "ok");
  }
}

function getArtifactBaseUrl() {
  return artifactBaseUrlFromWs($("wsUrl").value.trim() || defaultWsUrl());
}

function handleAttachments(attachments) {
  if (!attachments?.length) return;
  appendAttachmentCards(chat, attachments, {
    onOpen: (att) => openArtifactModal(att, getArtifactBaseUrl()),
  });
  updateEmptyState();
}

function handleOutbound(data) {
  if (data.uid !== uid) return;
  if (!historySynced && !data.proactive) return;
  if (!data.proactive && data.user_input_count !== userInputCount) {
    console.warn(
      "丢弃出站消息: count 不匹配",
      "server=",
      data.user_input_count,
      "client=",
      userInputCount,
    );
    return;
  }

  if (data.proactive && !busy) {
    busy = true;
    sendBtn.disabled = false;
    finishAssistantBubble();
    setStatus("助手通知…", "busy");
  }

  if (data.question_text) {
    if (lastUserEl) {
      lastUserEl.textContent = data.question_text;
    } else {
      lastUserEl = appendMsg("user", data.question_text);
    }
    chat.scrollTop = chat.scrollHeight;
  }
  if (data.answer_text) {
    const el = ensureAssistantBubble();
    setAssistantContent(el, (el._rawText || "") + data.answer_text);
    chat.scrollTop = chat.scrollHeight;
  }
  if (data.answer_audio && data.answer_audio !== "" && data.answer_audio !== 0) {
    enqueueAudio(data.answer_audio);
  }
  if (data.attachments?.length) {
    handleAttachments(data.attachments);
  }
  if (data.end_flag) {
    finishTurn();
  }
}

function connect() {
  const url = $("wsUrl").value.trim();
  if (connection) {
    connection.disconnect();
  }
  resetConnectionState();
  connection = new VoiceConnection({
    url,
    onStateChange: onConnectionStateChange,
    onMessage: handleSocketMessage,
    onError: () => setStatus("连接错误", "err"),
  });
  connection.connect();
}

async function sendText() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (!connection?.isOpen) {
    setStatus("请先连接", "err");
    openSettings();
    return;
  }
  if (busy) {
    setStatus("请等待上一条回复", "err");
    return;
  }
  if (!historySynced) {
    tryRequestHistorySync();
    setStatus("同步历史中…", "busy");
    return;
  }

  await audioCtx.resume();
  stopPlayback();

  userInputCount += 1;
  busy = true;
  sendBtn.disabled = true;
  finishAssistantBubble();
  lastUserEl = appendMsg("user", text);
  inputEl.value = "";
  setStatus("思考中…", "busy");

  connection.send({ uid, text });
}

export function initVoiceApp() {
  initPreferences();
  initBackgroundPanel($("bgPanel"));
  $("wsUrl").value = defaultWsUrl();
  $("asrUrl").value = localStorage.getItem(ASR_URL_STORAGE) || DEFAULT_ASR_URL;
  $("asrModel").value = localStorage.getItem(ASR_MODEL_STORAGE) || DEFAULT_ASR_MODEL;
  $("asrKey").value = localStorage.getItem(ASR_KEY_STORAGE) || "";

  connectBtn.addEventListener("click", connect);
  micBtn.addEventListener("click", toggleMic);
  sendBtn.addEventListener("click", sendText);
  settingsBtn?.addEventListener("click", openSettings);
  backBtn?.addEventListener("click", closeSettings);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendText();
    }
  });
  ["asrKey", "asrUrl", "asrModel"].forEach((id) => {
    $(id)?.addEventListener("change", persistAsrConfig);
  });
  themeSegment?.querySelectorAll(".segmented-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.dataset.theme));
  });
  voicePlaybackToggle?.addEventListener("change", () => {
    persistVoicePlayback(voicePlaybackToggle.checked);
  });
  updateEmptyState();
  connect();
}

window.addEventListener("DOMContentLoaded", () => {
  initVoiceApp();
});
