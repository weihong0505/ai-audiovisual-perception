"""连续录制：VideoSource 抽象 + CameraRecorder（分段 mp4 + 关键帧落库）。"""
import time
from pathlib import Path
import cv2
from store.db import insert_video_segment, insert_frame

class VideoSource:
    def read(self):
        raise NotImplementedError
    def fps(self):
        raise NotImplementedError
    def release(self):
        raise NotImplementedError

class CameraVideoSource(VideoSource):
    def __init__(self, source):
        # source 可为设备号(int) 或 rtsp/rtmp URL(str)
        s = str(source)
        self.cap = cv2.VideoCapture(int(s) if s.isdigit() else s)
    def read(self):
        return self.cap.read()
    def fps(self):
        return self.cap.get(cv2.CAP_PROP_FPS) or 30
    def release(self):
        self.cap.release()

class FileVideoSource(VideoSource):
    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
    def read(self):
        return self.cap.read()
    def fps(self):
        return self.cap.get(cv2.CAP_PROP_FPS) or 30
    def release(self):
        self.cap.release()

class CameraRecorder:
    def __init__(self, camera_id, source, db_path, media_dir, segment_sec=60, keyframe_sec=1):
        self.camera_id = camera_id
        self.source = source
        self.db_path = db_path
        self.media_dir = Path(media_dir); self.media_dir.mkdir(parents=True, exist_ok=True)
        self.fps = source.fps()
        self.segment_frames = max(1, int(self.fps * segment_sec))
        self.kf_frames = max(1, int(self.fps * keyframe_sec))

    def run(self):
        writer = None
        seg_idx = 0
        seg_start_n = 0
        seg_start_wall = int(time.time() * 1000)
        pending_frames = []   # (captured_ms, offset_ms, file_path)，段关闭后统一落库
        last_kf = None
        n = 0
        try:
            while True:
                ok, frame = self.source.read()
                if not ok:
                    break
                if writer is None or n - seg_start_n >= self.segment_frames:
                    if writer is not None:
                        writer.release()
                        self._close_segment(seg_idx, seg_start_wall, pending_frames)
                        pending_frames = []; seg_idx += 1
                    seg_start_n = n
                    seg_start_wall = int(time.time() * 1000)
                    writer = self._new_writer(seg_idx, frame)
                writer.write(frame)
                if last_kf is None or n - last_kf >= self.kf_frames:
                    now_ms = int(time.time() * 1000)
                    rel = f"c{self.camera_id}_{seg_idx}_{now_ms}.jpg"
                    cv2.imwrite(str(self.media_dir / rel), frame)
                    pending_frames.append((now_ms, now_ms - seg_start_wall, rel))
                    last_kf = n
                n += 1
        finally:
            if writer is not None:
                writer.release()
                self._close_segment(seg_idx, seg_start_wall, pending_frames)
            self.source.release()

    def _close_segment(self, seg_idx, seg_start_wall, pending_frames):
        end_ms = int(time.time() * 1000)
        seg_id = insert_video_segment(self.db_path, self.camera_id, seg_start_wall, end_ms,
                                      self._seg_path(seg_idx))
        for captured_ms, offset_ms, fpath in pending_frames:
            insert_frame(self.db_path, self.camera_id, seg_id, captured_ms, offset_ms, fpath)

    def _seg_path(self, seg_idx):
        return f"c{self.camera_id}_{seg_idx}.mp4"

    def _new_writer(self, seg_idx, frame):
        h, w = frame.shape[:2]
        return cv2.VideoWriter(str(self.media_dir / self._seg_path(seg_idx)),
                               cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
