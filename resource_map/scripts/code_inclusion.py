# -*- coding: utf-8 -*-
"""Apply docs/INCLUSION_CRITERIA.md to every row of the frame.

This is Nari's question 2: is what came INTO the frame supposed to be there.
v1 had no answer because it had no criteria; rows arrived by being on some
roster and nothing recorded why that made them a resource.

Two layers, in this order and no other:

  1. Deterministic. A row that is on an authoritative roster IN THAT CAPACITY
     is included on the roster's authority (`incl_basis=roster`) and its type
     comes from which roster it is. No model is asked, because the roster is
     better evidence than a model reading a name.

  2. Model, on evidence, for the rest. The rows that are left are the ones a
     keyword search put in the frame: NPAS registrations matching 이주 / 외국인
     / 다문화, curated additions, community organizations. Those get coded from
     the organization's OWN captured website text where there is one, and are
     marked `name_only` and sent to review where there is not.

The rule that keeps this honest: a name is never sufficient. An organization
called 다문화사랑회 that publishes nothing about serving migrants is a
`review` row, not an included one (criteria rule 11).

Run:  python scripts/v2/code_inclusion.py
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
from webcache import PageStore  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
MODEL = os.environ.get("INCLUSION_MODEL", "claude-sonnet-5")
CACHE = os.path.join(OUT, "inclusion_cache.jsonl")

# ---------------------------------------------------------------- layer 1

# (pattern on source_roster, serves, unit_type). Matched in order.
ROSTER_RULES = [
    (r"women/", "direct", "shelter"),
    (r"kiip/kiip_operating", "direct", "program_site"),
    (r"kiip/early_adaptation", "direct", "program_site"),
    (r"kiip/intl_marriage", "direct", "program_site"),
    (r"family/multicultural_family_center", "direct", "family_center"),
    (r"family/danuri", "direct", "resident_center"),
    (r"family/(translation|bilingual|korean_language)", "direct", "family_center"),
    # The refugee network's member list and the Buddhist migrant-support
    # association's member list are rosters OF migrant-support organizations:
    # membership is the capacity claim, so the roster settles it. The Catholic
    # directory is not in this class and is deliberately absent here, because
    # its migrant relevance came from a keyword match on the name, which rule 11
    # says is never sufficient on its own.
    (r"ngo/refugee_support_refugeeswelcome", "direct", "ngo"),
    (r"ngo/religious_buddhist_mahayu", "direct", "ngo"),
    (r"ngo/legal_aid_anchors", "direct", "legal"),
    (r"gov_labor/.*immigration", "direct", "administrative"),
    (r"gov_labor/", "direct", "worker_center"),
    (r"local_gov/", "direct", "resident_center"),
    (r"health_youth/medical", "direct", "medical"),
    (r"health_youth/youth", "direct", "youth_edu"),
    (r"health_youth/edu", "direct", "youth_edu"),
    # A school designated to run 다문화교육 or a 한국어학급 is a real resource for
    # a migrant-background child, and the designation roster says so. It gets its
    # own unit_type because 1,054 schools would otherwise swamp both the map and
    # the per-10,000-residents figure, which is meant to count places an adult
    # can walk into (see build_orgs.DENSITY_TYPES).
    (r"edu/edu_policy_school", "direct", "school"),
    (r"edu/edu_alternative_school", "direct", "school"),
    (r"edu/edu_intl_student", "direct", "intl_student_center"),
    (r"misc/misc_overseas_korean", "direct", "overseas_korean"),
    (r"misc/misc_seasonal_worker", "direct", "seasonal_worker"),
    (r"misc/misc_intl_org", "indirect", "umbrella"),
    (r"misc/misc_council", "indirect", "umbrella"),
    # A registered periodical is not a place anyone goes. It stays in the list
    # because a multilingual newspaper is part of the information environment,
    # but it is `indirect` and never in the density numerator.
    (r"misc/misc_media", "indirect", "media"),
    (r"community/migrant_religious_site", "direct", "religious_site"),
    (r"community/migrant_community_org", "direct", "community"),
    (r"community/migrant_led_org", "direct", "community"),
    (r"community/multicultural_library", "direct", "library"),
]

# v1 rows carry no roster path, so their category plus the data_source string
# is what says in what capacity they were listed.
V1_CATEGORY = {
    "multicultural_family_center": ("direct", "family_center"),
    "social_integration_program": ("direct", "program_site"),
    "immigration_office": ("direct", "administrative"),
    "medical_support_facility": ("direct", "medical"),
    "foreign_resident_center": ("direct", "resident_center"),
    "foreign_worker_center": ("direct", "worker_center"),
    "violence_victim_shelter": ("direct", "shelter"),
    "migrant_youth_center": ("direct", "youth_edu"),
    "research_institute": ("indirect", "research"),
    "legal_aid": ("direct", "legal"),
    "refugee_support": ("direct", "ngo"),
}
V1_SOURCE = [
    (r"socinet\.go\.kr", "direct", "program_site"),
    (r"다문화교육지원센터", "direct", "youth_edu"),
    (r"mogef\.go\.kr|성평등가족부 시설찾기", "direct", "shelter"),
    (r"refugeeswelcome\.kr", "direct", "ngo"),
    (r"liveinkorea", "direct", "family_center"),
    (r"immigration\.go\.kr", "direct", "administrative"),
]

# Rule 12: migrant-adjacent but not support. Rule 13: defector-only.
EXCLUDE_NAME = re.compile(
    r"(유학원|어학원|인력\s*송출|송출\s*업체|국제결혼\s*중개|결혼중개업|"
    r"비자\s*대행|행정사\s*사무소|이민\s*컨설팅|유학\s*컨설팅|"
    r"인력\s*파견|헤드헌팅|무역|상사\b|주식회사|㈜)")
DEFECTOR = re.compile(r"(북한이탈|탈북|하나원|하나센터|새터민)")


def layer1(row):
    name = str(row.get("name_ko") or "")
    if DEFECTOR.search(name):
        return "no", "", "rule13_defector", "이름이 북한이탈주민 전용 기관을 가리킨다"
    if EXCLUDE_NAME.search(name):
        return "no", "", "rule12_not_support", "영리 알선·중개·교육업으로 보인다"
    rosters = str(row.get("source_roster") or "")
    for pat, serves, ut in ROSTER_RULES:
        if re.search(pat, rosters):
            basis = ("umbrella_member" if pat.startswith("ngo/") else "roster")
            return serves, ut, basis, f"명부 {pat} 에 그 자격으로 실려 있다"
    if "v1/master_all.csv" in rosters:
        src = str(row.get("source_url") or "")
        for pat, serves, ut in V1_SOURCE:
            if re.search(pat, src):
                return serves, ut, "roster", f"v1 출처 {pat}"
        cat = str(row.get("category") or "")
        if cat in V1_CATEGORY:
            serves, ut = V1_CATEGORY[cat]
            return serves, ut, "roster", f"v1 카테고리 {cat}"
    return None, None, None, None


# ---------------------------------------------------------------- layer 2

SYSTEM = """당신은 한국의 이주민 지원 자원지도에 들어갈 기관인지 판정한다.
근거는 아래에 주어진 것뿐이다. 기억이나 추측으로 채우지 마라.

