from pathlib import Path
from capture.recorder import FileVideoSource, CameraRecorder
from store.db import insert_camera, init_db, connect

FIXTURE = Path(__file__).parent / "fixtures" / "clip.mp4"

def test_recorder_writes_segment_and_frames(tmp_path):
    db = str(tmp_path / "r.sqlite"); init_db(db)
    insert_camera(db, "c1", "0", cam_id=1)
    media = tmp_path / "media"; media.mkdir()
    src = FileVideoSource(str(FIXTURE))
    rec = CameraRecorder(camera_id=1, source=src, db_path=db,
                         media_dir=str(media), segment_sec=60, keyframe_sec=1)
    rec.run()
    conn = connect(db)
    segs = conn.execute("SELECT * FROM video_segments").fetchall()
    frames = conn.execute("SELECT * FROM frames").fetchall()
    conn.close()
    assert len(segs) == 1
    assert Path(media / segs[0]["file_path"]).exists()
    assert len(frames) >= 2  # 30 帧、每 10 帧抽 1 关键帧 → ≥2
    # 关键帧必须挂到真实视频段 id（评审关注点 #3）
    seg_ids = {s["id"] for s in segs}
    assert {f["video_segment_id"] for f in frames} <= seg_ids
