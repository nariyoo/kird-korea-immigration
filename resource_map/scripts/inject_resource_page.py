# -*- coding: utf-8 -*-
"""Rewrite the resource page's inlined data from orgs.json.

h-resource.html carries its own copy of the list, as `const R_RES={...}` for the
summary and `R_RES.list=[...]` for the rows. The prose above it was rewritten by
hand; if the data underneath is not rewritten too, the page says 2,950 and shows
903, which is worse than either number alone.

This replaces only those two statements. It deliberately does not run
gen_rest_data.py, which regenerates fourteen other screens and would collide
with the design work happening in the same tree.

Run:  python scripts/v2/inject_resource_page.py
"""
from __future__ import annotations
import argparse
import collections
import io
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DASH = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard"))
REDESIGN = os.path.abspath(os.path.join(ROOT, "..", "09_design_mockups", "redesign"))

# The label a visitor reads. Keys are build_orgs unit_type values.
SVC_KO = {
    "korean": "한국어 교육", "interpret": "통역과 번역", "counsel": "생활 상담",
    "legal": "법률과 체류 상담", "labor": "노동 상담", "shelter": "보호와 쉼터",
    "medical": "의료", "job": "취업과 직업훈련", "child": "자녀 교육과 돌봄",
    "youth": "이주배경 청소년", "women": "이주여성",
    "settle": "정착과 사회통합 프로그램", "culture": "문화 교류",
    "community": "커뮤니티와 모임 공간", "welfare": "생계와 복지 연계",
    "refugee": "난민", "admin": "체류 행정 창구", "info": "정보 제공과 매체",
}

# Who the place is for. The rosters write this 259 different ways, including
# "이주민/이주노동자/다문화가정 (세부는 subcategory 참조)" and "고용허가제(E-9)·
# 방문취업(H-2) 외국인근로자 및 고용사업주", so the raw column made a facet with
# a 259-value vocabulary and a card that printed a bureaucrat's parenthesis.
# Twelve codes carry it; the raw wording is kept in orgs.json under "target".
POP_KO = {
    "marriage": "결혼이민자", "worker": "이주노동자", "refugee": "난민",
    "family": "다문화가족", "child": "이주배경 아동·학생",
    "youth": "이주배경 청소년", "women": "이주여성", "student": "유학생",
    "undocumented": "미등록 이주민", "diaspora": "동포·고려인",
    "naturalize": "영주·귀화 준비", "all": "체류 외국인 전반",
}

POP_ICON = {
    "marriage": "fa-ring", "worker": "fa-hard-hat", "refugee": "fa-tent",
    "family": "fa-house-user", "child": "fa-child-reaching",
    "youth": "fa-user-group", "women": "fa-venus", "student": "fa-graduation-cap",
    "undocumented": "fa-user-shield", "diaspora": "fa-globe",
    "naturalize": "fa-passport", "all": "fa-users",
}


# 누가 돈을 대고 누가 운영하는가. 한 지역이 국가가 직접 운영하는 관서로 덮여
# 있는 것과 민간 단체가 자기 돈으로 버티고 있는 것은 예산이 움직일 때 전혀 다른
# 일이 되는데, 지도에는 그 구분이 없었다. 코드는 code_governance.py 가 만든다.
GOV_KO = {
    "central/direct": "중앙정부 직영",
    "central/contracted": "중앙정부 위탁",
    "central/designated": "중앙정부 지정",
    "central_local/contracted": "중앙·지방 위탁",
    "central_local/direct": "중앙·지방 직영",
    "local/direct": "지자체 직영",
    "local/contracted": "지자체 위탁",
    "local/unknown": "지자체 (운영주체 확인 안 됨)",
    "private/self": "민간 자체",
    "religious/self": "종교기관 자체",
    "academic/self": "대학 자체",
}

GOV_ICON = {
    "중앙정부 직영": "fa-landmark",
    "중앙정부 위탁": "fa-file-signature",
    "중앙정부 지정": "fa-certificate",
    "중앙·지방 위탁": "fa-handshake",
    "중앙·지방 직영": "fa-landmark-dome",
    "지자체 직영": "fa-city",
    "지자체 위탁": "fa-file-contract",
    "지자체 (운영주체 확인 안 됨)": "fa-city",
    "민간 자체": "fa-people-group",
    "종교기관 자체": "fa-place-of-worship",
    "대학 자체": "fa-graduation-cap",
}


def gov_label(o):
    """The pair, as one label. A row whose funder is known and whose operator is
    not still says something worth showing, so it gets a label of its own rather
    than being folded into 확인 안 됨."""
    f = str(o.get("gov_funder", "")).strip()
    op = str(o.get("gov_operator", "")).strip()
    if not f or f == "unknown":
        return ""
    return GOV_KO.get(f + "/" + op, "")


