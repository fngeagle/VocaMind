/**
 * 单端口 WebSocket 连接管理：状态机 + 统一收发。
 */
export class VoiceConnection {
  static State = {
    DISCONNECTED: "disconnected",
    CONNECTING: "connecting",
    CONNECTED: "connected",
  };

  /**
   * @param {object} options
   * @param {string} options.url - WebSocket 地址
   * @param {(state: string) => void} [options.onStateChange]
   * @param {(data: object) => void} [options.onMessage]
   * @param {(err: Event) => void} [options.onError]
   */
  constructor({ url, onStateChange, onMessage, onError }) {
    this.url = url;
    this.onStateChange = onStateChange || (() => {});
    this.onMessage = onMessage || (() => {});
    this.onError = onError || (() => {});
    this._ws = null;
    this._state = VoiceConnection.State.DISCONNECTED;
    this._reconnectTimer = null;
    this._manualClose = false;
  }

  get state() {
    return this._state;
  }

  get isOpen() {
    return this._ws?.readyState === WebSocket.OPEN;
  }

  _setState(next) {
    if (this._state === next) return;
    this._state = next;
    this.onStateChange(next);
  }

  connect() {
    if (this._ws?.readyState === WebSocket.OPEN || this._ws?.readyState === WebSocket.CONNECTING) {
      return;
    }
    this._manualClose = false;
    clearTimeout(this._reconnectTimer);
    this._setState(VoiceConnection.State.CONNECTING);

    const ws = new WebSocket(this.url);
    this._ws = ws;

    ws.onopen = () => {
      if (this._ws !== ws) return;
      this._setState(VoiceConnection.State.CONNECTED);
    };

    ws.onmessage = (ev) => {
      if (this._ws !== ws) return;
      try {
        const data = JSON.parse(ev.data);
        this.onMessage(data);
      } catch (_) {
        /* 忽略非 JSON */
      }
    };

    ws.onerror = (ev) => {
      if (this._ws !== ws) return;
      this.onError(ev);
    };

    ws.onclose = () => {
      if (this._ws !== ws) return;
      this._ws = null;
      this._setState(VoiceConnection.State.DISCONNECTED);
      if (!this._manualClose) {
        this._reconnectTimer = setTimeout(() => this.connect(), 2000);
      }
    };
  }

  disconnect() {
    this._manualClose = true;
    clearTimeout(this._reconnectTimer);
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._setState(VoiceConnection.State.DISCONNECTED);
  }

  send(payload) {
    if (!this.isOpen) {
      throw new Error("WebSocket 未连接");
    }
    this._ws.send(JSON.stringify(payload));
  }
}
