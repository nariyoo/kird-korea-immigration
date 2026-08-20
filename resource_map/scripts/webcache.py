# -*- coding: utf-8 -*-
"""Resumable page store. One JSONL line per URL, written the moment that URL
finishes (census failure #11: a batch-level write hides a stall, and a long
resumable job with no output is indistinguishable from a hung one).

Each unit is also capped, so a single site with a slow renderer cannot hold up
the rest of the run.
"""
from __future__ import annotations
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from fetchpage import fetch, close_browser


class PageStore:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.Lock()
        self.rows = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    self.rows[r["url"]] = r

    def has(self, url):
        return url in self.rows

    def get(self, url):
        return self.rows.get(url)

    def put(self, row):
        with self._lock:
            self.rows[row["url"]] = row
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _one(url, use_browser):
    try:
        return fetch(url, use_browser=use_browser)
    except Exception as e:
        return {"url": url, "final_url": None, "http": 0, "how": "none",
                "state": "error", "title": "", "og_site_name": "",
                "description": "", "text": "", "n_text": 0, "socials": [],
                "tried": [f"outer:err:{type(e).__name__}"]}


def crawl(urls, store, workers=6, use_browser=True, unit_timeout=90, browser_conc=6,
          log_every=25, label="crawl"):
    """Fetch every URL not already in the store, in two passes: threaded plain
    clients first, then a concurrent browser pass over whatever they could not
    read. The browser pass is async rather than threaded because Playwright's
    sync API cannot be shared across threads."""
    todo = [u for u in dict.fromkeys(urls) if u and not store.has(u)]
    print(f"[{label}] {len(todo)} to fetch ({len(store.rows)} cached)", flush=True)
    if not todo:
        return

    # pass 1: threaded, no browser
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, u, False): u for u in todo}
        for fu in as_completed(futs):
            u = futs[fu]
            try:
                r = fu.result(timeout=unit_timeout)
            except Exception as e:
                r = {"url": u, "final_url": None, "http": 0, "how": "none",
                     "state": "error", "title": "", "og_site_name": "",
                     "description": "", "text": "", "n_text": 0, "socials": [],
                     "tried": [f"pool:err:{type(e).__name__}"]}
            store.put(r)
            done += 1
            if done % log_every == 0:
                ok = sum(1 for x in store.rows.values() if x["state"] == "ok")
                print(f"[{label}] {done}/{len(todo)} | ok {ok}", flush=True)

    if not use_browser:
        return
    # pass 2: concurrent browser recovery. Runs on the whole todo set at once
    # rather than one URL at a time, and skips the two dead client attempts a
    # failed URL has already paid for.
    from browser_batch import recover
    recover(store, urls=todo, conc=browser_conc)
