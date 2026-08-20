# -*- coding: utf-8 -*-
"""Measure the misattribution in the websites and socials already published.

This answers Nari's question 3 with a number instead of an impression. It does
not change anything; it writes a verdict table and a review sheet.

Method, in the order the census work found it has to run:
  1. Classify the URL by what the HOST is (aggregator / social / news / portal /
     filejunk). These are wrong regardless of which organization they sit on.
  2. Fetch every distinct URL once, escalating requests -> curl_cffi ->
     Playwright, and record blocked separately from dead. A refusal is not
     evidence of anything.
  3. Fingerprint the page against the organization (phone, street address,
     whole name, region, distinctive tokens) and tier the evidence.
  4. Collide on the normalized URL, not the host, and mark the clusters.
  5. Flag a bare parent domain held by a row whose name says it is a branch.

Run:  python scripts/v2/audit_current_web.py
"""
from __future__ import annotations
import json
import os
import sys
import collections
import urllib.parse as up

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import idmatch  # noqa: E402
import hosts  # noqa: E402
from webcache import PageStore, crawl  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DASH = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard"))
OUTDIR = os.path.join(ROOT, "data", "processed", "v2")
os.makedirs(OUTDIR, exist_ok=True)
STORE = os.path.join(OUTDIR, "pages_current.jsonl")


def load_frame():
    """master_all.csv is the of-record frame; facilities.json is what the site
    actually publishes and is the only place the fb/ig values live."""
    m = pd.read_csv(os.path.join(ROOT, "data", "processed", "master_all.csv"),
                    dtype=str).fillna("")
    fac = json.load(open(os.path.join(DASH, "facilities.json"),
                        encoding="utf-8"))["facilities"]
    # facilities.json has no facility_id, so join on name + sido, the same key
    # gen_rest_data.py already uses. Report how many rows fail to join instead
    # of letting a silent partial join look like success.
    by_key = {}
    for x in fac:
        k = (x.get("name_ko") or "").strip() + "|" + (x.get("sido") or "").strip()
        by_key.setdefault(k, []).append(x)
    joined = amb = miss = 0
    rows = []
    for r in m.to_dict("records"):
        k = r["name_ko"].strip() + "|" + r.get("sido", "").strip()
        cands = by_key.get(k, [])
        if len(cands) == 1:
            x = cands[0]
            joined += 1
        elif len(cands) > 1:
            x = cands[0]
            amb += 1
        else:
            x = {}
            miss += 1
        r["fb"] = x.get("facebook", "")
        r["ig"] = x.get("instagram", "")
        r["published"] = bool(x)
        r["addr"] = x.get("addr", "") or r.get("road_address", "")
        # Two different URLs can sit on one row and they fail differently. The
        # roster value is what the source list handed over (for the family
        # centres that is the national 다누리 portal, the same URL 216 times).
        # The published value is what the enrichment wrote and what a visitor
        # actually clicks. Audit the published one, keep the roster one beside
        # it, and never let the two be silently confused.
        r["website_roster"] = r.get("website", "")
        r["website_published"] = x.get("website", "")
        r["website"] = r["website_published"] or r["website_roster"]
        r["which"] = ("published" if r["website_published"]
                      else ("roster" if r["website_roster"] else ""))
        rows.append(r)
    print(f"frame {len(rows)} | joined to published {joined} | "
          f"ambiguous key {amb} | not published {miss}")
    df = pd.DataFrame(rows)
    print(f"audited URL taken from: "
          f"{(df.which == 'published').sum()} published, "
          f"{(df.which == 'roster').sum()} roster only, "
          f"{(df.which == '').sum()} none")
    return df


def main():
    df = load_frame()
    urls = sorted({u.strip() for u in df["website"] if u and u.strip()})
    print(f"distinct current website URLs: {len(urls)}")

    store = PageStore(STORE)
    crawl(urls, store, workers=8, label="current-web")

    # ---- collision clusters on the normalized URL, never the bare host
    norm = df["website"].map(hosts.norm_url)
    cnt = collections.Counter(u for u in norm if u)
    # a site builder tenant is not a collision
    plat = {u for u in cnt if hosts.PLATFORM.search(u)}

    out = []
    for r, nu in zip(df.to_dict("records"), norm):
        w = (r.get("website") or "").strip()
        rec = {"name_ko": r["name_ko"], "category": r["category"],
               "sido": r["sido"], "sigungu": r["sigungu"],
               "phone": r["phone"], "addr": r.get("addr", ""),
               "website": w, "norm": nu, "which": r.get("which", ""),
               "website_roster": r.get("website_roster", ""),
               "data_source": r.get("data_source", ""),
               "fb": r.get("fb", ""), "ig": r.get("ig", "")}
        if not w:
            rec.update(verdict="no_website", labels="", state="", tier="",
                       evidence="", page_title="", collision=0)
            out.append(rec)
            continue

        p = store.get(w) or {}
        title, og = p.get("title", ""), p.get("og_site_name", "")
        labels = hosts.classify(w, title, og)
        state = p.get("state", "unfetched")
        fp = idmatch.fingerprint(r, p.get("text", ""), title + " " + og)
        coll = cnt.get(nu, 0) if nu not in plat else 1

        if set(labels) & hosts.DEMOTE:
            verdict = "not_a_homepage:" + ",".join(sorted(set(labels) & hosts.DEMOTE))
        elif state in ("blocked", "error"):
            verdict = "unverifiable_blocked"
        elif state in ("parked", "notfound"):
            verdict = "dead"
        elif state in ("thin", "spa"):
            verdict = "unverifiable_thin"
        elif fp["tier"] in ("A", "B"):
            verdict = "confirmed_" + fp["tier"]
        elif fp["tier"] == "C":
            verdict = "weak_C"
        else:
            verdict = "name_absent"
        if coll > 1 and not verdict.startswith("not_a_homepage"):
            verdict += "+collision"

        rec.update(verdict=verdict, labels=",".join(labels), state=state,
                   tier=fp["tier"] or "", evidence=",".join(fp["evidence"]),
                   page_title=title[:120], collision=coll)
        out.append(rec)

    res = pd.DataFrame(out)
    res.to_csv(os.path.join(OUTDIR, "audit_current_web.csv"), index=False,
               encoding="utf-8-sig")

    print("\n=== verdict on the 906-row published frame ===")
    base = res[res.website != ""]
    for v, n in res.verdict.value_counts().items():
        print(f"{n:5d}  {v}")
    print(f"\nwith a website: {len(base)} of {len(res)}")
    good = base.verdict.str.startswith("confirmed").sum()
    print(f"identity-confirmed (tier A or B): {good} ({good/max(len(base),1):.1%})")

    print("\n=== by category ===")
    piv = (base.assign(ok=base.verdict.str.startswith("confirmed"))
              .groupby("category").agg(n=("ok", "size"), confirmed=("ok", "sum")))
    piv["rate"] = (piv.confirmed / piv.n).map(lambda x: f"{x:.0%}")
    print(piv.sort_values("n", ascending=False).to_string())

    review = base[~base.verdict.str.startswith("confirmed")]
    review.sort_values(["verdict", "category", "name_ko"]).to_csv(
        os.path.join(OUTDIR, "review_web_current.csv"), index=False,
        encoding="utf-8-sig")
    print(f"\nreview sheet: {len(review)} rows -> "
          f"data/processed/v2/review_web_current.csv")


if __name__ == "__main__":
    main()
