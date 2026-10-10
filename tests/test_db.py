import sqlite3
import pytest
from store.db import init_db, connect, insert_camera, insert_transcription, insert_frame

def test_init_db_creates_tables(tmp_path):
    db = str(tmp_path / "t.sqlite")
    init_db(db)
    conn = connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cameras", "video_segments", "transcriptions", "frames", "clip_analyses", "events"} <= names
    conn.close()

def test_insert_and_fts_search_chinese(tmp_path):
    db = str(tmp_path / "t.sqlite")
    init_db(db)
    cid = insert_camera(db, "c1", "0")
    insert_transcription(db, cid, 1000, 4000, "仓库门口来了一辆货车")
    conn = connect(db)
    rows = conn.execute(
        "SELECT rowid FROM transcriptions_fts WHERE transcriptions_fts MATCH ?",
        ('"辆货车"',),
    ).fetchall()
    assert len(rows) == 1
    conn.close()

def test_insert_transcription_skips_empty(tmp_path):
    db = str(tmp_path / "t.sqlite")
    init_db(db)
    cid = insert_camera(db, "c1", "0")
    assert insert_transcription(db, cid, 1000, 2000, "  ") is None

def test_write_failure_releases_connection_lock(tmp_path):
    db = str(tmp_path / "t.sqlite")
    init_db(db)
    cid = insert_camera(db, "c1", "0")
    # 触发一次失败写：video_segment_id 不存在 → FK 失败（异常对象引用 conn 局部变量）
    with pytest.raises(sqlite3.IntegrityError):
        insert_frame(db, cid, 9999, 0, 0, "x.jpg")
    # 无需 gc.collect()，紧跟的正常写入必须成功（否则即连接泄漏 → database is locked 级联）
    rid = insert_transcription(db, cid, 1000, 2000, "锁已释放")
    assert rid is not None
