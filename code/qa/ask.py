"""问答：组装上下文 + 调 Ollama。"""
import requests

def _fmt_ms(ms):
    s = ms // 1000
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

def build_context(transcriptions, clip_summaries=None):
    parts = []
    for t in transcriptions:
        parts.append(f"[{_fmt_ms(t['start_ms'])}] {t['text']}")
    for c in clip_summaries or []:
        parts.append(f"[画面 {_fmt_ms(c['start_ms'])}-{_fmt_ms(c['end_ms'])}] {c['summary']}")
    return "\n".join(parts)

def ask_ollama(host, model, question, context, images=None):
    prompt = (
        "你是视频监控记录助手。只依据下面带时间戳的记录回答，记录没有的就回答「记录里没有」，不要编造。\n\n"
        f"记录：\n{context}\n\n问题：{question}"
    )
    msg = {"role": "user", "content": prompt}
    if images:
        msg["images"] = images  # base64 列表
    r = requests.post(f"{host}/api/chat",
                      json={"model": model, "messages": [msg], "stream": False},
                      timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"]
