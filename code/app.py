"""CLI 入口与录制编排。"""
import sys
import time
import threading
from pathlib import Path
import numpy as np

from config import load_config
from store.db import init_db, insert_camera, insert_transcription, insert_event
from capture.recorder import CameraRecorder, CameraVideoSource, FileVideoSource
from capture.audio import FileAudioSource, MicAudioSource
from perception.asr import Transcriber

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def _resolve(cfg, root, key, default):
    p = Path(cfg["storage"].get(key, default))
    return str(p if p.is_absolute() else root / p)

def run_record(cfg, root, stop_event=None):
    db = _resolve(cfg, root, "db", "data/audiovisual.sqlite")
    media = _resolve(cfg, root, "media_dir", "data/media")
    init_db(db)
    stop = stop_event or threading.Event()

    # 注册摄像头（config id 即 cameras.id，多路一致）
    for c in cfg.get("cameras", []):
        insert_camera(db, c["name"], str(c["source"]), cam_id=c["id"])

    # 每路一个录制线程
    recorders = []
    for c in cfg.get("cameras", []):
        src = c["source"]
        src_obj = (FileVideoSource(src) if isinstance(src, str) and src.endswith((".mp4", ".mkv", ".avi"))
                   else CameraVideoSource(src))
        recorders.append(CameraRecorder(c["id"], src_obj, db, media,
                                        cfg["recording"]["segment_sec"],
                                        cfg["recording"]["keyframe_sec"]))

    def _record_all():
        for r in recorders:
            r.run()
        stop.set()

    threading.Thread(target=_record_all, daemon=True).start()

    # 音频 + 转写线程
    trans = Transcriber(cfg["whisper"]["model"], cfg["whisper"]["device"],
                        cfg["whisper"].get("language", "zh"))
    audio_src = (FileAudioSource(cfg["audio"]["device"], cfg["audio"]["sample_rate"])
                 if cfg["audio"]["source"] == "file" else
                 MicAudioSource(cfg["audio"]["device"], cfg["audio"]["sample_rate"]))
    window_samples = cfg["audio"]["sample_rate"] * cfg["audio"]["window_sec"]

    def _audio_loop():
        buf = np.zeros(0, dtype=np.float32)
        t0 = None
        for chunk in audio_src.chunks():
            if t0 is None:
                t0 = int(time.time() * 1000)
            buf = np.concatenate([buf, chunk])
            while len(buf) >= window_samples:
                win, buf = buf[:window_samples], buf[window_samples:]
                for s in trans.transcribe(win, cfg["audio"]["sample_rate"]):
                    insert_transcription(db, None, t0 + int(s["start"] * 1000),
                                         t0 + int(s["end"] * 1000), s["text"])
                t0 += window_samples * 1000 // cfg["audio"]["sample_rate"]
        stop.set()

    threading.Thread(target=_audio_loop, daemon=True).start()

    try:
        while not stop.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        stop.set()
    insert_event(db, int(time.time() * 1000), "system", "record stopped")

def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python app.py record|ask|repl|analyze"); return
    cfg_path = PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        cfg_path = PROJECT_ROOT / "config.yaml.example"
    cfg = load_config(str(cfg_path))
    if argv[0] == "record":
        run_record(cfg, PROJECT_ROOT)
    else:
        print(f"'{argv[0]}' 将在 Task 10 实现")

if __name__ == "__main__":
    main()
