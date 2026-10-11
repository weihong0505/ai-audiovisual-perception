"""时序理解：视频片段 → 抽多帧 → VLM 动态描述 → clip_analyses。"""
import base64
from pathlib import Path
import cv2
import numpy as np
import requests
from store.db import connect, insert_clip_analysis

def sample_frames(segment_path, start_offset_ms, end_offset_ms, n=8):
    cap = cv2.VideoCapture(str(segment_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release(); return []
    start_f = min(int(start_offset_ms / 1000 * fps), total - 1)
    end_f = min(int(end_offset_ms / 1000 * fps), total - 1)
    if end_f < start_f:
        end_f = start_f
    indices = np.linspace(start_f, end_f, n, dtype=int)
    frames = []
    for i in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames

def _to_b64(frame):
    ok, buf = cv2.imencode(".jpg", frame)
    return base64.b64encode(buf.tobytes()).decode("ascii")

def _segments_in_range(db_path, camera_id, start_ms, end_ms):
    conn = connect(db_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM video_segments WHERE camera_id=? AND start_ms < ? AND end_ms > ? ORDER BY start_ms",
        (camera_id, end_ms, start_ms)).fetchall()]
    conn.close()
    return rows

def analyze_clip(db_path, media_dir, camera_id, start_ms, end_ms, host, vlm, n=8):
    segs = _segments_in_range(db_path, camera_id, start_ms, end_ms)
    frames = []
    for s in segs:
        path = Path(media_dir) / s["file_path"]
        off_start = max(0, start_ms - s["start_ms"])
        off_end = min(s["end_ms"] - s["start_ms"], end_ms - s["start_ms"])
        per = max(1, n // max(1, len(segs)))
        frames.extend(sample_frames(str(path), off_start, off_end, n=per))
    if not frames:
        return None
    images = [_to_b64(f) for f in frames]
    prompt = "这些是按时间顺序排列的连续帧。请用一两句话描述这段时间里发生了什么（动作/变化/出现的人和物）。"
    r = requests.post(f"{host}/api/chat",
                      json={"model": vlm,
                            "messages": [{"role": "user", "content": prompt, "images": images}],
                            "stream": False},
                      timeout=300)
    r.raise_for_status()
    summary = r.json()["message"]["content"].strip()
    insert_clip_analysis(db_path, camera_id, start_ms, end_ms, summary, vlm)
    return summary
