/**
 * 根据运行环境推断默认 WebSocket 地址。
 * - Android 模拟器：10.0.2.2 映射宿主机 localhost
 * - 桌面浏览器 / Tauri 桌面：localhost
 * - 真机：需改为电脑局域网 IP，保留 UI 可编辑
 */
export function defaultWsUrl() {
  const ua = navigator.userAgent || "";
  if (/Android/i.test(ua)) {
    return "ws://10.0.2.2:9001";
  }
  return "ws://localhost:9001";
}
