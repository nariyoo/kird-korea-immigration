# -*- coding: utf-8 -*-
"""What each organization actually DOES, as service tags.

`unit_type` says what kind of body it is. That is what a researcher counts and
what a roster records, but it is not what a person needs. Somebody looking for
한국어 수업 does not know whether it happens at a 가족센터, a KIIP 운영기관, a
교회 or a 도서관, and on the current filter they have to guess the institution
type to find the service. The US dashboard this project borrows from filters on
services for exactly that reason.

Two layers, in this order.

  1. The programme a roster designates an organization to run IS a service.
     A KIIP 운영기관 teaches 한국어 and 한국사회이해; a 통번역서비스 배치기관
     provides 통번역; a 폭력피해 이주여성 상담소 provides 상담 and 보호. That
     is not an inference, it is what the designation means, so no model is asked.
  2. Everything else is read from the organization's own words: the roster's
     사업내용 column and the captured website text. A model tags only what the
     text says, and tags nothing when the text says nothing.

The tags are deliberately few. Twenty-six would be a taxonomy nobody filters on.

Run:  python scripts/v2/code_services.py
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import threading
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402
from webcache import PageStore  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
MODEL = os.environ.get("SERVICE_MODEL", "claude-sonnet-5")
CACHE = os.path.join(OUT, "services_cache.jsonl")

# The vocabulary. Korean label -> what counts as that service.
SERVICES = {
    "korean":     "한국어 교육",
    "interpret":  "통역과 번역",
    "counsel":    "생활 상담",
    "legal":      "법률과 체류 상담",
    "labor":      "노동 상담과 권리 구제",
    "shelter":    "보호와 쉼터",
    "medical":    "의료",
    "job":        "취업과 직업훈련",
    "child":      "자녀 교육과 돌봄",
    "youth":      "이주배경 청소년",
    "women":      "이주여성",
    "settle":     "정착과 사회통합 프로그램",
    "culture":    "문화 교류와 행사",
    "community":  "커뮤니티와 모임 공간",
    "welfare":    "생계와 복지 연계",
    "refugee":    "난민 신청과 정착",
    "admin":      "체류 행정 창구",
    "info":       "정보 제공과 매체",
}

# Layer 1. A designation IS a service. Keyed on source_roster patterns and on
# unit_type, applied in that order.
ROSTER_SERVICES = [
    (r"kiip/kiip_operating", ["settle", "korean"]),
    (r"kiip/early_adaptation", ["settle"]),
    (r"kiip/intl_marriage", ["settle"]),
    (r"family/translation_interpretation", ["interpret"]),
    (r"family/korean_language_education", ["korean"]),
    (r"family/bilingual_coach", ["child", "korean"]),
    (r"family/multicultural_family_center", ["korean", "counsel", "interpret",
                                             "child", "settle"]),
    (r"family/danuri_call_center", ["counsel", "interpret"]),
    (r"women/", ["women", "counsel", "shelter"]),
    (r"health_youth/medical", ["medical"]),
    (r"health_youth/youth", ["youth", "child"]),
    (r"health_youth/edu", ["child", "korean"]),
    (r"edu/edu_policy_school", ["child", "korean"]),
    (r"edu/edu_alternative_school", ["child", "korean"]),
    (r"edu/edu_intl_student", ["settle", "counsel"]),
    (r"gov_labor/.*immigration", ["admin"]),
    (r"gov_labor/", ["labor", "counsel"]),
    (r"ngo/refugee_support_refugeeswelcome", ["refugee", "legal"]),
    (r"ngo/legal_aid_anchors", ["legal"]),
    (r"community/migrant_religious_site", ["community", "culture"]),
    (r"community/multicultural_library", ["info", "culture"]),
    (r"community/migrant_community_org", ["community"]),
    (r"community/migrant_led_org", ["community", "labor"]),
    (r"misc/misc_media", ["info"]),
    (r"misc/misc_seasonal_worker", ["labor"]),
]
TYPE_SERVICES = {
    "administrative": ["admin"],
    "medical": ["medical"],
    "shelter": ["shelter", "counsel", "women"],
    "legal": ["legal"],
    "library": ["info", "culture"],
    "media": ["info"],
    "school": ["child", "korean"],
    "religious_site": ["community", "culture"],
    "intl_student_center": ["settle", "counsel"],
    "seasonal_worker": ["labor"],
}

# Layer 2 fallback before the model: words an organization uses about itself.
TEXT_RULES = [
    ("korean", r"한국어\s*(교육|교실|수업|강좌)|한글\s*(교실|학교)|TOPIK|토픽"),
    ("interpret", r"통역|번역|통번역|다국어\s*안내"),
    ("counsel", r"생활\s*상담|고충\s*상담|종합\s*상담|상담\s*지원"),
    ("legal", r"법률\s*상담|체류\s*상담|비자|출입국\s*민원|인권\s*상담|법률\s*지원"),
    ("labor", r"노동\s*상담|임금\s*체불|산업\s*재해|근로\s*조건|노동\s*권익"),
    ("shelter", r"쉼터|임시\s*보호|긴급\s*보호|보호\s*시설|자립\s*지원\s*시설"),
    ("medical", r"진료|의료\s*지원|건강\s*검진|무료\s*진료|병원\s*연계"),
    ("job", r"취업\s*지원|직업\s*훈련|일자리|구직|창업\s*지원"),
    ("child", r"자녀\s*교육|방문\s*교육|언어\s*발달|학습\s*지도|돌봄|보육"),
    ("youth", r"이주배경\s*청소년|중도입국\s*청소년|청소년\s*지원|레인보우\s*스쿨"),
    ("women", r"이주\s*여성|결혼\s*이주\s*여성|여성\s*폭력|가정\s*폭력"),
    ("settle", r"사회통합\s*프로그램|조기적응|정착\s*지원|한국\s*생활\s*적응"),
    ("culture", r"문화\s*교류|다문화\s*축제|문화\s*체험|문화\s*행사"),
    ("community", r"자조\s*모임|커뮤니티|동아리|공동체\s*공간|모국어\s*모임"),
    ("welfare", r"생계\s*지원|물품\s*지원|복지\s*연계|긴급\s*지원|후원"),
    ("refugee", r"난민\s*신청|난민\s*인정|인도적\s*체류|난민\s*지원"),
    ("info", r"소식지|신문|방송|정보\s*제공|다국어\s*자료"),
]

# ---------------------------------------------------------------- population
#
# The rosters wrote 259 different strings into target_population, from a bare
# 결혼이민자 to "이주민/이주노동자/다문화가정 (세부는 subcategory 참조)" and
# "고용허가제(E-9)·방문취업(H-2) 외국인근로자 및 고용사업주". Printed as-is they
# are unreadable on a card and unusable as a filter. These twelve are what a
# person would actually pick from; the raw string is kept beside them.
POPULATIONS = {
    "marriage":    "결혼이민자",
    "worker":      "이주노동자",
    "refugee":     "난민",
    "family":      "다문화가족",
    "child":       "이주배경 아동·학생",
    "youth":       "이주배경 청소년",
    "women":       "이주여성",
    "student":     "유학생",
    "undocumented": "미등록 이주민",
    "diaspora":    "동포·고려인",
    "naturalize":  "영주·귀화 준비",
    "all":         "체류 외국인 전반",
}

POP_RULES = [
    ("marriage", r"결혼\s*이(민|주)|국제결혼|혼인귀화"),
    ("worker", r"이주\s*노동|외국인\s*(근로자|노동자)|고용허가|E-?9|H-?2|"
               r"계절\s*근로|선원|고용\s*사업주"),
    ("refugee", r"난민|인도적\s*체류|무국적"),
    ("family", r"다문화\s*(가족|가정)"),
    ("child", r"이주배경\s*(자녀|아동|학생)|중도입국|다문화\s*(가정\s*)?학생|"
              r"영유아|아동|보호자|학부모"),
    ("youth", r"이주배경\s*청소년|중도입국\s*청소년|청소년"),
    ("women", r"이주\s*여성|결혼이주여성|폭력\s*피해\s*이주"),
    ("student", r"유학생|외국인\s*유학|D-?2|D-?4|어학연수"),
    ("undocumented", r"미등록|불법\s*체류|의료급여\s*미적용"),
    ("diaspora", r"동포|고려인|조선족|사할린|재외국민|귀국"),
    ("naturalize", r"영주\s*(신청|자격)|국적\s*취득|귀화|사회통합\s*프로그램\s*이수"),
    ("all", r"체류\s*외국인\s*전반|외국인\s*주민\s*전반|전체\s*외국인|이민자|"
            r"^이주민$|^외국인주민$|^외국인$"),
]


def populations(row):
    """Normalize the roster's own words about who the place is for."""
    blob = " ".join([str(row.get("target_population", "")),
                     str(row.get("name_ko", "")),
                     str(row.get("services_provided", ""))])
    got = []
    for key, rx in POP_RULES:
        if re.search(rx, blob, re.M):
            got.append(key)
    # 이민자 / 이주민 on their own mean everybody, and saying so beside six
    # specific groups adds nothing
    if "all" in got and len(got) > 1:
        got.remove("all")
    return sorted(set(got))


