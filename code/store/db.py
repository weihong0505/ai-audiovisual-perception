"""SQLite 存储层：建表、写入、FTS5(trigram) 手动同步。"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS video_segments (
  id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL REFERENCES cameras(id),
  start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, file_path TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_seg_cam_ts ON video_segments(camera_id, start_ms);
CREATE TABLE IF NOT EXISTS transcriptions (
  id INTEGER PRIMARY KEY, camera_id INTEGER,
  start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, text TEXT NOT NULL,
  device TEXT NOT NULL DEFAULT 'mic', model TEXT NOT NULL DEFAULT 'faster-whisper',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_trans_start ON transcriptions(start_ms);
CREATE VIRTUAL TABLE IF NOT EXISTS transcriptions_fts USING fts5(text, tokenize='trigram');
CREATE TABLE IF NOT EXISTS frames (
  id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL REFERENCES cameras(id),
  video_segment_id INTEGER NOT NULL REFERENCES video_segments(id),
  captured_ms INTEGER NOT NULL, offset_ms INTEGER NOT NULL, file_path TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_frames_cam_ts ON frames(camera_id, captured_ms);
CREATE TABLE IF NOT EXISTS clip_analyses (
  id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL REFERENCES cameras(id),
  start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, summary TEXT NOT NULL, model TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_clip_cam_ts ON clip_analyses(camera_id, start_ms);
CREATE VIRTUAL TABLE IF NOT EXISTS clip_analyses_fts USING fts5(summary, tokenize='trigram');
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, ts_ms INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL
);
"""

def connect(db_path):
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db(db_path):
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def insert_camera(db_path, name, source, cam_id=None):
    conn = connect(db_path)
    if cam_id is not None:
        conn.execute("INSERT OR IGNORE INTO cameras(id, name, source) VALUES (?,?,?)",
                     (cam_id, name, str(source)))
        rid = cam_id
    else:
        cur = conn.execute("INSERT INTO cameras(name, source) VALUES (?,?)", (name, str(source)))
        rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid

def insert_video_segment(db_path, camera_id, start_ms, end_ms, file_path):
    conn = connect(db_path)
    cur = conn.execute(
        "INSERT INTO video_segments(camera_id, start_ms, end_ms, file_path) VALUES (?,?,?,?)",
        (camera_id, start_ms, end_ms, file_path))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid

def insert_transcription(db_path, camera_id, start_ms, end_ms, text, device="mic", model="faster-whisper"):
    text = (text or "").strip()
    if not text:
        return None
    conn = connect(db_path)
    cur = conn.execute(
        "INSERT INTO transcriptions(camera_id, start_ms, end_ms, text, device, model) VALUES (?,?,?,?,?,?)",
        (camera_id, start_ms, end_ms, text, device, model))
    rid = cur.lastrowid
    conn.execute("INSERT INTO transcriptions_fts(rowid, text) VALUES (?, ?)", (rid, text))
    conn.commit(); conn.close()
    return rid

def insert_frame(db_path, camera_id, video_segment_id, captured_ms, offset_ms, file_path):
    conn = connect(db_path)
    cur = conn.execute(
        "INSERT INTO frames(camera_id, video_segment_id, captured_ms, offset_ms, file_path) VALUES (?,?,?,?,?)",
        (camera_id, video_segment_id, captured_ms, offset_ms, file_path))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid

def insert_clip_analysis(db_path, camera_id, start_ms, end_ms, summary, model):
    summary = (summary or "").strip()
    if not summary:
        return None
    conn = connect(db_path)
    cur = conn.execute(
        "INSERT INTO clip_analyses(camera_id, start_ms, end_ms, summary, model) VALUES (?,?,?,?,?)",
        (camera_id, start_ms, end_ms, summary, model))
    rid = cur.lastrowid
    conn.execute("INSERT INTO clip_analyses_fts(rowid, summary) VALUES (?, ?)", (rid, summary))
    conn.commit(); conn.close()
    return rid

def insert_event(db_path, ts_ms, kind, payload):
    conn = connect(db_path)
    cur = conn.execute("INSERT INTO events(ts_ms, kind, payload) VALUES (?,?,?)", (ts_ms, kind, payload))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid
