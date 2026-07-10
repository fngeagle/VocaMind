/** 后端 VAD 单帧采样点数（16kHz × 512 samples = 2048 bytes） */
export const VAD_FRAME_SAMPLES = 512;

const TARGET_RATE = 16000;

/**
 * 将 float32 PCM 从源采样率重采样到 16kHz（线性插值抽取）。
 */
export function resampleTo16k(input, sourceSampleRate) {
  if (sourceSampleRate === TARGET_RATE) {
    return input;
  }
  const ratio = sourceSampleRate / TARGET_RATE;
  const outLen = Math.floor(input.length / ratio);
  if (outLen <= 0) {
    return new Float32Array(0);
  }
  const output = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const s0 = input[idx] ?? 0;
    const s1 = input[Math.min(idx + 1, input.length - 1)];
    output[i] = s0 + (s1 - s0) * frac;
  }
  return output;
}

/** 拼接两段 float32 音频 */
export function concatFloat32(a, b) {
  if (!a?.length) return b ?? new Float32Array(0);
  if (!b?.length) return a;
  const out = new Float32Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

/**
 * 按固定帧对齐缓冲，攒够整帧再回调。
 */
export class PcmFrameBuffer {
  constructor(frameSamples = VAD_FRAME_SAMPLES) {
    this.frameSamples = frameSamples;
    this._pending = new Float32Array(0);
  }

  /** @param {Float32Array} samples @param {(frame: Float32Array) => void} sendFrame */
  push(samples, sendFrame) {
    this._pending = concatFloat32(this._pending, samples);
    while (this._pending.length >= this.frameSamples) {
      const frame = this._pending.subarray(0, this.frameSamples);
      sendFrame(frame);
      this._pending = this._pending.subarray(this.frameSamples);
    }
  }

  reset() {
    this._pending = new Float32Array(0);
  }
}
