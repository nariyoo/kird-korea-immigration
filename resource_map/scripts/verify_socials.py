# -*- coding: utf-8 -*-
"""Keep only the social accounts that belong to the organization.

`find_socials.py` accepts an account read off the organization's own website
without further test, which is right: the organization published the link.
For organizations with no website it also searched, and that half went wrong in
exactly the way the census warned about (#15, a social account that came from a
name search).

What the search returned was pages ABOUT the organization, not pages BY it:

    blog.naver.com/PostView.naver     61 organizations   (not even a blog, a
                                                          post-viewer path)
    blog.naver.com/2mcool             27 organizations
    blog.naver.com/yshan941           로뎀이주민지원센터 and 마하다문화교육센터
    facebook.com/sidacool             (사)외국인근로자문화센터

The snippet named the organization because the post was about it. So the test
has to move off the snippet and onto the account itself.

Three rules, applied only to searched accounts:

  1. A Naver blog or cafe URL's first path segment is a USER ID, not a name.
     Nothing in a search result can tie it to an organization, so searched
     blogs and cafes are dropped outright. The same for YouTube and KakaoTalk
     channels, which add no contact route the phone number does not.
  2. A Facebook or Instagram handle IS the page's own identity. It is kept when
     the profile page itself, fetched, names the organization; or when the
     search result TITLE (which for a profile is the page's own name) carries
     the organization's whole name.
  3. A handle attached to two different organizations is wrong for at least one
     of them, so it is dropped from both.

Run:  python scripts/v2/verify_socials.py
"""
from __future__ import annotations
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import idmatch  # noqa: E402
from webcache import PageStore, crawl  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")

SEARCH_DROP = ["naver_blog", "naver_cafe", "youtube", "kakao", "band"]
SEARCH_KEEP = ["facebook", "instagram"]
JUNK_PATH = re.compile(r"(PostView|postview)", re.I)


def handle_of(url):
    m = re.search(r"(?:facebook|instagram)\.com/([^/?#]+)", str(url or ""), re.I)
    return (m.group(1).lower() if m else "")


def main(a):
    df = pd.read_csv(a.socials, dtype=str).fillna("")
    frame = pd.read_csv(a.frame, dtype=str).fillna("")
    org = {r["facility_id"]: r for _, r in frame.iterrows()}
    plats = [c for c in df.columns
             if c not in ("facility_id", "name_ko", "website", "src")
             and not c.endswith("_title")]

    before = {p: int((df[p] != "").sum()) for p in plats}
    searched = df.src == "searched_no_website"
    print(f"{len(df)} rows | read off own site {(df.src=='own_site').sum()} "
          f"| searched {int(searched.sum())}")

    # rule 1
    for p in SEARCH_DROP:
        if p in df.columns:
            df.loc[searched, p] = ""

    # rule 2: fetch the profile and read its own name
    want = [u for u in
            pd.concat([df.loc[searched, p] for p in SEARCH_KEEP if p in df.columns])
            if u and not JUNK_PATH.search(u)]
    store = PageStore(os.path.join(OUT, "pages_social.jsonl"))
    print(f"profiles to read: {len(set(want))}")
    crawl(list(dict.fromkeys(want)), store, workers=12, use_browser=False,
          label="socials")

    kept = collections.Counter()
    for i, r in df[searched].iterrows():
        o = org.get(r["facility_id"], {})
        for p in SEARCH_KEEP:
            u = r.get(p, "")
            if not u:
                continue
            if JUNK_PATH.search(u):
                df.at[i, p] = ""
                continue
            page = store.get(u) or {}
            name_src = " ".join([page.get("title", ""),
                                 page.get("og_site_name", "")])
            fp = idmatch.fingerprint(o, "", name_src)
            # The whole name, in the page's OWN name. Facebook and Instagram
            # wall most profiles, and an unreadable profile is dropped rather
            # than guessed at: a wrong contact link is worse than none, and the
            # organization's phone number is still on the card.
            ok = "name_full" in fp["evidence"]
            if not ok and page.get("state") != "ok":
                # Facebook and Instagram wall most profiles to a non-logged-in
                # client. Google indexed them from a session that was not
                # walled, and for a profile its result TITLE is the page's own
                # name. Admit it, on the whole name only.
                ok = "name_full" in idmatch.fingerprint(
                    o, "", str(r.get(p + "_title", "")))["evidence"]
            if ok:
                kept[p] += 1
            else:
                df.at[i, p] = ""

    # rule 3: a handle on two organizations is wrong for at least one
    for p in SEARCH_KEEP:
        if p not in df.columns:
            continue
        c = collections.Counter(handle_of(u) for u in df[p] if u)
        dupes = {h for h, n in c.items() if h and n > 1}
        if dupes:
            n = int(df[p].map(lambda u: handle_of(u) in dupes).sum())
            df.loc[df[p].map(lambda u: handle_of(u) in dupes), p] = ""
            print(f"  dropped {n} {p} links whose handle sat on 2+ organizations")

    has = df[plats].apply(lambda row: any(str(v).strip() for v in row), axis=1)
    df.loc[~has, "src"] = ""
    df.to_csv(a.out, index=False, encoding="utf-8-sig")

    print("\n=== accounts per platform, before and after ===")
    for p in plats:
        print(f"  {p:12s} {before[p]:5d} -> {int((df[p] != '').sum()):5d}")
    print("\n=== provenance after ===")
    print(df.src.value_counts().to_string())
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--socials", default=os.path.join(OUT, "socials_v2.csv"))
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "socials_v2.csv"))
    sys.exit(main(ap.parse_args()))
