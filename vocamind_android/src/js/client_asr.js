const DEFAULT_ASR_URL = "https://api.siliconflow.cn/v1/audio/transcriptions";
const DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall";

/** float32 PCM → 16-bit WAV Blob */
export function encodeWavBlob(samples, sampleRate = 16000) {
  const numChannels = 1;
  const bitsPerSample = 16;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * blockAlign;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    const val = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(offset, val, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

/**
 * 调用云端 ASR，将语音段转为文本。
 * @param {Float32Array} samples
 * @param {object} options
 */
export async function transcribeAudio(samples, options = {}) {
  const apiKey = options.apiKey?.trim();
  if (!apiKey) {
    throw new Error("请填写 ASR API Key");
  }
  const apiUrl = options.apiUrl?.trim() || DEFAULT_ASR_URL;
  const model = options.model?.trim() || DEFAULT_ASR_MODEL;
  const sampleRate = options.sampleRate ?? 16000;

  const wav = encodeWavBlob(samples, sampleRate);
  const form = new FormData();
  form.append("file", wav, "audio.wav");
  form.append("model", model);

  const response = await fetch(apiUrl, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`ASR 请求失败 (${response.status}): ${detail.slice(0, 120)}`);
  }
  const data = await response.json();
  return (data.text || "").trim();
}

export { DEFAULT_ASR_URL, DEFAULT_ASR_MODEL };
