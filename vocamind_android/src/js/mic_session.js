/**
 * 请求麦克风音频流，按平台选择约束并返回可读错误信息。
 */
export async function requestMicStream() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前环境不支持麦克风 API");
  }

  const isAndroid = /Android/i.test(navigator.userAgent);
  const constraints = isAndroid
    ? { audio: true, video: false }
    : {
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        video: false,
      };

  try {
    return await navigator.mediaDevices.getUserMedia(constraints);
  } catch (err) {
    throw new Error(mapMicError(err, isAndroid));
  }
}

/** 将 DOMException 映射为中文提示 */
function mapMicError(err, isAndroid) {
  const name = err?.name || "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "麦克风权限被拒绝，请在系统设置中允许";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return isAndroid
      ? "未找到麦克风：模拟器请在 Extended controls → Microphone 启用虚拟麦克风"
      : "未找到可用麦克风设备";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "麦克风被占用或无法读取，请检查模拟器/系统音频设置";
  }
  if (name === "SecurityError") {
    return "安全限制：当前页面无法访问麦克风";
  }
  return `麦克风打开失败（${name || "未知错误"}）`;
}
