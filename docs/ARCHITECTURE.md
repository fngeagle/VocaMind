# VocaMind 架构文档

本文档描述 VocaMind 语音对话系统的整体架构、功能模块划分，以及核心业务流程的时序交互。

---

## 1. 系统架构图

VocaMind 采用**客户端语音处理 + 后台对话编排**的分层架构。语音识别（ASR）与语音活动检测（VAD）在客户端完成，后台专注于对话推理、语音合成与 Agent 任务执行。

```mermaid
flowchart TB
    subgraph Client["客户端（Web / Tauri Android）"]
        MIC["麦克风"]
        VAD["ClientVAD<br/>能量检测切段"]
        ASR["Client ASR<br/>SiliconFlow API"]
        UI["对话 UI"]
        PLAY["音频播放"]
        WS_C["VoiceConnection<br/>WebSocket 客户端"]
    end

    subgraph Backend["后台（python main.py）"]
        GW["WebSocket Gateway<br/>:9001 单端口"]
        IN["InboundRouter<br/>入站文本路由"]
        OUT["OutboundDispatcher<br/>出站推送"]

        subgraph Pipeline["处理管道（多线程队列）"]
            VOICE["VoiceOrchestratorHandler<br/>前台 Voice LLM"]
            TTS_H["APITTSHandler<br/>语音合成"]
        end

        subgraph AgentLayer["Agent 后台"]
            AQ["AgentTaskQueue<br/>任务队列"]
            AR["AgentRuntime<br/>Daemon 线程"]
            TOOLS["内置工具集<br/>shell / 文件 / MCP / cron"]
        end

        subgraph Storage["持久化"]
            MEM_S[".memory/sessions<br/>对话记忆"]
            MEM_C[".memory/core<br/>长期记忆"]
            TASKS[".tasks/<br/>任务状态"]
            LOGS[".conversations/<br/>对话日志"]
        end
    end

    subgraph Cloud["云端 API"]
        ASR_API["ASR API<br/>SiliconFlow"]
        LLM_API["LLM API<br/>DeepSeek 等"]
        TTS_API["TTS API<br/>SiliconFlow"]
    end

    MIC --> VAD
    VAD --> ASR
    ASR --> ASR_API
    ASR -->|"{ text, audio_input }"| WS_C
    UI -->|"{ text }"| WS_C
    WS_C <-->|"JSON over WebSocket"| GW

    GW --> IN
    IN -->|text_prompt_queue| VOICE
    VOICE --> LLM_API
    VOICE -->|dispatch_task| AQ
    AQ --> AR
    AR --> LLM_API
    AR --> TOOLS
    VOICE -->|lm_response_queue| TTS_H
    TTS_H --> TTS_API
    TTS_H -->|outbound_queue| OUT
    OUT --> GW
    GW --> WS_C
    WS_C --> PLAY
    WS_C --> UI

    VOICE --> MEM_S
    VOICE --> MEM_C
    AR --> TASKS
    VOICE --> LOGS
    AR --> LOGS
    AR -->|任务完成通知| AQ
    AQ -->|proactive 推送| VOICE
```

### 架构要点

| 层级 | 职责 | 技术 |
|------|------|------|
| 客户端 | 采集音频、VAD 切段、ASR 转文字、播放 TTS、WebSocket 通信 | JS / Tauri WebView |
| 网关 | 单活跃连接管理、入站/出站 JSON 路由、打断信号 | `websockets` |
| Voice 管道 | 对话推理、工具调用（派发任务/查状态/记忆）、流式回复 | OpenAI 兼容 LLM |
| Agent 后台 | 异步执行复杂任务（文件、命令、MCP 等） | 独立 Daemon 线程 |
| 云端 | ASR（客户端）、LLM、TTS（后台） | SiliconFlow / DeepSeek 等 |

---

## 2. 功能模块图

按代码包划分的功能模块及其依赖关系。