# One icon per service. Font Awesome 6 is already loaded by the page. The icon
# carries the meaning at a glance on a phone, where a row of Korean labels reads
# as a block of text; the label stays because an icon alone is a guessing game.
SVC_ICON = {
    "korean": "fa-language",
    "interpret": "fa-comments",
    "counsel": "fa-comment-dots",
    "legal": "fa-scale-balanced",
    "labor": "fa-helmet-safety",
    "shelter": "fa-shield-heart",
    "medical": "fa-stethoscope",
    "job": "fa-briefcase",
    "child": "fa-children",
    "youth": "fa-user-group",
    "women": "fa-venus",
    "settle": "fa-passport",
    "culture": "fa-masks-theater",
    "community": "fa-people-roof",
    "welfare": "fa-hand-holding-heart",
    "refugee": "fa-tent",
    "admin": "fa-building-columns",
    "info": "fa-newspaper",
}

TYPE_KO = {
    "family_center": "가족센터",
    "resident_center": "외국인주민지원센터",
    "worker_center": "외국인근로자지원센터",
    "migrant_worker_center": "외국인근로자지원센터",
    "program_site": "사회통합·조기적응 프로그램 운영기관",
    "shelter": "폭력피해 이주여성 시설",
    "medical": "의료지원 기관",
    "legal": "법률과 인권 지원",
    "youth_edu": "이주배경청소년·다문화교육 기관",
    "school": "다문화교육 정책학교와 한국어학급",
    "community": "이주민 커뮤니티",
    "religious_site": "이주민 종교시설",
    "library": "다문화 도서관",
    "ngo": "이주민 지원 시민·종교 단체",
    "administrative": "출입국·외국인관서",
    "overseas_korean": "재외동포 지원기관",
    "seasonal_worker": "계절근로자 지원",
    "intl_student_center": "유학생 지원센터",
    "media": "이주민 매체",
    "research": "연구·정책 기관",
    "umbrella": "협의체와 연대체",
    "funder": "배분·모금 기관",
}


# 명부 파일 -> (화면에 쓸 이름, 출처 링크). 표에 올릴 것만 적는다.
ROSTER_KO = {
    "edu/edu_policy_school.csv":
        ("다문화교육 정책학교와 한국어학급",
         "https://www.data.go.kr/data/15090344/fileData.do"),
    "kiip/kiip_operating_institutions.csv":
        ("사회통합프로그램 운영기관",
         "https://www.moj.go.kr/bbs/moj/184/590427/artclView.do"),
    "ngo/npas_migrant_keyword_registry.csv":
        ("비영리민간단체 등록현황",
         "https://npas.mois.go.kr/nsbms/hmp/nfvnzBsisStat/nfvnzRegSituStat/asscInfoListM.do"),
    "family/korean_language_education_service.csv":
        ("한국어교육 운영기관", "https://www.data.go.kr"),
    "family/bilingual_coach_service.csv":
        ("이중언어코치 배치기관", "https://www.data.go.kr"),
    "family/multicultural_family_center.csv":
        ("전국 가족센터",
         "https://www.liveinkorea.kr/portal/KOR/centerIntro/centerList.do"),
    "family/translation_interpretation_service.csv":
        ("결혼이민자 통번역서비스 배치기관", "https://www.data.go.kr"),
    "kiip/early_adaptation_program_institutions.csv":
        ("조기적응프로그램 운영기관",
         "https://www.cppb.go.kr/bbs/moj/184/590428/artclView.do"),
    "misc/misc_media.csv":
        ("이주민 대상 정기간행물", "https://www.mcst.go.kr"),
    "health_youth/medical_designated_institutions.csv":
        ("외국인근로자 등 의료지원 사업시행 의료기관", "https://www.mohw.go.kr"),
    "local_gov/local_gov_foreign_resident_facilities.csv":
        ("지자체 외국인주민 지원시설", "https://www.data.go.kr"),
    "gov_labor/immigration_office_full_roster.csv":
        ("출입국·외국인관서",
         "https://www.immigration.go.kr/immigration/2057/subview.do"),
    "community/migrant_religious_site.csv":
        ("이주민 종교시설", "https://www.koreaislam.org"),
    "ngo/refugee_support_refugeeswelcome_members.csv":
        ("난민인권네트워크 회원단체", "https://refugeeswelcome.kr/members"),
    "ngo/religious_catholic_migrant_pastoral.csv":
        ("교구별 천주교 이주사목 기관", "https://directory.cbck.or.kr"),
    "women/mogef_violence_victim_migrant_women_counseling_centers.csv":
        ("폭력피해 이주여성 상담소",
         "https://www.mogef.go.kr/inc/fs_fsc_s003.do?mid=fsc300"),
}


def _roster_rows(orgs, top=12):
    import collections as _c
    n = _c.Counter()
    for o in orgs:
        for src in o.get("src", []):
            if src in ROSTER_KO:
                n[src] += 1
    return "".join(
        f'<tr><td><a href="{ROSTER_KO[k][1]}">{ROSTER_KO[k][0]}</a></td>'
        f'<td class="num">{v:,}</td></tr>'
        for k, v in n.most_common(top))


