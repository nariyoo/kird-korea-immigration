# -*- coding: utf-8 -*-
"""Assemble the v2 frame from the v1 master plus every roster collected under
data/raw/v2/, and de-duplicate on rules that can be argued for.

De-duplication follows docs/INCLUSION_CRITERIA.md section 5, which exists
because of a specific US-census failure (#9): an address key was allowed to
SETTLE identity, two different organizations in one building collided, and 78
recognized bodies were reported as already covered when they were absent.

So here:
  same normalized name AND same street address  -> one row, programmes merged
  same normalized name, no address on either    -> one row only if same 시군구
  same address, different names                 -> two rows (one building, two
                                                   organizations is normal)
  similar but not equal names                   -> REVIEW SHEET, never merged

Run:  python scripts/v2/build_frame.py
"""
from __future__ import annotations
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
import hosts  # noqa: E402
import idmatch  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW2 = os.path.join(ROOT, "data", "raw", "v2")
OUT = os.path.join(ROOT, "data", "processed", "v2")
os.makedirs(OUT, exist_ok=True)

COLS = ["name_ko", "name_en", "category", "subcategory", "governing_ministry",
        "operator_type", "operator_name", "road_address", "jibun_address",
        "sido", "sigungu", "eupmyeondong", "postal_code", "lat", "lng",
        "phone", "email", "website", "target_population", "services_provided",
        "languages_supported", "established_year", "closed_year",
        "operational_status", "source_url", "source_date", "notes"]

# The vocabulary here is the one the POPULATION INDEX uses, not the newest
# official one. indices.json is built from the 2025 yearbook and writes 강원도
# and 전라북도; writing 강원특별자치도 and 전북특별자치도 instead left 213 rows
# joining to no district at all, which silently removes them from every
# per-10,000-residents figure. The modern name is preserved in sido_2026.
SIDO_CANON = {
    "서울": "서울특별시", "서울시": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산시": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구시": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천시": "인천광역시", "인천광역시": "인천광역시",
    "광주": "광주광역시", "광주시": "광주광역시", "광주광역시": "광주광역시",
    "대전": "대전광역시", "대전시": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산시": "울산광역시", "울산광역시": "울산광역시",
    "세종": "세종특별자치시", "세종시": "세종특별자치시",
    "세종특별자치시": "세종특별자치시", "세종특별시": "세종특별자치시",
    "경기": "경기도", "경기도": "경기도",
    "강원": "강원도", "강원도": "강원도", "강원특별자치도": "강원도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전라북도", "전라북도": "전라북도",
    "전북특별자치도": "전라북도",
    "전남": "전라남도", "전라남도": "전라남도",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주특별자치도", "제주도": "제주특별자치도",
    "제주특별자치도": "제주특별자치도",
}


# 2026-07-01 administrative changes, mapped BACK to the pre-merger geography.
#
# 전남광주통합특별시 (광주광역시 + 전라남도) and 인천 제물포구 / 영종구 / 검단구
# (from 중구, 동구, 서구) are real and current. The frame stays on the pre-merger
# 17 시도 anyway, because the resident-population denominators the density figures
# divide by are published on the old geography and a facility counted in a region
# that has no matching population is a broken ratio, not a more current one.
# The 2026 name is preserved in sido_2026 / sigungu_2026 so the switch is one
# join away when the population series moves.
GWANGJU_SGG = {"동구", "서구", "남구", "북구", "광산구"}
INCHEON_2026 = {"제물포구": "중구", "영종구": "중구", "검단구": "서구"}


def canon_sido(s, addr="", sigungu=""):
    # some rosters write the district in brackets after the province
    # ("경상남도(진주)", "경기도 광주시"), which matches no 시도 and leaves the row
    # counted in no district at all
    s = re.sub(r"[（(][^)）]*[)）]", "", str(s or "")).strip()
    if s not in SIDO_CANON:
        head = s.split()[0] if s.split() else s
        if head in SIDO_CANON:
            s = head
    sg = str(sigungu or "").strip()
    if s in ("전남광주통합특별시", "전남광주통합시", "광주전남통합특별시"):
        # 광주 and 전남 share no 시군구 name, so the district settles it
        return "광주광역시" if sg in GWANGJU_SGG else "전라남도"
    if s in SIDO_CANON:
        return SIDO_CANON[s]
    a = str(addr or "").strip()
    for k in sorted(SIDO_CANON, key=len, reverse=True):
        if a.startswith(k):
            return SIDO_CANON[k]
    # some rosters put a 시군구 in the 시도 column; recover it from the address
    if a:
        for k in sorted(SIDO_CANON, key=len, reverse=True):
            if k in a[:12]:
                return SIDO_CANON[k]
    return s


def canon_sigungu(sg, sido=""):
    sg = str(sg or "").strip()
    if sido == "인천광역시" and sg in INCHEON_2026:
        return INCHEON_2026[sg]
    return sg


# The 250 시군구 of the population index, which is what the density figures join
# against. Loaded once and used for two repairs that were leaving the same
# facility in the frame twice:
#   1. a roster that puts a 시군구 in the 시도 column (용인시, 시흥시, 안산시 ...)
#   2. a roster that writes 천안시 where the index writes 천안시 동남구
_SGG = {}


def _load_sigungu():
    if _SGG:
        return _SGG
    import json
    p = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard", "data",
                                     "indices.json"))
    idx = json.load(open(p, encoding="utf-8"))["data"]["by_sigungu"]
    rows = idx[max(idx, key=int)]
    uniq, base = defaultdict(set), defaultdict(set)
    for r in rows:
        uniq[r["sigungu"]].add(r["sido"])
        base[r["sigungu"].split()[0]].add(r["sido"])
    # 중구, 동구, 서구 and the like belong to several 시도 and can never be
    # resolved from the name alone. Only unambiguous names are usable.
    _SGG["to_sido"] = {k: list(v)[0] for k, v in uniq.items() if len(v) == 1}
    _SGG["base_to_sido"] = {k: list(v)[0] for k, v in base.items()
                            if len(v) == 1}
    _SGG["by_sido"] = defaultdict(set)
    for r in rows:
        _SGG["by_sido"][r["sido"]].add(r["sigungu"])
        _SGG["by_sido"][r["sido"]].add(r["sigungu"].split()[0])
    # by_sido deliberately also holds the bare city name (고양시 beside 고양시
    # 일산동구) because it is used to RECOGNISE a token in an address. It must
    # never be used to decide whether a row joins to the index: 고양시 is in
    # by_sido and is not a row of the index, so a join test against by_sido
    # says yes and the density table counts the facility nowhere.
    _SGG["exact"] = {(r["sido"], r["sigungu"]) for r in rows}
    return _SGG


