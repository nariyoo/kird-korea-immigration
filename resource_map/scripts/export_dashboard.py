# -*- coding: utf-8 -*-
"""Write the dashboard's data files from orgs.json.

orgs.json is the record. facilities.json is a projection of it kept in the
shape the current pages already read, so the site keeps working while the
richer fields are wired in. facility_counts.json is the per-시군구 numerator
for the density figures.

The numerator is NOT "every row". It is rows whose unit_type is a service the
public can walk into and that are not closed, per docs/INCLUSION_CRITERIA.md
section 3. A research institute and a national coordinating body do not make a
district better served, and counting them was one of the two things wrong with
the v1 density figures (the other was 다누리 portal links standing in for 216
family-centre homepages).

Run:  python scripts/v2/export_dashboard.py
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DASH = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard"))
REDESIGN = os.path.abspath(os.path.join(ROOT, "..", "09_design_mockups", "redesign"))

# the v1 category vocabulary the existing pages switch on
TYPE_TO_CAT = {
    "family_center": "multicultural_family_center",
    "resident_center": "foreign_resident_center",
    "worker_center": "foreign_worker_center",
    "program_site": "social_integration_program",
    "shelter": "violence_victim_shelter",
    "medical": "medical_support_facility",
    "legal": "legal_aid",
    "youth_edu": "migrant_youth_center",
    "community": "migrant_community_org",
    "religious_site": "migrant_religious_site",
    "ngo": "religious_or_civic_ngo",
    "administrative": "immigration_office",
    "research": "research_institute",
    "umbrella": "religious_or_civic_ngo",
}


def main(a):
    payload = json.load(io.open(a.orgs, encoding="utf-8"))
    orgs = payload["orgs"]
    density = set(payload.get("density_types", []))

    # ---- facilities.json, in the shape the pages already read
    facs = []
    for o in orgs:
        f = {
            "name_ko": o["name"],
            "category": TYPE_TO_CAT.get(o["type"], o["type"] or "religious_or_civic_ngo"),
            "governing_ministry": o.get("ministry", ""),
            "operator_type": o.get("operator", ""),
            "sido": o.get("sido", ""),
            "sigungu": o.get("sigungu", ""),
            "phone": o.get("tel", ""),
            "website": o.get("web", ""),
            "operational_status": o.get("status", ""),
            "verified": "True" if o.get("web_tier") in ("A", "B") else "False",
            "data_source": (o.get("src") or [""])[0],
            "addr": o.get("addr", ""),
            "cats": [TYPE_TO_CAT.get(o["type"], o["type"])] if o.get("type") else [],
            # new fields the pages can start using
            "unit_type": o.get("type", ""),
            "serves": o.get("serves", ""),
            "web_tier": o.get("web_tier", ""),
            "web_src": o.get("web_src", ""),
            "incl_basis": o.get("incl_basis", ""),
            "programs": o.get("programs", []),
        }
        for k in ("facebook", "instagram", "band", "naver_cafe", "naver_blog",
                  "youtube", "kakao"):
            if o.get(k):
                f[k] = o[k]
        if o.get("lat") is not None and o.get("lng") is not None:
            f["lat"] = o["lat"]
            f["lng"] = o["lng"]
        facs.append(f)

    out = {"updated": payload["updated"], "version": payload["version"],
           "count": len(facs),
           "mapped": sum(1 for f in facs if "lat" in f),
           "facilities": facs}
    with io.open(os.path.join(DASH, "facilities.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"facilities.json: {len(facs)} rows, {out['mapped']} mapped")

    # ---- facility_counts.json: the density numerator only
    idx = json.load(io.open(os.path.join(DASH, "data", "indices.json"),
                            encoding="utf-8"))["data"]
    Y = max(idx["by_sigungu"], key=int)
    pop = {(r["sido"], r["sigungu"]): r.get("foreign_total") or 0
           for r in idx["by_sigungu"][Y]}

    cnt = collections.Counter()
    skipped = collections.Counter()
    for o in orgs:
        if o.get("type") not in density or o.get("status") == "closed":
            skipped[o.get("type") or "(none)"] += 1
            continue
        key = (o.get("sido", ""), o.get("sigungu", ""))
        if not key[1]:
            skipped["no_sigungu"] += 1
            continue
        cnt[key] += 1

    counts = {}
    unmatched = []
    for (sd, sg), n in cnt.items():
        p = pop.get((sd, sg))
        if p is None:
            unmatched.append(f"{sd}|{sg}")
            continue
        counts[f"{sd}|{sg}"] = {
            "count": n,
            "per_10k_foreign": round(n / (p / 10000), 2) if p else 0}
    with io.open(os.path.join(REDESIGN, "facility_counts.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(counts, fh, ensure_ascii=False)
    print(f"facility_counts.json: {len(counts)} 시군구, "
          f"{sum(v['count'] for v in counts.values())} facilities counted")
    print(f"  excluded from the numerator: "
          f"{sum(skipped.values())} ({dict(skipped.most_common(8))})")
    if unmatched:
        print(f"  WARNING {len(unmatched)} 시군구 not in the population index "
              f"(counted nowhere): {unmatched[:10]}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", default=os.path.join(DASH, "orgs.json"))
    sys.exit(main(ap.parse_args()))
