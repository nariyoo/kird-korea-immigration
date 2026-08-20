# -*- coding: utf-8 -*-
"""Who pays for a place and who runs it.

A resource map that shows only where the organizations are cannot answer the
question the delivery-system literature actually asks: whether a district is
covered by the state, by a contract the state signed with somebody else, or by
people who organized without the state. Those three are different things when a
budget line moves, and the map was carrying no way to tell them apart.

The rosters already answer it, because a roster IS a designation or a funding
programme. 가족센터 appears on the 성평등가족부 list because the ministry funds
the programme and the 시군구 contracts a 법인 to run it; 출입국·외국인사무소
appears on the 법무부 list because the ministry runs it directly; an NGO appears
on the NPAS registry because it registered itself. Reading the roster is reading
the arrangement, which is why the roster is checked before the free-text
`operator_type` column, where 1,265 of 2,800 rows are blank and the rest mix
`public`, `NGO`, `정부`, `사단법인` and `시민단체` in two languages.

Two fields, because one would collapse a real distinction:

  gov_funder    central        중앙정부
                local          지방자치단체
                central_local  중앙·지방 매칭 (국고보조사업)
                private        민간 자체 재원
                religious      종교기관
                academic       대학
                unknown

  gov_operator  direct         직영 (재원 주체가 직접 운영)
                contracted     위탁 (재원 주체가 다른 법인에 맡김)
                designated     지정 (기관이 자기 재원으로 운영하되 정부가 지정)
                self           자체 (정부 재원 없음)
                unknown

The pair is what carries the meaning. 가족센터 is central_local + contracted:
the money is a matched national grant and the door is opened by a 법인 the
district chose. A KIIP 운영기관 is central + designated: 법무부 designates it and
pays per programme, but the university or the NGO existed first and would exist
without the designation. Collapsing those two into "government" would say a
district has state provision when what it has is a designation on a body that
was already there.

Run:  python scripts/v2/code_governance.py
"""
from __future__ import annotations
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")

FUNDERS = {
    "central": "중앙정부",
    "local": "지방자치단체",
    "central_local": "중앙·지방 매칭",
    "private": "민간",
    "religious": "종교기관",
    "academic": "대학",
    "unknown": "확인 안 됨",
}

OPERATORS = {
    "direct": "직영",
    "contracted": "위탁",
    "designated": "지정",
    "self": "자체",
    "unknown": "확인 안 됨",
}

