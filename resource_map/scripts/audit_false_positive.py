# -*- coding: utf-8 -*-
"""Find what is in the frame that should not be, before a model is asked.

`code_inclusion.py` answers "is this a migrant support resource" from evidence.
This runs first and answers a different question: which rows carry a SIGNAL of
not belonging, so that the model sees the signal instead of having to notice it,
and so that the count of each kind of doubt is reportable.

The seven signals, and why each one exists:

  keyword_only     the row's only roster is one built by matching a keyword
                   against a name (NPAS, 공익법인 공시, 복지로, 인허가 데이터).
                   Criteria rule 11: a name is never sufficient.
  unlocatable      no address, no 시군구 and no coordinate. Rule 15: an entry
                   nothing can place may not be a live facility. NOT the same as
                   "no phone": a 폭력피해 이주여성 쉼터 has its address withheld
                   by law and a hospital roster may simply omit one, and both are
                   real. Missing contact detail on its own is a completeness
                   problem, reported separately and flagged on nobody.
  dissolved        the source says 말소 / 해산 / 폐지 / 폐업, or the row is
                   already marked closed.
  overseas         the organization's stated work is abroad. 국제개발협력 NGOs
                   match 다문화 and 국제 on their names and serve nobody in
                   Korea. This is the single largest untested false-positive
                   route in the keyword rosters.
  not_a_place      the name denotes a programme, a fund, a committee or a
                   representative council. Real, but not somewhere a person
                   goes. It belongs in the list with unit_type=umbrella, never
                   in the density numerator.
  defector         rule 13, 북한이탈주민 전용.
  commercial       rule 12, 알선·중개·유학원·행정사.

Nothing here removes a row. It writes flags and a review sheet.

Run:  python scripts/v2/audit_false_positive.py
"""
from __future__ import annotations
import argparse
import os
import re
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")

# Rosters built by matching a keyword against a name. Being on one of these and
# nothing else is a lead, not a qualification.
KEYWORD_ROSTERS = re.compile(
    r"(npas_migrant_keyword_registry|public_interest_corp_migrant|"
    r"social_welfare_facility_migrant|bigreg|localdata|coalition_member)")

DISSOLVED = re.compile(r"(말소|해산|폐지|폐업|해체|운영\s*중단|사업\s*종료|"
                       r"등록\s*취소|closed)")

# Overseas development work. The domestic hook has to be absent for this to
# fire, because plenty of real migrant organizations also run overseas projects.
OVERSEAS = re.compile(
    r"(국제개발|개발협력|해외원조|해외구호|해외사업|해외아동|해외선교|"
    r"기아대책|월드비전|굿네이버스|지구촌공생회|해외봉사|국제구호|"
    r"저개발국|개도국|아프리카\s*지원|캄보디아\s*학교|베트남\s*지원사업)")
DOMESTIC = re.compile(
    r"(국내\s*거주|체류\s*외국인|이주노동자|결혼이민|다문화가족|난민신청|"
    r"한국어\s*교육|통번역|상담소|쉼터|정착지원|사회통합프로그램|"
    r"외국인주민|이주배경\s*청소년|미등록)")

# Names that denote a programme, a fund or a deliberative body rather than a
# place. 협회 / 네트워크 / 연대 / 위원회 are deliberately NOT here: 재한외국인
# 지원협회, 이주인권연대 and 천주교인권위원회 are ordinary organizations with
# staff and an address, and flagging them was noise.
NOT_A_PLACE = re.compile(
    r"(대표자회의|기금$|사업단$|추진단$|협의체$|"
    r"^.{0,12}사업$|공모사업|지원사업$|기본계획|시행계획)")

DEFECTOR = re.compile(r"(북한이탈|탈북|하나원|하나센터|새터민|북향민)")
# Rule 13 excludes defector-ONLY bodies. Several real migrant organizations
# serve both populations (이주배경청소년 work routinely covers 탈북청소년), so
# the flag only fires when nothing migrant-facing appears alongside.
MIGRANT_WORD = re.compile(
    r"(이주|외국인|다문화|난민|이민|결혼이민|고려인|중국동포|조선족|"
    r"migrant|foreign|multicultural|refugee)")
