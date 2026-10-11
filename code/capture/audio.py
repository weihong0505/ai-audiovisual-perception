"""音频源：抽象 + 文件/麦克风实现，产出 float32 16kHz 单声道 chunks。"""
import subprocess
import numpy as np

class AudioSource:
    def chunks(self):
        raise NotImplementedError

class FileAudioSource(AudioSource):
    def __init__(self, path, sample_rate=16000):
        self.path = str(path)
        self.sample_rate = sample_rate

    def chunks(self):
        cmd = ["ffmpeg", "-i", self.path, "-f", "s16le", "-ac", "1",
               "-ar", str(self.sample_rate), "pipe:1"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        chunk_bytes = self.sample_rate * 2  # 1 秒 = sample_rate 采样 × 2 字节
        while True:
            raw = proc.stdout.read(chunk_bytes)
            if not raw:
                break
            yield np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        proc.wait()

class MicAudioSource(AudioSource):
    def __init__(self, device=None, sample_rate=16000):
        self.device = device
        self.sample_rate = sample_rate

    def chunks(self):
        import sounddevice as sd
        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                            device=self.device, dtype="float32") as stream:
            while True:
                data, _ = stream.read(self.sample_rate)  # 每次 1 秒
                yield data[:, 0] if data.ndim > 1 else data