```mermaid
flowchart LR
    subgraph Entry["入口"]
        MAIN["main.py"]
        FE["frontend/"]
        AND["vocamind_android/"]
    end

    subgraph Core["vocamind.common"]
        CFG["config.py<br/>PipelineConfig"]
        HND["handler.py<br/>ThreadManager"]
        MSG["messages.py"]
        AUDIO["audio.py"]
    end

    subgraph Gateway["vocamind.gateway"]
        SRV["server.py<br/>WebSocketGateway"]
        INB["inbound.py<br/>InboundRouter"]
        OTB["outbound.py<br/>OutboundDispatcher"]
        SES["session.py"]
        SIG["session_signals.py"]
    end

    subgraph Voice["vocamind.voice"]
        VH["handler.py<br/>VoiceOrchestrator"]
        VS["steps.py<br/>对话轮次"]
        VT["tools.py<br/>dispatch_task 等"]
        VP["prompt.py"]
    end

    subgraph LLM["vocamind.llm"]
        TC["tool_client.py"]
        SS["stream_steps.py"]
        API["openai_api.py"]
    end

    subgraph Agent["vocamind.agent"]
        RUN["runner.py<br/>Agent Loop"]
        STP["steps.py"]
        BLD["builder.py"]
    end

    subgraph Tasks["vocamind.tasks"]
        QUE["queue.py"]
        STO["store.py"]
    end

    subgraph Memory["vocamind.memory"]
        DSS["session_store.py"]
        CMS["core_store.py"]
    end

    subgraph TTS["vocamind.tts"]
        TAPI["api.py<br/>APITTSHandler"]
        VPF["voice_profile.py"]
    end

    subgraph Pipeline["vocamind.pipeline"]
        BLD_P["builder.py"]
        FAC["factories.py"]
        CTX["state.py<br/>PipelineContext"]
        NOT["notification.py"]
        INT["interruption.py"]
    end

    subgraph Tools["vocamind.tools"]
        BLN["builtin.py"]
        MCP["mcp.py"]
        CRN["cron.py"]
        BG["background.py"]
    end

    MAIN --> BLD_P
    FE --> SRV
    AND --> SRV

    BLD_P --> FAC
    FAC --> SRV
    FAC --> VH
    FAC --> TAPI

    SRV --> INB
    SRV --> OTB
    INB --> VH
    VH --> TC
    VH --> VT
    VT --> QUE
    VH --> DSS
    VH --> CMS
    VH --> TAPI
    TAPI --> OTB
    OTB --> SRV

    QUE --> RUN
    RUN --> STP
    RUN --> STO
    RUN --> BLN
    RUN --> MCP
    RUN --> NOT
    NOT --> VH

    CFG --> BLD_P
    HND --> BLD_P
    CTX --> FAC
```

### 模块职责一览

| 模块 | 核心类/文件 | 功能 |
|------|------------|------|
| `gateway` | `WebSocketGateway` | WebSocket 服务，管理单活跃客户端连接 |
| `gateway` | `InboundRouter` | 解析入站 JSON，写入 `text_prompt_queue` |
| `gateway` | `OutboundDispatcher` | 从 `outbound_queue` 取消息推送给客户端 |
| `voice` | `VoiceOrchestratorHandler` | 前台对话 LLM，可派发任务、维护记忆 |
| `voice` | `VOICE_TOOLS` | `dispatch_task` / `list_tasks` / `query_status` / `core_memory_*` |
| `agent` | `AgentRuntime` | 后台 Daemon，消费任务队列，执行完整 tool loop |
| `tasks` | `AgentTaskQueue` | 任务入队、完成通知、主动推送给 Voice |
| `memory` | `DialogueSession` | 当前会话短期对话记忆 |
| `memory` | `CoreMemoryStore` | 跨会话长期用户画像 |
| `tts` | `APITTSHandler` | 将 LLM 流式文本逐句合成音频 |
| `pipeline` | `PipelineContext` | 跨节点共享的队列与事件（打断、会话生命周期） |

### 管道队列数据流

```mermaid
flowchart LR
    IN["InboundRouter"] -->|text_prompt_queue| VOICE["Voice LLM"]
    VOICE -->|lm_response_queue| TTS["TTS Handler"]
    TTS -->|outbound_queue| OUT["OutboundDispatcher"]
    NOT["任务通知"] -->|text_prompt_queue| VOICE
```

---

## 3. 功能时序图

### 3.1 语音对话主流程

用户开麦说话，客户端完成 VAD + ASR 后发送文字，后台 LLM 推理并 TTS 播报。

