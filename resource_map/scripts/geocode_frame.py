# -*- coding: utf-8 -*-
"""Geocode the v2 frame with Kakao, and record HOW each coordinate was got.

The precision of a pin decides which 시군구 a facility is counted in, and the
map's density figures are per 시군구. So a coordinate that came from an exact
road address and one that came from a keyword search for the organization's
name are not interchangeable and are labelled differently:

  road      exact road address lookup
  jibun     lot-number address lookup
  keyword   Kakao place search on the organization name plus its region
  admin     the 시군구 office coordinate, when only a region is known. Good
            enough to count the facility in the right district, never good
            enough to draw a pin claiming a street location.
  none      no coordinate. The row stays in the frame and is reported as
            unmapped rather than dropped.

Run:  python scripts/v2/geocode_frame.py
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import threading
import time
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
CACHE = os.path.join(ROOT, "data", "interim", "geocode_v2_cache.json")

ADDR_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KW_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def load_key():
    k = os.environ.get("KAKAO_REST_API_KEY") or os.environ.get("KAKAO_REST_API")
    if k:
        return k.strip()
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("KAKAO_REST_API_KEY"):
                return line.split("=", 1)[1].strip()
    return None


_lock = threading.Lock()
_cache = {}
if os.path.exists(CACHE):
    try:
        _cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        _cache = {}

SESSION = requests.Session()


def _get(url, params, key):
    for attempt in range(3):
        try:
            r = SESSION.get(url, params=params, timeout=10,
                            headers={"Authorization": f"KakaoAK {key}"})
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(1 + attempt)
                continue
            return {}
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return {}


def _simplify(addr):
    """Drop unit and floor detail Kakao cannot resolve, keeping the building."""
    a = re.sub(r"\s*\([^)]*\)\s*", " ", str(addr or ""))
    a = re.sub(r"\s*(\d+층|지하\s*\d+층|[\dA-Za-z\-]+호|B\d+)\s*", " ", a)
    a = re.sub(r",.*$", "", a)
    return re.sub(r"\s+", " ", a).strip()


def geocode(row, key):
    addr = str(row.get("road_address") or "").strip()
    jibun = str(row.get("jibun_address") or "").strip()
    name = str(row.get("name_ko") or "").strip()
    sido = str(row.get("sido") or "").strip()
    sg = str(row.get("sigungu") or "").strip()

    def _q(a):
        """Kakao resolves 양평군 개군면 불곡리 산32 only when it can tell which
        province it is in, and half the rosters write the address without one."""
        a = str(a or "").strip()
        if a and sido and not a.startswith(sido[:2]):
            return f"{sido} {a}"
        return a

    tries = []
    if addr:
        tries.append(("road", addr))
        tries.append(("road", _q(addr)))
        s = _simplify(addr)
        if s and s != addr:
            tries.append(("road", s))
            tries.append(("road", _q(s)))
    if jibun:
        tries.append(("jibun", jibun))
        tries.append(("jibun", _q(jibun)))
    # A district that does not exist makes Kakao reject the whole address.
    # 달성군종합사회복지관 is written 대구광역시 달서군 논공읍 논공로 697-9, and
    # 달서군 is nowhere: the roster meant 달성군, which is where 논공읍 is. The
    # 읍 and the road are correct, so drop the district token and let the rest
    # resolve rather than losing the row's coordinate to one wrong word.
    for a in (addr, jibun):
        if not a or not sg:
            continue
        stripped = re.sub(r"\s*" + re.escape(sg) + r"\s*", " ", a).strip()
        if stripped and stripped != a:
            tries.append(("road_nodistrict", _q(stripped)))
    tries = [t for i, t in enumerate(tries) if t[1] and t not in tries[:i]]
    for how, q in tries:
        ck = f"a|{q}"
        with _lock:
            hit = _cache.get(ck)
        if hit is None:
            j = _get(ADDR_URL, {"query": q, "size": 1}, key)
            docs = j.get("documents") or []
            hit = ({"x": docs[0]["x"], "y": docs[0]["y"]} if docs else {})
            with _lock:
                _cache[ck] = hit
        if hit:
            return float(hit["y"]), float(hit["x"]), how

    if name:
        q = f"{sg or sido} {name}".strip()
        ck = f"k|{q}"
        with _lock:
            hit = _cache.get(ck)
        if hit is None:
            j = _get(KW_URL, {"query": q, "size": 1}, key)
            docs = j.get("documents") or []
            hit = ({"x": docs[0]["x"], "y": docs[0]["y"],
                    "addr": docs[0].get("address_name", "")} if docs else {})
            with _lock:
                _cache[ck] = hit
        if hit:
            # a keyword hit in the wrong 시군구 is worse than no hit
            if sg and hit.get("addr") and sg.split()[0][:2] not in hit["addr"]:
                pass
            else:
                return float(hit["y"]), float(hit["x"]), "keyword"

    if sg or sido:
        q = f"{sido} {sg}".strip()
        ck = f"r|{q}"
        with _lock:
            hit = _cache.get(ck)
        if hit is None:
            j = _get(ADDR_URL, {"query": q, "size": 1}, key)
            docs = j.get("documents") or []
            hit = ({"x": docs[0]["x"], "y": docs[0]["y"]} if docs else {})
            with _lock:
                _cache[ck] = hit
        if hit:
            return float(hit["y"]), float(hit["x"]), "admin"
    return None, None, "none"


REGION_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"


def reverse_region(lat, lng, key):
    """The 시도/시군구 Kakao says the coordinate is in.

    Used only where a row's own region strings fail to join to the population
    index. Regex repairs get most of the way (부산중구, 전주시완산구, 인천 남구)
    but leave a tail of one-off spellings, and a row that joins to nothing is
    silently absent from every per-10,000-residents figure. The coordinate is
    the one piece of the row that has no spelling."""
    ck = f"g|{lat:.5f},{lng:.5f}"
    with _lock:
        hit = _cache.get(ck)
    if hit is None:
        j = _get(REGION_URL, {"x": f"{lng}", "y": f"{lat}"}, key)
        docs = [d for d in (j.get("documents") or [])
                if d.get("region_type") == "B"] or (j.get("documents") or [])
        hit = ({"sido": docs[0].get("region_1depth_name", ""),
                "sgg": docs[0].get("region_2depth_name", "")} if docs else {})
        with _lock:
            _cache[ck] = hit
    return (hit.get("sido", ""), hit.get("sgg", "")) if hit else ("", "")


def repair_unjoined(df, key):
    """Re-derive the region from the coordinate for rows that join to nothing."""
    import json as _json
    ip = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard", "data",
                                      "indices.json"))
    idx = _json.load(open(ip, encoding="utf-8"))["data"]["by_sigungu"]
    rows = idx[max(idx, key=int)]
    canon = {(r["sido"], r["sigungu"]) for r in rows}
    bases = {(r["sido"], r["sigungu"].split()[0]) for r in rows}
    by_sido = collections.defaultdict(set)
    for sd, sg in canon:
        by_sido[sd].add(sg)

    fixed = 0
    for i, r in df.iterrows():
        sd, sg = str(r.get("sido", "")).strip(), str(r.get("sigungu", "")).strip()
        # EXACT match only. 고양시 matches 고양시 일산동구 at the city level, which
        # looks fine and then joins to no polygon and no population row, so the
        # facility is counted in no district at all. A 특례시 written without its
        # 구 has to be resolved to the actual 구, and the coordinate is the only
        # thing on the row that can do it.
        if sd and sg and (sd, sg) in canon:
            continue
        la, ln = str(r.get("lat", "")).strip(), str(r.get("lng", "")).strip()
        if not (la and ln):
            continue
        # A coordinate obtained by looking up the 시도 alone is the provincial
        # office, and reverse-geocoding it returns the district that office sits
        # in. 나섬 다문화 생태마을, whose address reads 양평군 개군면 불곡리, was
        # written into 수원시 영통구 that way, because 경기도 resolves to the
        # 경기도청 in Suwon. An `admin` coordinate encodes the 시도 and nothing
        # finer, so it may never settle a 시군구.
        if str(r.get("geo_how", "")).startswith("admin"):
            continue
        nsd, nsg = reverse_region(float(la), float(ln), key)
        if not nsd:
            continue
        nsd = SIDO_FIX.get(nsd, nsd)
        if not nsg:
            continue
        if (nsd, nsg) in canon:
            pass
        elif (nsd, nsg.split()[-1]) in NEW_DISTRICT:
            # checked BEFORE the base test: "부천시 원미구" passes a base match on
            # 부천시 and then stays written as 부천시 원미구, which joins to
            # nothing. The base test says a parent exists; it does not make the
            # value usable.
            nsg = NEW_DISTRICT[(nsd, nsg.split()[-1])]
        elif (nsd, nsg.split()[0]) in bases and (nsd, nsg.split()[0]) in canon:
            nsg = nsg.split()[0]
        else:
            cands = [x for x in by_sido.get(nsd, set())
                     if x.split()[0] == nsg or x == nsg]
            if len(cands) != 1:
                continue
            nsg = cands[0]
        df.at[i, "sido"], df.at[i, "sigungu"] = nsd, nsg
        df.at[i, "geo_how"] = str(df.at[i, "geo_how"] or "") + "+region_from_coord"
        fixed += 1
    print(f"region re-derived from the coordinate: {fixed}")
    return df


# Kakao answers with the current official names; the population index is on the
# 2025 yearbook's, and the frame follows the index (see build_frame.SIDO_CANON).
SIDO_FIX = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도",
            "전남광주통합특별시": "전라남도"}

# Districts created after the population index was built. Kakao answers with the
# current name and the index has only the parent city, so the coordinate lands
# in a district that does not exist as far as the denominator is concerned.
NEW_DISTRICT = {
    ("경기도", "원미구"): "부천시", ("경기도", "소사구"): "부천시",
    ("경기도", "오정구"): "부천시",
    ("경기도", "효행구"): "화성시", ("경기도", "병점구"): "화성시",
    ("경기도", "동탄구"): "화성시", ("경기도", "남양읍"): "화성시",
}


def run(frame, out_csv, workers=8):
    key = load_key()
    if not key:
        raise SystemExit("KAKAO_REST_API_KEY not found")
    df = pd.read_csv(frame, dtype=str).fillna("")
    todo = [i for i, r in df.iterrows()
            if not (str(r.get("lat", "")).strip() and str(r.get("lng", "")).strip())]
    print(f"{len(df)} rows | already have coordinates {len(df)-len(todo)} "
          f"| geocoding {len(todo)}")

    df["geo_how"] = ""
    for i, r in df.iterrows():
        if i not in todo:
            df.at[i, "geo_how"] = "carried"

    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(geocode, df.loc[i].to_dict(), key): i for i in todo}
        done = 0
        for fu in as_completed(futs):
            i = futs[fu]
            try:
                res[i] = fu.result()
            except Exception:
                res[i] = (None, None, "none")
            done += 1
            if done % 100 == 0:
                print(f"  geocoded {done}/{len(todo)}", flush=True)
                with _lock:
                    json.dump(_cache, open(CACHE, "w", encoding="utf-8"),
                              ensure_ascii=False)

    for i, (la, ln, how) in res.items():
        if la is not None:
            df.at[i, "lat"] = f"{la:.6f}"
            df.at[i, "lng"] = f"{ln:.6f}"
        df.at[i, "geo_how"] = how
    with _lock:
        json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    df = repair_unjoined(df, key)
    with _lock:
        json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("\n=== coordinate provenance ===")
    print(df.geo_how.value_counts().to_string())
    n = (df.lat.astype(str).str.strip() != "").sum()
    print(f"\nmapped {n} of {len(df)} ({n/len(df):.1%}); wrote {out_csv}")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run(a.frame, a.out, a.workers)