def scope_short(summary):
    """What belongs beside the list itself: the counts, one caveat, a link.

    Everything else about how the list was built is reference material and sits
    on the 지표와 범위 page. A visitor looking for a 가족센터 does not need the
    sampling frame in front of the search box."""
    ko = lambda x: f"{x:,}"
    return f"""  <h2>목록의 범위</h2>
  <p>정부 공표 통계가 아니며 목록에 없는 기관이 있을 수 있습니다. 전화가 적힌
  기관은 {ko(summary['tel'])}곳, 주소가 있는 기관은 {ko(summary['addr'])}곳,
  누리집이 확인된 기관은 {ko(summary['web'])}곳입니다. 누리집은 그 기관의 것임을
  확인한 것만 실었습니다. 빠진 기관이나 틀린 연락처는 알려 주시면 반영합니다.</p>
  <p>어느 명부에서 모았고 무엇이 빠져 있는지는
  <a href="h-notes.html#resource-scope">지표와 범위</a>에 적었습니다.</p>
"""


def scope_full(orgs, summary):
    """The reference version, for the 지표와 범위 page."""
    ko = lambda x: f"{x:,}"
    return f"""<section class="tool" id="resource-scope" aria-label="지원기관 목록의 범위">
  <h2>지원기관 목록</h2>
  <p>이민자를 지원하는 기관 {ko(summary['total'])}곳입니다. 전화가 적힌 기관은
  {ko(summary['tel'])}곳, 주소가 있는 기관은 {ko(summary['addr'])}곳, 누리집이
  확인된 기관은 {ko(summary['web'])}곳, SNS 계정이 확인된 기관은
  {ko(summary['socialAny'])}곳입니다. 정부 공표 통계가 아닙니다.</p>

  <h3>출처</h3>
  <p>마흔한 개 명부에서 모은 뒤 이름과 주소와 전화번호로 중복을 제거했습니다.
  기관 수가 많은 열두 곳입니다.</p>
  <table class="yb">
    <thead><tr><th>명부</th><th class="num">기관</th></tr></thead>
    <tbody>{_roster_rows(orgs)}</tbody>
  </table>
  <p>나머지는 시도교육청 다문화교육지원센터, 이주배경청소년 지원기관, 다문화
  도서관, 이주민 커뮤니티, 재외동포청 계열, 국세청 공익법인 공시에서 왔습니다.
  명부마다 전체가 몇 곳이고 그중 몇 곳을 받았는지는
  <a href="https://github.com/nariyoo/kird-korea-immigration">저장소</a>의
  대조표에 있습니다.</p>

  <h3>누리집 확인</h3>
  <p>기관마다 다섯 가지 검색을 돌리고 후보 페이지를 모두 열어, 그 기관의
  전화번호나 도로명주소가 기관 이름과 함께 적혀 있는지 확인한 것만 실었습니다.
  이름만 비슷한 페이지, 지도 서비스, 업체정보 조회 사이트, 명부 페이지는
  기관의 누리집이 아니므로 비웠습니다.</p>

  <h3>목록의 한계</h3>
  <ul class="limits">
    <li><b>폭력피해 이주여성 보호시설</b>. 전국 33개소(쉼터 28, 그룹홈 4,
        자활지원센터 1)가 운영되나 소재지가 법으로 공개되지 않습니다. 이름이
        확인된 곳만 지역 단위로 실었고 지도에는 없습니다. 지도에 없는 것과
        존재하지 않는 것은 다릅니다.</li>
    <li><b>밀도 계산에서 뺀 것</b>. 학교와 정기간행물은 목록에 있으나
        <a href="h-gap.html">지역별 기관 밀도</a> 계산에서는 뺐습니다. 학교를
        넣으면 학교가 많은 지역이 자원이 많은 지역으로 읽힙니다.</li>
    <li><b>유형 중복</b>. 한 기관이 두 유형에 해당하기도 하므로 유형별 수의 합은
        기관 수보다 큽니다.</li>
    <li><b>지자체 시설</b>. 전국 단일 명부가 없어 공개된 자료를 모은 것입니다.
        공공데이터를 많이 여는 지자체가 과대표집되어 있습니다.</li>
  </ul>
  <p class="src">자료: 위의 명부와 개별 확인. 수집 기준일은 2026년 8월 19일입니다.</p>
</section>
"""


