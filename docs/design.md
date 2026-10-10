# AI 视听感知 —— 设计文档

> 定位：给「没有视频/音频能力」的纯文本大模型，装上一副本地「眼睛和耳朵」。
> 版本 v0.1 · 2026-10-10 · 状态：待评审

## 1. 目标与范围

### 1.1 目标（Goals）

- **G1 本地采集**：摄像头视频流 + 麦克风音频流，数据不出本机。
- **G2 能听**：音频经 faster-whisper 转写为带时间戳的文字记录。
- **G3 能看**：视频抽关键帧落盘，按需用 VLM（qwen2.5vl）描述画面。
- **G4 能查**：对已记录内容做关键词 + 时间范围检索。
- **G5 能答**：向文本 LLM（qwen2.5）提问，基于检索到的记录作答。

### 1.2 验收标准（Acceptance Criteria）

- **AC1** 录一段含人声的视频，能按关键词检索到对应转写片段，时间误差 < 1s。
- **AC2** 提问「刚才发生了什么」，LLM 答案能回溯到具体记录（不编造）。
- **AC3** 全程不访问外网（模型、存储、推理均本地）。
- **AC4** 8GB 显存下持续运行 ≥ 10 分钟不 OOM、不崩溃。

### 1.3 非目标（明确不做）

- 不做实时低延迟对话 / TTS 语音合成（本系统是「记录 + 事后问答」）。
- 不做真正连续动态视觉（本质是抽帧，接受快速动作丢失）。
- 不做说话人分离 / 人脸识别 / 物体追踪（后续可加）。
- 不做多摄像头 / 云存储 / 多用户。
- 不直接商用（screenpipe 许可证约束，见 §11）。

## 2. 架构总览

五层单向数据流，层间用队列/函数调用解耦，每层可独立替换：

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  采集     │ → │  感知     │ → │  存储     │ → │  检索     │ → │  问答     │
│ capture  │   │ perceive │   │  store   │   │ retrieve │   │   qa     │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
 摄像头/麦克风     ASR/VLM      SQLite+FTS5    FTS5 查询     Ollama LLM
