# REVIEW.md — AI视听感知 M1-M4 复盘

> 2026-10-11（时间已校准）· 分支 `feat/audiovisual-m1-m4` · 计划 `docs/plans/2026-10-11-m1-m4.md` · 规格 `docs/design.md` v0.2
> 执行方式：superpowers:subagent-driven-development（SDD）。完整 commit 链见 `git log --oneline master..HEAD`。

## 做了什么

- 按 10 任务计划完成 M1–M4，交付五层流水线（采集→感知→存储→检索→问答），给纯文本 LLM（qwen2.5:7b）装上本地「眼睛和耳朵」。
- 模块：`store/db.py`（SQLite+FTS5 trigram）、`capture/audio.py`、`capture/recorder.py`、`perception/asr.py`（faster-whisper）、`perception/clip_analyzer.py`（抽帧→VLM）、`retrieve/search.py`、`qa/ask.py`、`app.py`（`record/ask/repl/analyze` CLI）。
- 全量测试 **17 passed**（每任务 TDD RED→GREEN），逐任务评审 + 最终全分支评审全部通过。

## 关键决策

- **时间标准**：全库一律 **UTC epoch 毫秒 INTEGER**；仅在**人机边界**（CLI 解析 `_parse_range`、问答上下文显示 `_fmt_ms`）做本地墙钟 ↔ UTC 换算，存储/比较不做本地时区换算。
- **FTS5 trigram**：≥3 字走 `MATCH`、<3 字走 `LIKE` 回退（中文 2 字词可搜）。
- **时间过滤 = 重叠语义**（段与查询窗相交即命中，AC2「刚才发生了什么」需要）。
- **多摄像头并行**：每路独立录制线程，不顺序阻塞。
- **`cameras.id` = config 里 `cameras[].id`**（`insert_camera(..., cam_id=...)`，多路录制/检索路由一致）。
- **`frames.video_segment_id`** 在段关闭、拿到真实段 id 后再落库（段内先内存缓冲），保证 FK 完整。
- **`config.yaml` 缺失回退 `config.yaml.example`**（全新 checkout 可用）。

## 教训坑

- **计划自身有 3 处缺陷，逐任务评审才兜住**：Task5 FK 约束未 seed camera、Task7 时间过滤「包含↔重叠」自相矛盾、Task10 `main()` 丢了 config 回退（违反 Ruling#1b）。预检扫描对 Task5/Task7 均误判「已修复」，印证**预检不可替代逐任务评审**。
- **跨任务语义不一致只有全分支评审能抓**：`_fmt_ms`（时长格式化器）接绝对 epoch ms → 显示「496944:23:45」。单任务各自自洽、跨任务才矛盾——印证「逐任务 + 全分支」双层评审必要。
- **台账 Edit 反复失败**：progress.md 短串不唯一，靠带前文唯一锚点解决（写台账时用足够长唯一锚）。
- 评审模型分档有效：机械转写用 haiku、集成/时间语义用 sonnet、最终全分支用 fable，抓到的问题与模型档位正相关。

## 下一步（M5 backlog · 13 条遗留，全部 ACCEPTABLE，无一条破 AC1–AC6）

1. 摄像头 Ctrl+C 优雅停机未接线（Ruling#4，AC5 用文件源 EOF 自动停验）。
2. `analyze_clip` VLM 路径无自动化测试（Ruling#5，AC6 由手工 Step5 验）。
3. `search_clip_analyses` / `frames_in_range` 无单测（同构于已测 `search_transcripts`）。
4. FTS5 `MATCH` 查询含双引号会语法错误（无转义；CLI 恒传 `q=""` 故不触发）。
5. `_fmt_ms` 负值未处理（现有数据全非负，不可达）。
6. `ask_ollama`/`analyze_clip` 裸 `r.json()["message"]["content"]`（响应缺字段 → KeyError）。
7. `_to_b64` 不查 `cv2.imencode` 返回码。
8. `analyze_clip` 总帧数可超 `n`（n 是每段均值，非硬上限）。
9. CLI `ask/repl/analyze` 无 try/except（Ollama 挂 → 裸 traceback；设计 §7 错误处理归 M5）。
10. `frames_in_range` 导入未用。
11. `FileAudioSource` 丢 ffmpeg stderr / 不查返回码。
12. `last_kf` 段回卷未重置（仅关键帧索引偏移，无正确性影响）。
13. 测试夹具 `clip.mp4`/`tone.wav` gitignored（ffmpeg 再生成）。

## 验收对照

| AC | 状态 |
|---|---|
| AC1 关键词检索 | 单测覆盖（test_search） |
| AC2 可回溯问答 | 单测覆盖（test_ask / test_e2e，上下文拼装 + 时间戳显示） |
| AC3 全程本地 | 架构保证（SQLite+Ollama+faster-whisper 全本地） |
| AC4 8GB/10min | 调度已实现（whisper CPU、VLM 按需加载）；实机压测待 M5 |
| AC5 录制不丢帧 | test_app_record（文件源）覆盖；真摄像头待 M5 |
| AC6 时序理解 | 手工 Step5 待真机验（需 Ollama+qwen2.5vl） |
