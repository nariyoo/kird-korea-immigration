# -*- coding: utf-8 -*-
"""Resolve every address in the rosters to one canonical building key.

The de-duplication in `build_frame.py` groups rows by `addrkey`, which is the
road name plus the building number pulled out of the string with a regex. That
works only when two rosters spell the same address the same way, and they do
not. 진주YWCA sits at 동진로263번길 14 in one roster and 동진로 263번길 14 in
another, so the regex reads `동진로263번길14` from one and `동진로263` from the
other and the two rows never meet. Worse, one roster writes a 지번 address where
another writes a 도로명 address for the same door, and no amount of string
normalization brings those together: they are different addressing systems.

Kakao's address search resolves both systems to the same record, and that record
carries the 법정동 code with the 본번 and 부번. That triple names a parcel and
nothing else, so it is the key both spellings and both systems agree on.

  경상남도 진주시 동진로263번길 14        -> 4817011400-330-4
  경상남도 진주시 동진로 263번길 14       -> 4817011400-330-4
  경남 진주시 상대동 330-4               -> 4817011400-330-4

Output is a cache keyed on the raw address string, so a rebuild costs nothing
and only new addresses hit the API.

Run:  python scripts/v2/normalize_addresses.py
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import geocode_frame as gf  # noqa: E402
import build_frame as bf  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
CANON = os.path.join(ROOT, "data", "interim", "addr_canon.json")

_lock = threading.Lock()


def load_canon():
    if os.path.exists(CANON):
        try:
            with open(CANON, encoding="utf-8", errors="replace") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def canon_of(addr, key):
    """One Kakao lookup. Returns the parcel key and the two canonical strings.

    `same_as` is what the merge groups on. It is the 법정동 code plus the parcel
    numbers when Kakao gives a 지번 record, and the road name plus building
    numbers when it does not, because a road-only record still names one door.
    """
    a = str(addr or "").strip()
    if not a:
        return None
    j = gf._get(gf.ADDR_URL, {"query": gf._simplify(a), "size": 1}, key)
    docs = (j or {}).get("documents") or []
    if not docs:
        # Kakao refuses the unit and floor detail more often than the address;
        # the simplified form is already what went out, so a miss here is a miss
        return None
    d = docs[0]
    ad, rd = d.get("address") or {}, d.get("road_address") or {}
    same = ""
    if ad.get("b_code") and ad.get("main_address_no"):
        same = "-".join([ad["b_code"], str(ad.get("main_address_no") or ""),
                         str(ad.get("sub_address_no") or "0")])
    elif rd.get("road_name") and rd.get("main_building_no"):
        same = "-".join([str(rd.get("region_1depth_name") or ""),
                         str(rd.get("region_2depth_name") or ""),
                         rd["road_name"], str(rd["main_building_no"]),
                         str(rd.get("sub_building_no") or "0")])
    if not same:
        return None
    return {"same_as": same,
            "road": rd.get("address_name", ""),
            "jibun": ad.get("address_name", ""),
            "building": rd.get("building_name", ""),
            "x": d.get("x", ""), "y": d.get("y", "")}


def collect_addresses():
    """Every address string the build will ever compare, from the rosters and
    from the address ledger, before any merging has happened."""
    seen = []
    parts = bf.load_rosters()
    v1 = pd.read_csv(os.path.join(ROOT, "data", "processed", "master_all.csv"),
                     dtype=str).fillna("")
    for d in [v1] + parts:
        for c in ("road_address", "jibun_address"):
            if c in d.columns:
                seen += [str(x).strip() for x in d[c] if str(x).strip()]
    led = os.path.join(ROOT, "data", "raw", "v2", "fixup", "manual_address.csv")
    if os.path.exists(led):
        led_d = pd.read_csv(led, dtype=str, encoding="utf-8-sig").fillna("")
        seen += [str(x).strip() for x in led_d.get("road_address", [])
                 if str(x).strip()]
    return list(dict.fromkeys(seen))


def main(a):
    key = gf.load_key()
    if not key:
        raise SystemExit("KAKAO_REST_API_KEY not found")
    canon = load_canon()
    addrs = collect_addresses()
    todo = [x for x in addrs if x not in canon]
    print(f"addresses in the rosters: {len(addrs)} | already resolved: "
          f"{len(addrs)-len(todo)} | to resolve: {len(todo)}")

    done = 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(canon_of, x, key): x for x in todo}
        for f in cf.as_completed(futs):
            x = futs[f]
            try:
                r = f.result()
            except Exception:
                r = None
            with _lock:
                canon[x] = r
                done += 1
                if done % 250 == 0:
                    print(f"  resolved {done}/{len(todo)}", flush=True)
                    json.dump(canon, open(CANON, "w", encoding="utf-8"),
                              ensure_ascii=False)
    json.dump(canon, open(CANON, "w", encoding="utf-8"), ensure_ascii=False)

    got = {k: v for k, v in canon.items() if v}
    print(f"\nresolved to a parcel key: {len(got)} of {len(canon)} "
          f"({len(got)/max(len(canon),1):.0%})")
    # what this actually buys: how many spellings collapse onto one key
    groups = {}
    for k, v in got.items():
        groups.setdefault(v["same_as"], []).append(k)
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"parcels written more than one way: {len(multi)}")
    for k, v in list(multi.items())[:6]:
        print(f"  {k}")
        for s in v[:3]:
            print(f"      {s[:64]}")
    print(f"wrote {CANON}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    sys.exit(main(ap.parse_args()))
