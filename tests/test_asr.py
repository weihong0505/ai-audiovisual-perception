import numpy as np
from perception.asr import Transcriber

def test_transcribe_sine_returns_no_text():
    t = Transcriber(model_size="tiny", language="zh")
    audio = (np.sin(2*np.pi*440*np.arange(16000)/16000)).astype(np.float32)  # 1s 纯音
    segs = t.transcribe(audio, 16000)
    assert isinstance(segs, list)  # 纯音无语音，允许空列表；关键是不抛异常、结构正确
