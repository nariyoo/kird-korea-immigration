# -*- coding: utf-8 -*-
"""Evidence that an organization exists and is active, for the ones with no site.

A website is one kind of evidence, not the only kind. Plenty of small migrant
organizations never built one: they run a Facebook page, or they appear in the
local paper when they open a Korean class, and that is the whole of their
public trace. Judging those rows on website text alone marks a real 이주민센터
as unverifiable and drops it, which is a false negative dressed up as rigour.

So this pass looks for two other traces and records them AS SUCH, never as a
website:

  news      an article, a municipal press release or a notice that names the
            organization, with its date. Dated within the last three years it
            says the organization was doing something recently.
  mention   a listing on a body that would know (a 연대체, a 지자체 page, a
            사업 공고), which says it existed when that page was written.

Nothing here fills the `web` field. The output feeds the inclusion coder as
extra evidence and gives the card a link when there is nothing else to show.

Run:  python scripts/v2/find_news_evidence.py
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import idmatch  # noqa: E402
import hosts  # noqa: E402
import serper  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")

DATE = re.compile(r"(20\d{2})[.\-/년]\s*(\d{1,2})?")
THIS_YEAR = dt.date.today().year


def _year(text):
    ys = [int(m.group(1)) for m in DATE.finditer(str(text or ""))]
    ys = [y for y in ys if 2000 <= y <= THIS_YEAR]
    return max(ys) if ys else None


def gather(org):
    """Up to four traces, each one a page that names this organization."""
    name = str(org.get("name_ko") or "").strip()
    sg = str(org.get("sigungu") or "").strip()
    sd = re.sub(r"(특별자치도|특별자치시|특별시|광역시|자치도|자치시)$", "",
                str(org.get("sido") or "").strip())
    if not name:
        return []
    out, seen = [], set()
    for q in (f'"{name}"', f'"{name}" {sg or sd}'.strip()):
        for pos, o in enumerate(serper.organic(q, 10)):
            link = (o.get("link") or "").strip()
            if not link:
                continue
            nu = hosts.norm_url(link)
            if not nu or nu in seen:
                continue
            title, snip = o.get("title", ""), o.get("snippet", "")
            # the result must NAME the organization, not merely share a word
            fp = idmatch.fingerprint(org, snip, title)
            if "name_full" not in fp["evidence"]:
                continue
            lab = hosts.classify(link, title, "")
            kind = ("news" if "news" in lab else
                    "social" if "social" in lab else
                    "portal" if "portal" in lab else "mention")
            seen.add(nu)
            out.append({"url": link, "kind": kind, "title": title[:160],
                        "snippet": snip[:300],
                        "year": _year(f"{title} {snip}"), "pos": pos})
            if len(out) >= 4:
                return out
    return out


def run(frame, websites, out_csv, workers=10):
    df = pd.read_csv(frame, dtype=str).fillna("")
    have = set()
    if websites and os.path.exists(websites):
        w = pd.read_csv(websites, dtype=str).fillna("")
        col = "final_website" if "final_website" in w.columns else "url"
        have = {r["facility_id"] for _, r in w.iterrows()
                if str(r.get(col, "")).strip()}
    todo = df[~df.facility_id.isin(have)].copy()
    print(f"frame {len(df)} | already has a website {len(have)} "
          f"| looking for other traces on {len(todo)}")

    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(gather, r): r["facility_id"]
                for _, r in todo.iterrows()}
        done = 0
        for fu in as_completed(futs):
            fid = futs[fu]
            try:
                res[fid] = fu.result()
            except Exception:
                res[fid] = []
            done += 1
            if done % 100 == 0:
                print(f"  searched {done}/{len(todo)}", flush=True)

    rows = []
    for _, r in todo.iterrows():
        hits = res.get(r["facility_id"], [])
        yrs = [h["year"] for h in hits if h["year"]]
        rows.append({
            "facility_id": r["facility_id"], "name_ko": r["name_ko"],
            "n_traces": len(hits),
            "latest_year": max(yrs) if yrs else "",
            "recent": "yes" if (yrs and max(yrs) >= THIS_YEAR - 3) else "no",
            "kinds": ",".join(sorted({h["kind"] for h in hits})),
            "traces": json.dumps(hits, ensure_ascii=False),
        })
    out = pd.DataFrame(rows)
    out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("\n=== traces found ===")
    print(f"  with at least one page that names them: "
          f"{(out.n_traces > 0).sum()} of {len(out)}")
    print(f"  dated within the last three years:      {(out.recent == 'yes').sum()}")
    print(out.kinds.value_counts().head(10).to_string())
    print(f"\nwrote {out_csv}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--websites", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "existence_evidence.csv"))
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()
    run(a.frame, a.websites, a.out, a.workers)
