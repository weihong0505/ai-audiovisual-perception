from unittest import mock
import pytest
import requests
from qa.ask import build_context, _fmt_ms, ask_ollama

def test_build_context_formats_records():
    trans = [{"start_ms": 1000, "text": "有人来了"}, {"start_ms": 5000, "text": "门开了"}]
    clips = [{"start_ms": 0, "end_ms": 6000, "summary": "一个人从左边走到门口"}]
    ctx = build_context(trans, clips)
    assert "有人来了" in ctx
    assert "一个人从左边走到门口" in ctx
    assert "00:00:01" in ctx  # 时间格式化

def test_fmt_ms_no_day_rollover():
    assert _fmt_ms(86400000) == "24:00:00"
    assert _fmt_ms(25 * 3600000 + 5 * 60000) == "25:05:00"

def test_ask_ollama_raises_on_connection_error():
    with mock.patch("qa.ask.requests.post",
                    side_effect=requests.exceptions.ConnectionError("refused")):
        with pytest.raises(requests.exceptions.ConnectionError):
            ask_ollama("http://localhost:11434", "qwen2.5:7b", "q", "ctx")
