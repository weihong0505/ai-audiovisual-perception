import datetime
from unittest import mock
import pytest
import requests
from qa.ask import build_context, _fmt_ms, ask_ollama

def test_build_context_formats_records():
    t0 = int(datetime.datetime(2026, 10, 11, 10, 0, 0).timestamp() * 1000)
    trans = [{"start_ms": t0, "text": "有人来了"}, {"start_ms": t0 + 4000, "text": "门开了"}]
    clips = [{"start_ms": t0, "end_ms": t0 + 6000, "summary": "一个人从左边走到门口"}]
    ctx = build_context(trans, clips)
    assert "有人来了" in ctx
    assert "一个人从左边走到门口" in ctx
    assert "10:00:00" in ctx  # 绝对 epoch ms → 本地墙钟

def test_fmt_ms_epoch_to_wallclock():
    ms = int(datetime.datetime(2026, 10, 11, 14, 5, 0).timestamp() * 1000)
    assert _fmt_ms(ms) == "14:05:00"

def test_ask_ollama_raises_on_connection_error():
    with mock.patch("qa.ask.requests.post",
                    side_effect=requests.exceptions.ConnectionError("refused")):
        with pytest.raises(requests.exceptions.ConnectionError):
            ask_ollama("http://localhost:11434", "qwen2.5:7b", "q", "ctx")