# The roster is the arrangement. Ordered most specific first; the first roster a
# row carries that appears here decides, because a row on two rosters is on the
# more specific one for a reason.
ROSTER_GOV = [
    # 법무부가 직접 운영하는 관서
    ("gov_labor/immigration_office_full_roster.csv", "central", "direct"),
    # 고용노동부가 예산을 대고 민간·공공 법인에 맡긴 외국인력지원센터
    ("gov_labor/eps_foreign_worker_support_center.csv", "central", "contracted"),
    # 성평등가족부 국고보조사업, 시군구가 법인에 위탁
    ("family/multicultural_family_center.csv", "central_local", "contracted"),
    ("family/korean_language_education_service.csv", "central_local", "contracted"),
    ("family/bilingual_coach_service.csv", "central_local", "contracted"),
    ("family/translation_interpretation_service.csv", "central_local", "contracted"),
    ("family/danuri_call_center.csv", "central", "contracted"),
    ("women/danuri_callcenter_migrant_women_emergency_support.csv",
     "central", "contracted"),
    # 성평등가족부가 지정하고 예산을 지원하는 상담소
    ("women/mogef_violence_victim_migrant_women_counseling_centers.csv",
     "central", "contracted"),
    # 법무부가 지정하는 프로그램 운영기관. 기관 자체는 지정 전부터 존재한다
    ("kiip/kiip_operating_institutions.csv", "central", "designated"),
    ("kiip/early_adaptation_program_institutions.csv", "central", "designated"),
    ("kiip/intl_marriage_program_institutions.csv", "central", "designated"),
    # 보건복지부 의료지원 지정 의료기관
    ("health_youth/medical_designated_institutions.csv", "central", "designated"),
    # 교육부·교육청 지정 학교와 센터
    ("edu/edu_policy_school.csv", "local", "direct"),
    ("health_youth/edu_multicultural_education_center.csv", "local", "direct"),
    ("health_youth/youth_rainbow_school.csv", "central", "contracted"),
    # 지자체 조례로 설치한 시설. 직영인지 위탁인지는 조례만으로 알 수 없다
    ("local_gov/local_gov_foreign_resident_facilities.csv", "local", "unknown"),
    ("gov_labor/foreign_worker_center_local_relaunch.csv", "local", "contracted"),
    # 정부 보조금을 받는 사업이지만 단체가 신청해서 받는 것
    ("crosscut/grantee_org.csv", "private", "self"),
    # 스스로 등록한 단체
    ("ngo/npas_migrant_keyword_registry.csv", "private", "self"),
    ("crosscut/public_interest_corp_migrant.csv", "private", "self"),
    ("bigreg/nts_public_interest_corp_keyword_supplement.csv", "private", "self"),
    ("ngo/coalition_member_rosters.csv", "private", "self"),
    ("ngo/refugee_support_refugeeswelcome_members.csv", "private", "self"),
    ("ngo/legal_aid_anchors.csv", "private", "self"),
    ("community/migrant_community_org.csv", "private", "self"),
    ("community/migrant_led_org.csv", "private", "self"),
    ("ngo/religious_catholic_migrant_pastoral.csv", "religious", "self"),
    ("ngo/maha_migrant_network_members.csv", "religious", "self"),
    ("community/migrant_religious_site.csv", "religious", "self"),
    ("youth/migrant_youth_foundation_partners.csv", "private", "self"),
    ("ngo/migrant_human_rights_solidarity_members.csv", "private", "self"),
    ("ngo/migrant_worker_equality_solidarity_members.csv", "private", "self"),
]

# unit_type, used only where no roster in the table above claims the row
TYPE_GOV = {
    "administrative": ("central", "direct"),
    "family_center": ("central_local", "contracted"),
    "resident_center": ("local", "unknown"),
    "worker_center": ("central", "contracted"),
    "migrant_worker_center": ("central", "contracted"),
    "library": ("local", "direct"),
    "religious_site": ("religious", "self"),
    "ngo": ("private", "self"),
    "community": ("private", "self"),
    "umbrella": ("private", "self"),
    "media": ("private", "self"),
    "research": ("academic", "self"),
    "intl_student_center": ("academic", "self"),
    "school": ("local", "direct"),
}

# The operator column, when it says something the roster does not. 위탁 운영 is
# written into the operator NAME far more often than into the type column:
# "재단법인 ○○복지재단(위탁운영)".
_CONTRACTED = re.compile(r"(위탁|수탁|위·수탁)")
_DIRECT = re.compile(r"(직영|직접\s*운영)")
_LOCALGOV = re.compile(r"(시청|군청|구청|도청|지방자치단체|지자체)")
_ACADEMIC = re.compile(r"(대학교|대학|학교법인|산학협력단)")
_RELIGIOUS = re.compile(r"(교회|성당|사찰|교구|대한불교|기독교|천주교|불교|"
                        r"원불교|선교)")


def from_roster(row):
    rost = str(row.get("source_roster", ""))
    for path, f, o in ROSTER_GOV:
        if path in rost:
            return f, o, "roster:" + path.split("/")[-1].replace(".csv", "")
    return None


