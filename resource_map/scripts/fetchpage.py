# -*- coding: utf-8 -*-
"""Fetch a page and return its readable text, or say honestly why it could not.

Three lessons are wired in here.

1. A capture is BLOCKED when it is an interstitial, not only when it is empty
   (census failure #13). A Cloudflare or Akamai challenge is several thousand
   characters long and sails past a `len(text) < 300` test, after which the
   challenge text gets coded as the organization's own.
2. Dead detection from outside Korea is unreliable. The previous KIRD run
   marked 242 of 650 URLs dead with plain `requests`; .go.kr hosts refuse
   non-Korean TLS fingerprints and familynet.or.kr answers HTTP 400. So a URL
   is only "dead" after requests AND a browser-fingerprinted client AND a real
   browser have all failed.
3. A long resumable job writes per unit and caps per unit (#11), so one slow
   site cannot hide the progress of the rest.

Escalation ladder: requests -> curl_cffi (Chrome TLS) -> Playwright Chromium.
"""
from __future__ import annotations
import re
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Interstitials and walls. Matching any of these means we did NOT read the site.
WALL = re.compile(
    r"(just a moment|checking your browser|cf-browser-verification|cf_chl|"
    r"attention required!?\s*\|\s*cloudflare|enable javascript and cookies|"
    r"ddos-guard|incapsula|imperva|access denied|forbidden|error 1020|"
    r"request unsuccessful|akamai|request blocked|blocked by|"
    r"unusual traffic|rate limit|too many requests|"
    r"자동\s*등록\s*방지|비정상적인\s*접근|접근이\s*차단|보안정책에\s*의해|"
    r"잠시\s*후\s*다시\s*시도|서비스\s*점검\s*중|일시적으로\s*이용할\s*수\s*없)",
    re.I,
)
# Pages that exist but carry nothing: parked domains, for-sale pages, blank CMS.
PARKED = re.compile(
    r"(this domain (is|may be) for sale|buy this domain|도메인.{0,10}판매|"
    r"sedoparking|hugedomains|afternic|dan\.com|"
    r"준비\s*중\s*입니다|홈페이지\s*준비중|under construction|coming soon|"
    r"default web site page|apache2? (ubuntu|debian) default page|"
    r"welcome to nginx|it works!)",
    re.I,
)
# A JS shell: the HTML is a mount point and the content never arrives to requests.
SPA_HINT = re.compile(r'<div id="(root|app|__next)"', re.I)

MIN_TEXT = 220