```mermaid
sequenceDiagram
    actor User as 用户
    participant MIC as 麦克风
    participant VAD as ClientVAD
    participant ASR as ASR API
    participant WS as WebSocket 客户端
    participant GW as WebSocket Gateway
    participant IN as InboundRouter
    participant VOICE as Voice LLM
    participant LLM as LLM API
    participant TTS as TTS Handler
    participant TAPI as TTS API
    participant OUT as OutboundDispatcher

    User->>MIC: 说话
    MIC->>VAD: PCM 音频帧
    VAD->>VAD: 检测语音开始
    Note over VAD: 若正在播放，停止播报
    VAD->>VAD: 检测静音 ≥ 1.2s
    VAD->>ASR: 完整语音段
    ASR-->>VAD: 识别文本
    VAD->>WS: 显示「识别中…」
    WS->>GW: { uid, text, audio_input: true }
    GW->>IN: 解析 JSON
    IN->>IN: 检查打断（助手是否在说话）
    IN->>VOICE: text_prompt_queue.put(text)
    IN-->>WS: { placeholder: "" }

    VOICE->>LLM: 流式对话请求（含记忆/工具）
    loop 流式输出
        LLM-->>VOICE: delta token
        VOICE->>TTS: lm_response_queue（句子片段）
        TTS->>TAPI: 合成音频
        TAPI-->>TTS: PCM 音频
        TTS->>OUT: outbound_queue
        OUT->>GW: 推送 JSON
        GW-->>WS: { answer_text, answer_audio }
        WS->>User: 显示文字 + 播放音频
    end
    VOICE->>OUT: { end_flag: true }
    OUT-->>WS: 轮次结束
```

### 3.2 文字输入流程

用户直接输入文字，跳过客户端 ASR。

```mermaid
sequenceDiagram
    actor User as 用户
    participant UI as 对话 UI
    participant WS as WebSocket 客户端
    participant IN as InboundRouter
    participant VOICE as Voice LLM
    participant TTS as TTS Handler
    participant OUT as OutboundDispatcher

    User->>UI: 输入文字并发送
    UI->>WS: 显示用户消息
    WS->>IN: { uid, text }
    IN->>IN: 打断检查
    IN->>VOICE: text_prompt_queue
    IN-->>WS: { placeholder: "" }

    VOICE->>VOICE: LLM 推理 + 流式输出
    VOICE->>TTS: 句子片段
    TTS->>OUT: 文本/音频块
    OUT-->>WS: 流式推送
    WS->>UI: 更新助手气泡
```

### 3.3 Agent 任务派发与完成通知

用户请求后台执行任务（如跑测试、读写文件），Voice 派发任务，Agent 异步执行完成后主动通知用户。

```mermaid
sequenceDiagram
    actor User as 用户
    participant WS as 客户端
    participant VOICE as Voice LLM
    participant LLM as LLM API
    participant AQ as AgentTaskQueue
    participant AR as Agent Runtime
    participant TOOLS as Agent 工具
    participant NOT as notification.py
    participant TTS as TTS Handler

    User->>WS: "帮我跑一下测试"
    WS->>VOICE: { text: "帮我跑一下测试" }

    VOICE->>LLM: 对话 + tools
    LLM-->>VOICE: tool_call: dispatch_task
    VOICE->>AQ: 创建任务并入队
    VOICE-->>WS: "好的，我去跑测试"（流式回复）

    par Agent 后台异步执行
        AQ->>AR: claim_task
        AR->>LLM: Agent LLM + 工具循环
        loop tool loop
            AR->>TOOLS: shell / 文件 / ...
            TOOLS-->>AR: 执行结果
        end
        AR->>AQ: notify_complete(task_id, summary)
    end

    AQ->>NOT: TaskNotification
    NOT->>NOT: 打断当前轮次（若在说话）
    NOT->>VOICE: proactive 消息入队
    VOICE->>LLM: 生成任务完成播报
    VOICE->>TTS: 合成语音
    TTS-->>WS: 主动推送任务结果
    WS->>User: "测试跑完了，全部通过"
```

### 3.4 用户打断流程

助手正在播报时，用户再次说话触发打断。

```mermaid
sequenceDiagram
    actor User as 用户
    participant VAD as ClientVAD
    participant WS as 客户端
    participant IN as InboundRouter
    participant VOICE as Voice LLM
    participant TTS as TTS Handler
    participant OUT as OutboundDispatcher

    Note over VOICE,TTS: 助手正在流式输出 + TTS 播报

    User->>VAD: 开始说话
    VAD->>WS: stopPlayback()
    VAD->>VAD: 切段 → ASR → 文本
    WS->>IN: { text, audio_input: true }

    IN->>IN: assistant_turn_active == true
    IN->>IN: trigger_interruption_queues()
    Note over VOICE,TTS: 清空 lm_response / outbound 积压
    IN-->>WS: { stop_playback: true }

    VOICE->>VOICE: 输出打断过渡语
    Note over VOICE: "好，稍等一下。"
    VOICE->>VOICE: 处理新用户输入
    VOICE->>TTS: 新的回复流
    TTS-->>WS: 新一轮播报
```