def refine(funder, operator, row):
    """Let an explicit operator note settle what the roster left open.

    지자체 시설은 조례만으로는 직영인지 위탁인지 알 수 없다. 명부가 운영주체를
    적어 두었으면 그것이 답이고, 안 적어 두었으면 확인 안 됨으로 남긴다. 비어
    있는 것을 채우기만 하고, 명부가 이미 정한 값을 덮어쓰지는 않는다.
    """
    blob = " ".join([str(row.get("operator_name", "")),
                     str(row.get("operator_type", "")),
                     str(row.get("notes", "")),
                     str(row.get("subcategory", ""))])
    why = []
    if operator == "unknown":
        if _CONTRACTED.search(blob):
            operator, why = "contracted", why + ["operator_note:위탁"]
        elif _DIRECT.search(blob):
            operator, why = "direct", why + ["operator_note:직영"]
    if funder == "unknown":
        if _RELIGIOUS.search(blob):
            funder, why = "religious", why + ["operator_note:종교"]
        elif _ACADEMIC.search(blob):
            funder, why = "academic", why + ["operator_note:대학"]
        elif _LOCALGOV.search(blob):
            funder, why = "local", why + ["operator_note:지자체"]
    # A university or a church that pays for its own centre runs its own centre.
    # Leaving those as 확인 안 됨 would report a gap in the coding where there is
    # none: 자체 재원이면 위탁할 상대가 없다.
    if operator == "unknown" and funder in ("religious", "academic", "private"):
        operator, why = "self", why + ["own_funds"]
    return funder, operator, why


def code(row):
    hit = from_roster(row)
    if hit:
        funder, operator, why = hit[0], hit[1], [hit[2]]
    else:
        t = str(row.get("unit_type", "")).strip()
        if t in TYPE_GOV:
            funder, operator = TYPE_GOV[t]
            why = ["unit_type:" + t]
        else:
            funder, operator, why = "unknown", "unknown", []
    funder, operator, extra = refine(funder, operator, row)
    return funder, operator, "|".join(why + extra)


def main(a):
    df = pd.read_csv(a.inclusion, dtype=str).fillna("")
    frame = pd.read_csv(a.frame, dtype=str).fillna("")
    want = ("source_roster", "operator_name", "operator_type", "notes",
            "subcategory")
    keep = ["facility_id"] + [c for c in want if c in frame.columns]
    df = df.merge(frame[keep], on="facility_id", how="left",
                  suffixes=("", "_f")).fillna("")
    for c in want:
        if c + "_f" in df.columns:
            if c in df.columns:
                df[c] = df[c].where(df[c].astype(str).str.strip() != "",
                                    df[c + "_f"])
            else:
                df[c] = df[c + "_f"]
            df = df.drop(columns=[c + "_f"])

    got = [code(r) for _, r in df.iterrows()]
    df["gov_funder"] = [g[0] for g in got]
    df["gov_operator"] = [g[1] for g in got]
    df["gov_basis"] = [g[2] for g in got]
    df.to_csv(a.out, index=False, encoding="utf-8-sig")

    print("=== who pays ===")
    for k, v in collections.Counter(df.gov_funder).most_common():
        print("  %5d  %-14s %s" % (v, k, FUNDERS.get(k, "")))
    print("")
    print("=== who runs it ===")
    for k, v in collections.Counter(df.gov_operator).most_common():
        print("  %5d  %-12s %s" % (v, k, OPERATORS.get(k, "")))
    print("")
    print("=== the pair ===")
    pair = collections.Counter(zip(df.gov_funder, df.gov_operator))
    for (f, o), v in pair.most_common(14):
        print("  %5d  %s / %s" % (v, FUNDERS.get(f, f), OPERATORS.get(o, o)))
    n_un = int(((df.gov_funder == "unknown") & (df.gov_operator == "unknown")).sum())
    print("")
    print("rows with neither field settled: %d of %d" % (n_un, len(df)))
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inclusion", default=os.path.join(OUT, "inclusion_coded.csv"))
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "inclusion_coded.csv"))
    sys.exit(main(ap.parse_args()))