def repair_region(sido, sigungu, addr=""):
    """Return (sido, sigungu) using the population index as the authority."""
    g = _load_sigungu()
    sd = str(sido or "").strip()
    sg = str(sigungu or "").strip()
    if sd in SIDO_CANON.values():
        return sd, sg
    # the 시도 column is holding a 시군구
    for key in (sd, sd.split()[0] if sd else ""):
        if not key:
            continue
        hit = g["to_sido"].get(key) or g["base_to_sido"].get(key)
        if hit:
            return hit, (sg or key)
    return sd, sg


def sigungu_from_address(sido, addr):
    """The district the address itself names.

    An address is the row's own statement about where it is, and it was going
    unread: a row whose 시군구 column was empty fell through to a coordinate
    that had been resolved from the 시도 alone. Read the address first."""
    g = _load_sigungu()
    a = re.sub(r"\s+", " ", str(addr or "")).strip()
    if not a:
        return ""
    known = g["by_sido"].get(sido, set())
    # longest first so 성남시 분당구 wins over 성남시
    for sg in sorted(known, key=len, reverse=True):
        if sg and sg in a:
            return sg
    return ""


def region_from_name(name):
    """A 시도 or 시군구 spelled at the front of the organization's own name.

    Only used for rows that have no address and no region at all, which in
    practice means the 폭력피해 이주여성 쉼터 whose location is withheld by law.
    서울이주여성쉼터 is in 서울 and 여수이주여성쉼터 is in 여수; that is the
    organization's own statement about itself, and recording it beats leaving a
    real shelter with no region at all. It is marked `region_src=name` so no
    later step mistakes it for an address."""
    g = _load_sigungu()
    n = idmatch.compact(name)
    if not n:
        return "", ""
    for full, shorts in SIDO_FULL_SHORT:
        for sh in shorts:
            if n.startswith(idmatch.compact(sh)):
                return full, ""
    # a 시/군 name at the front, unambiguous across the country
    for sgg, sd in sorted(g["base_to_sido"].items(), key=lambda t: -len(t[0])):
        stem = re.sub(r"(시|군|구)$", "", sgg)
        if len(stem) >= 2 and n.startswith(idmatch.compact(stem)):
            return sd, sgg
    return "", ""


SIDO_FULL_SHORT = [
    ("서울특별시", ["서울"]), ("부산광역시", ["부산"]), ("대구광역시", ["대구"]),
    ("인천광역시", ["인천"]), ("광주광역시", ["광주"]), ("대전광역시", ["대전"]),
    ("울산광역시", ["울산"]), ("세종특별자치시", ["세종"]),
    ("경기도", ["경기"]), ("강원도", ["강원"]),
    ("충청북도", ["충북"]), ("충청남도", ["충남"]),
    ("전라북도", ["전북"]), ("전라남도", ["전남"]),
    ("경상북도", ["경북"]), ("경상남도", ["경남"]),
    ("제주특별자치도", ["제주"]),
]


# District names that changed, kept in step with 09_design_mockups/redesign/
# fix_facility_regions.py so the map and the index agree on one geography.
SGG_RENAME = {
    ("인천광역시", "남구"): "미추홀구",
    ("경기도", "여주군"): "여주시",
    ("충청남도", "당진군"): "당진시",
    ("충청북도", "청원군"): "청주시 청원구",
    ("충청북도", "청원"): "청주시 청원구",
    ("경기도", "원미구"): "부천시",
    ("경기도", "소사구"): "부천시",
    ("경기도", "오정구"): "부천시",
    ("경상남도", "창원시마산"): "창원시 마산회원구",
    # typos carried in the source rosters
    ("전라남도", "광야시"): "광양시",
    ("충청북도", "친천군"): "진천군",
}


def snap_sigungu(sido, sg):
    """Put a 시군구 into the exact spelling the population index uses.

    Rows arrive with the city prefix glued on (부산중구), the district glued to
    its parent (전주시완산구), an abolished name (인천 남구), or the 시도 name
    repeated. Each of those joins to nothing, and a row that joins to nothing is
    dropped from every density figure without anything saying so."""
    g = _load_sigungu()
    sg = re.sub(r"\s+", " ", str(sg or "").strip())
    if not sg:
        return sg
    known = g["by_sido"].get(sido, set())
    if sg in known:
        return sg
    if (sido, sg) in SGG_RENAME:
        return SGG_RENAME[(sido, sg)]
    # the 시도 name repeated in the 시군구 column
    short = re.sub(r"(특별자치도|특별자치시|특별시|광역시|도|시)$", "", str(sido))
    if sg in (sido, short):
        return ""
    # 부산중구 -> 중구, 대구동구 -> 동구
    if short and sg.startswith(short) and len(sg) > len(short):
        cand = sg[len(short):]
        if cand in known:
            return cand
    # 전주시완산구 -> 전주시 완산구
    m = re.match(r"^(.+?[시군])([가-힣]{1,4}구)$", sg)
    if m:
        cand = f"{m.group(1)} {m.group(2)}"
        if cand in known:
            return cand
    # 포천시 소흘읍 -> 포천시. An 읍/면/동 is a sub-unit of the 시군구 the index
    # counts by, so a row carrying one joins to nothing while the district it
    # belongs to is written right there in front of it.
    m = re.match(r"^(.+?[시군구])\s*[가-힣]{1,5}[읍면동리]$", sg)
    if m and m.group(1) in known:
        return m.group(1)
    # A wrong unit suffix is NOT repaired here. 대구광역시 달서군 looks like a
    # typo for 달서구 and the address reads 달서군 논공읍, but 논공읍 is in
    # 달성군, so the swap that reads best is the wrong district. Rows whose
    # 시군구 joins to nothing are left alone and repaired from their coordinate
    # in geocode_frame.repair_unjoined, which reads the district off the map
    # instead of off the spelling.
    return sg


def attach_parent_city(sido, sg):
    """단원구 -> 안산시 단원구. A 특례시 district written on its own does not
    join to the population index, and a row that joins to nothing is counted in
    no district at all."""
    g = _load_sigungu()
    sg = str(sg or "").strip()
    if not sg or (sido, sg) in {(s, x) for s, xs in g["by_sido"].items()
                                for x in xs}:
        return sg
    cands = [x for x in g["by_sido"].get(sido, set())
             if " " in x and x.split()[-1] == sg]
    return cands[0] if len(cands) == 1 else sg


def sigungu_base(sg):
    """천안시 동남구 -> 천안시. Used only to decide whether two rows are in the
    same place; never written to the output."""
    sg = str(sg or "").strip()
    return sg.split()[0] if sg else ""


