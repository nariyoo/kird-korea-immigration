# -*- coding: utf-8 -*-
"""Build the hand-search worklist: what the automatic pass could not settle.

A row lands here when the search found nothing, or found something an
adversarial read judged to be a directory, a parent body, or a different
organization. The automatic pass has already removed the wrong URL, so these
rows currently carry no website at all. That is the correct state: an empty
field is a true statement, and the wrong URL was not.

The batches are cut by 시도 so one person (or one agent) works a coherent
region and can reuse what they learn about that province's portals.

Run:  python scripts/v2/make_search_batches.py --batches 8
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
BATCH = os.path.join(ROOT, "data", "raw", "v2", "websearch")

KEEP = {"own", "settled_by_key"}


def main(a):
    frame = pd.read_csv(a.frame, dtype=str).fillna("")
    ver = pd.read_csv(a.verified, dtype=str).fillna("")
    ok = {r.facility_id: r.final_website for _, r in ver.iterrows()
          if r.get("final_website", "").strip()}
    why = {r.facility_id: (r.get("llm_verdict", "") or "", r.get("url", ""))
           for _, r in ver.iterrows()}

    rows = []
    for _, r in frame.iterrows():
        fid = r["facility_id"]
        if fid in ok:
            continue
        v, tried = why.get(fid, ("not_found", ""))
        rows.append({
            "facility_id": fid,
            "name_ko": r["name_ko"],
            "category": r.get("category", ""),
            "sido": r.get("sido", ""),
            "sigungu": r.get("sigungu", ""),
            "road_address": r.get("road_address", ""),
            "phone": r.get("phone", ""),
            "auto_result": v,
            "auto_rejected_url": tried,
            "website": "", "evidence": "", "facebook": "", "instagram": "",
            "band": "", "naver_cafe": "", "kakao": "", "note": "",
        })
    todo = pd.DataFrame(rows)
    print(f"frame {len(frame)} | settled automatically {len(ok)} "
          f"| for hand search {len(todo)}")
    print("\n=== why the automatic pass could not settle them ===")
    print(todo.auto_result.value_counts().to_string())
    print("\n=== by category ===")
    print(todo.category.value_counts().head(14).to_string())

    os.makedirs(BATCH, exist_ok=True)
    todo = todo.sort_values(["sido", "sigungu", "name_ko"]).reset_index(drop=True)
    n = int(a.batches)
    size = -(-len(todo) // n)
    for i in range(n):
        part = todo.iloc[i * size:(i + 1) * size]
        if not len(part):
            continue
        p = os.path.join(BATCH, f"batch_{i+1:02d}.csv")
        part.to_csv(p, index=False, encoding="utf-8-sig")
        regions = ", ".join(sorted({x for x in part.sido if x})[:4])
        print(f"  batch_{i+1:02d}.csv  {len(part):4d} rows  {regions}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--verified", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--batches", type=int, default=8)
    sys.exit(main(ap.parse_args()))
