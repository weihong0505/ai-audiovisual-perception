from config import load_config

def test_load_config_merges_defaults(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("cameras:\n  - id: 1\n    name: c1\n    source: 0\n", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg["cameras"][0]["name"] == "c1"
    assert cfg["recording"]["segment_sec"] == 60      # 默认值
    assert cfg["ollama"]["llm"] == "qwen2.5:7b"       # 默认值
