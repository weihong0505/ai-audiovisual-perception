"""加载并合并默认配置。"""
from pathlib import Path
import yaml

DEFAULTS = {
    "recording": {"segment_sec": 60, "keyframe_sec": 1},
    "audio": {"source": "mic", "device": None, "sample_rate": 16000, "window_sec": 6},
    "whisper": {"model": "small", "device": "cpu", "language": "zh"},
    "ollama": {"host": "http://localhost:11434", "vlm": "qwen2.5vl:7b", "llm": "qwen2.5:7b"},
    "storage": {"db": "data/audiovisual.sqlite", "media_dir": "data/media"},
}

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    cfg = {}
    for k, v in DEFAULTS.items():
        cfg[k] = {**v, **(user.get(k) or {})}
    if "cameras" in user:
        cfg["cameras"] = user["cameras"]
    return cfg
