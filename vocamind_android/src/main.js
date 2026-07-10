import { VoiceConnection } from "./js/voice_connection.js";
import { defaultWsUrl } from "./js/ws_config.js";
import { requestMicStream } from "./js/mic_session.js";
import { PcmFrameBuffer, resampleTo16k } from "./js/audio_resample.js";
import { ClientVAD } from "./js/client_vad.js";
import { transcribeAudio, DEFAULT_ASR_URL, DEFAULT_ASR_MODEL } from "./js/client_asr.js";

const SAMPLE_RATE = 16000;
const ASR_KEY_STORAGE = "vocamind_asr_api_key";
const ASR_URL_STORAGE = "vocamind_asr_api_url";
const ASR_MODEL_STORAGE = "vocamind_asr_model";
const uid = crypto.randomUUID();

let connection = null;
let userInputCount = 0;
let busy = false;
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
const inputEl = $("input");
const sendBtn = $("sendBtn");
const connectBtn = $("connectBtn");
const micBtn = $("micBtn");

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

async function onSpeechSegment(segment) {
  if (!connection?.isOpen || busy) return;

  userInputCount += 1;
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
  if (data.stop_playback) {
    if (!data.uid || data.uid === uid) {
      stopPlayback();
    }
    return;
  }
  if (
    data.placeholder !== undefined ||
    (data.answer_text === undefined && data.answer_audio === undefined && !data.end_flag)
  ) {
    return;
  }
  handleOutbound(data);
}

async function startMic() {
  if (micOn) return;
  if (!connection?.isOpen) {
    setStatus("请先连接", "err");
    return;
  }
  persistAsrConfig();
  if (!getAsrConfig().apiKey) {
    setStatus("请先填写 ASR API Key", "err");
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
    micBtn.textContent = "🔴";
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
  micBtn.textContent = "🎤";
}

async function toggleMic() {
  if (micOn) stopMic();
  else await startMic();
}

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = "status" + (kind ? " " + kind : "");
}

function appendMsg(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  chat.appendChild(el);
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
  if (!b64) return;
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
    if (!busy) {
      setStatus(micOn ? "麦克风已开" : "已连接", "ok");
    }
    sendBtn.disabled = false;
    micBtn.disabled = false;
    connectBtn.textContent = "已连接";
  } else if (state === VoiceConnection.State.CONNECTING) {
    setStatus("连接中…", "busy");
    sendBtn.disabled = true;
    micBtn.disabled = true;
    connectBtn.textContent = "连接中";
  } else {
    stopMic();
    micBtn.disabled = true;
    if (!busy) {
      setStatus("未连接", "");
      sendBtn.disabled = true;
    } else {
      setStatus("思考中…", "busy");
    }
    connectBtn.textContent = "重连";
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

function handleOutbound(data) {
  if (data.uid !== uid) return;
  if (!data.proactive && data.user_input_count !== userInputCount) return;

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
    el.textContent += data.answer_text;
    chat.scrollTop = chat.scrollHeight;
  }
  if (data.answer_audio && data.answer_audio !== "" && data.answer_audio !== 0) {
    enqueueAudio(data.answer_audio);
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
    return;
  }

  await audioCtx.resume();
  stopPlayback();

  userInputCount += 1;
  busy = true;
  sendBtn.disabled = false;
  finishAssistantBubble();
  lastUserEl = appendMsg("user", text);
  inputEl.value = "";
  setStatus("思考中…", "busy");

  connection.send({ uid, text });
}

export function initVoiceApp() {
  $("wsUrl").value = defaultWsUrl();
  $("asrUrl").value = localStorage.getItem(ASR_URL_STORAGE) || DEFAULT_ASR_URL;
  $("asrModel").value = localStorage.getItem(ASR_MODEL_STORAGE) || DEFAULT_ASR_MODEL;
  $("asrKey").value = localStorage.getItem(ASR_KEY_STORAGE) || "";

  connectBtn.addEventListener("click", connect);
  micBtn.addEventListener("click", toggleMic);
  sendBtn.addEventListener("click", sendText);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendText();
    }
  });
  ["asrKey", "asrUrl", "asrModel"].forEach((id) => {
    $(id)?.addEventListener("change", persistAsrConfig);
  });
}

window.addEventListener("DOMContentLoaded", () => {
  initVoiceApp();
});
