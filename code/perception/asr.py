"""语音转写：faster-whisper 封装。"""
import numpy as np
from faster_whisper import WhisperModel

class Transcriber:
    def __init__(self, model_size="small", device="cpu", language="zh"):
        self.language = language
        self.model = WhisperModel(model_size, device=device, compute_type="int8")

    def transcribe(self, audio: np.ndarray, sample_rate=16000):
        if audio is None or len(audio) == 0:
            return []
        segments, _info = self.model.transcribe(
            audio, language=self.language, beam_size=5, vad_filter=True)
        return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