`serves` 를 셋 중 하나로 고른다.

- `direct`: 이주민·다문화가족·난민·외국인주민이 직접 찾아가 상담, 통역, 한국어교육,
  법률지원, 의료, 보호(쉼터), 돌봄, 취업지원, 정착지원 중 무언가를 받는 곳
- `indirect`: 이주민을 위해 존재하지만 이주민이 직접 이용하지 않는 곳
  (연구소, 정책기관, 배분재단, 회원단체를 조직만 하는 협의체 본부, 종사자 양성기관)
- `no`: 이주민 지원기관이 아니다. 이름에 이주·외국인·다문화가 들어갈 뿐 근거가 없거나,
  인력송출·유학원·국제결혼중개·비자대행 같은 영리 알선업이거나,
  북한이탈주민 전용 기관이다

`unit_type` 을 하나 고른다: family_center, resident_center, worker_center,
program_site, shelter, medical, legal, youth_edu, community, religious_site,
ngo, administrative, research, umbrella, funder, school, library,
overseas_korean, seasonal_worker, intl_student_center, media

**핵심 규칙: 이름만으로 `direct` 를 주지 마라.** 아래 증거 안에 이주민 대상 사업이
문장으로 나와야 한다. 증거가 기관명과 주소뿐이면 `serves` 는 당신이 판단할 수 없는
것이고, 그때는 `evidence_enough` 를 false 로 놓아라. 그 행은 사람이 본다.

**다만 웹사이트만 증거가 아니다.** 홈페이지가 없는 작은 단체가 많다. 그 기관이 운영하는
SNS 계정, 그 기관을 이름으로 지목하는 최근 기사나 지자체 공고에 이주민 대상 사업이
적혀 있으면 그것도 충분한 증거다. 홈페이지가 없다는 이유만으로 `evidence_enough` 를
false 로 놓지 마라.