### 3.5 WebSocket 连接生命周期

```mermaid
sequenceDiagram
    participant WS as 客户端
    participant GW as WebSocketGateway
    participant SL as SessionLifecycle
    participant OUT as OutboundDispatcher

    WS->>GW: 连接 ws://host:9001
    GW->>GW: claim_connection（关闭旧连接）
    GW->>SL: signal_connect()
    GW-->>WS: { type: "ready" }

    loop 对话
        WS->>GW: 入站消息
        GW-->>WS: 出站回复
    end

    WS->>GW: 断开连接
    GW->>SL: signal_disconnect()
    Note over SL: flush_requested 置位<br/>各 Handler 清空队列积压
```

---

## 4. WebSocket 协议摘要

### 4.1 客户端 → 后台（入站）

| 字段 | 类型 | 说明 |
|------|------|------|
| `uid` | string | 会话唯一标识（客户端生成 UUID） |
| `text` | string | 用户输入文字（ASR 结果或键盘输入） |
| `audio_input` | bool | `true` 表示来自语音输入，后台会回显 `question_text` |
| `is_playing` | string | `"true"` / `"false"`，告知后台客户端是否在播放音频 |
| `audio` | string | **已废弃**，后台会忽略并打日志 |

### 4.2 后台 → 客户端（出站）

| 字段 | 类型 | 说明 |
|------|------|------|
| `uid` | string | 会话标识 |
| `user_input_count` | int | 用户输入轮次序号 |
| `question_text` | string | 用户问题文本（语音输入时回显） |
| `answer_text` | string | 助手回复文本片段（流式追加） |
| `answer_audio` | string | Base64 编码的 PCM 音频（16kHz） |
| `end_flag` | bool | `true` 表示本轮对话结束 |
| `stop_playback` | bool | `true` 表示立即停止音频播放 |
| `proactive` | bool | `true` 表示后台主动推送（如任务完成通知） |
| `placeholder` | string | 空 ACK，表示入站消息已收到 |

---

## 5. 部署拓扑

```mermaid
flowchart LR
    subgraph DevMachine["开发机 / 服务器"]
        PY["python main.py<br/>:9001"]
        ENV[".env<br/>LLM + TTS Key"]
    end

    subgraph Devices["客户端设备"]
        WEB["浏览器<br/>frontend/index.html"]
        APK["Android<br/>vocamind_android"]
    end

    subgraph APIs["云端"]
        SF["SiliconFlow<br/>ASR + TTS"]
        DS["DeepSeek 等<br/>LLM"]
    end

    WEB -->|ASR Key 本地配置| SF
    APK -->|ASR Key 本地配置| SF
    WEB <-->|WebSocket| PY
    APK <-->|WebSocket| PY
    PY --> ENV
    PY --> DS
    PY --> SF
```

| 组件 | 默认地址 | API Key 配置位置 |
|------|---------|-----------------|
| 后台 WebSocket | `ws://0.0.0.0:9001` | — |
| LLM | `.env` → `LLM_API_KEY` | 后台 |
| TTS | `.env` → `ASR_TTS_API_KEY` | 后台 |
| ASR | SiliconFlow transcriptions | **客户端**设置页 |
| Android 模拟器 WS | `ws://10.0.2.2:9001` | 客户端 |
| 真机 WS | `ws://<电脑局域网IP>:9001` | 客户端 |

---

## 6. 线程模型

后台启动后运行 4 个并发线程（`ThreadManager`）：

```mermaid
flowchart TB
    TM["ThreadManager"]
    TM --> T1["Gateway 线程<br/>asyncio event loop"]
    TM --> T2["Voice LLM 线程<br/>消费 text_prompt_queue"]
    TM --> T3["TTS 线程<br/>消费 lm_response_queue"]
    TM --> T4["Agent Daemon 线程<br/>消费 task_queue"]

    T1 --> T1A["InboundRouter.run_loop"]
    T1 --> T1B["OutboundDispatcher.run"]
```

各线程通过 `queue.Queue` 传递消息，通过 `threading.Event` 协调打断与会话 flush。

---

*文档版本：与 `f05996a`（ASR 客户端化）同步*
