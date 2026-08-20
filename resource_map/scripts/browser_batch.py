# -*- coding: utf-8 -*-
"""Concurrent browser recovery for URLs a plain client could not read.

The sequential version was correct and unusably slow: every hard URL paid two
dead client attempts plus a full page render, one after another, so 250 URLs
took hours and 10,000 would never finish.

Two rules from the census carry over unchanged.

  Per-unit write and per-unit cap (#11). Each page is written the moment it
  returns, and each page is capped, so one site that clicks through a hundred
  language controls cannot hold the batch or hide the progress of the rest.

  A refusal is not a verdict. A page that comes back blocked stays blocked in
  the store; nothing here decides a URL is dead.
"""
from __future__ import annotations
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetchpage import UA, _pack  # noqa: E402

NOTHING_TO_RECOVER = {"parked", "notfound"}


async def _render(ctx, url, timeout_ms):
    pg = await ctx.new_page()
    try:
        resp = await pg.goto(url, wait_until="domcontentloaded",
                             timeout=timeout_ms)
        try:
            await pg.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        html = await pg.content()
        return _pack(url, pg.url, resp.status if resp else 0, html, "playwright")
    finally:
        await pg.close()


async def _worker(browser, queue, store, sem, timeout_ms, stats):
    while True:
        try:
            url = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        async with sem:
            ctx = await browser.new_context(
                user_agent=UA, locale="ko-KR",
                viewport={"width": 1366, "height": 900},
                ignore_https_errors=True)
            try:
                r = await asyncio.wait_for(
                    _render(ctx, url, timeout_ms), timeout=timeout_ms / 1000 + 20)
            except Exception as e:
                r = None
                stats["err"] += 1
            finally:
                try:
                    await ctx.close()
                except Exception:
                    pass
        if r is not None:
            prev = store.get(url)
            if prev is None or r["state"] == "ok" or r["n_text"] > prev.get("n_text", 0):
                store.put(r)
            if r["state"] == "ok":
                stats["ok"] += 1
        stats["done"] += 1
        if stats["done"] % 20 == 0:
            print(f"  browser {stats['done']}/{stats['total']} | "
                  f"recovered {stats['ok']} | errors {stats['err']}", flush=True)


async def _run(urls, store, conc, timeout_ms):
    from playwright.async_api import async_playwright
    q = asyncio.Queue()
    for u in urls:
        q.put_nowait(u)
    stats = {"done": 0, "ok": 0, "err": 0, "total": len(urls)}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-gpu", "--mute-audio"])
        sem = asyncio.Semaphore(conc)
        await asyncio.gather(*[
            _worker(browser, q, store, sem, timeout_ms, stats)
            for _ in range(conc)])
        await browser.close()
    return stats


def recover(store, urls=None, conc=6, timeout_ms=25000):
    """Re-read every stored URL that is not `ok` and could still turn out to be
    readable. Pass `urls` to restrict the set."""
    pool = urls if urls is not None else list(store.rows)
    hard = [u for u in dict.fromkeys(pool)
            if store.get(u) is None
            or (store.get(u)["state"] != "ok"
                and store.get(u)["state"] not in NOTHING_TO_RECOVER
                and store.get(u).get("how") != "playwright")]
    print(f"browser recovery: {len(hard)} urls at concurrency {conc}", flush=True)
    if not hard:
        return {"done": 0, "ok": 0, "err": 0, "total": 0}
    return asyncio.run(_run(hard, store, conc, timeout_ms))


if __name__ == "__main__":
    import argparse
    from webcache import PageStore
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=25000)
    a = ap.parse_args()
    st = PageStore(a.store)
    s = recover(st, conc=a.conc, timeout_ms=a.timeout)
    print(s)
