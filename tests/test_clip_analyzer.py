from pathlib import Path
from perception.clip_analyzer import sample_frames

FIXTURE = Path(__file__).parent / "fixtures" / "clip.mp4"

def test_sample_frames_returns_frames():
    frames = sample_frames(str(FIXTURE), 0, 3000, n=4)
    assert 3 <= len(frames) <= 4  # 30 帧里 linspace 抽 4，末尾可能越界被跳过
    assert all(f is not None and f.ndim == 3 for f in frames)