def canon_phone(p):
    d = re.sub(r"[^\d]", "", str(p or ""))
    if not d or len(d) < 9:
        return ""
    if d.startswith("02"):
        return f"02-{d[2:-4]}-{d[-4:]}" if len(d) in (9, 10) else ""
    if len(d) in (10, 11) and d[0] == "0":
        return f"{d[:3]}-{d[3:-4]}-{d[-4:]}"
    if len(d) == 8:
        return f"{d[:4]}-{d[4:]}"
    return ""


def canon_url(u):
    u = str(u or "").strip()
    if not u or u.lower() in ("nan", "none", "-", "없음"):
        return ""
    if not re.match(r"^https?://", u, re.I):
        if re.match(r"^[\w.-]+\.[a-z]{2,}", u, re.I):
            u = "http://" + u
        else:
            return ""
    return u


def namekey(n):
    s = idmatch.strip_legal(str(n or ""))
    s = re.sub(r"[（(\[【][^)）\]】]*[)）\]】]", " ", s)
    return idmatch.compact(s)


_SIDO_TOKEN = re.compile(
    r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|"
    r"경북|경남|제주|충청북도|충청남도|전라북도|전라남도|경상북도|경상남도|"
    r"강원도|경기도|제주도|특별시|광역시|자치시|자치도|시|도|군|구)+$")


def residual_is_cosmetic(short, long_):
    """True when the longer name is the shorter one plus nothing substantive.

    Containment alone is never identity, and at a shared address it is still not
    identity when the extra words NAME A DIFFERENT BODY: 대구가톨릭대학교 and
    대구가톨릭대학교 다문화연구원 sit in the same building and are a university
    and a research institute. What is safe to fold is a name that gained an
    administrative prefix (남구 가족센터 / 대구남구가족센터) or a short tag
    (아시아평화를향한이주 / 아시아평화를향한이주MAP). So the residual must be a
    region word, or under four characters and carry no unit noun.
    """
    if short not in long_:
        return False
    i = long_.find(short)
    resid = (long_[:i] + long_[i + len(short):]).strip()
    if not resid:
        return True
    if _SIDO_TOKEN.match(resid):
        return True
    if re.search(r"(센터|연구|학교|대학|병원|재단|협회|교회|성당|사찰|쉼터|"
                 r"상담|지원|부설|분원|지부|지회|본부|사업소|복지관|"
                 r"점|분소|출장소|캠퍼스)", resid):
        return False
    return len(resid) <= 3


_DISSOLVED_DATED = re.compile(
    r"(말소|해산|등록\s*취소|폐업|직권\s*말소)\s*[（(]?\s*(\d{4})[-.\s]")


# Kakao resolved every roster address to one parcel (법정동 code + 본번-부번);
# `normalize_addresses.py` writes the table. Without it the address comparison
# is a regex over a string, and two rosters do not spell one address the same
# way: 동진로263번길 14 and 동진로 263번길 14 read as different buildings, and a
# 지번 address and a 도로명 address for one door never meet at all. That left
# 24 organizations in the published map twice.
_ADDR_CANON = None


def _load_addr_canon():
    global _ADDR_CANON
    if _ADDR_CANON is not None:
        return _ADDR_CANON
    p = os.path.join(ROOT, "data", "interim", "addr_canon.json")
    _ADDR_CANON = {}
    if os.path.exists(p):
        import json as _json
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                raw = _json.load(f)
            _ADDR_CANON = {k: v["same_as"] for k, v in raw.items()
                           if v and v.get("same_as")}
            print(f"canonical parcel keys loaded: {len(_ADDR_CANON)}")
        except Exception as e:
            print(f"addr_canon.json unreadable ({e}); "
                  "falling back to the string key")
    else:
        print("addr_canon.json absent; run normalize_addresses.py so that two "
              "spellings of one address stop reading as two buildings")
    return _ADDR_CANON


def addrkey(a):
    canon = _load_addr_canon()
    hit = canon.get(str(a or "").strip())
    if hit:
        return hit
    ks = idmatch.address_keys(a)
    return ks[0] if ks else ""


# Files under data/raw/v2 that are NOT rosters and must not enter the frame.
SKIP_ROSTERS = {
    "misc/council_denominator_lists.csv":
        "raw full-text search dump kept for the denominator only; the collector "
        "reports it carries known false hits (예산제 조례, 인구늘리기 조례)",
    "misc/misc_council_full.csv":
        "duplicate of misc/misc_council.csv, which the collector restored to "
        "its own 17-row version after a stray writer had truncated it",
    "edu/_agent_B_daejeon_ulsan_sejong_gyeonggi.csv":
        "intermediate worker output, already merged into edu/edu_policy_school.csv",
    "edu/_agent_C_gangwon_chungbuk_chungnam_jeonbuk.csv":
        "intermediate worker output, already merged into edu/edu_policy_school.csv",
    "kiip/kiip_local_gov_linked_programs.csv":
        "법무부 지자체 연계프로그램 143개의 사업 단위 목록이라 시설 명부가 아니다. "
        "행의 26개가 담당 부서(창원시 환경정책과, 김해시 성평등가족과)나 지자체 "
        "이름 자체이고, 여럿은 이미 틀에 있는 시설의 방 이름(창원시 가족센터 교육실, "
        "진천군 가족센터 프로그램실)이다. 실제 시설만 골라낸 것이 "
        "kiip/kiip_local_gov_linked_facilities.csv 이고, 원본은 분모와 근거로 남긴다",
}


FIXUP = os.path.join(RAW2, "fixup")


def apply_manual_address(allrows):
    """Addresses a person looked up, written into the rows before the merge.

    Applied here rather than after, because an address is what the merge keys on:
    a row that gains one can then fold into the row it was a duplicate of. The
    match is on the normalized name plus the 시도, never on facility_id, which is
    a hash OF the address and therefore changes the moment one is written.

    Every ledger row that matches nothing is printed. A ledger that silently
    matches nothing is the census's failure #4 wearing a different hat."""
    p = os.path.join(FIXUP, "manual_address.csv")
    if not os.path.exists(p):
        return allrows
    led = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
    want = {(r["name_key"], r["sido"]): r for _, r in led.iterrows()}
    hit, filled = set(), 0
    for i, r in allrows.iterrows():
        k = (namekey(r["name_ko"]), str(r["sido"]).strip())
        e = want.get(k)
        if e is None:
            continue
        hit.add(k)
        if not str(r["road_address"]).strip():
            allrows.at[i, "road_address"] = e["road_address"]
            allrows.at[i, "notes"] = (str(r["notes"]) + " | 주소 수동 확인: "
                                      + e["evidence"][:120]).strip(" |")
            filled += 1
    miss = [f'{v["name_ko"]}({v["sido"]})' for k, v in want.items() if k not in hit]
    print(f"manual addresses: {filled} written, {len(want)} in the ledger, "
          f"{len(miss)} matched no row")
    for m in miss[:8]:
        print(f"    unmatched: {m}")
    return allrows


