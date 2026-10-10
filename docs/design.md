# AI 视听感知 —— 设计文档

> 定位：给「没有视频/音频能力」的纯文本大模型，装上一副本地「眼睛和耳朵」——**多摄像头连续录制 + 片段级时序理解 + 随时问答**。
> 版本 v0.2 · 2026-10-11 · 状态：待评审

## 1. 目标与范围

### 1.1 目标（Goals）

- **G1 多路连续采集**：多摄像头并行，**每路完整连续录制（不丢帧）** + 麦克风，数据不出本机。
- **G2 能听**：音频经 faster-whisper 转写为带时间戳的文字记录。
- **G3 能看（静态 + 动态）**：从录制流抽关键帧建索引；**对视频片段做时序理解**（描述「发生了什么动作」，而非孤立单帧）。
- **G4 能查**：对已记录内容按「关键词 + 时间范围 + 摄像头」检索。
- **G5 能答**：向文本 LLM（qwen2.5）提问，基于检索到的记录作答。

### 1.2 验收标准（Acceptance Criteria）

- **AC1** 录一段含人声的视频，能按关键词检索到对应转写片段，时间误差 < 1s。
- **AC2** 提问「刚才发生了什么」，LLM 答案能回溯到具体记录（不编造）。
- **AC3** 全程不访问外网（模型、存储、推理均本地）。
- **AC4** 8GB 显存下多路持续运行 ≥ 10 分钟不 OOM、不崩溃。
- **AC5 录制不丢帧**：录制时长 ≈ 视频段覆盖的总时长；快速动作可事后回看（连续录制，非抽帧）。
- **AC6 时序理解**：对一段含动作的视频片段，能描述「发生了什么动作」（多帧序列级，非单帧）。

### 1.3 边界与非目标（明确不做 / 明确边界）

**边界说明（必须清楚）**：本项目做**「连续完整录制 + 片段级时序理解」**——录制端是真正连续的（不丢帧）；理解端是「视频片段 → 抽帧序列 → VLM 时序建模」。**「绝对像人眼一样连续感知」任何现有 AI 都做不到**（Gemini Live、Qwen-Omni 内部同样抽帧建模），这是行业现状，本项目也不承诺。

- 不做实时低延迟对话 / TTS 语音合成（本系统是「记录 + 事后问答」）。
- 不做说话人分离 / 人脸识别 / 物体追踪（后续可加）。
- 不做云存储 / 多用户。
- 不直接商用（screenpipe 许可证约束，见 §11）。

## 2. 架构总览

五层单向数据流，层间用队列/函数调用解耦，每层可独立替换：

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  采集     │ → │  感知     │ → │  存储     │ → │  检索     │ → │  问答     │
│ capture  │   │ perceive │   │  store   │   │ retrieve │   │   qa     │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
 多摄像头/麦克风   ASR/时序理解   SQLite+FTS5    FTS5 查询     Ollama LLM