SYSTEM = """당신은 한국의 이주민 지원기관이 **무엇을 하는지**를 태그로 붙인다.
아래에 주어진 글에 실제로 적혀 있는 것만 붙인다. 기관 이름이나 유형에서 짐작하지 마라.

고를 수 있는 태그는 이것뿐이다.
korean(한국어 교육) interpret(통역·번역) counsel(생활 상담) legal(법률·체류 상담)
labor(노동 상담) shelter(보호·쉼터) medical(의료) job(취업·직업훈련)
child(자녀 교육·돌봄) youth(이주배경 청소년) women(이주여성) settle(정착·사회통합)
culture(문화 교류) community(커뮤니티·모임 공간) welfare(생계·복지 연계)
refugee(난민) admin(체류 행정 창구) info(정보 제공·매체)

규칙.
- 글에 그 사업이 문장으로 나와야 붙인다. 한 단어가 스쳐 지나가는 것은 근거가 아니다.
- **방 이름은 사업이 아니다.** "물리치료실, 교육실, 다목적 대강당" 같은 것은 건물에
  무슨 공간이 있는지를 적은 것이지 무엇을 해 준다는 말이 아니다. 그런 목록만 있으면
  아무 태그도 붙이지 마라. 실제로 사할린 영주귀국 동포 복지관(평균연령 78세)이
  "물리치료실"이라는 이유로 medical, "교육실"이라는 이유로 child 를 받은 적이 있다.
- **대상을 보라.** 노인이나 성인만을 대상으로 적은 기관에 child 나 youth 를 붙이지 마라.
- 하나도 확인되지 않으면 빈 배열을 돌려준다. 그것이 정답인 경우가 많다.
- 다섯 개를 넘기지 마라. 다 붙이면 필터로 쓸 수 없다.

JSON 하나만 출력한다.
{"services":["...","..."],"why":"한 문장, 글 안의 표현을 인용"}"""


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


