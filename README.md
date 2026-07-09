# VocaMind

轻量级语音对话（Speech-to-Speech）管道，支持实时语音输入、LLM 对话、TTS 播报，以及后台 Agent 任务执行。

## 功能概览

- **实时语音对话**：WebSocket 双向通信，VAD 语音活动检测，支持用户打断
- **ASR / TTS**：通过 OpenAI 兼容 API 调用语音识别与合成（默认 SiliconFlow）
- **双 LLM 架构**：Voice LLM 负责前台对话与任务派发，Agent LLM 负责后台工具调用与任务执行
- **Web 测试页**：内置 `frontend/index.html`，可在浏览器中快速体验语音对话
- **可配置管道**：ASR、TTS、LLM 模型与 API 均可通过环境变量或命令行参数调整

## 环境要求

- Python 3.10+
- 可用的 LLM API（OpenAI 兼容，如 DeepSeek、火山引擎等）
- ASR/TTS API Key（如 [SiliconFlow](https://siliconflow.cn/)）

## 快速开始

### 1. 克隆仓库

```bash
git clone git@github.com:fngeagle/VocaMind.git
cd VocaMind
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制示例配置并填入你的 API Key：

```bash
cp .env.example .env
```

主要变量说明：

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` | 对话 LLM 的 API Key |
| `LLM_API_URL` | LLM 接口地址，如 `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称，如 `deepseek-chat` |
| `ASR_TTS_API_KEY` | ASR/TTS 服务的 API Key |
| `AGENT_LLM_API_KEY` | 后台 Agent 的 API Key（可选，默认回落到 `LLM_API_KEY`） |

> **注意**：`.env` 含敏感信息，已在 `.gitignore` 中排除，请勿提交到仓库。

### 4. （可选）配置 TTS 参考音色

在 `ref_audio/` 目录下放置参考音频与 `ref.json`：

```json
[
  {
    "ref_wav_path": "ref_audio_3.wav",
    "prompt_text": "参考音频对应的文本内容"
  }
]
```

### 5. 启动服务

```bash
python main.py
```

默认监听 `0.0.0.0:9001`。常用参数：

```bash
python main.py --ws-port 9001 --reply-mode audio --no-interruption
```

### 6. 打开 Web 测试页

用浏览器打开 `frontend/index.html`，将 WebSocket 地址设为 `ws://localhost:9001`，即可开始语音对话。

## 项目结构

```
VocaMind/
├── main.py              # 命令行入口
├── vocamind/
│   ├── gateway/         # WebSocket 网关、VAD、会话管理
│   ├── asr/             # 语音识别
│   ├── tts/             # 语音合成
│   ├── llm/             # LLM 流式调用
│   ├── voice/           # 前台 Voice 对话逻辑
│   ├── agent/           # 后台 Agent 执行
│   ├── pipeline/        # 管道组装与调度
│   ├── tasks/           # 任务队列与存储
│   ├── memory/          # 会话记忆
│   └── tools/           # Agent 工具集
├── frontend/            # Web 测试界面
├── ref_audio/           # TTS 参考音色
├── tests/               # 单元测试
└── .env.example         # 环境变量示例
```

## 运行测试

```bash
pytest tests/
```

## 许可证

本项目仅供学习与研究使用。使用前请确保遵守各 API 服务商的使用条款。