def build(orgs, counts):
    lst, cat, sido, tgt, mini = [], collections.Counter(), collections.Counter(), \
        collections.Counter(), collections.Counter()
    svc = collections.Counter()
    pop = collections.Counter()
    gov = collections.Counter()
    web = ig = fb = tel = 0
    for o in orgs:
        label = TYPE_KO.get(o.get("type", ""), o.get("type", "") or "기타")
        # the page filters on f.c, a list, because one facility can be listed
        # under two programmes
        cats = [label]
        lst.append({
            "n": o.get("name", ""),
            "nf": (o.get("name_raw", "") if o.get("name_raw") != o.get("name")
                   else ""),
            "c": cats,
            "s": [SVC_KO[x] for x in o.get("svc", []) if x in SVC_KO],
            "sd": o.get("sido", ""), "sg": o.get("sigungu", ""),
            "a": o.get("addr", ""), "t": o.get("tel", ""),
            "w": o.get("web", ""), "ig": o.get("instagram", ""),
            "fb": o.get("facebook", ""), "m": o.get("ministry", ""),
            "p": [POP_KO[x] for x in o.get("pop", []) if x in POP_KO],
            "gv": gov_label(o),
            "g": "|".join(o.get("target", []) or []),
            "y": o.get("lat"), "x": o.get("lng"),
        })
        cat[label] += 1
        for x in o.get("svc", []):
            if x in SVC_KO:
                svc[SVC_KO[x]] += 1
        if o.get("sido"):
            sido[o["sido"]] += 1
        if o.get("ministry"):
            mini[o["ministry"]] += 1
        for x in o.get("pop", []):
            if x in POP_KO:
                pop[POP_KO[x]] += 1
        gl = gov_label(o)
        if gl:
            gov[gl] += 1
        for t in (o.get("target") or []):
            if t.strip():
                tgt[t.strip()] += 1
        web += 1 if o.get("web") else 0
        ig += 1 if o.get("instagram") else 0
        fb += 1 if o.get("facebook") else 0
        tel += 1 if o.get("tel") else 0
    # A row with no region sorted to the very top, so the first screen of the
    # list was twenty-eight organizations with no address and no district. The
    # ones a visitor can actually go to come first; the unplaced ones keep their
    # place in the list, at the end, where they read as a remainder rather than
    # as the answer.
    lst.sort(key=lambda d: (0 if d["sd"] else 1, d["sd"], d["sg"], d["n"]))

    # "placed" on this page means "drawn on the map", not "in the density
    # numerator". facility_counts.json holds the latter (1,620) and using it
    # here would tell a visitor that 1,330 organizations are missing from a map
    # that actually shows 2,920 of them.
    placed = sum(1 for o in orgs if o.get("lat") is not None
                 and o.get("lng") is not None)
    nsgg = len({(o.get("sido", ""), o.get("sigungu", "")) for o in orgs
                if o.get("sigungu")})
    top = sorted(((k.split("|")[1], k.split("|")[0], v["count"],
                   v["per_10k_foreign"]) for k, v in counts.items()),
                 key=lambda t: -t[2])[:20]
    summary = {
        "total": len(orgs), "placed": placed, "nSigungu": nsgg,
        "addr": sum(1 for o in orgs if o.get("addr")),
        "socialAny": sum(1 for o in orgs if any(
            o.get(k) for k in ("facebook", "instagram", "band", "naver_cafe",
                               "naver_blog", "youtube", "kakao"))),
        "noSigungu": sum(1 for o in orgs if not o.get("sigungu")),
        "unplaced": len(orgs) - placed,
        "cat": cat.most_common(), "svc": svc.most_common(),
        "svcIcon": {SVC_KO[k]: v for k, v in SVC_ICON.items() if k in SVC_KO},
        "sido": sido.most_common(),
        "pop": pop.most_common(),
        "gov": gov.most_common(),
        "govIcon": GOV_ICON,
        "popIcon": {POP_KO[k]: v for k, v in POP_ICON.items() if k in POP_KO},
        "target": tgt.most_common(14), "ministry": mini.most_common(),
        "web": web, "ig": ig, "fb": fb, "tel": tel, "top": top,
        "list": [],
    }
    return summary, lst


NLMED = "\n    "
NLSP = "\n    "
NLIND = "\n  "


