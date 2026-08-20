# -*- coding: utf-8 -*-
"""가족센터의 주소와 전화를 정부 시설등록부로 대조한다.

`pull_ssis_facilities.py` 가 받아 둔 한국사회보장정보원 시설등록부에는 시설마다
정부가 부여한 `fcltCd` 와 도로명주소와 전화가 있다. 우리 틀의 가족센터 주소는 다누리
명부에서 왔다. 둘 다 공식 출처이고 **둘이 다를 때가 있다.**

  진천군 가족센터   틀: 진천읍 중앙북1길 11-10   등록부: 진천읍 남산10길 29
  제천시 가족센터   틀: 명륜로 13길 3           등록부: 강명길 24-12
  철원군 가족센터   틀: 갈말읍 삼부연로 22-1     등록부: 갈말읍 갈말로 32-10

한쪽이 이전 전 주소다. 어느 쪽이 최신인지는 두 출처의 갱신 시점을 모르면 판정할 수
없고, 등록부가 정부 것이라는 이유만으로 덮어쓰면 이전한 센터를 옛 주소로 되돌릴 수도
있다. 그래서 이 스크립트는 **세 경우를 구분한다.**

  fill      틀에 주소가 없다           -> 등록부 값을 쓴다
  refine    같은 필지인데 등록부가 더 상세  -> 등록부 값을 쓴다
  conflict  다른 필지를 가리킨다         -> 쓰지 않고 사람이 볼 시트로 뺀다

전화는 더 조심한다. 등록부의 전화는 구분기호가 없고 자릿수가 어긋난 것이 있다
(`05404398279` 는 11자리인데 054 지역번호다). 틀에 전화가 없을 때만, 그리고 자릿수가
9에서 11 사이일 때만 채운다.

Run:  python scripts/v2/enrich_from_ssis.py
"""
from __future__ import annotations
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import build_frame as bf  # noqa: E402
# 2026 개편 이후 이름을 개편 전 17개 시도로 되돌리는 표는 pull 쪽에 있다
from pull_ssis_facilities import back_convert  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INTERIM = os.path.join(ROOT, "data", "interim")
FIX = os.path.join(ROOT, "data", "raw", "v2", "fixup")
OUT = os.path.join(ROOT, "data", "processed", "v2")


def norm(n):
    """가족센터는 한 시설이 네 가지 이름으로 불린다. 통합 전 명칭(건강가정다문화가족
    지원센터), 통합 후 명칭(가족센터), 지역명이 앞에 붙은 형태, 안 붙은 형태."""
    n = str(n)
    for a, b in (("건강가정", ""), ("다문화가족지원센터", "가족센터"),
                 ("다문화가족복지센터", "가족센터"), ("가족지원센터", "가족센터")):
        n = n.replace(a, b)
    return bf.namekey(n)


_SIDO_PREFIX = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
                "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")


def strip_region(k):
    for p in _SIDO_PREFIX:
        if k.startswith(p):
            return k[len(p):]
    return k


def phone_ok(digits):
    return 9 <= len(digits) <= 11


def fmt_phone(d):
    if len(d) == 11 and d.startswith("0") and not d.startswith("01"):
        # 05404398279 style: a stray zero after the area code
        return ""
    if len(d) == 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}" if d.startswith("02") is False \
            else f"{d[:2]}-{d[2:6]}-{d[6:]}"
    if len(d) == 9 and d.startswith("02"):
        return f"{d[:2]}-{d[2:5]}-{d[5:]}"
    return ""


def prewrite_address(addr, sido):
    """등록부 주소 문자열의 시도 이름을 개편 전 표기로 되돌린다.

    등록부는 2026-07-01 개편 이후 이름을 쓴다. 우리 틀은 인구 분모가 개편 전
    17개 시도 기준이므로 개편 전 이름을 유지하기로 했고, 그 결정은 시도 칼럼만이
    아니라 주소 문자열에도 적용되어야 한다. 그러지 않으면 카드에
    "전남광주통합특별시 광산구" 가 찍힌다.
    """
    a = str(addr or "").strip()
    for pre, post in (("전남광주통합특별시", sido or "광주광역시"),
                      ("강원특별자치도", "강원도"),
                      ("전북특별자치도", "전라북도")):
        if a.startswith(pre):
            a = post + a[len(pre):]
    return a


def sgg_of(basic_row, listing):
    """The 시도 and 시군구 the registry itself assigns, via fcltCd.

    The basic-info operation carries only a 시군구 code; the listing operation
    carries the readable name. Joining them is what makes a region check
    possible, and without one the name match crosses cities: 대구광역시 북구
    다문화가족지원센터 matched 부산광역시 북구, and 고성군 가족센터 in 강원
    matched the one in 경남, because stripping the city prefix leaves 북구 and
    고성군 standing for two places each.
    """
    r = listing.get(str(basic_row.get("fcltCd", "")).strip())
    if r is None:
        return "", ""
    return back_convert(r.get("jrsdSggNm", ""))


