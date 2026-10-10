from store.db import init_db, insert_camera, insert_transcription
from retrieve.search import search_transcripts

def _seed(db):
    init_db(db)
    cid = insert_camera(db, "c1", "0")
    insert_transcription(db, cid, 1000, 4000, "仓库门口来了一辆货车")
    insert_transcription(db, cid, 5000, 8000, "有人按了门铃")

def test_search_chinese_3chars(tmp_path):
    db = str(tmp_path / "s.sqlite"); _seed(db)
    rows = search_transcripts(db, "辆货车")  # 3 字，走 trigram FTS 路径
    assert len(rows) == 1 and "货车" in rows[0]["text"]

def test_search_short_query_like_fallback(tmp_path):
    db = str(tmp_path / "s.sqlite"); _seed(db)
    rows = search_transcripts(db, "门铃")  # 2 字符，trigram 会空 → LIKE 回退
    assert len(rows) == 1 and "门铃" in rows[0]["text"]

def test_search_time_filter(tmp_path):
    db = str(tmp_path / "s.sqlite"); _seed(db)
    assert len(search_transcripts(db, "货车", start_ms=0, end_ms=2000)) == 1
    assert len(search_transcripts(db, "货车", start_ms=9000, end_ms=20000)) == 0

def test_search_desc_order(tmp_path):
    db = str(tmp_path / "s.sqlite"); _seed(db)
    rows = search_transcripts(db, "", desc=True)
    assert [r["text"] for r in rows] == ["有人按了门铃", "仓库门口来了一辆货车"]
