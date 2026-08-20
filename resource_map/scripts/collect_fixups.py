# -*- coding: utf-8 -*-
"""Turn the hand-checked worksheets into two ledgers the build reads.

The census lesson this is built against (#4): a ledger that only protects and
never materializes is useless. Twenty gold-verified organizations were written
into a manual list and only five appeared, because the list was consumed as
"do not drop these" when what it needed to do was ADD them. So each ledger here
is applied by `build_frame.py` and the build reports how many rows it matched
and how many it could not, by name.

The key is NOT facility_id. The id is a hash of the name and the street address,
so writing an address into a row changes the id of the row you were writing it
into. The ledgers key on the normalized name plus the 시도, which survives the
edit.

  manual_address.csv   name_key, sido, road_address, evidence, source
  manual_dedup.csv     name_key_a, name_key_b, sido, sigungu, verdict, evidence

Run:  python scripts/v2/collect_fixups.py
"""
from __future__ import annotations
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import build_frame as bf  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIX = os.path.join(ROOT, "data", "raw", "v2", "fixup")


def collect_addresses():
    rows, skipped = [], 0
    for p in sorted(glob.glob(os.path.join(FIX, "addr_*_done.csv"))):
        d = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
        got = 0
        for _, r in d.iterrows():
            a = str(r.get("road_address", "")).strip()
            if not a:
                skipped += 1
                continue
            rows.append({
                "name_key": bf.namekey(r["name_ko"]),
                "name_ko": r["name_ko"],
                "sido": str(r.get("sido", "")).strip(),
                "road_address": a,
                "evidence": str(r.get("evidence", ""))[:300],
                "note": str(r.get("note", ""))[:160],
                "source": os.path.basename(p),
            })
            got += 1
        print(f"  {got:4d}/{len(d):<4d} {os.path.basename(p)}")
    # Twenty organizations appear on more than one sheet, and the sheets were
    # filled at different times. Keeping the first alphabetically let
    # addr_01_done.csv, filled when a row simply had no address, override
    # addr_ssis_done.csv, where a person compared two official sources and said
    # which one is current. The later judgement wins, and PRIORITY says so
    # rather than leaving it to a filename.
    PRIORITY = {"addr_ssis_done.csv": 0}   # smaller wins; everything else 1
    out = pd.DataFrame(rows)
    if len(out):
        out["_rank"] = [PRIORITY.get(x, 1) for x in out["source"]]
        out = (out.sort_values("_rank", kind="stable")
                  .drop_duplicates("name_key", keep="first")
                  .drop(columns=["_rank"]))
    print(f"addresses collected: {len(out)} (left blank by the checker: {skipped})")
    # a checker who wrote (미확인) read it off a search snippet, not the page
    unc = int(out.note.str.contains("미확인", na=False).sum()) if len(out) else 0
    print(f"  of which marked (미확인): {unc}")
    return out


def collect_inclusion():
    """serves 판정을 사람이 내린 것. 모델이 결론을 못 낸 행만 여기로 온다.

    근거가 부족해서 보류된 것이지 없는 기관이라는 뜻이 아니므로, 이 판정은
    모델의 판정을 덮어쓴다. 무엇을 근거로 그렇게 판정했는지가 evidence 칸에
    남고 그 칸이 비어 있으면 받지 않는다.
    """
    rows = []
    for p in sorted(glob.glob(os.path.join(FIX, "incl_*_done.csv"))):
        d = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
        c = d.verdict.str.strip().str.lower().value_counts().to_dict()
        print(f"  {os.path.basename(p)}: {c}")
        for _, r in d.iterrows():
            v = str(r.get("verdict", "")).strip().lower()
            if v not in ("direct", "indirect", "no"):
                continue
            if not str(r.get("evidence", "")).strip():
                print(f"    skipped, no evidence: {r.get('name_ko','')}")
                continue
            rows.append({
                "facility_id": r.get("facility_id", ""),
                "name_key": bf.namekey(r.get("name_ko", "")),
                "name_ko": r.get("name_ko", ""),
                "sido": r.get("sido", ""),
                "serves": v,
                "evidence": str(r.get("evidence", ""))[:400],
                "source": os.path.basename(p),
            })
    out = pd.DataFrame(rows)
    if len(out):
        print(f"inclusion judgements: {len(out)} "
              f"({int((out.serves=='no').sum())} removed from the list)")
    return out


def collect_dedup():
    rows = []
    # dup_*  first round, dup2_*  second round. The first glob was
    # "dup_*_done.csv", which matches neither dup2_01_done.csv nor anything a
    # later round names, so a whole round of human judgements would have been
    # collected into nothing while this script still printed a success line.
    sheets = sorted(glob.glob(os.path.join(FIX, "dup_*_done.csv"))
                    + glob.glob(os.path.join(FIX, "dup2_*_done.csv")))
    for p in sheets:
        d = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
        c = d.verdict.str.strip().str.lower().value_counts().to_dict()
        print(f"  {os.path.basename(p)}: {c}")
        for _, r in d.iterrows():
            v = str(r.get("verdict", "")).strip().lower()
            if v not in ("same", "different"):
                continue
            rows.append({
                "name_key_a": bf.namekey(r.get("a", "")),
                "name_key_b": bf.namekey(r.get("b", "")),
                "a": r.get("a", ""), "b": r.get("b", ""),
                "sido": r.get("sido", ""), "sigungu": r.get("sigungu", ""),
                "verdict": v,
                "evidence": str(r.get("evidence", ""))[:300],
                "source": os.path.basename(p),
            })
    out = pd.DataFrame(rows)
    if len(out):
        print(f"pairs judged: {len(out)} "
              f"({int((out.verdict=='same').sum())} same, "
              f"{int((out.verdict=='different').sum())} different)")
    return out


def main(a):
    print("=== addresses ===")
    addr = collect_addresses()
    print("\n=== duplicate pairs ===")
    dup = collect_dedup()
    print("")
    print("=== inclusion judgements ===")
    inc = collect_inclusion()
    if len(addr):
        addr.to_csv(os.path.join(FIX, "manual_address.csv"), index=False,
                    encoding="utf-8-sig")
        print(f"\nwrote manual_address.csv ({len(addr)})")
    if len(dup):
        dup.to_csv(os.path.join(FIX, "manual_dedup.csv"), index=False,
                   encoding="utf-8-sig")
        print(f"wrote manual_dedup.csv ({len(dup)})")
    if len(inc):
        inc.to_csv(os.path.join(FIX, "manual_inclusion.csv"), index=False,
                   encoding="utf-8-sig")
        print(f"wrote manual_inclusion.csv ({len(inc)})")
    if not len(addr) and not len(dup) and not len(inc):
        print("nothing to collect yet")
    return 0


if __name__ == "__main__":
    sys.exit(main(argparse.ArgumentParser().parse_args()))