def main(a):
    bp = os.path.join(INTERIM, "ssis_140101_basic.csv")
    if not os.path.exists(bp):
        raise SystemExit("run pull_ssis_facilities.py first")
    b = pd.read_csv(bp, dtype=str).fillna("")
    b["addr"] = (b["fcltAddr"].str.strip() + " "
                 + b.get("fcltDtl_1Addr", pd.Series([""] * len(b))).str.strip()
                 ).str.strip()
    b["addr"] = b["addr"].str.replace(r"\s+", " ", regex=True)
    lp = os.path.join(INTERIM, "ssis_140101_raw.csv")
    listing = {}
    if os.path.exists(lp):
        ld = pd.read_csv(lp, dtype=str).fillna("")
        listing = {str(r["fcltCd"]).strip(): r for _, r in ld.iterrows()}
        print("등록부 시군구를 붙일 수 있는 시설: %d" % len(listing))
    else:
        print("ssis_140101_raw.csv 없음 -- 지역 대조 없이 이름만으로 맞춘다")
    f = pd.read_csv(os.path.join(OUT, "frame_v2_geo.csv"), dtype=str).fillna("")

    idx, alt = {}, {}
    for _, r in f.iterrows():
        k = norm(r["name_ko"])
        idx.setdefault(k, []).append(r)
    for k, v in idx.items():
        alt.setdefault(strip_region(k), []).extend(v)

    fills, refines, conflicts, unmatched, crosscity = [], [], [], [], []
    for _, r in b.iterrows():
        k = norm(r["fcltNm"])
        got = idx.get(k) or alt.get(strip_region(k))
        if not got or len(got) != 1:
            unmatched.append(r)
            continue
        fr = got[0]
        sd, _sg = sgg_of(r, listing)
        if sd and str(fr["sido"]).strip() and sd != str(fr["sido"]).strip():
            crosscity.append({"fcltNm": r["fcltNm"], "fcltCd": r.get("fcltCd", ""),
                              "ssis_sido": sd, "frame_name": fr["name_ko"],
                              "frame_sido": fr["sido"]})
            continue
        cur, new = str(fr["road_address"]).strip(), r["addr"]
        rec = {"name_key": bf.namekey(fr["name_ko"]), "name_ko": fr["name_ko"],
               "sido": fr["sido"],
               "road_address": prewrite_address(new, fr["sido"]),
               "frame_address": cur, "fclt_cd": r.get("fcltCd", ""),
               "evidence": "한국사회보장정보원 시설등록부, 시설코드 "
                           + str(r.get("fcltCd", "")),
               "source": "ssis_140101"}
        if not new:
            continue
        if not cur:
            fills.append(rec)
            continue
        same_parcel = bf.addrkey(cur) and bf.addrkey(cur) == bf.addrkey(new)
        if same_parcel:
            if len(new) > len(cur):
                refines.append(rec)
        else:
            conflicts.append(rec)

    # phone, only where the frame has none
    tel = []
    for _, r in b.iterrows():
        k = norm(r["fcltNm"])
        got = idx.get(k) or alt.get(strip_region(k))
        if not got or len(got) != 1:
            continue
        fr = got[0]
        sd, _sg = sgg_of(r, listing)
        if sd and str(fr["sido"]).strip() and sd != str(fr["sido"]).strip():
            continue
        if str(fr["phone"]).strip():
            continue
        d = re.sub(r"\D", "", str(r.get("fcltTelNo", "")))
        if phone_ok(d) and fmt_phone(d):
            tel.append({"name_ko": fr["name_ko"], "phone": fmt_phone(d),
                        "fclt_cd": r.get("fcltCd", "")})

    print("등록부 %d행 대 틀" % len(b))
    print("  틀에 주소가 없어 채움      : %d" % len(fills))
    print("  같은 필지, 더 상세해짐     : %d" % len(refines))
    print("  다른 필지를 가리킴(보류)   : %d" % len(conflicts))
    print("  틀에서 한 행을 특정 못 함  : %d" % len(unmatched))
    print("  이름은 같은데 시도가 다름  : %d  <- 걷어냄" % len(crosscity))
    print("  전화를 새로 채울 수 있음   : %d" % len(tel))

    take = fills + refines
    if take:
        cols = ["name_key", "name_ko", "sido", "road_address", "evidence",
                "source"]
        pd.DataFrame(take)[cols].to_csv(
            os.path.join(FIX, "addr_ssis_done.csv"), index=False,
            encoding="utf-8-sig")
        print("\nwrote fixup/addr_ssis_done.csv (%d)" % len(take))
    if conflicts:
        pd.DataFrame(conflicts).to_csv(
            os.path.join(OUT, "review_address_conflict.csv"), index=False,
            encoding="utf-8-sig")
        print("wrote review_address_conflict.csv (%d) "
              "-- 두 공식 출처가 다른 주소를 말한다" % len(conflicts))
        for c in conflicts[:6]:
            print("   %-20s 틀 %s" % (c["name_ko"][:20], c["frame_address"][:40]))
            print("   %-20s 등록부 %s" % ("", c["road_address"][:40]))
    if crosscity:
        pd.DataFrame(crosscity).to_csv(
            os.path.join(OUT, "review_ssis_crosscity.csv"), index=False,
            encoding="utf-8-sig")
        for c in crosscity:
            print("   %-26s %s / 틀 %s" % (c["fcltNm"][:26], c["ssis_sido"],
                                          c["frame_sido"]))
    if unmatched:
        pd.DataFrame(unmatched).to_csv(
            os.path.join(OUT, "review_ssis_unmatched.csv"), index=False,
            encoding="utf-8-sig")
        print("wrote review_ssis_unmatched.csv (%d)" % len(unmatched))
    return 0


if __name__ == "__main__":
    sys.exit(main(argparse.ArgumentParser().parse_args()))