def _text_from_html(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    title = (soup.title.get_text(" ", strip=True) if soup.title else "")
    og = ""
    m = soup.find("meta", property="og:site_name")
    if m and m.get("content"):
        og = m["content"].strip()
    desc = ""
    m = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description")
    if m and m.get("content"):
        desc = m["content"].strip()
    body = soup.get_text(" ", strip=True)
    body = re.sub(r"\s+", " ", body)
    # Outbound social links AS PRINTED ON THIS PAGE. A social account read off
    # the organization's own site is evidence; one found by searching its name
    # is not (census failure #15), so the two are never mixed later.
    socials = []
    for a in soup.find_all("a", href=True):
        h = a["href"].strip()
        if SOCIAL_HREF.search(h):
            socials.append(h)
    seen, uniq = set(), []
    for h in socials:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return title, og, desc, body, uniq[:40]


SOCIAL_HREF = re.compile(
    r"(facebook\.com|instagram\.com|youtube\.com/|youtu\.be/|twitter\.com|x\.com/|"
    r"blog\.naver\.com|cafe\.naver\.com|band\.us|pf\.kakao\.com|"
    r"threads\.(net|com)|tiktok\.com|linkedin\.com)", re.I)


def _classify(title, og, desc, body, html, status=200):
    joined = " ".join([title, og, desc, body[:4000]])
    if WALL.search(joined) or WALL.search(html[:6000]):
        return "blocked"
    # A short body behind 400/403/406/429/451 is a refusal, not an empty site.
    # Korean .go.kr / familynet hosts answer 400 to any non-Korean client, and
    # the previous run booked 242 of those as dead.
    if status in (400, 401, 403, 405, 406, 409, 429, 451) and len(body) < 1200:
        return "blocked"
    if PARKED.search(joined):
        return "parked"
    if status in (404, 410):
        return "notfound"
    if len(body) < MIN_TEXT:
        return "spa" if SPA_HINT.search(html or "") else "thin"
    return "ok"


def _pack(url, final_url, status, html, how):
    title, og, desc, body, socials = _text_from_html(html or "")
    state = _classify(title, og, desc, body, html or "", status or 0)
    return {"url": url, "final_url": final_url, "http": status, "how": how,
            "state": state, "title": title, "og_site_name": og,
            "description": desc, "text": body[:120000], "n_text": len(body),
            "socials": socials}


_META_CHARSET = re.compile(
    rb'charset\s*=\s*["\']?\s*([A-Za-z0-9_\-]+)', re.I)


def _decode(content, declared=None):
    """Korean pages are still served in EUC-KR/CP949 often enough that guessing
    wrong turns the whole page into mojibake and every name test then fails."""
    cands = []
    m = _META_CHARSET.search(content[:4096])
    if m:
        cands.append(m.group(1).decode("ascii", "ignore"))
    if declared:
        cands.append(declared)
    cands += ["utf-8", "cp949", "euc-kr"]
    seen = set()
    for enc in cands:
        e = (enc or "").lower().replace("ks_c_5601-1987", "cp949")
        if not e or e in seen:
            continue
        seen.add(e)
        try:
            return content.decode(e)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", "replace")


def fetch_requests(url, timeout=10):
    import requests
    r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    return _pack(url, r.url, r.status_code,
                 _decode(r.content, r.encoding), "requests")


def fetch_curl(url, timeout=12):
    from curl_cffi import requests as creq
    r = creq.get(url, headers=HEADERS, timeout=timeout, impersonate="chrome",
                 allow_redirects=True)
    return _pack(url, str(r.url), r.status_code,
                 _decode(r.content, getattr(r, "encoding", None)), "curl_cffi")


_PW = {"pw": None, "browser": None}


# The browser is the last rung of the ladder and the only one that can take the
# whole run down with it: a driver that dies mid-run raises
# "Connection closed while reading from the driver", which is not an error about
# any one page. Two full pipeline runs ended there. A failure to launch or a
# driver that goes away now disables the rung and the run continues on requests
# and curl_cffi, which is what the escalation ladder is for.
_PW_DEAD = []


def _browser():
    if _PW_DEAD:
        return None
    if _PW["browser"] is None:
        try:
            from playwright.sync_api import sync_playwright
            _PW["pw"] = sync_playwright().start()
            _PW["browser"] = _PW["pw"].chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled",
                      "--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as e:
            _PW_DEAD.append(str(e)[:160])
            print(f"  playwright unavailable, continuing without it: {_PW_DEAD[0]}",
                  flush=True)
            return None
    return _PW["browser"]


def close_browser():
    if _PW["browser"] is not None:
        try:
            _PW["browser"].close()
        finally:
            _PW["pw"].stop()
            _PW["browser"] = _PW["pw"] = None


def fetch_playwright(url, timeout=30000):
    br = _browser()
    if br is None:
        return None
    try:
        return _fetch_playwright(br, url, timeout)
    except Exception as e:
        # a dead driver is not a fact about this page; stop using the rung
        if "Connection closed" in str(e) or "Target page" in str(e):
            _PW_DEAD.append(str(e)[:160])
            _PW["browser"] = None
            print("  playwright driver went away, continuing without it",
                  flush=True)
        return None


def _fetch_playwright(br, url, timeout=30000):
    ctx = br.new_context(user_agent=UA, locale="ko-KR",
                         viewport={"width": 1366, "height": 900},
                         ignore_https_errors=True)
    try:
        pg = ctx.new_page()
        resp = pg.goto(url, wait_until="domcontentloaded", timeout=timeout)
        try:
            pg.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass
        html = pg.content()
        status = resp.status if resp else 0
        final = pg.url
        return _pack(url, final, status, html, "playwright")
    finally:
        ctx.close()


# Better = more likely to be the site's real content. "blocked" outranks
# "notfound" because a refusal says nothing about whether the site exists.
_RANK = {"ok": 0, "spa": 1, "blocked": 2, "thin": 3, "parked": 4,
         "notfound": 5, "error": 6}


def fetch(url, use_browser=True):
    """Escalate until the page is genuinely readable. `state` is one of
    ok / blocked / parked / thin / spa / notfound / error, and `how` says which
    client finally read it, so a later pass can tell a real dead site from a
    client that could not get in.

    Nothing here is allowed to conclude "dead" on its own. `state` plus `tried`
    is the evidence; the demotion rule lives in the caller."""
    tried = []
    best = None

    def keep(r):
        nonlocal best
        if r is None:      # the browser rung is unavailable this run
            return
        tried.append(f"{r['how']}:{r['http']}:{r['state']}")
        if best is None or _RANK[r["state"]] < _RANK[best["state"]] or (
                _RANK[r["state"]] == _RANK[best["state"]]
                and r["n_text"] > best["n_text"]):
            best = r
        return r["state"] == "ok"

    for fn, name in ((fetch_requests, "requests"), (fetch_curl, "curl_cffi")):
        try:
            if keep(fn(url)):
                best["tried"] = tried
                return best
        except Exception as e:
            tried.append(f"{name}:err:{type(e).__name__}")
        # A 404 is the server answering, not refusing. A second client with a
        # different TLS fingerprint gets the same 404 and costs another timeout.
        if best is not None and best["state"] == "notfound":
            break

    if use_browser and (best is None or best["state"] != "ok"):
        for _ in range(2):
            try:
                keep(fetch_playwright(url))
                break
            except Exception as e:
                tried.append(f"playwright:err:{type(e).__name__}")
                close_browser()
                time.sleep(1)

    if best is None:
        best = {"url": url, "final_url": None, "http": 0, "how": "none",
                "state": "error", "title": "", "og_site_name": "",
                "description": "", "text": "", "n_text": 0, "socials": []}
    best["tried"] = tried
    return best


if __name__ == "__main__":
    import sys, json
    for u in sys.argv[1:]:
        r = fetch(u)
        r["text"] = r["text"][:200]
        print(json.dumps(r, ensure_ascii=False, indent=1))
    close_browser()
