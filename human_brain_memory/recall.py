"""Adapted from the QQ bot's recall algorithm; retrieval is not fact verification."""

import json
import math
import re

DAY = 86400
FACTORS = {"fact": 3, "episode": 1, "reflection": 2, "gist": 2.5}
EMOTIONS = {"开心", "感动", "平静", "难过", "生气", "焦虑", "尴尬", "惊讶"}
STOP = set("的了是我你他她它们在有和就都也很不这那个吗呢吧啊呀哦嗯么着过给被把与及或而还又要会想说")


def initial_strength(importance, kind, intensity=0):
    return importance * FACTORS[kind] * (1 + 0.5 * max(0, min(3, intensity)))


def retention(memory, now):
    since = memory["last_recalled"] if memory["last_recalled"] is not None else memory["created"]
    return math.exp(-max(0, now - since) / DAY / max(0.1, memory["strength"]))


def tokens(text):
    out = {}
    for word in re.findall(r"[a-z0-9]+|[一-鿿]+", text.lower()):
        if word.isascii():
            if len(word) >= 2:
                out[word] = 1.0
        else:
            out.update({ch: 0.5 for ch in word if ch not in STOP})
            out.update({word[i:i+2]: 1.0 for i in range(len(word)-1)
                        if not (word[i] in STOP and word[i+1] in STOP)})
    return out


def overlap(base, query, idf):
    total = sum(w * idf.get(t, 1) for t, w in base.items())
    return sum(w * idf.get(t, 1) for t, w in base.items() if t in query) / total if total else 0


def cosine(a, b):
    if not a or len(a) != len(b):
        return 0
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / norm if norm else 0


def select(candidates, query, subject, now, config, semantic=None, search=False, feeling=""):
    q = tokens(query)
    docs = [tokens(m["content"]) for m in candidates]
    df = {}
    for d in docs:
        for t in d:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + len(docs)/n) for t, n in df.items()}
    ranked = []
    for m, d in zip(candidates, docs):
        kw = overlap(q, d, idf) if search else overlap(d, q, idf)
        cos = (semantic or {}).get(m["id"], -1)
        sem = max(0, min(1, (cos-config.semantic_floor)/(config.semantic_ceiling-config.semantic_floor)))
        rel = max(kw, sem)
        if search and kw < 0.3 and sem < 0.1:
            continue
        if not search and m["status"] == "frozen" and rel < 0.3:
            continue
        category = 0 if m["pinned"] else 1 if rel >= 0.1 or search else 2
        if category == 2 and not (m["kind"] == "fact" and m["subject"] == subject):
            continue
        ret = 1 if m["status"] == "frozen" else retention(m, now)
        bonus = 0.05 if config.emotions and m["intensity"] and (
            (feeling == "好" and m["emotion"] in {"开心", "感动"}) or
            (feeling == "不好" and m["emotion"] in {"难过", "生气", "焦虑", "尴尬"})
        ) else 0
        score = 0.5*rel + 0.3*ret + 0.2*m["importance"]/10 + bonus
        ranked.append((category, -rel if search else -score, m["id"],
                       {**m, "relevance": rel, "retention": ret, "score": score}))
    ranked.sort(key=lambda x: x[:3])
    return [m for _, _, _, m in ranked]


def reinforce(store, selected, now, day_start, search=False):
    for m in selected:
        if m["status"] == "frozen":
            store.execute("UPDATE memories SET status='active',status_ts=?,version=version+1 WHERE id=?", (now, m["id"]))
        if search or m["relevance"] >= 0.3:
            store.execute(
                "UPDATE memories SET strength=MIN(strength*1.8,3650),last_recalled=?,recall_count=recall_count+1 "
                "WHERE id=? AND COALESCE(last_recalled,created)<?", (now, m["id"], day_start),
            )
        else:
            store.execute(
                "UPDATE memories SET strength=MAX(strength,MIN(strength*1.2,30)),last_seen=? "
                "WHERE id=? AND COALESCE(last_recalled,created)<? AND COALESCE(last_seen,0)<?",
                (now, m["id"], day_start, day_start),
            )


def sweep(store, scope, now):
    for m in store.candidates(scope):
        if m["status"] == "active" and not m["pinned"] and m["importance"] < 8 and retention(m, now) < 0.05:
            store.execute("UPDATE memories SET status='frozen',status_ts=?,version=version+1 WHERE id=?", (now, m["id"]))
    store.execute("UPDATE memories SET status='trash',status_ts=?,version=version+1 "
                  "WHERE scope=? AND status='frozen' AND status_ts<? AND pinned=0 AND importance<8",
                  (now, scope, now-30*DAY))


def format_memory(m):
    return {"id": m["id"], "subject": m["subject"], "kind": m["kind"], "basis": m["basis"],
            "content": m["content"], "fuzzy": m.get("retention", 1) < 0.3}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