def apply_manual_website(allrows):
    """Websites a person confirmed. Same keying and the same loud reporting as
    the address ledger; the value still enters the finder as one candidate among
    the rest and has to pass the identity test like any other."""
    p = os.path.join(FIXUP, "manual_website.csv")
    if not os.path.exists(p):
        return allrows
    led = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
    want = {(r["name_key"], r["sido"]): r for _, r in led.iterrows()}
    hit, filled = set(), 0
    for i, r in allrows.iterrows():
        k = (namekey(r["name_ko"]), str(r["sido"]).strip())
        e = want.get(k)
        if e is None:
            continue
        hit.add(k)
        if str(e.get("website", "")).strip():
            allrows.at[i, "website"] = e["website"].strip()
            filled += 1
    miss = [f'{v.get("name_ko", k[0])}({k[1]})' for k, v in want.items()
            if k not in hit]
    print(f"manual websites: {filled} written, {len(want)} in the ledger, "
          f"{len(miss)} matched no row")
    for m in miss[:6]:
        print(f"    unmatched: {m}")
    return allrows


def reregion_after_ledger(allrows):
    """Recompute the region of rows the address ledger just filled.

    The ledger runs after normalization, so a row that had no address at load
    time keeps the blank 시도 it was loaded with even once a street address is
    written into it. That row then merges with nothing, because stage 3 groups
    by (시도, address): 아시아평화를향한이주MAP sat one row away from
    아시아평화를향한이주 at the same door and stayed a separate organization.
    """
    fixed = 0
    for i, r in allrows.iterrows():
        ad = str(r.get("road_address", "")).strip()
        if not ad:
            continue
        sd = str(r.get("sido", "")).strip()
        if not sd:
            sd = canon_sido("", ad, "")
            if not sd:
                continue
            allrows.at[i, "sido"] = sd
            fixed += 1
        if not str(r.get("sigungu", "")).strip():
            hit = sigungu_from_address(sd, ad)
            if hit:
                allrows.at[i, "sigungu"] = attach_parent_city(
                    sd, snap_sigungu(sd, hit))
    print(f"region recovered after the ledgers wrote an address: {fixed}")
    return allrows


def load_manual_dedup():
    """Pairs a person judged. `same` forces a merge the machine would not make."""
    p = os.path.join(FIXUP, "manual_dedup.csv")
    if not os.path.exists(p):
        return set()
    led = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
    same = {(r["name_key_a"], r["name_key_b"], r["sido"], r["sigungu"])
            for _, r in led.iterrows() if r["verdict"] == "same"}
    print(f"manual dedup: {len(same)} pairs judged the same organization")
    return same


def load_rosters():
    """Every CSV under data/raw/v2/, tagged with the folder and file it came
    from so a row can always be traced back to the roster that asserted it."""
    rows = []
    for p in sorted(glob.glob(os.path.join(RAW2, "**", "*.csv"), recursive=True)):
        rel = os.path.relpath(p, RAW2).replace("\\", "/")
        if "/files/" in rel:          # untouched source downloads
            continue
        # the hand-search worklists are a projection OF the frame, not a source
        # for it; ingesting them writes "websearch/batch_06.csv" into the
        # provenance of rows that came from a government roster
        if rel.startswith("websearch/"):
            continue
        # fixup/ holds ledgers ABOUT the frame, not sources for it. Reading
        # manual_address.csv as a roster added its 84 rows back as facilities
        # and wrote "fixup/manual_address.csv" into their provenance.
        # archive/ holds rosters that were WITHDRAWN, with a note saying why.
        # Reading them puts the withdrawn rows straight back: the 2026-08-19
        # 마하 roster had 부산경남마주협회 and 제주마주협회 in it, which are
        # 馬主協會, associations of racehorse owners, and moving the file to
        # archive/ left both in the published frame.
        if rel.startswith("archive/"):
            continue
        if rel.startswith("fixup/"):
            continue
        if rel in SKIP_ROSTERS:
            print(f"  SKIP {rel}: {SKIP_ROSTERS[rel]}")
            continue
        try:
            d = pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("")
        except Exception as e:
            print(f"  SKIP {rel}: {type(e).__name__}")
            continue
        if "name_ko" not in d.columns:
            print(f"  SKIP {rel}: no name_ko column ({list(d.columns)[:6]})")
            continue
        d = d[d["name_ko"].astype(str).str.strip() != ""]
        for c in COLS:
            if c not in d.columns:
                d[c] = ""
        d = d[COLS].copy()
        d["source_roster"] = rel
        rows.append(d)
        print(f"  {len(d):5d}  {rel}")
    return rows


