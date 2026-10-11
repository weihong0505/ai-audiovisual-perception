import numpy as np
from pathlib import Path
from capture.audio import FileAudioSource

FIXTURE = Path(__file__).parent / "fixtures" / "tone.wav"

def test_file_audio_source_yields_float32_chunks():
    src = FileAudioSource(str(FIXTURE), sample_rate=16000)
    chunks = list(src.chunks())
    assert len(chunks) > 0
    assert all(c.dtype == np.float32 for c in chunks)
    assert all(c.ndim == 1 for c in chunks)
    total = sum(len(c) for c in chunks)
    assert abs(total / 16000 - 3.0) < 0.5  # 约 3 秒
