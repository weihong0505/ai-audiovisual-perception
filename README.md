# AI 视听感知 · ai-audiovisual-perception

> 给「没有视频 / 音频能力」的纯文本大模型，装上一副本地「眼睛和耳朵」：
> 多路摄像头**连续录制不丢帧** + 麦克风采集 → 语音转写 / 片段级时序理解 → 带时间戳入库 → 关键词检索 → 基于检索作答。
> **全程本地运行，不访问外网。**

<p>
<img alt="tests" src="https://img.shields.io/badge/tests-22%20passed-brightgreen">
<img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue">
<img alt="local-only" src="https://img.shields.io/badge/inference-100%25%20local-success">
</p>

---

## 它解决什么问题

纯文本 LLM 只能读字。你问它"刚才发生了什么"，它没有任何输入来源。
这个项目把摄像头和麦克风变成 LLM 可检索的记忆：**录制端真连续，理解端做片段级时序建模**，
回答时把检索到的原始记录拼成上下文，让每个答案都能回溯到具体时间戳。

---

## 架构

五层单向数据流，层间用队列 / 函数调用解耦，**每层可独立替换**：

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  采集     │ → │  感知     │ → │  存储     │ → │  检索     │ → │  问答     │
│ capture  │   │ perceive │   │  store   │   │ retrieve │   │   qa     │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
 多摄像头/麦克风   ASR/时序理解   SQLite+FTS5    FTS5 查询     Ollama LLM
```

| 组件 | 模块 | 职责 | 依赖 |
|---|---|---|---|
| 视频录制 | `code/capture/recorder.py` | 每路摄像头连续录 mp4 分段落盘（不丢帧）+ 抽关键帧 | ffmpeg / cv2 |
| 音频采集 | `code/capture/audio.py` | 麦克风 / 文件采集，产出 AudioChunk | sounddevice |
| 语音感知 | `code/perception/asr.py` | 音频块 → 带时间戳转写段 | faster-whisper |
| 时序理解 | `code/perception/clip_analyzer.py` | 视频片段 → 多帧序列 → 动态描述 | ffmpeg + Ollama(qwen2.5-VL) |
| 存储 | `code/store/db.py` | 建表 / 写入 / FTS | sqlite3 |
| 检索 | `code/retrieve/search.py` | 关键词 + 时间范围 + 摄像头过滤 | store |
| 问答 | `code/qa/ask.py` | 组装上下文 + 调 LLM | Ollama(qwen2.5) |
| 编排 | `code/app.py` | 多路线程、队列、CLI（`record/ask/repl/analyze`） | 以上全部 |

---

## 快速开始

```bash
pip install -r requirements.txt

# 缺省配置回退到 example，全新 checkout 可直接跑
cp config.yaml.example config.yaml

python -m pytest                    # 22 passed
python code/app.py record --duration 10
python code/app.py ask "刚才发生了什么"
```

---

## 三个我在设计上刻意的选择

**1. 时间标准：全库一律 UTC epoch 毫秒 INTEGER**
只在**人机边界**（CLI 解析、问答上下文显示）做本地墙钟 ↔ UTC 换算。
存储和比较永不碰时区 —— 这样跨摄像头、跨设备的记录天然可比。

**2. FTS5 检索：trigram + 降级回退**
≥3 字走 `MATCH`，<3 字走 `LIKE` 回退（保证中文 2 字词可搜）。
含 FTS5 特殊字符或大写布尔算子时也路由到 LIKE 字面回退 —— 见下方 F1。

**3. 时间过滤用「重叠语义」而非「包含语义」**
段与查询窗相交即命中。因为「刚才发生了什么」这个问法，本质上问的是一个时间窗，
而不是一个时间点。

---

## 我自己找出来的三个真实缺陷

M1–M4 完成后，我做了一轮**独立对抗性审查**（不看实现作者的思路，只从攻击面出发）。
它实测出 3 条 load-bearing 缺陷，全部按 TDD（先写红测试 → 再修）修复，测试从 17 增至 22：

| # | 严重度 | 缺陷 | 修复 |
|---|---|---|---|
| **F1** | Important | **FTS5 引号注入**：`q` 被直接拼进 `MATCH` 短语。`q='"""'` 触发 `OperationalError: unterminated string`；`q='xyz" OR "辆货车'` 可逃逸引号、注入 FTS 布尔算子 | `retrieve/search.py` 新增 `_fts_safe` 检测：含 `" * - ( ) :` 或大写 `AND/OR/NOT/NEAR` 时路由 LIKE 字面回退；常规 ≥3 字查询仍走 MATCH，不回归 |
| **F2** | Important | **写失败后连接泄漏**：`insert_*` 无 try/finally，写异常时 `conn.close()` 不执行，且 traceback 帧引用 `conn`，写锁常驻 → 后续写入 `database is locked` 级联 | `store/db.py` 统一 `_write` 上下文管理器（成功 commit / 异常 rollback / finally close），异常仍上抛不吞 |
| **F7** | Minor→硬 DoS | **`window_sec=0` 死循环**：`window_samples=0` 时 `_audio_loop` 恒真且缓冲区不缩减 | `app.py` 新增 `_validate_record_cfg`，`run_record` 开头 fail-fast 校验 `sample_rate` / `window_sec` > 0 |