JSON 하나만 출력한다.
{"serves":"...","unit_type":"...","evidence_enough":true|false,"why":"한 문장, 증거 안의 표현을 인용"}"""


def build_evidence(row, page, extra=None):
    parts = [
        f"기관명: {row.get('name_ko','')}",
        f"명부상 분류: {row.get('category','')} / {row.get('subcategory','')}",
        f"소관: {row.get('governing_ministry','')}",
        f"운영주체: {row.get('operator_type','')} {row.get('operator_name','')}",
        f"소재: {row.get('sido','')} {row.get('sigungu','')} {row.get('road_address','')}",
        f"전화: {row.get('phone','')}",
        f"명부가 적은 대상: {row.get('target_population','')}",
        f"명부가 적은 사업: {row.get('services_provided','')}",
        f"비고: {row.get('notes','')}",
        f"수집 명부: {row.get('source_roster','')}",
    ]
    txt = (page or {}).get("text", "")
    if (page or {}).get("state") == "ok" and txt:
        parts.append("\n## 기관 자신의 웹사이트 본문 (앞부분)\n" + txt[:3000])
    else:
        parts.append("\n## 기관 자신의 웹사이트 본문\n(확보하지 못함)")

    # A website is one kind of evidence, not the only kind. A small organization
    # that never built one still runs a Facebook page and still gets a line in
    # the local paper when it opens a Korean class. Judging it on website text
    # alone marks a real 이주민센터 unverifiable and drops it, which is a false
    # negative wearing the clothes of rigour. So the accounts it runs and the
    # pages that name it go in front of the coder too, each labelled for what it
    # is, and never as a website.
    extra = extra or {}
    soc = [f"{k}: {v}" for k, v in (extra.get("socials") or {}).items() if v]
    if soc:
        parts.append("\n## 이 기관이 운영하는 SNS 계정\n" + "\n".join(soc))
    traces = extra.get("traces") or []
    if traces:
        lines = []
        for t in traces[:4]:
            yr = f"({t.get('year')})" if t.get("year") else ""
            lines.append(f"- [{t.get('kind','')}]{yr} {t.get('title','')}\n"
                         f"  {t.get('snippet','')}\n  {t.get('url','')}")
        parts.append("\n## 이 기관을 이름으로 지목하는 최근 페이지\n"
                     + "\n".join(lines))
    if not soc and not traces and (page or {}).get("state") != "ok":
        parts.append("\n## 그 밖의 흔적\n(웹사이트도 SNS도 기사도 찾지 못했다)")
    return "\n".join(parts)


_lock = threading.Lock()
_cache = {}
if os.path.exists(CACHE):
    with open(CACHE, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
                _cache[r["k"]] = r["v"]
            except Exception:
                pass

CLI = None


def _client():
    import anthropic
    return anthropic.Anthropic(
        api_key=(os.environ.get("ANTHROPIC_API_KEY")
                 or os.environ.get("ANTHROPIC_API_KEY_BATCH")))


def code_one(row, page, extra=None):
    global CLI
    nx = (len((extra or {}).get("traces") or [])
          + len((extra or {}).get("socials") or {}))
    k = (f"{row.get('facility_id','')}|{MODEL}|"
         f"{'web' if (page or {}).get('state')=='ok' else 'noweb'}|x{nx}")
    if k in _cache:
        return _cache[k]
    if CLI is None:
        CLI = _client()
    v = {"serves": "", "unit_type": "", "evidence_enough": False,
         "why": "api error"}
    for _ in range(3):
        try:
            m = CLI.messages.create(
                model=MODEL, max_tokens=400, system=SYSTEM,
                messages=[{"role": "user",
                           "content": build_evidence(row, page, extra)}])
            t = "".join(b.text for b in m.content if b.type == "text").strip()
            v = json.loads(t[t.find("{"): t.rfind("}") + 1])
            break
        except Exception as e:
            v = {"serves": "", "unit_type": "", "evidence_enough": False,
                 "why": type(e).__name__}
    with _lock:
        _cache[k] = v
        with open(CACHE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")
    return v


# ---------------------------------------------------------------- driver

def apply_manual_inclusion(df):
    """Judgements a person made on the rows the model could not settle.

    A row reaches `review` because the evidence in front of the model was thin,
    which is a statement about what was fetched and not about whether the place
    exists. A person who then searched and found the district press release has
    better evidence than the model had, so this overrides the model, and it runs
    last so nothing after it can quietly undo the override.

    Keyed on facility_id when the sheet carries one and on the normalized name
    plus 시도 otherwise, because a facility_id is a hash of the name and the
    address and shifts if either is edited between the sheet and the build.
    """
    ledger = os.path.join(ROOT, "data", "raw", "v2", "fixup",
                          "manual_inclusion.csv")
    if not os.path.exists(ledger):
        print("no manual_inclusion.csv; run collect_fixups.py")
        return df
    import build_frame as bf
    led = pd.read_csv(ledger, dtype=str, encoding="utf-8-sig").fillna("")
    by_id = {r["facility_id"]: r for _, r in led.iterrows() if r["facility_id"]}
    by_key = {(r["name_key"], r["sido"]): r for _, r in led.iterrows()}
    applied, hit = 0, set()
    for i, row in df.iterrows():
        e = by_id.get(str(row.get("facility_id", "")))
        if e is None:
            e = by_key.get((bf.namekey(row.get("name_ko", "")),
                            str(row.get("sido", "")).strip()))
        if e is None:
            continue
        hit.add(str(e.get("facility_id", "")) or e.get("name_key", ""))
        df.at[i, "serves"] = e["serves"]
        df.at[i, "incl_basis"] = "person_verified"
        df.at[i, "incl_why"] = str(e.get("evidence", ""))[:400]
        applied += 1
    unmatched = [r.get("name_ko", "") for _, r in led.iterrows()
                 if (str(r.get("facility_id", "")) or r.get("name_key", ""))
                 not in hit]
    print(f"person-verified inclusion: {applied} applied, {len(led)} in the "
          f"ledger, {len(unmatched)} matched no row")
    for m in unmatched[:8]:
        print(f"    unmatched: {m}")
    return df


def run(frame, websites, out_csv, workers=6):
    df = pd.read_csv(frame, dtype=str).fillna("")
    web = {}
    if websites and os.path.exists(websites):
        w = pd.read_csv(websites, dtype=str).fillna("")
        col = "final_website" if "final_website" in w.columns else "url"
        web = {r["facility_id"]: r[col] for _, r in w.iterrows()
               if r.get(col, "").strip()}
    for _, r in df.iterrows():
        web.setdefault(r["facility_id"], r.get("website", ""))

    s1 = PageStore(os.path.join(OUT, "pages_candidates.jsonl"))
    s2 = PageStore(os.path.join(OUT, "pages_current.jsonl"))

    extra = {}
    sp = os.path.join(OUT, "socials_v2.csv")
    if os.path.exists(sp):
        sd = pd.read_csv(sp, dtype=str).fillna("")
        plats = [c for c in sd.columns
                 if c not in ("facility_id", "name_ko", "website", "src")]
        for _, x in sd.iterrows():
            got = {p: x[p] for p in plats if str(x[p]).strip()}
            if got:
                extra.setdefault(x["facility_id"], {})["socials"] = got
    ep = os.path.join(OUT, "existence_evidence.csv")
    if os.path.exists(ep):
        ed = pd.read_csv(ep, dtype=str).fillna("")
        for _, x in ed.iterrows():
            try:
                tr = json.loads(x.get("traces") or "[]")
            except Exception:
                tr = []
            if tr:
                extra.setdefault(x["facility_id"], {})["traces"] = tr
    print(f"extra evidence available for {len(extra)} rows "
          f"(social accounts and pages that name them)")

    df["serves"] = ""
    df["unit_type"] = ""
    df["incl_basis"] = ""
    df["incl_why"] = ""

    todo = []
    for i, r in df.iterrows():
        serves, ut, basis, why = layer1(r)
        if serves is not None:
            df.at[i, "serves"] = serves
            df.at[i, "unit_type"] = ut or ""
            df.at[i, "incl_basis"] = basis
            df.at[i, "incl_why"] = why
        else:
            todo.append(i)
    print(f"frame {len(df)} | settled by roster or rule: {len(df)-len(todo)} "
          f"| sent to evidence coding: {len(todo)}")

    res = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for i in todo:
            r = df.loc[i].to_dict()
            u = web.get(r["facility_id"], "")
            page = (s1.get(u) or s2.get(u) or {}) if u else {}
            futs[ex.submit(code_one, r, page, extra.get(r["facility_id"]))] = i
        done = 0
        for fu in as_completed(futs):
            res[futs[fu]] = fu.result()
            done += 1
            if done % 50 == 0:
                print(f"  coded {done}/{len(todo)}", flush=True)

    for i, v in res.items():
        enough = bool(v.get("evidence_enough"))
        df.at[i, "serves"] = v.get("serves", "") if enough else "review"
        df.at[i, "unit_type"] = v.get("unit_type", "")
        df.at[i, "incl_basis"] = "own_site" if enough else "name_only"
        df.at[i, "incl_why"] = v.get("why", "")

    df = apply_manual_inclusion(df)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    rev = df[(df.serves == "review") | (df.serves == "no")]
    rev.to_csv(os.path.join(OUT, "review_inclusion.csv"), index=False,
               encoding="utf-8-sig")

    print("\n=== serves ===")
    print(df.serves.value_counts().to_string())
    print("\n=== incl_basis ===")
    print(df.incl_basis.value_counts().to_string())
    print("\n=== unit_type (serves=direct only) ===")
    print(df[df.serves == "direct"].unit_type.value_counts().to_string())
    print(f"\nwrote {out_csv}; review sheet {len(rev)} rows")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2.csv"))
    ap.add_argument("--websites", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "inclusion_coded.csv"))
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    run(a.frame, a.websites, a.out, a.workers)
