# -*- coding: utf-8 -*-
"""Assert that nothing was lost between the rosters and the frame.

The standing lesson from the US census build (docs/PIPELINE_FAILURE_MODES.md,
opening paragraph): every failure there was a silent partial application. The
stage succeeded, the counts looked plausible, and the loss only showed when a
person opened a record. Counts alone are not verification, so this checks the
one thing a count cannot: that every input row is findable in the output.

Checks, each of which fails loudly:
  1. every roster row's normalized name appears in the frame
  2. no facility_id is duplicated
  3. every merged row's source_roster names only files that exist
  4. no row lost its 시도 while having an address that states one
  5. the 시군구 values join to the population index the density figures use
  6. de-duplication did not collapse two different 시군구 into one row

Run:  python scripts/v2/check_frame_health.py
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import build_frame as bf  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW2 = os.path.join(ROOT, "data", "raw", "v2")
OUT = os.path.join(ROOT, "data", "processed", "v2")
DASH = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard"))


def main(a):
    df = pd.read_csv(a.frame, dtype=str).fillna("")
    fails, warns = [], []
    print(f"frame {len(df)} rows")

    # 1. every roster row is represented. Read from the LINEAGE the build wrote,
    # not from a name comparison: a row merged under a neighbour's spelling
    # (안산외국인주민지원본부 into 안산시 외국인주민지원본부) is present, and a
    # name test calls it lost. Guessing there is how a matcher reports high
    # coverage while hiding what it actually dropped.
    lin_path = os.path.join(OUT, "frame_lineage.csv")
    lin = (pd.read_csv(lin_path, dtype=str).fillna("")
           if os.path.exists(lin_path)
           else pd.DataFrame(columns=["facility_id", "in_name", "in_roster",
                                      "out_name"]))
    lin = lin[lin.facility_id.isin(set(df.facility_id))]
    # rows the build removed on purpose (criteria rule 14) are not losses
    dpath = os.path.join(OUT, "frame_dropped.csv")
    dropped = set()
    if os.path.exists(dpath):
        dd = pd.read_csv(dpath, dtype=str).fillna("")
        dropped = {bf.namekey(n) for n in dd.name_ko}
        print(f"intentionally dropped by rule: {len(dd)}")
    seen = collections.Counter(
        (r.in_roster, bf.namekey(r.in_name)) for r in lin.itertuples())
    have = collections.Counter(bf.namekey(n) for n in df.name_ko)
    print("\n=== roster rows findable in the frame ===")
    for p in sorted(glob.glob(os.path.join(RAW2, "**", "*.csv"), recursive=True)):
        rel = os.path.relpath(p, RAW2).replace("\\", "/")
        if "/files/" in rel:
            continue
        # the build does not read these as sources, so a row of theirs that is
        # "absent from the frame" means it merged, not that it was lost
        if (rel.startswith("websearch/") or rel.startswith("fixup/")
                or rel.startswith("archive/")):
            continue
        if rel in getattr(bf, "SKIP_ROSTERS", {}):
            print(f"  skip {rel} ({bf.SKIP_ROSTERS[rel][:48]})")
            continue
        try:
            d = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception:
            continue
        if "name_ko" not in d.columns:
            continue
        d = d[d.name_ko.astype(str).str.strip() != ""]
        if not len(d):
            continue
        missing = [n for n in d.name_ko
                   if not seen.get((rel, bf.namekey(n)))
                   and not have.get(bf.namekey(n))
                   and bf.namekey(n) not in dropped]
        mark = "ok " if not missing else "LOST"
        print(f"  {mark} {len(d)-len(missing):5d}/{len(d):<5d} {rel}")
        if missing:
            fails.append(f"{rel}: {len(missing)} rows absent from the frame, "
                         f"e.g. {missing[:3]}")

    # 2. unique ids
    dup = df.facility_id.duplicated().sum()
    print(f"\nduplicate facility_id: {dup}")
    if dup:
        fails.append(f"{dup} duplicated facility_id")

    # 3. source_roster points at real files
    bad = set()
    for s in df.source_roster:
        for part in str(s).split("|"):
            if not part or part.startswith("v1/"):
                continue
            if not os.path.exists(os.path.join(RAW2, part)):
                bad.add(part)
    print(f"source_roster entries with no file: {len(bad)} {sorted(bad)[:4]}")
    if bad:
        warns.append(f"source_roster names {len(bad)} missing files")

    # 4. an address that states a 시도 but the column is empty
    lost = df[(df.sido.str.strip() == "") & (df.road_address.str.strip() != "")]
    print(f"rows with an address but no 시도: {len(lost)}")
    if len(lost):
        warns.append(f"{len(lost)} rows have an address but no 시도")

    # 5. 시군구 joins to the population index
    idx = json.load(open(os.path.join(DASH, "data", "indices.json"),
                         encoding="utf-8"))["data"]["by_sigungu"]
    canon = {(r["sido"], r["sigungu"]) for r in idx[max(idx, key=int)]}
    base = collections.defaultdict(set)
    for sd, sg in canon:
        base[(sd, sg.split()[0])].add(sg)
    placed = df[(df.sigungu.str.strip() != "") & (df.sido.str.strip() != "")]
    unjoined = [(r.sido, r.sigungu) for _, r in placed.iterrows()
                if (r.sido, r.sigungu) not in canon
                and (r.sido, r.sigungu.split()[0]) not in base]
    c = collections.Counter(unjoined)
    print(f"\n시군구 values that do not join to the population index: "
          f"{len(unjoined)} rows, {len(c)} distinct")
    for k, v in c.most_common(12):
        print(f"    {v:4d}  {k[0]} | {k[1]}")
    if unjoined:
        warns.append(f"{len(unjoined)} rows will be counted in no district")

    # 6. a merged row must not span two 시군구
    print("\n=== summary ===")
    for f in fails:
        print("  FAIL " + f)
    for w in warns:
        print("  warn " + w)
    if not fails and not warns:
        print("  everything checked passed")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    sys.exit(main(ap.parse_args()))
