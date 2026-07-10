import { concatFloat32 } from "./audio_resample.js";

/** 客户端能量 VAD：检测到静音后输出完整语音段。 */
export class ClientVAD {
  /**
   * @param {object} options
   * @param {number} [options.sampleRate]
   * @param {number} [options.frameSamples]
   * @param {number} [options.energyThreshold]
   * @param {number} [options.minSpeechMs]
   * @param {number} [options.minSilenceMs]
   * @param {() => void} [options.onSpeechStart]
   * @param {(segment: Float32Array) => void} [options.onSpeechSegment]
   */
  constructor(options = {}) {
    this.sampleRate = options.sampleRate ?? 16000;
    this.frameSamples = options.frameSamples ?? 512;
    this.energyThreshold = options.energyThreshold ?? 0.012;
    const msPerFrame = (this.frameSamples / this.sampleRate) * 1000;
    this.minSpeechFrames = Math.max(1, Math.ceil((options.minSpeechMs ?? 400) / msPerFrame));
    this.minSilenceFrames = Math.max(1, Math.ceil((options.minSilenceMs ?? 1200) / msPerFrame));
    this.onSpeechStart = options.onSpeechStart ?? (() => {});
    this.onSpeechSegment = options.onSpeechSegment ?? (() => {});
    this.reset();
  }

  reset() {
    this._inSpeech = false;
    this._speechFrames = 0;
    this._silenceFrames = 0;
    this._segment = new Float32Array(0);
    this._preRoll = [];
    this._preRollMax = 6;
  }

  _rms(frame) {
    let sum = 0;
    for (let i = 0; i < frame.length; i++) {
      sum += frame[i] * frame[i];
    }
    return Math.sqrt(sum / frame.length);
  }

  /** @param {Float32Array} frame */
  pushFrame(frame) {
    const loud = this._rms(frame) >= this.energyThreshold;

    if (!this._inSpeech) {
      this._preRoll.push(frame);
      if (this._preRoll.length > this._preRollMax) {
        this._preRoll.shift();
      }
      if (!loud) {
        this._speechFrames = 0;
        return;
      }
      this._speechFrames += 1;
      if (this._speechFrames < this.minSpeechFrames) {
        return;
      }
      this._inSpeech = true;
      this._silenceFrames = 0;
      this._segment = new Float32Array(0);
      for (const chunk of this._preRoll) {
        this._segment = concatFloat32(this._segment, chunk);
      }
      this._preRoll = [];
      this.onSpeechStart();
      return;
    }

    this._segment = concatFloat32(this._segment, frame);
    if (loud) {
      this._silenceFrames = 0;
      return;
    }

    this._silenceFrames += 1;
    if (this._silenceFrames >= this.minSilenceFrames) {
      const segment = this._segment;
      this.reset();
      if (segment.length > 0) {
        this.onSpeechSegment(segment);
      }
    }
  }
}