新增 5 条回归测试（`test_search_fts_quote_no_crash`、`test_write_failure_releases_connection_lock`、
`test_validate_record_cfg_rejects_zero_window_sec` 等）。

> **为什么这件事比功能本身更重要**：这三个缺陷单靠"功能跑通了"永远发现不了。
> 也是这一轮让我确认：**逐任务评审 + 全分支评审的双层结构是必要的** ——
> 计划自身有 3 处缺陷（FK 未 seed camera、时间过滤语义自相矛盾、`main()` 丢 config 回退），
> 预检扫描误判其中 2 处"已修复"，只有逐任务评审兜住了。
> 而跨任务的语义不一致（`_fmt_ms` 接绝对 epoch ms → 显示 `496944:23:45`），单任务各自自洽，只有全分支评审能抓。

---

## 验收对照

| 验收标准 | 状态 |
|---|---|
| AC1 关键词检索，时间误差 < 1s | ✅ 单测覆盖 |
| AC2 可回溯问答，LLM 不编造 | ✅ 单测覆盖（`test_ask` / `test_e2e`） |
| AC3 全程不访问外网 | ✅ 架构保证（SQLite + Ollama + faster-whisper 全本地） |
| AC4 8GB 显存 / 多路 ≥10min 不 OOM | 🟡 调度已实现，实机压测待 M5 |
| AC5 录制不丢帧 | 🟡 `test_app_record`（文件源）覆盖，真摄像头待 M5 |
| AC6 片段级时序理解 | 🟡 VLM 路径手工验证通过，自动化测试待 M5 |

M5 遗留 13 条已逐条登记在 [REVIEW.md](REVIEW.md)，全部为 ACCEPTABLE 级，无一条破坏 AC1–AC6。

---

## 边界（明确不做）

- ❌ 不做实时低延迟对话 / TTS 语音合成 —— 本系统是**「记录 + 事后问答」**
- ❌ 不做说话人分离 / 人脸识别 / 物体追踪（后续可加）
- ❌ 不做云存储 / 多用户
- ⚠️ **不承诺"像人眼一样连续感知"** —— 理解端是「片段 → 抽帧序列 → VLM 时序建模」，
  录制端才是真连续。这是行业现状（Gemini Live、Qwen-Omni 内部同样抽帧），本项目如实标注

---

## 目录

```
├─ code/
│  ├─ app.py                 编排 + CLI（record / ask / repl / analyze）
│  ├─ capture/               多路连续录制 + 音频采集
│  ├─ perception/            faster-whisper ASR + 片段级时序理解
│  ├─ store/db.py            SQLite + FTS5(trigram)
│  ├─ retrieve/search.py     FTS-safe 检索
│  └─ qa/ask.py              上下文组装 + Ollama 问答
├─ tests/                    22 项，含对抗审查回归测试
├─ docs/design.md            设计规格 v0.2（目标 / 验收标准 / 组件契约）
├─ docs/plans/               M1–M4 十任务计划
└─ REVIEW.md                 复盘：关键决策 / 教训坑 / 缺陷修复记录
```