def main():
    print("=== v1 master ===")
    v1 = pd.read_csv(os.path.join(ROOT, "data", "processed", "master_all.csv"),
                     dtype=str).fillna("")
    for c in COLS:
        if c not in v1.columns:
            v1[c] = ""
    v1["source_url"] = v1.get("data_source", "")
    v1["source_date"] = v1.get("data_source_date", "")
    v1["source_roster"] = "v1/master_all.csv"
    v1 = v1[COLS + ["source_roster"]]
    print(f"  {len(v1)} rows")

    print("=== v2 rosters ===")
    parts = load_rosters()
    allrows = pd.concat([v1] + parts, ignore_index=True) if parts else v1.copy()
    print(f"total before de-duplication: {len(allrows)}")

    # normalize
    allrows["name_ko"] = allrows["name_ko"].astype(str).map(
        lambda s: re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip())
    allrows["sido_2026"] = allrows["sido"]
    allrows["sigungu_2026"] = allrows["sigungu"]
    allrows["sido"] = [canon_sido(s, a, g) for s, a, g in
                       zip(allrows["sido"], allrows["road_address"],
                           allrows["sigungu"])]
    allrows["sigungu"] = [canon_sigungu(g, s) for g, s in
                          zip(allrows["sigungu"], allrows["sido"])]
    fixed = [repair_region(s, g, a) for s, g, a in
             zip(allrows["sido"], allrows["sigungu"], allrows["road_address"])]
    nrep = sum(1 for (s, g), s0 in zip(fixed, allrows["sido"]) if s != s0)
    allrows["sido"] = [x[0] for x in fixed]
    allrows["sigungu"] = [attach_parent_city(x[0], snap_sigungu(x[0], x[1]))
                          for x in fixed]
    print(f"rows whose 시도 column held a 시군구, repaired: {nrep}")

    # the district the address itself names, before anything else is guessed
    from_addr = 0
    sg2 = []
    _exact = _load_sigungu()["exact"]
    overrode = 0
    for sd, sg, ad, jb in zip(allrows["sido"], allrows["sigungu"],
                              allrows["road_address"], allrows["jibun_address"]):
        sd, sg = str(sd).strip(), str(sg).strip()
        if not sd:
            sg2.append(sg)
            continue
        # The roster's own value is kept whenever it joins to the population
        # index. It is overridden only when it joins to NOTHING and the address
        # names a district that does: 천주교마산교구 이주사목위원회 carried
        # 창원시, which the index does not have because 창원 is split into five
        # 구, while its own address reads 창원시 의창구 창이대로600번길 2. A row
        # that joins to nothing is counted in no district at all, so reading the
        # address there is not a guess, it is reading what the row already says.
        joins = bool(sg) and (sd, sg) in _exact
        if joins:
            sg2.append(sg)
            continue
        hit = sigungu_from_address(sd, ad) or sigungu_from_address(sd, jb)
        if hit:
            if sg:
                overrode += 1
            else:
                from_addr += 1
        sg2.append(hit or sg)
    allrows["sigungu"] = sg2
    print(f"시군구 read out of the address text: {from_addr}")
    print(f"시군구 that joined to nothing, replaced from the address: {overrode}")

    # last resort for rows with no address and no region: the region the
    # organization spells in its own name
    from_name = 0
    sd_new, sg_new, rsrc = [], [], []
    for sd, sg, ad, nm in zip(allrows["sido"], allrows["sigungu"],
                              allrows["road_address"], allrows["name_ko"]):
        src = "roster"
        if not str(sd).strip() and not str(ad).strip():
            a, b = region_from_name(nm)
            if a:
                sd, sg, src, from_name = a, (sg or b), "name", from_name + 1
        sd_new.append(sd); sg_new.append(sg); rsrc.append(src)
    allrows["sido"] = sd_new
    allrows["sigungu"] = sg_new
    allrows["region_src"] = rsrc
    print(f"region recovered from the organization's own name: {from_name}")
    n26 = sum(1 for a, b in zip(allrows["sido_2026"], allrows["sido"]) if a != b)
    print(f"sido normalized or mapped back from the 2026 geography: {n26}")
    allrows["phone"] = allrows["phone"].map(canon_phone)
    allrows["website"] = allrows["website"].map(canon_url)

    # A roster that links to its own portal entry has not given a homepage. The
    # 다누리 roster does this for all 229 family centres, which is how the same
    # URL ended up on 216 rows in v1. Keep the link (it is the provenance of the
    # row) but move it out of the slot that means "this organization's site".
    import hosts as _h
    def _split_web(u):
        if not u:
            return "", ""
        lab = _h.classify(u)
        return ("", u) if set(lab) & _h.DEMOTE else (u, "")
    pairs = allrows["website"].map(_split_web)
    allrows["website"] = [p[0] for p in pairs]
    allrows["roster_page"] = [p[1] for p in pairs]
    moved = sum(1 for p in pairs if p[1])
    print(f"moved out of the website slot (portal/aggregator/social/file): {moved}")
    allrows = apply_manual_address(allrows)
    allrows = apply_manual_website(allrows)
    allrows = reregion_after_ledger(allrows)
    MANUAL_SAME = load_manual_dedup()
    allrows["_nk"] = allrows["name_ko"].map(namekey)
    allrows["_ak"] = allrows["road_address"].map(addrkey)
    allrows = allrows[allrows["_nk"] != ""]

    # ---- merge, in two stages
    #
    # Stage 1 keys on name AND street address, the pair that actually singles a
    # facility out. Stage 2 then attaches the rows that carry no address, which
    # a one-stage key would have stranded: the medical roster gives 113 hospital
    # names with no address at all, and every one of them would have become a
    # second row beside the same hospital already in the frame.
    #
    # A row with no address joins a name group only when there is exactly ONE
    # candidate in its 시군구. Two candidates means the address is the thing
    # that would have to decide, and it is missing, so the row stays separate
    # and goes to the review sheet. Guessing there is the shape of US-census
    # failure #9.
    groups = defaultdict(list)
    with_addr, no_addr = [], []
    for i, r in allrows.iterrows():
        (with_addr if r["_ak"] else no_addr).append(i)
    for i in with_addr:
        r = allrows.loc[i]
        groups[(r["_nk"], r["_ak"])].append(i)

    by_name = defaultdict(list)
    for (nk, ak) in groups:
        by_name[nk].append(ak)

    def _region(r):
        return (sigungu_base(r["sigungu"]), str(r["sido"]).strip())

    ambiguous = []
    for i in no_addr:
        r = allrows.loc[i]
        aks = by_name.get(r["_nk"], [])
        # candidates whose region agrees with this row
        cands = []
        for ak in aks:
            sub = allrows.loc[groups[(r["_nk"], ak)]]
            regs = {_region(x) for _, x in sub.iterrows()}
            sg, sd = _region(r)
            if any((sg and sg == g[0]) or (not sg and sd and sd == g[1])
                   for g in regs):
                cands.append(ak)
        if not cands and not str(r["sigungu"]).strip() and not str(r["sido"]).strip():
            # No address AND no region: the only thing left is the name. Attach
            # it when exactly one addressed row in the country carries that
            # normalized name, since there is then nothing for a region test to
            # disambiguate. Two or more and it stays separate.
            if len(aks) == 1:
                cands = aks
        if len(cands) == 1:
            groups[(r["_nk"], cands[0])].append(i)
        else:
            if len(cands) > 1:
                ambiguous.append(i)
            groups[(r["_nk"], "@" + (str(r["sigungu"]).strip()
                                     or str(r["sido"]).strip()))].append(i)
    print(f"rows with no street address: {len(no_addr)} "
          f"(attached to an addressed row where unambiguous; "
          f"{len(ambiguous)} left separate because two candidates matched)")

    merged = []
    for k, idxs in groups.items():
        sub = allrows.loc[idxs]
        base = {}
        for c in COLS + ["roster_page", "sido_2026", "sigungu_2026",
                         "region_src"]:
            vals = [str(v).strip() for v in sub[c] if str(v).strip()]
            base[c] = vals[0] if vals else ""
        # keep the longest address and the richest free-text fields
        for c in ("road_address", "services_provided", "target_population",
                  "notes", "languages_supported"):
            vals = sorted({str(v).strip() for v in sub[c] if str(v).strip()},
                          key=len, reverse=True)
            base[c] = vals[0] if vals else ""
        # a row is closed only if every roster says so
        st = {str(v).strip() for v in sub["operational_status"] if str(v).strip()}
        base["operational_status"] = ("closed" if st == {"closed"}
                                      else ("active" if "active" in st else
                                            (list(st)[0] if st else "unknown")))
        # A roster can carry the dissolution in its free text and still leave
        # the status column saying active. NPAS does exactly this: "상태 원문:
        # 말소(2025-07-02)" sat in notes on 59 rows the frame was publishing as
        # live organizations. Only an explicit dated statement is read; a
        # sentence that merely mentions 폐지 (a school closing one course while
        # the school stays open) is not enough.
        m = _DISSOLVED_DATED.search(base.get("notes", ""))
        if m:
            base["operational_status"] = "closed"
            if not str(base.get("closed_year", "")).strip():
                base["closed_year"] = m.group(2)
        base["source_roster"] = "|".join(sorted(set(sub["source_roster"])))
        base["n_rosters"] = len(set(sub["source_roster"]))
        base["source_url"] = "|".join(sorted({str(v).strip() for v in sub["source_url"]
                                              if str(v).strip()})[:4])
        base["_key"] = f"{k[0]}|{k[1]}"
        base["_rows"] = list(idxs)
        merged.append(base)

    # Stage 3: same street address AND a near-identical name. Neither signal
    # settles identity alone -- an address is shared by every tenant of a
    # building, and a 95% name match is shared by 광주이주여성지원센터 and
    # 광주이주민지원센터, which are two different organizations. Together they
    # do: 포천시 외국인주민지원센터 and 포천외국인주민지원센터 differ by one
    # administrative suffix and sit at the same door with the same phone.
    from rapidfuzz import fuzz as _fz
    by_ak = defaultdict(list)
    for j, m in enumerate(merged):
        ak = addrkey(m.get("road_address", ""))
        if ak:
            by_ak[(m.get("sido", ""), ak)].append(j)
    absorbed, pairs3, by_containment = set(), 0, []
    for _, js in by_ak.items():
        for x in range(len(js)):
            if js[x] in absorbed:
                continue
            for y in range(x + 1, len(js)):
                if js[y] in absorbed:
                    continue
                a, b = merged[js[x]], merged[js[y]]
                ka, kb = namekey(a["name_ko"]), namekey(b["name_ko"])
                # Containment on its own is never identity (census failure #10:
                # "Michigan Immigrant Rights Center" is contained in "One
                # Michigan for Immigrant Rights" and they are different bodies).
                # Containment AT THE SAME STREET ADDRESS is a different claim.
                # 아시아평화를향한이주 and 아시아평화를향한이주MAP both sit at
                # 동호로24길 27-17 우리함께빌딩 303호 and score only 87 on the
                # fuzzy test, so the ratio alone left them as two organizations.
                short, long_ = sorted((ka, kb), key=len)
                contained = len(short) >= 5 and residual_is_cosmetic(short, long_)
                if not contained and _fz.ratio(ka, kb) < 92:
                    continue
                if contained and _fz.ratio(ka, kb) < 92:
                    by_containment.append((a["name_ko"], b["name_ko"],
                                           a.get("road_address", "")))
                for c in list(b):
                    if c in ("source_roster", "n_rosters", "_key"):
                        continue
                    if not str(a.get(c, "")).strip() and str(b.get(c, "")).strip():
                        a[c] = b[c]
                a["source_roster"] = "|".join(sorted(
                    set(str(a["source_roster"]).split("|"))
                    | set(str(b["source_roster"]).split("|"))))
                a["n_rosters"] = len(str(a["source_roster"]).split("|"))
                a["_rows"] = list(a.get("_rows", [])) + list(b.get("_rows", []))
                absorbed.add(js[y])
                pairs3 += 1
    if absorbed:
        merged = [m for j, m in enumerate(merged) if j not in absorbed]
    print(f"same-address near-identical-name merges: {pairs3}")
    if by_containment:
        print(f"  of which name-containment at one address ({len(by_containment)}), "
              f"each listed so a person can reverse it:")
        for aa, bb, ad in by_containment:
            print(f"    {aa}  <=  {bb}   @ {ad[:40]}")

    # Stage 4: same name, same phone, different address. A building is shared by
    # every tenant; a phone number is not. 위기이주여성긴급보호쉼터 was in the
    # frame three times because one roster gave the operating body's address
    # (명동길 80, the archdiocese) and another gave the shelter's own, while both
    # printed 070-8829-1366. Requiring the name to match as well keeps a shared
    # switchboard from pulling unrelated offices together.
    by_tel = defaultdict(list)
    for j, m in enumerate(merged):
        t = idmatch.phone_digits(m.get("phone", ""))
        if t:
            by_tel[t].append(j)
    absorbed4, pairs4 = set(), 0
    for _, js in by_tel.items():
        for x in range(len(js)):
            if js[x] in absorbed4:
                continue
            for y in range(x + 1, len(js)):
                if js[y] in absorbed4:
                    continue
                a, b = merged[js[x]], merged[js[y]]
                if namekey(a["name_ko"]) != namekey(b["name_ko"]):
                    continue
                for c in list(b):
                    if c in ("source_roster", "n_rosters", "_key"):
                        continue
                    if not str(a.get(c, "")).strip() and str(b.get(c, "")).strip():
                        a[c] = b[c]
                a["source_roster"] = "|".join(sorted(
                    set(str(a["source_roster"]).split("|"))
                    | set(str(b["source_roster"]).split("|"))))
                a["n_rosters"] = len(str(a["source_roster"]).split("|"))
                a["_rows"] = list(a.get("_rows", [])) + list(b.get("_rows", []))
                absorbed4.add(js[y])
                pairs4 += 1
    if absorbed4:
        merged = [m for j, m in enumerate(merged) if j not in absorbed4]
    print(f"same-name same-phone merges: {pairs4}")

    # Stage 4b: same name, same official-platform host, different address.
    # 한국건강가정진흥원 gives one familynet subdomain to one 가족센터 and to
    # nobody else, so two rows on gwangjin.familynet.or.kr are one centre no
    # matter what address each roster wrote. They differ because a centre runs
    # its 한국어교육 in a rented office and its 이중언어코치 programme in a
    # university lecture hall, and each programme roster recorded the room its
    # own programme uses. 포천시 가족센터 was in the map three times that way.
    # The rows are delivery sites of one organization; the map shows the
    # organization, and the addresses it absorbs are kept in other_addresses.
    # The roster's website column predates the website search, so on a first
    # pass almost no row carries its familynet address yet and this stage sees
    # nothing to merge. website_verified.csv holds what the search confirmed, so
    # read it when it exists. Only the absorbed rows disappear; the surviving
    # row keeps its own facility_id, which is a hash of its own merge key, so
    # everything already joined to that id still joins.
    verified = {}
    vp = os.path.join(OUT, "website_verified.csv")
    if os.path.exists(vp):
        vd = pd.read_csv(vp, dtype=str).fillna("")
        for _, vr in vd.iterrows():
            u = str(vr.get("final_website", "")).strip()
            if u:
                verified[str(vr.get("name_ko", "")).strip()] = u
        print(f"verified websites available to the platform merge: {len(verified)}")

    by_plat = defaultdict(list)
    for j, m in enumerate(merged):
        u = (str(m.get("website", "")).strip()
             or verified.get(str(m.get("name_ko", "")).strip(), ""))
        if u and hosts.is_official_subdomain(u):
            by_plat[(hosts.host_of(u), namekey(m["name_ko"]))].append(j)
    absorbed4b, pairs4b = set(), 0
    for _, js in by_plat.items():
        if len(js) < 2:
            continue
        # the designation roster's row is the centre itself; a programme roster
        # gives the room that programme uses. Keep the row that the most
        # rosters agree on, and among ties the one that has a phone number.
        js = sorted(js, key=lambda j: (-int(merged[j].get("n_rosters", 1) or 1),
                                       0 if str(merged[j].get("phone", "")).strip()
                                       else 1))
        a = merged[js[0]]
        extra = [x for x in str(a.get("other_addresses", "")).split("|") if x]
        for j in js[1:]:
            b = merged[j]
            ad = str(b.get("road_address", "")).strip()
            if ad and ad != str(a.get("road_address", "")).strip():
                extra.append(ad)
            for c in list(b):
                if c in ("source_roster", "n_rosters", "_key", "other_addresses"):
                    continue
                if not str(a.get(c, "")).strip() and str(b.get(c, "")).strip():
                    a[c] = b[c]
            a["source_roster"] = "|".join(sorted(
                set(str(a["source_roster"]).split("|"))
                | set(str(b["source_roster"]).split("|"))))
            a["n_rosters"] = len(str(a["source_roster"]).split("|"))
            a["_rows"] = list(a.get("_rows", [])) + list(b.get("_rows", []))
            absorbed4b.add(j)
            pairs4b += 1
        a["other_addresses"] = "|".join(dict.fromkeys(extra))
    if absorbed4b:
        merged = [m for j, m in enumerate(merged) if j not in absorbed4b]
    print(f"same-name same-official-platform merges: {pairs4b}")

    # Stage 5: same name, same 시군구, and one of the two carries no address at
    # all. Stage 2 was supposed to catch these, but a roster that gives only a
    # 시도 (the 이중언어코치 list does) has no 시군구 to match on until the
    # coordinate repair fills one in, and that runs after the merge. An
    # address-less row contradicts nothing, so where its name and district agree
    # with exactly one addressed row it is that row. Where TWO addressed rows
    # share the name and district (광진구 가족센터 at 천호대로 and at 능동로, with
    # different phone numbers) nothing is merged and the pair goes to review.
    by_nk_sgg = defaultdict(list)
    for j, m in enumerate(merged):
        by_nk_sgg[(namekey(m["name_ko"]), m.get("sido", ""),
                   sigungu_base(m.get("sigungu", "")))].append(j)
    absorbed5, pairs5 = set(), 0
    for k, js in by_nk_sgg.items():
        if not k[0] or not k[1] or len(js) < 2:
            continue
        withA = [j for j in js if addrkey(merged[j].get("road_address", ""))]
        without = [j for j in js if not addrkey(merged[j].get("road_address", ""))]
        if len(withA) != 1 or not without:
            continue
        a = merged[withA[0]]
        for j in without:
            b = merged[j]
            for c in list(b):
                if c in ("source_roster", "n_rosters", "_key", "_rows"):
                    continue
                if not str(a.get(c, "")).strip() and str(b.get(c, "")).strip():
                    a[c] = b[c]
            a["source_roster"] = "|".join(sorted(
                set(str(a["source_roster"]).split("|"))
                | set(str(b["source_roster"]).split("|"))))
            a["n_rosters"] = len(str(a["source_roster"]).split("|"))
            a["_rows"] = list(a.get("_rows", [])) + list(b.get("_rows", []))
            absorbed5.add(j)
            pairs5 += 1
    if absorbed5:
        merged = [m for j, m in enumerate(merged) if j not in absorbed5]
    print(f"address-less rows folded into the one addressed row "
          f"of the same name and district: {pairs5}")

    # Stage 6: the pairs a person judged the same organization. The machine left
    # them apart because both carried an address and the addresses differed,
    # which is the correct default; a person who opened both pages can overrule
    # it, and this is where that ruling takes effect rather than sitting in a
    # file doing nothing.
    if MANUAL_SAME:
        idx = defaultdict(list)
        for j, m in enumerate(merged):
            idx[(namekey(m["name_ko"]), m.get("sido", ""),
                 sigungu_base(m.get("sigungu", "")))].append(j)
        absorbed6, pairs6, unmatched6 = set(), 0, 0
        for ka, kb, sd, sg in MANUAL_SAME:
            ja = idx.get((ka, sd, sigungu_base(sg)), [])
            jb = idx.get((kb, sd, sigungu_base(sg)), [])
            ja = [j for j in ja if j not in absorbed6]
            jb = [j for j in jb if j not in absorbed6]
            if len(ja) != 1 or len(jb) != 1 or ja[0] == jb[0]:
                unmatched6 += 1
                continue
            a, b = merged[ja[0]], merged[jb[0]]
            for c in list(b):
                if c in ("source_roster", "n_rosters", "_key", "_rows"):
                    continue
                if not str(a.get(c, "")).strip() and str(b.get(c, "")).strip():
                    a[c] = b[c]
            a["source_roster"] = "|".join(sorted(
                set(str(a["source_roster"]).split("|"))
                | set(str(b["source_roster"]).split("|"))))
            a["n_rosters"] = len(str(a["source_roster"]).split("|"))
            a["_rows"] = list(a.get("_rows", [])) + list(b.get("_rows", []))
            absorbed6.add(jb[0])
            pairs6 += 1
        if absorbed6:
            merged = [m for j, m in enumerate(merged) if j not in absorbed6]
        print(f"merges a person ruled on: {pairs6} applied, "
              f"{unmatched6} could not be located")

    # One status vocabulary. The rosters variously write active / operating /
    # open / 운영중 for the same thing, and a page that switches on the value
    # silently drops whichever spelling it did not expect.
    _ACTIVE = {"active", "operating", "open", "운영", "운영중", "정상"}
    for m in merged:
        v = str(m.get("operational_status", "")).strip().lower()
        m["operational_status"] = ("closed" if v == "closed"
                                   else "active" if v in _ACTIVE
                                   else "unknown" if not v else v)
        y = re.search(r"(19|20)\d{2}", str(m.get("closed_year", "")))
        m["closed_year"] = y.group(0) if y else ""

    # Criteria rule 14: a facility that closed before 2020 is out of scope.
    # Keeping it would put a resource on the map that nobody alive has used.
    pre2020 = [m for m in merged
               if m["operational_status"] == "closed"
               and m["closed_year"] and int(m["closed_year"]) < 2020]
    if pre2020:
        merged = [m for m in merged if m not in pre2020]
        pd.DataFrame([{"name_ko": m["name_ko"], "closed_year": m["closed_year"],
                       "source_roster": m["source_roster"],
                       "reason": "rule14_closed_before_2020"}
                      for m in pre2020]).to_csv(
            os.path.join(OUT, "frame_dropped.csv"), index=False,
            encoding="utf-8-sig")
        print(f"dropped, closed before 2020 (rule 14): {len(pre2020)} "
              f"-> frame_dropped.csv")

    df = pd.DataFrame(merged)
    # The id is a hash of the merge key, NOT the row number. A row number is an
    # identity only inside the file it was counted in (census failure #16): when
    # a new roster arrives, every positional id shifts by one and every table
    # keyed on it silently points at a different organization.
    df["facility_id"] = df["_key"].map(
        lambda k: "KIRD-" + hashlib.sha1(k.encode("utf-8")).hexdigest()[:10])
    dup = df["facility_id"].duplicated().sum()
    if dup:
        raise SystemExit(f"id collision on {dup} rows; the merge key is not unique")
    # Lineage: which input row became which facility_id. Without it, a check
    # that a roster row survived has to guess from the name, and a row merged
    # under a neighbour's spelling looks lost when it is not (census rule: a
    # positional or inferred key is not an identity).
    lin = []
    for _, r in df.iterrows():
        for i in r["_rows"]:
            src = allrows.loc[i]
            lin.append({"facility_id": r["facility_id"],
                        "in_name": src["name_ko"],
                        "in_roster": src["source_roster"],
                        "out_name": r["name_ko"]})
    pd.DataFrame(lin).to_csv(os.path.join(OUT, "frame_lineage.csv"),
                             index=False, encoding="utf-8-sig")
    print(f"lineage rows: {len(lin)} -> frame_lineage.csv")
    df = df.drop(columns=["_key", "_rows"])
    # The same repair again, now that merging has chosen which row survives.
    # 고양시 가족센터 entered with 고양시 일산동구 on one roster row and a bare
    # 고양시 on another; the merge keeps the row the most rosters agree on, and
    # that row can be the one carrying the weaker district. The index has no
    # 고양시, so the surviving row was counted in no district.
    _kn = _load_sigungu()["exact"]
    post = 0
    for i, r in df.iterrows():
        sd, sg = str(r.get("sido", "")).strip(), str(r.get("sigungu", "")).strip()
        if not sd or not sg or (sd, sg) in _kn:
            continue
        ad = str(r.get("road_address", "")) or str(r.get("jibun_address", ""))
        hit = sigungu_from_address(sd, ad)
        if hit and hit != sg:
            df.at[i, "sigungu"] = hit
            post += 1
            continue
        # the 시도 itself can be the wrong one. 목포서부초등학교 came in under
        # 전라북도 while its address reads 전라남도 목포시, and 군위군 moved from
        # 경상북도 to 대구광역시 in 2023 while the roster still says 경상북도.
        # The address is the row's own statement; prefer it over the column.
        sd2 = canon_sido("", ad, "")
        if sd2 and sd2 != sd:
            hit2 = sigungu_from_address(sd2, ad)
            if hit2 and (sd2, hit2) in _kn:
                df.at[i, "sido"] = sd2
                df.at[i, "sigungu"] = hit2
                post += 1
    print(f"시군구 repaired after merging, from the row's own address: {post}")
    if "other_addresses" not in df.columns:
        df["other_addresses"] = ""
    df["other_addresses"] = df["other_addresses"].fillna("")
    print(f"after de-duplication: {len(df)}")

    # ---- review sheet: names that are similar but not equal, same 시군구
    from rapidfuzz import fuzz
    df["_nk"] = df["name_ko"].map(namekey)
    review = []
    by_sg = defaultdict(list)
    for i, r in df.iterrows():
        by_sg[(r["sido"], r["sigungu"])].append(i)
    for key, idxs in by_sg.items():
        if len(idxs) < 2 or not key[1]:
            continue
        for ai in range(len(idxs)):
            for bi in range(ai + 1, len(idxs)):
                a, b = df.loc[idxs[ai]], df.loc[idxs[bi]]
                if a["_nk"] == b["_nk"]:
                    continue
                s = fuzz.ratio(a["_nk"], b["_nk"])
                # 80 rather than 88: at 88 the real cases are missed. 여수외국인
                # 근로자문화센터 vs 여수외국인노동자 문화센터 scores 83 and is
                # very likely one organization under two roster spellings, and
                # 광주이주여성지원센터 vs 광주이주민지원센터 scores 84 and is two
                # different organizations. Neither is decidable here, which is
                # the whole point of the sheet.
                if s >= 80:
                    review.append({"score": s, "sido": key[0], "sigungu": key[1],
                                   "a_id": a["facility_id"], "a": a["name_ko"],
                                   "a_addr": a["road_address"],
                                   "a_src": a["source_roster"],
                                   "b_id": b["facility_id"], "b": b["name_ko"],
                                   "b_addr": b["road_address"],
                                   "b_src": b["source_roster"]})
    rv = pd.DataFrame(review).sort_values("score", ascending=False) if review \
        else pd.DataFrame(columns=["score"])
    rv.to_csv(os.path.join(OUT, "review_dedup.csv"), index=False,
              encoding="utf-8-sig")

    keep = (["facility_id"] + COLS
            + ["roster_page", "sido_2026", "sigungu_2026", "region_src",
               "other_addresses", "source_roster", "n_rosters"])
    df[keep].to_csv(os.path.join(OUT, "frame_v2.csv"), index=False,
                    encoding="utf-8-sig")

    print(f"\nnear-duplicate pairs for human review: {len(rv)} -> review_dedup.csv")
    print("\n=== rows by source roster ===")
    ex = df["source_roster"].str.split("|").explode().value_counts()
    print(ex.to_string())
    print("\n=== rows by category ===")
    print(df["category"].value_counts().to_string())
    print(f"\nwrote frame_v2.csv ({len(df)} rows)")


if __name__ == "__main__":
    main()
