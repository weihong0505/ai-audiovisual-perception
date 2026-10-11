"""检索：FTS5(trigram) 关键词 + 时间/摄像头过滤。trigram 最短 3 字，<3 字查询走 LIKE 回退。"""
import re
from store.db import connect

# FTS5 查询语法特殊字符 + 大写布尔算子：q 含任一个即不能安全包进双引号短语（会被逃逸注入），改走 LIKE 字面回退。
_FTS5_SPECIAL = re.compile(r'["*\-():]')
_FTS5_BOOL = re.compile(r'\b(?:AND|OR|NOT|NEAR)\b')

def _fts_safe(q):
    """q 是否可安全包进 FTS5 双引号短语（不含特殊字符/大写布尔算子）。"""
    return not (_FTS5_SPECIAL.search(q) or _FTS5_BOOL.search(q))

def search_transcripts(db_path, q, start_ms=None, end_ms=None, camera_id=None, limit=20, desc=False):
    q = (q or "").strip()
    if len(q) >= 3 and _fts_safe(q):
        cond = "t.id IN (SELECT rowid FROM transcriptions_fts WHERE transcriptions_fts MATCH ?)"
        params = [f'"{q}"']
    else:
        cond = "t.text LIKE ?"
        params = [f"%{q}%"]
    where = [cond]
    if start_ms is not None:
        where.append("t.end_ms >= ?"); params.append(start_ms)
    if end_ms is not None:
        where.append("t.start_ms <= ?"); params.append(end_ms)
    if camera_id is not None:
        where.append("t.camera_id = ?"); params.append(camera_id)
    order = "DESC" if desc else "ASC"
    sql = f"SELECT t.* FROM transcriptions t WHERE {' AND '.join(where)} ORDER BY t.start_ms {order} LIMIT ?"
    params.append(limit)
    conn = connect(db_path)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

def search_clip_analyses(db_path, q, start_ms=None, end_ms=None, camera_id=None, limit=20, desc=False):
    q = (q or "").strip()
    if len(q) >= 3 and _fts_safe(q):
        cond = "c.id IN (SELECT rowid FROM clip_analyses_fts WHERE clip_analyses_fts MATCH ?)"
        params = [f'"{q}"']
    else:
        cond = "c.summary LIKE ?"
        params = [f"%{q}%"]
    where = [cond]
    if start_ms is not None:
        where.append("c.end_ms >= ?"); params.append(start_ms)
    if end_ms is not None:
        where.append("c.start_ms <= ?"); params.append(end_ms)
    if camera_id is not None:
        where.append("c.camera_id = ?"); params.append(camera_id)
    order = "DESC" if desc else "ASC"
    sql = f"SELECT c.* FROM clip_analyses c WHERE {' AND '.join(where)} ORDER BY c.start_ms {order} LIMIT ?"
    params.append(limit)
    conn = connect(db_path)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

def frames_in_range(db_path, camera_id, start_ms, end_ms, limit=50):
    conn = connect(db_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM frames WHERE camera_id=? AND captured_ms BETWEEN ? AND ? ORDER BY captured_ms LIMIT ?",
        (camera_id, start_ms, end_ms, limit)).fetchall()]
    conn.close()
    return rows
