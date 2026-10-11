from unittest import mock
from app import answer_question

def test_answer_question_calls_llm_with_context(tmp_path):
    cfg = {
        "storage": {"db": str(tmp_path / "e.sqlite"), "media_dir": str(tmp_path / "media")},
        "ollama": {"host": "http://localhost:11434", "llm": "qwen2.5:7b", "vlm": "qwen2.5vl:7b"},
    }
    with mock.patch("app.ask_ollama", return_value="记录里没有"):
        ans = answer_question(cfg, tmp_path, "刚才发生了什么")
    assert ans == "记录里没有"