```

- **采集**：摄像头抽帧、麦克风采集，产出带时间戳的「帧」与「音频块」，放入队列。
- **感知**：音频块 → 转写文本；帧 → 去重 +（按需）VLM 描述。
- **存储**：转写、关键帧、描述，统一落 SQLite（单库 + FTS5）。
- **检索**：FTS5 关键词 + 时间范围过滤，取回相关记录。
- **问答**：检索结果拼成上下文，交给文本 LLM 作答。

### 数据流（时序）

```
摄像头 ──采样──▶ 帧 ──变化检测去重──▶ 关键帧 ──▶ frames 表 + data/media/*.jpg
                                               │（按需触发）
                                               ▼
                                      qwen2.5vl 描述 ──▶ frame_captions 表
麦克风 ──连续采集──▶ 音频块 ──faster-whisper──▶ 转写段 ──▶ transcriptions 表（FTS5）

提问 ──▶ FTS5(转写) + 时间范围(帧/描述) ──▶ 拼上下文 ──▶ qwen2.5 ──▶ 回答
```

## 3. 组件设计

每个组件一个职责、一个清晰接口、明确依赖；全部通过注入的 config 取参数，无全局可变状态。

| 组件 | 模块 | 职责 | 关键接口 | 依赖 |
|---|---|---|---|---|
| 视频采集 | `capture/video.py` | 从摄像头/文件抽帧，产出带时间戳的 Frame | `class VideoSource` / `CameraVideoSource` / `FileVideoSource` | cv2 |
| 音频采集 | `capture/audio.py` | 从麦克风/文件采集，产出 AudioChunk | `class AudioSource` / `MicAudioSource` / `FileAudioSource` | sounddevice |
| 语音感知 | `perception/asr.py` | 音频块 → 转写段 | `transcribe(chunk) -> Transcription` | faster-whisper |
| 视觉感知 | `perception/vision.py` | 帧去重 + 描述 | `is_changed(frame) -> bool` / `caption(frame) -> str` | Ollama(qwen2.5vl) |
| 存储 | `store/db.py` | 建表 / 写入 / FTS | `insert_transcription(...)` / `insert_frame(...)` / `insert_caption(...)` | sqlite3 |
| 检索 | `retrieve/search.py` | 关键词 + 时间检索 | `search_transcripts(q, start, end)` / `frames_in_range(start, end)` | store |
| 问答 | `qa/ask.py` | 组装上下文 + 调 LLM | `answer(question, records) -> str` | Ollama(qwen2.5) |
| 编排 | `app.py` | 起线程、队列、REPL | `main()` | 以上全部 |

**Source 抽象（关键设计）**：`VideoSource` / `AudioSource` 都抽象成「产出带时间戳的帧/块」。这样：
- 生产环境 = 摄像头 / 麦克风；
- 测试 / 回放 = 文件（喂一段 mp4），下游逻辑完全复用，可离线回归。

## 4. 数据模型（SQLite 单库）

> **时间标准（全项目唯一约定）**：所有时间戳用 **UTC epoch 毫秒 INTEGER** 存储，另存 ISO8601 文本便于人读。跨表、跨模块、跨函数一律遵守，不做本地时区换算。

```sql
-- 转写段（音频 → 文字）
CREATE TABLE transcriptions (
  id         INTEGER PRIMARY KEY,
  start_ms   INTEGER NOT NULL,              -- UTC epoch ms，闭区间起点
  end_ms     INTEGER NOT NULL,
  text       TEXT    NOT NULL,
  device     TEXT    NOT NULL DEFAULT 'mic',
  model      TEXT    NOT NULL DEFAULT 'faster-whisper',  -- 记录用了哪个模型，便于复现
  created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_trans_start ON transcriptions(start_ms);

-- 转写全文索引（FTS5），触发器自动同步
CREATE VIRTUAL TABLE transcriptions_fts USING fts5(
  text, content='transcriptions', content_rowid='id'
);

-- 关键帧（去重后仅存显著变化帧）
CREATE TABLE frames (
  id          INTEGER PRIMARY KEY,
  captured_ms INTEGER NOT NULL,
  file_path   TEXT    NOT NULL,              -- 相对 data/media 的 jpg 路径
  created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_frames_ts ON frames(captured_ms);

-- 帧描述（VLM 按需生成，缓存，避免重复调模型）
CREATE TABLE frame_captions (
  id         INTEGER PRIMARY KEY,
  frame_id   INTEGER NOT NULL REFERENCES frames(id),
  caption    TEXT    NOT NULL,
  model      TEXT    NOT NULL,               -- 记录用了哪个 VLM
  created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE VIRTUAL TABLE frame_captions_fts USING fts5(
  caption, content='frame_captions', content_rowid='id'
);

-- 事件（系统状态 / 汇总 / 问答记录，可选扩展）
CREATE TABLE events (
  id      INTEGER PRIMARY KEY,
  ts_ms   INTEGER NOT NULL,
  kind    TEXT NOT NULL,                     -- 'system' | 'summary' | 'qa'
  payload TEXT NOT NULL
);
```

触发器（写入主表时自动同步 FTS，保持索引一致）：

```sql
CREATE TRIGGER tr_trans_ai AFTER INSERT ON transcriptions BEGIN
  INSERT INTO transcriptions_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER tr_caption_ai AFTER INSERT ON frame_captions BEGIN
  INSERT INTO frame_captions_fts(rowid, caption) VALUES (new.id, new.caption);
END;
-- 删除/更新触发器在实现阶段补齐（MVP 只增不删，先留 INSERT 即可）。
```

## 5. 实时性与性能（8GB 显存调度）

硬约束：RTX 5060 8GB。模型占用：qwen2.5vl:7b ≈ 6GB，qwen2.5:7b ≈ 4.7GB，**两者不可同时常驻**。

调度策略（MVP）：

- **faster-whisper 跑 CPU**（CTranslate2，模型 `small`），不占显存，与 Ollama 完全解耦。
- **文本模型 qwen2.5:7b 常驻 GPU**（问答是高频入口）。
- **视觉模型 qwen2.5vl:7b 按需加载**：仅当提问涉及画面时由 Ollama 换载，产生 ~秒级加载延迟——可接受，因为本系统是「记录 + 事后问答」，非低延迟场景。
- Ollama 侧用 `keep_alive` 与模型参数控制换载；后续可换 qwen2.5vl:3b 或量化版降延迟（记为优化项，非 MVP）。

采样参数（可配置，默认值）：

- **视频**：采样 1 fps；经变化检测去重后，仅存显著变化帧（目标：静态画面不重复落盘）。
- **音频**：每 ~6s 窗口转写一次；16kHz 单声道（faster-whisper 要求）。

## 6. 配置与接口

`config.yaml`（示例，所有参数可配置、不硬编码）：

```yaml
video:
  source: camera          # camera | file
  camera_index: 0         # cv2 设备号；source=file 时为文件路径
  sample_fps: 1
audio:
  source: mic             # mic | file
  device: null            # sounddevice 设备名；source=file 时为文件路径
  sample_rate: 16000
  window_sec: 6
whisper:
  model: small            # tiny/base/small/medium
  device: cpu             # cpu | cuda
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
python app.py record              # 仅持续录制（采集→感知→落库），Ctrl+C 停
python app.py ask "刚才说了什么"   # 对已录制内容单次提问
python app.py repl                # 交互式：后台录制 + 随时输入提问
python app.py summary 10:00-10:30 # （M4）时间范围小结
```

## 7. 错误处理

- **设备不可用**（摄像头被占用 / 无麦克风）：降级继续——摄像头挂了音频照录，反之亦然；通过 `events(kind='system')` 记录，CLI 打印状态，不崩溃。
- **ASR / LLM 出错**：指数退避重试 3 次，仍失败则记 `events` 并跳过当前段，不中断采集。
- **存储满 / 写失败**：警告 + 停止落盘但保持采集（不静默丢数据）。
- **模型加载失败**：明确报错「qwen2.5vl 未安装，请 ollama pull」，退出问答而非崩整个进程。

## 8. 测试策略

- **单测**：`store/db.py`（schema / 触发器 / FTS）、时间解析、`vision.is_changed`（给定已知帧对，验证去重阈值）。
- **集成**：用 `FileVideoSource` + `FileAudioSource` 喂一段带音频的 mp4（测试夹具），跑「文件 → 转写 → 落库 → 检索 → 问答」全链路；问答用真实本地 Ollama，或 `MockLLM` 打桩验证「上下文拼装正确」。
- **验收**：AC1~AC4 各对应一条可执行检查（脚本或手动清单）。
- 夹具放 `tests/fixtures/`，大文件不入库（.gitignore）。

## 9. 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| **M0 本阶段** | 设计文档 + 目录骨架 + git init + 依赖确认 | 本文档评审通过 |
| **M1 能听** | 采集 + ASR 转写落库 + FTS5 可查 | 关键词搜到转写，时间误差 <1s |
| **M2 能记帧 + 问答** | 关键帧落库 + 检索 + qwen2.5 问答（基于转写） | 问「刚才说了什么」能答且可回溯 |
| **M3 能看** | 帧去重 + qwen2.5vl 按需描述 + 视觉问答 | 问「刚才画面里有什么」能答 |
| **M4 可选** | 浏览器采集 / MCP 暴露 / 定时小结 | — |

## 10. 工程标准（Standards）

- **目录**：`G:\AI视听感知\{docs, code, data, output}` + `REVIEW.md`（遵循全局准则第 2 条）。
- **版本控制**：git；每次改动后 commit；`.gitignore` 排除 `data/`、`output/`、`__pycache__/`、`*.sqlite`、`venv/`、备份与测试大文件。
- **备份**：改代码前 `scripts/backup.mjs` 或手动复制到 `backup/<时间戳>/`（准则第 12 条）。
- **文档同步**：改了代码/配置，同步更新 `docs/design.md` 与 `REVIEW.md`（准则第 11 条，漏文档 = 没做完）。
- **代码规范**：Python 3.14；每模块单一职责 + 类型标注 + 模块 docstring；配置注入、不硬编码；时间一律 UTC epoch ms。
- **隐私**：全程本地，不外传、不上云（准则第 8 条）。
- **模型一致性**：每次推理记录所用模型名（`transcriptions.model` / `frame_captions.model`），便于复现与切换模型。

## 11. 参考与许可

- **screenpipe**（[github.com/screenpipe/screenpipe](https://github.com/screenpipe/screenpipe)）：存储 / 检索层参考；**license 已改 source-available，仅学架构、不抄代码商用**。
- **AURA**（[github.com/aurateam2026/AURA](https://github.com/aurateam2026/AURA)）：摄像头采集参考；模型过重，仅学采集工程做法。
- 本仓库依赖的模型：qwen2.5 / qwen2.5vl（Ollama）、faster-whisper / CTranslate2，各自遵守上游许可。
