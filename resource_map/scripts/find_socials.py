# -*- coding: utf-8 -*-
"""Social accounts, with the same provenance discipline as the websites.

The rule comes from a case in the US census (#15): the Korean American Senior
Association of Anchorage carried a LinkedIn, a YouTube, an X account, an email
and a phone number that all belonged to the Korean American Center in Orange
County, because a name search returns the largest same-name organization in the
country and nothing checked.

So:

  own_site   the account is linked FROM the organization's own verified
             website. This is evidence, and it is the only unconditional keep.
  searched   the account was found by searching the name. Kept ONLY when the
             organization has no website at all (the account is then the only
             way to reach it) AND the profile names the organization in full,
             not by a shared token.

Anything else is dropped. In Korea the channels that matter for small migrant
organizations are Facebook, Instagram, Naver Band, Naver Cafe and KakaoTalk
channels, so those are the ones searched; a searched YouTube, X or LinkedIn
adds no contact route and carries the same risk, so it is never searched for.

Run:  python scripts/v2/find_socials.py --frame data/processed/v2/frame_v2.csv
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import urllib.parse as up
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import idmatch  # noqa: E402
import serper  # noqa: E402
from webcache import PageStore  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")

PLATFORMS = {
    "facebook": re.compile(r"facebook\.com/", re.I),
    "instagram": re.compile(r"instagram\.com/", re.I),
    "youtube": re.compile(r"(youtube\.com/|youtu\.be/)", re.I),
    "band": re.compile(r"band\.us/", re.I),
    "naver_cafe": re.compile(r"cafe\.naver\.com/", re.I),
    "naver_blog": re.compile(r"(blog\.naver\.com|m\.blog\.naver\.com)/", re.I),
    "kakao": re.compile(r"pf\.kakao\.com/", re.I),
}
SEARCHABLE = ["facebook", "instagram", "band", "naver_cafe", "naver_blog"]

BAD_PATH = {
    "facebook": re.compile(
        r"facebook\.com/(sharer|login|help|policies|events|watch|marketplace|"
        r"story\.php|photo|permalink\.php|media|hashtag|people|groups|"
        r"privacy|terms|business|ads)", re.I),
    "instagram": re.compile(
        r"instagram\.com/(p|explore|accounts|reel|reels|tv|stories|about|"
        r"developer|legal)/", re.I),
}


def handle(url, plat):
    p = up.urlparse(url)
    seg = [s for s in (p.path or "").split("/") if s]
    if plat == "facebook" and "profile.php" in (p.path or ""):
        pid = up.parse_qs(p.query).get("id", [""])[0]
        return f"profile.php?id={pid}" if pid.isdigit() else ""
    if plat in ("naver_blog", "naver_cafe", "band", "kakao"):
        return seg[0] if seg else ""
    if not seg:
        return ""
    s = seg[0]
    if s.lower() in ("pages",) and len(seg) > 1:
        s = seg[1]
    return s


def canon(url, plat):
    h = handle(url, plat)
    if not h:
        return ""
    base = {"facebook": "https://www.facebook.com/",
            "instagram": "https://www.instagram.com/",
            "youtube": "https://www.youtube.com/",
            "band": "https://band.us/",
            "naver_cafe": "https://cafe.naver.com/",
            "naver_blog": "https://blog.naver.com/",
            "kakao": "https://pf.kakao.com/"}[plat]
    if plat in ("facebook", "instagram") and "profile.php" not in h:
        h = re.sub(r"[^A-Za-z0-9._\-가-힣]", "", h)
        if not h:
            return ""
    return base + h + ("/" if plat in ("facebook", "instagram") else "")


def platform_of(url):
    for k, rx in PLATFORMS.items():
        if rx.search(url or ""):
            return k
    return ""


def from_own_site(org, page):
    """Accounts printed on the organization's own site. No name test is needed:
    the site is already confirmed to be the organization's."""
    out = {}
    for href in (page.get("socials") or []):
        plat = platform_of(href)
        if not plat:
            continue
        bad = BAD_PATH.get(plat)
        if bad and bad.search(href):
            continue
        u = canon(href, plat)
        if u and plat not in out:
            out[plat] = u
    return out


def _names_org(org, text):
    """Strict: the profile must carry the WHOLE name, or two distinctive tokens
    together with the region. One shared token is what put the wrong Facebook
    page on organizations in v1."""
    fp = idmatch.fingerprint(org, text or "")
    ev = fp["evidence"]
    if "name_full" in ev:
        return True
    return "tokens2" in ev and "region" in ev