def from_rosters(row):
    got = []
    rosters = str(row.get("source_roster") or "")
    for pat, svc in ROSTER_SERVICES:
        if re.search(pat, rosters):
            got += svc
    for s in TYPE_SERVICES.get(str(row.get("unit_type") or ""), []):
        got.append(s)
    return got


ROOM_ONLY = re.compile(r"(실|관|장|당)\s*[,、]|다목적|대강당|회의실|강의실|"
                       r"프로그램실|상담실\s*[,、]|교육실|물리치료실")


def from_text(text):
    got = []
    t = str(text or "")
    for key, rx in TEXT_RULES:
        if re.search(rx, t):
            got.append(key)
    return got


def guard(tags, row, text, protected=None):
    """Drop tags the surrounding text does not actually support.

    Two failures seen on real rows: a list of the rooms in a building read as a
    list of services, and a service for adults tagged as one for children.

    A tag that came from a DESIGNATION is never dropped. A hospital on the
    보건복지부 의료지원 roster provides medical care whether or not its home page
    happens to use the word 진료, and trimming it here would undo the one layer
    that needs no evidence."""
    protected = set(protected or [])
    t = str(text or "")
    tgt = str(row.get("target_population", "")) + " " + str(row.get("name_ko", ""))
    out = list(tags)
    if "medical" in out and "medical" not in protected and not re.search(
            r"진료|치료\s*(지원|서비스)|의료비|건강\s*검진|병원\s*(연계|동행)|"
            r"의료\s*지원|간호|약제", t):
        out.remove("medical")
    if not re.search(r"자녀|아동|어린이|청소년|학생|보육|유아", t + tgt):
        out = [x for x in out if x in protected or x not in ("child", "youth")]
    if re.search(r"영주귀국|고령|노인|어르신", tgt) and not re.search(
            r"자녀|아동|청소년", t):
        out = [x for x in out if x in protected or x not in ("child", "youth")]
    return out