```

- **采集**：每路摄像头一个录制线程，连续录 mp4 分段落盘（不丢帧）；麦克风采集音频。
- **感知**：音频 → 转写；视频段 → 抽关键帧 + 片段级时序理解。
- **存储**：摄像头、视频段、转写、关键帧、时序分析，统一落 SQLite（单库 + FTS5）。
- **检索**：FTS5 关键词 + 时间范围 + 摄像头过滤，取回相关记录。
- **问答**：检索结果拼成上下文，交给文本 LLM 作答。

### 数据流（时序）

```
每路摄像头 ──ffmpeg 连续录制──▶ video_segments 表 + data/media/*.mp4（分段落盘，不丢帧）
                                 │ 定时抽帧
                                 ▼
                          frames 表 + data/media/*.jpg（关键帧索引/缩略图）
麦克风 ──连续采集──▶ 音频块 ──faster-whisper──▶ transcriptions 表（FTS5）

时序理解（查询时/后台定时）：video_segments 取一段 [start,end]
  ──ffmpeg 抽多帧序列──▶ 按时间顺序多图喂 qwen2.5-VL ──▶ clip_analyses 表（「发生了什么」）

提问 ──▶ FTS5(转写+时序分析) + 时间/摄像头过滤 + 关键帧 ──▶ 拼上下文 ──▶ qwen2.5 ──▶ 回答
```

## 3. 组件设计

每个组件一个职责、一个清晰接口、明确依赖；全部通过注入的 config 取参数，无全局可变状态。

| 组件 | 模块 | 职责 | 关键接口 | 依赖 |
|---|---|---|---|---|
| 视频录制 | `capture/recorder.py` | 每路摄像头连续录 mp4 分段落盘；抽关键帧 | `class CameraRecorder`（`camera_id`、`start()`、`stop()`） | ffmpeg / cv2 |
| 音频采集 | `capture/audio.py` | 从麦克风/文件采集，产出 AudioChunk | `class AudioSource` / `MicAudioSource` / `FileAudioSource` | sounddevice |
| 语音感知 | `perception/asr.py` | 音频块 → 转写段 | `transcribe(chunk) -> Transcription` | faster-whisper |
| 时序理解 | `perception/clip_analyzer.py` | 视频片段 → 多帧序列 → 动态描述 | `analyze_clip(camera_id, start_ms, end_ms) -> str` | ffmpeg + Ollama(qwen2.5-VL) |
| 存储 | `store/db.py` | 建表 / 写入 / FTS | `insert_*` 系列 | sqlite3 |
| 检索 | `retrieve/search.py` | 关键词 + 时间 + 摄像头检索 | `search(q, start, end, camera_id)` | store |
| 问答 | `qa/ask.py` | 组装上下文 + 调 LLM | `answer(question, records) -> str` | Ollama(qwen2.5) |
| 编排 | `app.py` | 起多路线程、队列、REPL | `main()` | 以上全部 |

**Source 抽象（关键设计）**：`VideoSource` / `AudioSource` 抽象成「产出带时间戳的帧/块」。生产环境 = 摄像头/麦克风；测试/回放 = 文件，下游逻辑复用，可离线回归。多摄像头 = 配置里声明多路 `CameraRecorder`，各自独立线程、各自 `camera_id`。

## 4. 数据模型（SQLite 单库）

> **时间标准（全项目唯一约定）**：所有时间戳用 **UTC epoch 毫秒 INTEGER** 存储，另存 ISO8601 文本便于人读。跨表、跨模块、跨函数一律遵守，不做本地时区换算。

```sql
-- 摄像头（多路）
CREATE TABLE cameras (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,            -- 配置名，如 front_door
  source     TEXT NOT NULL,            -- 设备索引 或 RTSP/RTMP URL
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 连续视频段（每路摄像头连续录制，分段落盘，不丢帧）
CREATE TABLE video_segments (
  id         INTEGER PRIMARY KEY,
  camera_id  INTEGER NOT NULL REFERENCES cameras(id),
  start_ms   INTEGER NOT NULL,
  end_ms     INTEGER NOT NULL,
  file_path  TEXT NOT NULL,            -- 相对 data/media 的 mp4 路径
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_seg_cam_ts ON video_segments(camera_id, start_ms);

-- 音频转写（每路可选麦克风/音轨）
CREATE TABLE transcriptions (
  id         INTEGER PRIMARY KEY,
  camera_id  INTEGER,                  -- 关联摄像头；NULL = 独立麦克风
  start_ms   INTEGER NOT NULL,
  end_ms     INTEGER NOT NULL,
  text       TEXT NOT NULL,
  device     TEXT NOT NULL DEFAULT 'mic',
  model      TEXT NOT NULL DEFAULT 'faster-whisper',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_trans_start ON transcriptions(start_ms);
CREATE VIRTUAL TABLE transcriptions_fts USING fts5(text, tokenize='trigram');

-- 关键帧（从视频段抽取的索引帧/缩略图）
CREATE TABLE frames (
  id               INTEGER PRIMARY KEY,
  camera_id        INTEGER NOT NULL REFERENCES cameras(id),
  video_segment_id INTEGER NOT NULL REFERENCES video_segments(id),
  captured_ms      INTEGER NOT NULL,
  offset_ms        INTEGER NOT NULL,   -- 在视频段内的偏移，便于回看
  file_path        TEXT NOT NULL,      -- 相对 data/media 的 jpg 路径
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_frames_cam_ts ON frames(camera_id, captured_ms);

-- 时序分析（把一段视频片段喂 VLM 得到的「动态理解」）
CREATE TABLE clip_analyses (
  id         INTEGER PRIMARY KEY,
  camera_id  INTEGER NOT NULL REFERENCES cameras(id),
  start_ms   INTEGER NOT NULL,
  end_ms     INTEGER NOT NULL,
  summary    TEXT NOT NULL,            -- 「这段时间发生了什么」
  model      TEXT NOT NULL,            -- 记录用了哪个 VLM
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_clip_cam_ts ON clip_analyses(camera_id, start_ms);
CREATE VIRTUAL TABLE clip_analyses_fts USING fts5(summary, tokenize='trigram');

-- 事件（系统状态 / 汇总 / 问答记录，可选扩展）
CREATE TABLE events (
  id      INTEGER PRIMARY KEY,
  ts_ms   INTEGER NOT NULL,
  kind    TEXT NOT NULL,               -- 'system' | 'summary' | 'qa'
  payload TEXT NOT NULL
);
```

> 注：FTS 索引在 `insert_*` 内手动同步（trigram 支持中文检索）。

## 5. 实时性与性能（8GB 显存调度）

### 5.1 连续录制（不丢帧）

- 每路摄像头用 ffmpeg 连续录 H.264 mp4，**分段**（如 60s 一段）落盘，硬件编码（5060 有 NVENC）降 CPU 占用。
- 关键帧由录制流定时抽取（仅作索引/缩略图，不影响原始视频完整性）。
- 磁盘预算：单路 1080p@H.264 ≈ 每分钟几十 MB，多路按倍数估算；保留策略（滚动删除旧段）实现阶段定。

### 5.2 理解端调度（8GB）

- **faster-whisper 跑 CPU**（模型 `small`），不占显存，与 Ollama 解耦。
- **文本模型 qwen2.5:7b 常驻 GPU**（问答高频入口）。
- **视觉模型 qwen2.5-VL:7b 按需加载**：时序理解/看图时才换载，产生 ~秒级加载延迟。
- **时序理解是「片段级 + 按需/定时」，不是全路实时连续理解**——后者 8GB 跑不动，也与「记录+问答」定位不符。录制连续、理解按片段。

### 5.3 采样参数（可配置，默认值）

- 视频录制：全帧率连续录（不抽帧）；关键帧索引：每 ~1s 抽 1 帧。
- 时序理解：查询时按需取片段，抽 N 帧（如每 1s 1 帧、最多 8~16 帧）按时间顺序多图喂 VLM。
- 音频：每 ~6s 窗口转写一次；16kHz 单声道。

## 6. 配置与接口

`config.yaml`（示例，所有参数可配置、不硬编码）：

```yaml
cameras:                      # 多路，每路一个 camera_id
  - id: 1
    name: front_door
    source: 0                 # cv2 设备号 或 rtsp://... 
  - id: 2
    name: warehouse
    source: rtsp://192.168.1.10/live
recording:
  segment_sec: 60             # 视频分段长度
  codec: h264
audio:
  source: mic                 # mic | file
  device: null
  sample_rate: 16000
  window_sec: 6
whisper:
  model: small                # tiny/base/small/medium
  device: cpu
ollama:
  host: http://localhost:11434
  vlm: qwen2.5vl:7b
  llm: qwen2.5:7b
storage:
  db: data/audiovisual.sqlite
  media_dir: data/media
```

CLI（MVP）：

```
python app.py record              # 启动所有摄像头录制 + 音频转写，Ctrl+C 停
python app.py ask "1号摄像头刚才发生了什么"   # 单次提问
python app.py repl                # 交互式：后台录制 + 随时提问
python app.py analyze 1 10:00-10:30  # 手动触发某摄像头的时序分析
python app.py summary 10:00-10:30 # （可选）时间范围小结
```

## 7. 错误处理

- **设备不可用**（某路摄像头被占用/离线）：该路降级停录、其余照常，通过 `events(kind='system')` 记录，不崩整体。
- **ASR / LLM / VLM 出错**：指数退避重试 3 次，仍失败则记 `events` 并跳过，不中断录制。
- **存储满 / 写失败**：警告 + 滚动删除最旧视频段（保留策略），不静默丢转写数据。
- **模型加载失败**：明确报错「qwen2.5-VL 未安装，请 ollama pull」，退出问答而非崩进程。

## 8. 测试策略

- **单测**：`store/db.py`（schema/FTS5 trigram 手动同步）、时间解析、多摄像头路由。
- **集成**：`FileVideoSource` + `FileAudioSource` 喂带音频的 mp4 夹具，跑「文件→录制分段→转写→落库→检索→问答」全链路；问答用真实 Ollama 或 `MockLLM` 验证上下文拼装。
- **时序理解验收**：对一段含明显动作的夹具视频，验证 `clip_analyses.summary` 能描述动作序列（AC6）。
- **不丢帧验收**：录制 1 分钟，校验 `video_segments` 覆盖时长 ≈ 60s（AC5）。
- 夹具放 `tests/fixtures/`，大文件不入库（.gitignore）。

## 9. 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M0 本阶段** | 设计文档 v0.2 + 目录骨架 + git init + 依赖确认 | 本文档评审通过 |
| **M1 连续录制 + 能听** | 单路 ffmpeg 连续录制分段 + ASR 转写落库 + FTS5 | 录制不丢帧（AC5）；关键词搜到转写（AC1） |
| **M2 多摄像头** | cameras 多路并行录制 + 按 camera 检索 | 两路以上并行录制不串、按路可查 |
| **M3 关键帧 + 问答** | 关键帧索引 + 文本问答（基于转写） | 问「刚才说了什么」能答且可回溯（AC2） |
| **M4 时序理解** | clip_analyzer 片段时序分析 + 动态问答 | 问「画面里发生了什么」能答（AC6） |
| **M5 可选** | 浏览器采集 / MCP 暴露 / 定时小结 | — |

## 10. 工程标准（Standards）

- **目录**：`G:\AI视听感知\{docs, code, data, output}` + `REVIEW.md`（遵循全局准则第 2 条）。
- **版本控制**：git；每次改动后 commit；`.gitignore` 排除 `data/`、`output/`、`__pycache__/`、`*.sqlite`、`venv/`、备份与测试大文件。
- **备份**：改代码前 `scripts/backup.mjs` 或手动复制到 `backup/<时间戳>/`（准则第 12 条）。
- **文档同步**：改了代码/配置，同步更新 `docs/design.md` 与 `REVIEW.md`（准则第 11 条，漏文档 = 没做完）。
- **代码规范**：Python 3.14；每模块单一职责 + 类型标注 + 模块 docstring；配置注入、不硬编码；时间一律 UTC epoch ms。
- **隐私**：全程本地，不外传、不上云（准则第 8 条）。
- **模型一致性**：每次推理记录所用模型名（`transcriptions.model` / `clip_analyses.model`），便于复现与切换模型。

## 11. 参考与许可

- **screenpipe**（[github.com/screenpipe/screenpipe](https://github.com/screenpipe/screenpipe)）：存储/检索层参考；**license 已改 source-available，仅学架构、不抄代码商用**。
- **AURA**（[github.com/aurateam2026/AURA](https://github.com/aurateam2026/AURA)）：摄像头采集参考；模型过重，仅学采集工程做法。
- **Qwen2.5-VL**：视频/多图时序理解模型（Ollama 多图输入）。
- 依赖模型 qwen2.5 / qwen2.5-VL（Ollama）、faster-whisper / CTranslate2，各自遵守上游许可。
