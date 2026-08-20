# -*- coding: utf-8 -*-
"""Serper query layer with a disk cache.

The v1 enrichment asked ONE query per organization and took the first organic
result whose TITLE looked like a name match. That is the whole reason 608 of
755 published websites are bare host roots and 54 of them are Kakao Map place
pages.

Here a query returns CANDIDATES. Nothing is chosen at this layer. The queries
are deliberately different in kind, because the strongest identity key is not
the name: an organization's phone number and its street address are printed on
its own site and almost nowhere else, so a search for those two reaches the
right site even when the name is generic (외국인주민지원센터 alone identifies
nobody).
"""
from __future__ import annotations
import hashlib
import json
import os
import threading
import time

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE = os.path.join(ROOT, "data", "interim", "serper_v2_cache.jsonl")
os.makedirs(os.path.dirname(CACHE), exist_ok=True)

_lock = threading.Lock()
_mem = {}
_loaded = False


def _key(q, num):
    return hashlib.sha1(f"{q}||{num}".encode("utf-8")).hexdigest()


def _load():
    global _loaded
    if _loaded:
        return
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                _mem[r["k"]] = r["v"]
    _loaded = True


def getkey():
    for k in ("SERPER_API_KEY", "SERPER_API", "SERPER_KEY"):
        if os.environ.get(k):
            return os.environ[k].strip()
    for p in (os.path.join(ROOT, "data", "serper_key.txt"),
              os.path.abspath(os.path.join(ROOT, "..", "..", "Immigrant Support Map",
                                           "data", "serper_key.txt"))):
        if os.path.exists(p):
            return open(p, encoding="utf-8-sig").read().strip()
    raise SystemExit("No Serper key")


_KEY = None


def search(q, num=10, retries=3):
    global _KEY
    _load()
    k = _key(q, num)
    if k in _mem:
        return _mem[k]
    if _KEY is None:
        _KEY = getkey()
    out = {}
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": _KEY, "Content-Type": "application/json"},
                data=json.dumps({"q": q, "num": num, "gl": "kr", "hl": "ko"}),
                timeout=30)
            if r.status_code == 200:
                out = r.json()
                break
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 * (attempt + 1))
                continue
            break
        except Exception:
            time.sleep(2 * (attempt + 1))
    with _lock:
        _mem[k] = out
        with open(CACHE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"k": k, "q": q, "v": out}, ensure_ascii=False) + "\n")
    return out


def organic(q, num=10):
    j = search(q, num)
    return j.get("organic") or []


def knowledge(q, num=10):
    return (search(q, num).get("knowledgeGraph") or {})
