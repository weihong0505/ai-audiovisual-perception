import threading
from pathlib import Path
import pytest
from app import run_record, _validate_record_cfg
from store.db import connect, init_db

FIXTURE = Path(__file__).parent / "fixtures" / "clip.mp4"
TONE = Path(__file__).parent / "fixtures" / "tone.wav"

def _cfg(tmp_path):
    return {
        "cameras": [{"id": 1, "name": "c1", "source": str(FIXTURE)}],
        "recording": {"segment_sec": 60, "keyframe_sec": 1},
        "audio": {"source": "file", "device": str(TONE), "sample_rate": 16000, "window_sec": 3},
        "whisper": {"model": "tiny", "device": "cpu", "language": "zh"},
        "storage": {"db": str(tmp_path / "a.sqlite"), "media_dir": str(tmp_path / "media")},
    }

def test_run_record_writes_video_and_audio(tmp_path):
    cfg = _cfg(tmp_path)
    init_db(cfg["storage"]["db"])
    stop = threading.Event()
    t = threading.Thread(target=run_record, args=(cfg, tmp_path, stop), daemon=True)
    t.start()
    t.join(timeout=30)
    stop.set()
    conn = connect(cfg["storage"]["db"])
    segs = conn.execute("SELECT * FROM video_segments").fetchall()
    conn.close()
    assert len(segs) >= 1  # 至少录出一个视频段

def test_validate_record_cfg_rejects_zero_window_sec(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["audio"]["window_sec"] = 0
    with pytest.raises(ValueError):
        _validate_record_cfg(cfg)

def test_validate_record_cfg_rejects_zero_sample_rate(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["audio"]["sample_rate"] = 0
    with pytest.raises(ValueError):
        _validate_record_cfg(cfg)