def ask(row, text):
    global CLI
    k = f"{row.get('facility_id','')}|{MODEL}|v2|{len(text)}"
    if k in _cache:
        return _cache[k]
    if CLI is None:
        import anthropic
        CLI = anthropic.Anthropic(
            api_key=(os.environ.get("ANTHROPIC_API_KEY")
                     or os.environ.get("ANTHROPIC_API_KEY_BATCH")))
    v = {"services": [], "why": "api error"}
    prompt = (f"기관명: {row.get('name_ko','')}\n"
              f"유형: {row.get('unit_type','')}\n"
              f"명부가 적은 사업: {row.get('services_provided','')}\n"
              f"명부가 적은 대상: {row.get('target_population','')}\n\n"
              f"## 기관이 자기 사업을 적은 글\n{text[:3000]}")
    for _ in range(3):
        try:
            m = CLI.messages.create(model=MODEL, max_tokens=300, system=SYSTEM,
                                    messages=[{"role": "user", "content": prompt}])
            t = "".join(b.text for b in m.content if b.type == "text").strip()
            v = json.loads(t[t.find("{"): t.rfind("}") + 1])
            break
        except Exception as e:
            v = {"services": [], "why": type(e).__name__}
    with _lock:
        _cache[k] = v
        with open(CACHE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False) + "\n")
    return v


def run(a):
    df = pd.read_csv(a.inclusion, dtype=str).fillna("")
    web = {}
    if os.path.exists(a.websites):
        w = pd.read_csv(a.websites, dtype=str).fillna("")
        col = "final_website" if "final_website" in w.columns else "url"
        web = {r["facility_id"]: r[col] for _, r in w.iterrows()
               if str(r.get(col, "")).strip()}
    s1 = PageStore(os.path.join(OUT, "pages_candidates.jsonl"))
    s2 = PageStore(os.path.join(OUT, "pages_current.jsonl"))

    src = collections.Counter()
    rows, todo = [], []
    for i, r in df.iterrows():
        base = from_rosters(r)
        u = web.get(r["facility_id"], "")
        page = (s1.get(u) or s2.get(u) or {}) if u else {}
        txt = page.get("text", "") if page.get("state") == "ok" else ""
        blob = " ".join([str(r.get("services_provided", "")),
                         str(r.get("target_population", "")),
                         str(r.get("notes", "")), txt[:6000]])
        hard = set(from_rosters(r))
        base += from_text(blob)
        rows.append(sorted(set(guard(base, r, blob, hard))))
        # ask the model only where the deterministic layers found little and
        # there is text for it to read
        if len(set(base)) < 2 and len(blob.strip()) > 120:
            todo.append((i, blob))
    print(f"{len(df)} rows | tagged by roster or by their own words "
          f"{sum(1 for x in rows if x)} | sent to the model {len(todo)}")

    got = {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(ask, df.loc[i].to_dict(), b): i for i, b in todo}
        done = 0
        for fu in as_completed(futs):
            i = futs[fu]
            got[i] = fu.result()
            done += 1
            if done % 100 == 0:
                print(f"  tagged {done}/{len(todo)}", flush=True)
    for i, v in got.items():
        extra = [x for x in (v.get("services") or []) if x in SERVICES]
        merged_tags = set(rows[i]) | set(extra)
        blob = dict(todo).get(i, "")
        rows[i] = sorted(set(guard(sorted(merged_tags), df.loc[i], blob,
                                   set(from_rosters(df.loc[i])))))

    df["services_tag"] = ["|".join(x) for x in rows]
    df["n_services"] = [len(x) for x in rows]
    pops = [populations(r) for _, r in df.iterrows()]
    df["pop_tag"] = ["|".join(x) for x in pops]
    df.to_csv(a.out, index=False, encoding="utf-8-sig")

    c = collections.Counter(x for r in rows for x in r)
    print("\n=== service tags ===")
    for k, v in c.most_common():
        print(f"  {v:5d}  {k:10s} {SERVICES[k]}")
    print(f"\nrows with no tag at all: {sum(1 for x in rows if not x)}")
    print(f"median tags per row: {sorted(len(x) for x in rows)[len(rows)//2]}")
    cp = collections.Counter(x for r in pops for x in r)
    print("")
    print("=== population tags ===")
    for k, v in cp.most_common():
        print(f"  {v:5d}  {k:13s} {POPULATIONS[k]}")
    raw = df.target_population.astype(str).str.strip()
    nblank = sum(1 for x in pops if not x)
    print("")
    print(f"rows with no population tag: {nblank}")
    print("distinct raw target_population strings folded: "
          f"{raw[raw != ''].nunique()}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inclusion", default=os.path.join(OUT, "inclusion_coded.csv"))
    ap.add_argument("--websites", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--out", default=os.path.join(OUT, "inclusion_coded.csv"))
    ap.add_argument("--workers", type=int, default=10)
    sys.exit(run(ap.parse_args()))