def gap_block(orgs, counts):
    """The density figures on h-gap, recomputed from the current build.

    h-gap carried its own inline copy of the v1 numbers: 903 organizations, 892
    placed, 244 districts, written when the frame was a third of its present
    size. The page was generated once by a script in the redesign folder that
    reads a stale local `facility_counts.json` and the v1 `master.csv`, so it
    could not follow the pipeline. It is rebuilt here instead, from the same two
    files every other page on the site is built from.
    """
    idxp = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard", "data",
                                        "indices.json"))
    idx = json.load(io.open(idxp, encoding="utf-8"))["data"]["by_sigungu"]
    year = max(idx, key=int)
    pop = {(r["sido"], r["sigungu"]): (r.get("foreign_total") or 0)
           for r in idx[year]}

    rows = []
    for key, v in counts.items():
        sd, sg = key.split("|")
        rows.append({"sigungu": sg, "sido": sd, "count": v["count"],
                     "per10k": v["per_10k_foreign"], "foreign": pop.get((sd, sg))})
    have = {(r["sido"], r["sigungu"]) for r in rows}
    zero = [{"sigungu": sg, "sido": sd, "count": 0, "per10k": 0, "foreign": f}
            for (sd, sg), f in pop.items() if (sd, sg) not in have]
    zero.sort(key=lambda r: -(r["foreign"] or 0))

    # A district with a handful of registered foreign residents produces a
    # density that swings on one organization, so the ranked figures are
    # restricted to districts with at least 10,000. The map shows every district.
    big = sorted([r for r in rows if (r["foreign"] or 0) >= 10000],
                 key=lambda r: r["per10k"])
    per = sorted(r["per10k"] for r in rows if r["foreign"])
    dens = {f'{r["sido"]}|{r["sigungu"]}': r["per10k"] for r in rows if r["foreign"]}
    for r in zero:
        dens[f'{r["sido"]}|{r["sigungu"]}'] = 0
    vals = sorted(dens.values())
    brk = [round(vals[int(len(vals) * f)], 2) for f in (.2, .4, .6, .8)] if vals else []

    fac, forg = collections.Counter(), collections.Counter()
    for k, v in counts.items():
        fac[k.split("|")[0]] += v["count"]
    for (sd, _sg), f in pop.items():
        forg[sd] += f or 0
    sido = sorted(((sd, fac.get(sd, 0), forg[sd],
                    round(fac.get(sd, 0) / forg[sd] * 10000, 1) if forg[sd] else 0)
                   for sd in forg), key=lambda t: -t[3])

    return {"sido": [list(x) for x in sido], "year": int(year),
            "nCovered": len(rows), "nZero": len(zero),
            "dens": dens, "densBreaks": brk,
            "zero": zero[:20], "lowest": big[:20],
            "highest": list(reversed(big))[:10], "nBig": len(big),
            "median": round(per[len(per) // 2], 2) if per else 0,
            "totalFac": sum(r["count"] for r in rows)}


def write_gap(orgs, summary, counts, j, ko):
    """Rewrite h-gap's data statement and the sentences that quote it."""
    gap = gap_block(orgs, counts)
    ndist = len(gap["dens"])
    # organizations the density table cannot place, and why. The withheld
    # shelters are a separate and larger absence than a missing 구 in an address.
    noreg = sum(1 for o in orgs if not o.get("sigungu"))
    # Not every shelter-type row is a 쉼터. The type also holds the 이주여성
    # 상담소, which publish their address. The claim about withheld addresses
    # has to be made about the rows that actually withhold one.
    shelter = sum(1 for o in orgs if o.get("type") == "shelter")
    withheld = sum(1 for o in orgs if o.get("type") == "shelter"
                   and not str(o.get("addr", "")).strip())
    for p in (os.path.join(DASH, "h-gap.html"),
              os.path.join(REDESIGN, "h-gap.html")):
        if not os.path.exists(p):
            continue
        t = io.open(p, encoding="utf-8").read()
        t, n = re.subn(r"const R_GAP=\{.*?\};", "const R_GAP=" + j(gap) + ";",
                       t, count=1, flags=re.S)
        if not n:
            print(f"  FAILED to locate R_GAP in {os.path.basename(p)}")
            continue
        # h-gap kept a second, unused copy of the whole resource list
        t = re.sub(r"const R_RES=\{.*?\};\n?", "", t, count=1, flags=re.S)
        t = re.sub(r"\d[\d,]*개 시군구 값의 5분위",
                   f"{ko(ndist)}개 시군구 값의 5분위", t)
        t = re.sub(r"1만 명 이상인 \d[\d,]*개 시군구",
                   f"1만 명 이상인 {ko(gap['nBig'])}개 시군구", t)
        t = re.sub(r"그림 2와 같은 \d[\d,]*개 시군구",
                   f"그림 2와 같은 {ko(gap['nBig'])}개 시군구", t)
        t = re.sub(r"기관이 확인된 \d[\d,]*개 시군구 전체의 중앙값은 1만 명당 [\d.]+곳",
                   f"기관이 확인된 {ko(gap['nCovered'])}개 시군구 전체의 중앙값은 "
                   f"1만 명당 {round(gap['median'], 1)}곳", t)
        note = (
            f"지원기관 {ko(summary['total'])}곳 가운데 {ko(noreg)}곳은 주소에 "
            "시군구가 적혀 있지 않아 어느 지역인지 정하지 못했습니다. 임의로 "
            "배정하지 않았으므로 그만큼 해당 지역의 기관 수와 밀도는 실제보다 "
            "낮게 계산됩니다.</p>\n"
            f"  <p>여기에 더해 보호시설과 상담소 {ko(shelter)}곳 가운데 "
            f"{ko(withheld)}곳은 주소가 공개되어 있지 않습니다. 폭력 피해 이주여성 "
            "쉼터는 거주자의 안전 때문에 소재지를 공개하지 않기 때문입니다. "
            "지도에 없는 것은 "
            "그 기관이 없다는 뜻이 아니라 위치를 공개할 수 없다는 뜻이며, "
            "밀도에서도 빠집니다. 이 시설을 찾는 사람은 여성긴급전화 1366이나 "
            "다누리콜센터 1577-1366으로 연락하면 됩니다."
        )
        t = re.sub(r"지원기관 [\d,]+곳 가운데 [\d,]+곳은 주소에.*?계산됩니다\."
                   r"(?:\s*</p>\s*<p>여기에 더해.*?됩니다\.)*",
                   note, t, count=1, flags=re.S)
        # The four sentences above the map are the same numbers again. They sat
        # in the markup as 244 시군구 / 892곳 / 7.2 while the map underneath
        # drew the current build.
        lo = gap["lowest"][0] if gap["lowest"] else None
        hi = gap["highest"][0] if gap["highest"] else None
        li = [f'<li><b class="num">{ko(gap["nCovered"])}</b>개 시군구에 '
              f'<b class="num">{ko(gap["totalFac"])}</b>곳이 있고, 등록외국인 '
              f'1만 명당 기관 수의 중앙값은 '
              f'<b class="num">{round(gap["median"], 1)}</b>곳입니다.</li>',
              f'<li>기관이 한 곳도 확인되지 않은 시군구는 '
              f'<b class="num">{ko(gap["nZero"])}</b>곳입니다.</li>']
        if lo:
            li.append(
                f'<li>등록외국인이 1만 명 이상인 <b class="num">{ko(gap["nBig"])}</b>개 '
                f'시군구만 놓고 보면, 밀도가 가장 낮은 곳은 {lo["sigungu"]}로 '
                f'등록외국인 <b class="num">{ko(lo["foreign"] or 0)}</b>명에 '
                f'<b class="num">{ko(lo["count"])}</b>곳, 1만 명당 '
                f'<b class="num">{round(lo["per10k"], 1)}</b>곳입니다.</li>')
        if hi:
            li.append(f'<li>가장 높은 곳은 {hi["sigungu"]}로 1만 명당 '
                      f'<b class="num">{round(hi["per10k"], 1)}</b>곳입니다.</li>')
        joined = (NLSP).join(li)
        t = re.sub(r'(<ul class="sumlist">).*?(</ul>)',
                   lambda m: m.group(1) + NLSP + joined + NLIND + m.group(2),
                   t, count=1, flags=re.S)
        io.open(p, "w", encoding="utf-8").write(t)
        print(f"  rewrote {os.path.basename(p)}: {gap['totalFac']} placed in "
              f"{gap['nCovered']} 시군구, {gap['nZero']} with none")


def _en_sgg():
    """The romanized 시군구 names the rest of the English site already uses."""
    fp = os.path.join(REDESIGN, "i18n_labels.json")
    if not os.path.exists(fp):
        return {}
    b = json.load(io.open(fp, encoding="utf-8"))
    out = {}
    for g in ("sigungu", "sido", "region", "common"):
        out.update(b.get(g, {}))
    return out


def write_gap_en(orgs, summary, counts, ko):
    """The two sentences on h-gap that carry numbers, in English.

    build_en.py translates from a table keyed on the exact Korean string, and
    these sentences change every time the frame changes, so the table can never
    hold them: after a rebuild the English page showed the Korean sentence with
    the new numbers in it. They are written here instead, from the same values
    the Korean sentence is written from, and this runs after build_en.py so it
    is not overwritten.
    """
    gap = gap_block(orgs, counts)
    sgg = _en_sgg()
    en = lambda n: sgg.get(n, n)
    noreg = sum(1 for o in orgs if not o.get("sigungu"))
    shelter = sum(1 for o in orgs if o.get("type") == "shelter")
    withheld = sum(1 for o in orgs if o.get("type") == "shelter"
                   and not str(o.get("addr", "")).strip())
    lo = gap["lowest"][0] if gap["lowest"] else None
    hi = gap["highest"][0] if gap["highest"] else None
    li = ['<li><b class="num">{}</b> districts hold <b class="num">{}</b> '
          'organizations, and the median across them is <b class="num">{}</b> '
          'per 10,000 registered foreign residents.</li>'.format(
              ko(gap["nCovered"]), ko(gap["totalFac"]), round(gap["median"], 1)),
          '<li><b class="num">{}</b> districts have none on record.</li>'.format(
              ko(gap["nZero"]))]
    if lo:
        li.append('<li>Among the <b class="num">{}</b> districts with at least '
                  '10,000 registered foreign residents, the lowest density is '
                  '{}, with <b class="num">{}</b> for <b class="num">{}</b> '
                  'residents, or <b class="num">{}</b> per 10,000.</li>'.format(
                      ko(gap["nBig"]), en(lo["sigungu"]), ko(lo["count"]),
                      ko(lo["foreign"] or 0), round(lo["per10k"], 1)))
    if hi:
        li.append('<li>The highest is {}, at <b class="num">{}</b> per '
                  '10,000.</li>'.format(en(hi["sigungu"]), round(hi["per10k"], 1)))

    note = (
        "Of the {} organizations, {} carry no district in their address, so "
        "they could not be placed. None was assigned to a district by guess, "
        "which means the count and the density for that district read lower "
        "than they are.</p>" + NLIND +
        "  <p>Beyond that, {} of the {} shelters and counselling centers do "
        "not publish an address. Shelters for migrant women who have "
        "experienced violence withhold their location for the safety of the "
        "people living there. Absence from the map means the location cannot "
        "be published, not that the organization does not exist, and those "
        "organizations are absent from the density figures too. Anyone looking "
        "for one can call the Women's Emergency Line at 1366 or the Danuri "
        "Call Center at 1577-1366."
    ).format(ko(summary["total"]), ko(noreg), ko(withheld), ko(shelter))

    # the same numbers wherever else the English pages quote them
    med = sum(1 for o in orgs if o.get("type") == "medical")
    soc = summary["socialAny"]
    elsewhere = [
        ("h-medical-en.html",
         re.compile(r"의료지원으로 분류된 기관은 [\d,]+곳이고, 이민자를 지원하는"
                    r"\s*기관은 모두 [\d,]+곳입니다"),
         "{} organizations carry the health care tag, out of {} that support "
         "immigrants".format(ko(med), ko(summary["total"]))),
        ("h-resource-en.html",
         re.compile(r"이민자를 지원하는 기관 [\d,]+곳입니다\. 전화가 적힌 기관은 "
                    r"[\d,]+곳, 주소가 있는 기관은 [\d,]+곳, 누리집이 확인된 기관은 "
                    r"[\d,]+곳, SNS 계정이 확인된 기관은 [\d,]+곳입니다\."),
         "{} organizations that support immigrants. {} have a phone number on "
         "record, {} an address, {} a website confirmed as their own, and {} a "
         "social media account.".format(
             ko(summary["total"]), ko(summary["tel"]), ko(summary["addr"]),
             ko(summary["web"]), ko(soc))),
    ]
    for name, rx, rep in elsewhere:
        for base in (DASH, REDESIGN):
            fp = os.path.join(base, name)
            if not os.path.exists(fp):
                continue
            t = io.open(fp, encoding="utf-8").read()
            t, n = rx.subn(rep, t, count=1)
            if n:
                io.open(fp, "w", encoding="utf-8").write(t)
                print(f"  english counts -> {name} ({os.path.basename(base)})")

    for p in (os.path.join(DASH, "h-gap-en.html"),
              os.path.join(REDESIGN, "h-gap-en.html")):
        if not os.path.exists(p):
            continue
        t = io.open(p, encoding="utf-8").read()
        t, n1 = re.subn(r'(<ul class="sumlist">).*?(</ul>)',
                        lambda m: m.group(1) + NLSP + (NLSP).join(li)
                        + NLIND + m.group(2), t, count=1, flags=re.S)
        t, n2 = re.subn(r"지원기관 [\d,]+곳 가운데 [\d,]+곳은 주소에.*?"
                        r"계산됩니다\.(?:\s*</p>\s*<p>여기에 더해.*?됩니다\.)*",
                        note, t, flags=re.S)
        io.open(p, "w", encoding="utf-8").write(t)
        print(f"  english prose -> {os.path.basename(p)} "
              f"(summary {n1}, note {n2})")


def write_other_pages(orgs, summary, ko):
    """Sentences on OTHER pages that quote the resource-map counts.

    h-medical said "의료지원으로 분류된 기관은 49곳이고, 이민자를 지원하는
    기관은 모두 903곳입니다" long after the list had grown past 1,800. The
    generator for that page does not read orgs.json, so nothing corrected it and
    nothing reported it. A count that appears on a page this build does not own
    is still this build's number, so it is written from here.
    """
    med = sum(1 for o in orgs if o.get("type") == "medical")
    pairs = [
        (re.compile(r"의료지원으로 분류된 기관은 [\d,]+곳이고, "
                    r"이민자를 지원하는\s*기관은 모두 [\d,]+곳입니다"),
         "의료지원으로 분류된 기관은 " + ko(med) + "곳이고, 이민자를 지원하는"
         + NLMED + "기관은 모두 " + ko(summary["total"]) + "곳입니다"),
    ]
    for name in ("h-medical.html",):
        for base in (DASH, REDESIGN):
            fp = os.path.join(base, name)
            if not os.path.exists(fp):
                continue
            t = io.open(fp, encoding="utf-8").read()
            hits = 0
            for rx, rep in pairs:
                t, n = rx.subn(rep, t, count=1)
                hits += n
            if hits:
                io.open(fp, "w", encoding="utf-8").write(t)
            print(f"  counts on {name} ({os.path.basename(base)}): {hits} rewritten")


def main(a):
    payload = json.load(io.open(os.path.join(DASH, "orgs.json"), encoding="utf-8"))
    counts = json.load(io.open(os.path.join(REDESIGN, "facility_counts.json"),
                               encoding="utf-8"))
    summary, lst = build(payload["orgs"], counts)
    j = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))

    # The prose above the list quotes the same counts. Written by hand it drifts
    # the moment the frame changes again, and a page that says 2,950 while
    # showing 2,910 is worse than one that says neither. Rewrite the sentences
    # here, from the same numbers the data statements are built from.
    def ko(x):
        return f"{x:,}"
    soc = summary["socialAny"]
    prose = [
        (re.compile(r"(<div class=\"deck\">\s*<p>)이민자를 지원하는 기관.*?</p>", re.S),
         lambda m: m.group(1) + f"이민자를 지원하는 기관 {ko(summary['total'])}곳입니다. "
         f"전화가 적힌 기관이 {ko(summary['tel'])}곳, 기관의 것임을 확인한 누리집이 "
         f"있는 기관이 {ko(summary['web'])}곳입니다.</p>"),
        (re.compile(r"(<h2>목록의 범위</h2>\s*<p>)정부 공표 통계가 아니며.*?</p>", re.S),
         lambda m: m.group(1) + "정부 공표 통계가 아니며 목록에 없는 기관이 있을 수 "
         f"있습니다. 전화가 적힌 기관은 {ko(summary['tel'])}곳, 주소가 있는 기관은 "
         f"{ko(summary['addr'])}곳, 누리집이 확인된 기관은 {ko(summary['web'])}곳, "
         f"SNS 계정이 확인된 기관은 {ko(soc)}곳입니다. 각 기관이 공개한 값이므로 "
         "변경되었을 수 있습니다. 빠진 기관이나 틀린 연락처는 알려 주시면 반영합니다.</p>"),
    ]

    for p in (os.path.join(DASH, "h-resource.html"),
              os.path.join(REDESIGN, "h-resource.html")):
        if not os.path.exists(p):
            print("  (absent)", p)
            continue
        s = io.open(p, encoding="utf-8").read()
        s2, n1 = re.subn(r"const R_RES=\{.*?\};", "const R_RES=" + j(summary) + ";",
                         s, count=1, flags=re.S)
        s2, n2 = re.subn(r"R_RES\.list=\[.*?\];", "R_RES.list=" + j(lst) + ";",
                         s2, count=1, flags=re.S)
        n3 = 0
        for rx, rep in prose:
            s2, k = rx.subn(rep, s2, count=1)
            n3 += k
        # the whole 목록의 범위 section, replaced as one block
        scope_at = s2.find("  <h2>목록의 범위</h2>")
        bnd = (s2.find('</div>' + chr(10) + '<footer class="site">', scope_at)
               if scope_at >= 0 else -1)
        if scope_at >= 0 and bnd > scope_at:
            s2 = s2[:scope_at] + scope_short(summary) + s2[bnd:]
            n3 += 1
        # the count shown before any filter is applied
        s2 = re.sub(r'<b id="rcount">[^<]*</b>',
                    f'<b id="rcount">{ko(summary["total"])}곳</b>', s2, count=1)
        s2 = re.sub(r"주소로 시군구를 정하지 못한 [0-9,]+곳",
                    f"주소로 시군구를 정하지 못한 {ko(summary['noSigungu'])}곳", s2)
        if not (n1 and n2):
            print(f"  FAILED to locate the data statements in {p} "
                  f"(summary {n1}, list {n2}); left untouched")
            continue
        io.open(p, "w", encoding="utf-8").write(s2)
        print(f"  rewrote {os.path.basename(p)}: {len(lst)} rows, "
              f"{len(summary['cat'])} types")

    # How the list was built is reference material, so it lives on 지표와 범위
    # rather than above the search box. The section replaces itself on each run.
    for np in (os.path.join(DASH, "h-notes.html"),
               os.path.join(REDESIGN, "h-notes.html")):
        if not os.path.exists(np):
            continue
        t = io.open(np, encoding="utf-8").read()
        block = scope_full(payload["orgs"], summary)
        start = t.find('<section class="tool" id="resource-scope"')
        if start >= 0:
            end = t.find("</section>", start) + len("</section>") + 1
            t = t[:start] + block + t[end:]
        else:
            i = t.find('<footer class="site">')
            t = (t[:i] + block + "\n" + t[i:]) if i >= 0 else (t + block)
        io.open(np, "w", encoding="utf-8").write(t)
        print(f"  reference version -> {os.path.basename(np)}")

    if a.en:
        write_gap_en(payload["orgs"], summary, counts, ko)
        return 0
    write_gap(payload["orgs"], summary, counts, j, ko)
    write_other_pages(payload["orgs"], summary, ko)

    print(f"\ntotal {summary['total']} | placed {summary['placed']} "
          f"| unplaced {summary['unplaced']} | 시군구 {summary['nSigungu']}")
    print(f"tel {summary['tel']} | web {summary['web']} "
          f"| fb {summary['fb']} | ig {summary['ig']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", action="store_true",
                    help="patch only the number-bearing English prose, after "
                         "build_en.py has regenerated the -en pages")
    sys.exit(main(ap.parse_args()))