COMMERCIAL = re.compile(
    r"(유학원|어학원|인력\s*송출|송출\s*업체|국제결혼\s*중개|결혼중개업|"
    r"비자\s*대행|행정사\s*사무소|이민\s*컨설팅|유학\s*컨설팅|"
    r"인력\s*파견|헤드헌팅|주식회사|㈜|\(주\))")


def flags(r):
    name = str(r.get("name_ko") or "")
    svc = str(r.get("services_provided") or "")
    notes = str(r.get("notes") or "")
    rosters = str(r.get("source_roster") or "")
    blob = " ".join([name, svc, notes, str(r.get("target_population") or "")])
    f = []

    kw_only = all(KEYWORD_ROSTERS.search(p) for p in rosters.split("|") if p)
    if kw_only and rosters:
        f.append("keyword_only")
    placed = any(str(r.get(c) or "").strip()
                 for c in ("road_address", "jibun_address", "sigungu", "lat"))
    if not placed:
        f.append("unlocatable")
    if DISSOLVED.search(blob) or str(r.get("operational_status") or "") == "closed":
        f.append("dissolved")
    if OVERSEAS.search(blob) and not DOMESTIC.search(blob):
        f.append("overseas")
    if NOT_A_PLACE.search(name.strip()):
        f.append("not_a_place")
    if DEFECTOR.search(blob) and not MIGRANT_WORD.search(blob):
        f.append("defector")
    if COMMERCIAL.search(name):
        f.append("commercial")
    return f


def main(a):
    df = pd.read_csv(a.frame, dtype=str).fillna("")
    df["fp_flags"] = ["|".join(flags(r)) for _, r in df.iterrows()]
    df["fp_n"] = df.fp_flags.map(lambda s: len(s.split("|")) if s else 0)

    cnt = collections.Counter()
    for s in df.fp_flags:
        for x in (s.split("|") if s else []):
            cnt[x] += 1

    print(f"frame {len(df)}")
    print("\n=== rows carrying each signal (a row can carry several) ===")
    for k, v in cnt.most_common():
        print(f"{v:5d}  {k}")
    print(f"\nrows with no signal at all: {(df.fp_n == 0).sum()}")
    print(f"rows with at least one:     {(df.fp_n > 0).sum()}")
    print(f"rows with two or more:      {(df.fp_n >= 2).sum()}")

    print("\n=== signal by source roster (first roster on the row) ===")
    first = df.source_roster.str.split("|").str[0]
    piv = pd.crosstab(first, df.fp_n > 0)
    piv.columns = ["clean", "flagged"]
    piv["rate"] = (piv.flagged / (piv.clean + piv.flagged)).map(lambda x: f"{x:.0%}")
    print(piv.sort_values("flagged", ascending=False).head(14).to_string())

    hot = df[df.fp_n > 0].copy()
    cols = ["facility_id", "name_ko", "category", "sido", "sigungu",
            "road_address", "phone", "website", "operational_status",
            "services_provided", "notes", "source_roster", "fp_flags"]
    hot[[c for c in cols if c in hot.columns]].sort_values(
        ["fp_flags", "name_ko"]).to_csv(
        os.path.join(OUT, "review_false_positive.csv"), index=False,
        encoding="utf-8-sig")
    df.to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"\nwrote {a.out} (fp_flags column added)")
    print(f"review sheet: {len(hot)} rows -> review_false_positive.csv")

    print("\n=== 20 examples, most-flagged first ===")
    for _, r in hot.sort_values("fp_n", ascending=False).head(20).iterrows():
        print(f"  [{r.fp_flags}] {r.name_ko}  ({r.source_roster.split('|')[0]})")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "frame_v2_flagged.csv"))
    sys.exit(main(ap.parse_args()))