def searched(org):
    """Only for organizations with no website. Uses the search result's own
    title and snippet plus the handle, because Facebook and Instagram profile
    pages are bot-walled to a plain client and a login wall carries no name."""
    name = str(org.get("name_ko") or "").strip()
    sg = str(org.get("sigungu") or "").strip()
    out = {}
    for plat in SEARCHABLE:
        label = {"facebook": "facebook", "instagram": "instagram",
                 "band": "네이버 밴드", "naver_cafe": "네이버 카페",
                 "naver_blog": "네이버 블로그"}[plat]
        for o in serper.organic(f'"{name}" {sg} {label}'.strip(), 8):
            link = (o.get("link") or "").strip()
            if platform_of(link) != plat:
                continue
            bad = BAD_PATH.get(plat)
            if bad and bad.search(link):
                continue
            # The TITLE of a profile result is the page's own name, which is
            # what identity should be read from. The SNIPPET is the post text
            # and names the organization whenever the post is merely ABOUT it;
            # matching on that is how blog.naver.com/PostView.naver ended up on
            # 61 organizations. Keep both, but keep them apart.
            u = canon(link, plat)
            if not u:
                continue
            title = o.get("title", "")
            if _names_org(org, " ".join([title, handle(link, plat)])):
                out[plat] = u
                out[plat + "_title"] = title[:160]
                break
    return out


def run(frame, websites_csv, out_csv, workers=8):
    df = pd.read_csv(frame, dtype=str).fillna("")
    web = {}
    if websites_csv and os.path.exists(websites_csv):
        w = pd.read_csv(websites_csv, dtype=str).fillna("")
        col = "final_website" if "final_website" in w.columns else "url"
        for _, r in w.iterrows():
            if r.get(col, "").strip():
                web[r["facility_id"]] = r[col].strip()
    for _, r in df.iterrows():
        if r["facility_id"] not in web and r.get("website", "").strip():
            web[r["facility_id"]] = r["website"].strip()

    store = PageStore(os.path.join(OUT, "pages_candidates.jsonl"))
    store2 = PageStore(os.path.join(OUT, "pages_current.jsonl"))

    rows = []
    need_search = []
    for o in df.to_dict("records"):
        u = web.get(o["facility_id"], "")
        page = (store.get(u) or store2.get(u) or {}) if u else {}
        got = from_own_site(o, page) if page.get("state") == "ok" else {}
        rec = {"facility_id": o["facility_id"], "name_ko": o["name_ko"],
               "website": u, "src": "own_site" if got else ""}
        for p in PLATFORMS:
            rec[p] = got.get(p, "")
            rec[p + "_title"] = ""
        rows.append(rec)
        # "has a website" is not the same as "its accounts can be read off it".
        # mapcast.org answers with almost no text, so 아시아평화를향한이주 got a
        # website and lost the Facebook page and Instagram account it had had.
        # A site that cannot be read tells us nothing, which is the same
        # position as having no site at all, so search in both cases.
        if not got:
            need_search.append(o)

    print(f"{len(df)} rows | accounts read off own site: "
          f"{sum(1 for r in rows if r['src'] == 'own_site')} | "
          f"nothing readable on the site, searching: {len(need_search)}")

    found = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(searched, o): o["facility_id"] for o in need_search}
        done = 0
        for fu in as_completed(futs):
            fid = futs[fu]
            try:
                found[fid] = fu.result()
            except Exception:
                found[fid] = {}
            done += 1
            if done % 50 == 0:
                print(f"  searched {done}/{len(need_search)}", flush=True)

    idx = {r["facility_id"]: r for r in rows}
    for fid, got in found.items():
        if not got:
            continue
        r = idx[fid]
        r["src"] = "searched_no_website"
        for p, u in got.items():
            r[p] = u

    res = pd.DataFrame(rows)
    res.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("\n=== social accounts by provenance ===")
    print(res.src.value_counts().to_string())
    print("\n=== by platform ===")
    for p in PLATFORMS:
        print(f"{(res[p] != '').sum():5d}  {p}")
    print(f"\nwrote {out_csv}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2.csv"))
    ap.add_argument("--websites", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "socials_v2.csv"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run(a.frame, a.websites, a.out, a.workers)
