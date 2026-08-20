# -*- coding: utf-8 -*-
"""Build orgs.json, the single published artefact of the resource map.

Every field carries its provenance beside it, because the whole reason v1 went
wrong is that a value and the reason to believe it were stored in different
places, or the reason was not stored at all:

  web / web_tier / web_src   the site, how strongly it was tied to this
                             organization, and by what route
  fb / ig / ... / social_src whether the account was read off the organization's
                             own site or found by searching
  serves / unit_type /
  incl_basis                 why this row is in the list at all
  geo_how                    how precise the pin is
  src                        every roster that asserted this row

Two rules the builder enforces, both of them census scars:

  * Replacing a website invalidates everything derived from the old one (#14).
    So a social account is only carried when the host it was read from is still
    the host on file.
  * A count is not verification (#1-#6). The build prints a per-field census
    and refuses to write when a field that should be near-universal collapses.

Run:  python scripts/v2/build_orgs.py
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import collections
import datetime as dt
import re
import urllib.parse as up

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "data", "processed", "v2")
DASH = os.path.abspath(os.path.join(ROOT, "..", "05_dashboard"))

SOCIALS = ["facebook", "instagram", "youtube", "band", "naver_cafe",
           "naver_blog", "kakao"]

# unit types that count toward the per-10,000-residents density figure.
# docs/INCLUSION_CRITERIA.md section 3 is the authority for this list.
DENSITY_TYPES = {"family_center", "resident_center", "worker_center",
                 "program_site", "shelter", "medical", "legal", "youth_edu",
                 "community", "religious_site", "ngo", "overseas_korean",
                 "seasonal_worker", "library", "intl_student_center"}
# Deliberately OUT of the numerator, with the reason:
#   school            1,054 designated 다문화교육 정책학교. Real resources for a
#                     migrant-background child, but counting them turns the
#                     indicator into a count of schools; a district with many
#                     schools would read as well served for adults too.
#   media             a registered periodical is not a place anyone goes.
#   research/umbrella/funder/administrative  criteria section 3.


# A legal form is how a body is registered, not what anyone calls it. Leaving
# it on the front of the name pushes 145 organizations under 사 and 재 in an
# alphabetical list and wastes the first characters of every card. Strip it for
# display and keep the registered string in name_raw.
_LEGAL_PREFIX = re.compile(
    r"^\s*(?:[（(]\s*[사재복학의종주유비]\s*[)）]|[사재복학의종주유비]\s*[)）]|"
    r"사단법인|재단법인|사회복지법인|학교법인|의료법인|종교법인|특수법인|"
    r"비영리민간단체|공익법인|법인)\s*")


def display_name(n):
    s = str(n or "").strip()
    out = _LEGAL_PREFIX.sub("", s, count=1).strip()
    # never strip a name down to nothing, and never below two characters
    return out if len(out) >= 2 else s


def host(u):
    try:
        h = up.urlparse(str(u or "")).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def load(path, key="facility_id"):
    if not path or not os.path.exists(path):
        print(f"  (absent) {os.path.basename(path or '')}")
        return {}
    d = pd.read_csv(path, dtype=str).fillna("")
    return {r[key]: r for _, r in d.iterrows()}


# Rule 15 of INCLUSION_CRITERIA: an ordinary school carrying a designation is
# not a place a person can go to for help. 948 of the 2,879 rows in the frame
# are public elementary, middle, and high schools and kindergartens that the
# education ministry designated as a 다문화교육 정책학교 or gave a 한국어학급.
# They teach the children already enrolled in them, and a parent looking for a
# Korean class cannot walk into 두촌초등학교 and take one. Listing them made a
# third of the map ordinary schools and buried the 483 NGOs and 244 family
# centres a user is looking for. They stay in frame_v2.csv and in the coverage
# table; they do not enter the published map.
#
# The test is the DESIGNATION, not the name. Reading school level off the name
# needs the name to be spelled right, and this roster contains 삼서초둥학교 and
# the truncated 군산중앙유, both of which a name test lets through. The
# designation column says 정책학교(초중등) and 정책학교(유치원) for both.
#
# Schools built FOR migrant-background students are a different body and stay:
# 인천한누리학교, 지구촌학교, 서울다솜관광고등학교 exist because those students
# exist. Two signals keep a row: another roster listed it independently, or its
# designation is an alternative-school or centre designation instead of a
# classroom one.
_CLASSROOM_DESIGNATION = re.compile(r"(다문화교육\s*(정책|연구|선도)학교|한국어학급)")
_SCHOOL_ROSTER = "edu/edu_policy_school.csv"


def is_ordinary_school(row):
    rost = str(row.get("source_roster", ""))
    if _SCHOOL_ROSTER not in rost:
        return False
    # a row another roster listed on its own terms has a second, independent
    # reason to be in the frame
    if [x for x in rost.split("|") if x and x != _SCHOOL_ROSTER]:
        return False
    return bool(_CLASSROOM_DESIGNATION.search(str(row.get("subcategory", ""))))


def main(args):
    frame = pd.read_csv(args.frame, dtype=str).fillna("")
    web = load(args.websites)
    soc = load(args.socials)
    inc = load(args.inclusion)
    print(f"frame {len(frame)} | websites {len(web)} | socials {len(soc)} "
          f"| inclusion {len(inc)}")

    orgs = []
    dropped = collections.Counter()
    for _, r in frame.iterrows():
        fid = r["facility_id"]
        ic = inc.get(fid)
        serves = (str(ic.get("serves", "")) if ic is not None else "")
        if serves == "no":
            dropped["serves_no"] += 1
            continue
        if serves == "review":
            dropped["needs_review"] += 1
            continue
        if is_ordinary_school(r):
            dropped["ordinary_school_designation_only"] += 1
            continue

        w = web.get(fid)
        url = (str(w.get("final_website", "")) if w is not None else "").strip()
        wtier = (str(w.get("tier", "")) if (w is not None and url) else "")
        wsrc = ""
        if url:
            ev = str(w.get("evidence", ""))
            wsrc = ("ledger" if "manual_verified" in ev
                    else "key" if ("phone" in ev or "address" in ev)
                    else ("verified" if str(w.get("llm_verdict", "")) == "own"
                          else "fingerprint"))

        s = soc.get(fid)
        have_s = s is not None
        # A social account read off a site that is no longer the site on file
        # describes whoever owns that other site. Drop it rather than carry it.
        s_ok = (not have_s or s.get("src") != "own_site"
                or host(s.get("website", "")) == host(url))
        social = {}
        if have_s and s_ok:
            for p in SOCIALS:
                v = str(s.get(p, "") or "").strip()
                if v:
                    social[p] = v
        elif have_s and not s_ok:
            dropped["social_stale_host"] += 1

        o = {
            "id": fid,
            "name": display_name(r["name_ko"]),
            "name_raw": r["name_ko"],
            "name_en": r.get("name_en", ""),
            "type": (str(ic.get("unit_type", "")) if ic is not None else ""),
            "serves": serves or "",
            "incl_basis": (str(ic.get("incl_basis", "")) if ic is not None else ""),
            # what the organization DOES, as opposed to what kind of body it is.
            # A person looking for 한국어 수업 should not have to guess whether it
            # happens at a 가족센터, a KIIP 운영기관 or a 도서관.
            "svc": [x for x in str(
                ic.get("services_tag", "") if ic is not None else "").split("|")
                if x],
            # who the place is for, normalized. The rosters say this 259
            # different ways, from "결혼이민자" to "이주민/이주노동자/다문화가정
            # (세부는 subcategory 참조)" to "고용허가제(E-9)·방문취업(H-2)
            # 외국인근로자 및 고용사업주". Twelve codes carry all of it, and the
            # raw wording stays in "target" for anyone who wants it.
            "pop": [x for x in str(
                ic.get("pop_tag", "") if ic is not None else "").split("|")
                if x],
            # who pays and who runs it. A district covered by 민간 자체 단체 and
            # a district covered by 중앙정부 직영 관서 are not the same coverage,
            # and the map could not tell them apart. See code_governance.py.
            "gov_funder": (str(ic.get("gov_funder", "")) if ic is not None else ""),
            "gov_operator": (str(ic.get("gov_operator", ""))
                             if ic is not None else ""),
            "gov_basis": (str(ic.get("gov_basis", "")) if ic is not None else ""),
            "ministry": r.get("governing_ministry", ""),
            "operator": r.get("operator_type", ""),
            "operator_name": r.get("operator_name", ""),
            "sido": r.get("sido", ""),
            "sigungu": r.get("sigungu", ""),
            "addr": r.get("road_address", "") or r.get("jibun_address", ""),
            "tel": r.get("phone", ""),
            "email": r.get("email", ""),
            "web": url,
            "web_tier": wtier,
            "web_src": wsrc,
            "roster_page": r.get("roster_page", ""),
            "social_src": (str(s.get("src", "")) if social else ""),
            "target": [t.strip() for t in
                       str(r.get("target_population", "")).split("|") if t.strip()],
            "services": [t.strip() for t in
                         str(r.get("services_provided", "")).split("|") if t.strip()],
            "langs": [t.strip() for t in
                      str(r.get("languages_supported", "")).split("|") if t.strip()],
            "status": r.get("operational_status", "") or "unknown",
            "closed_year": r.get("closed_year", ""),
            "programs": sorted({p.split("/")[-1].replace(".csv", "")
                                for p in str(r.get("source_roster", "")).split("|")
                                if p and not p.startswith("v1/")}),
            "src": str(r.get("source_roster", "")).split("|"),
            "n_rosters": int(r.get("n_rosters", 1) or 1),
            "geo_how": r.get("geo_how", ""),
        }
        o.update(social)
        la, ln = str(r.get("lat", "")).strip(), str(r.get("lng", "")).strip()
        if la and ln:
            try:
                o["lat"] = round(float(la), 6)
                o["lng"] = round(float(ln), 6)
            except ValueError:
                pass
        orgs.append(o)

    # ---- census of the built record, printed before anything is written
    print("\n=== field census ===")
    n = len(orgs)
    for f in ("name", "type", "serves", "sido", "addr", "tel", "web", "lat",
              "svc", "pop", "gov_funder"):
        c = sum(1 for o in orgs if o.get(f) not in ("", None, []))
        print(f"  {c:5d}/{n}  {f}  ({c/max(n,1):.0%})")
    print("\n=== dropped ===")
    for k, v in dropped.items():
        print(f"  {v:5d}  {k}")

    hard_fail = []
    if n and sum(1 for o in orgs if o.get("name")) < n:
        hard_fail.append("some rows have no name")
    if n and sum(1 for o in orgs if o.get("lat")) < 0.8 * n:
        hard_fail.append("fewer than 80% of rows have coordinates")
    # find_websites.py defaults to searching only rows whose website column is
    # blank. Run it that way against a frame whose rosters already carry URLs
    # and website_verified.csv comes back holding a few hundred rows, every
    # other organization silently loses the link it had, and the build still
    # writes. That happened once and the census read "0/1835 web (0%)".
    if n and sum(1 for o in orgs if o.get("web")) < 0.2 * n:
        hard_fail.append(
            "fewer than 20% of rows have a website; run find_websites.py with "
            "--frame data/processed/v2/frame_v2_geo.csv --all")
    if hard_fail:
        print("\nREFUSING TO WRITE: " + "; ".join(hard_fail))
        return 1

    frame_cov = {}
    fc = os.path.join(ROOT, "docs", "frame_coverage.json")
    if os.path.exists(fc):
        frame_cov = json.load(open(fc, encoding="utf-8"))

    by_type = collections.Counter(o["type"] for o in orgs)
    by_sido = collections.Counter(o["sido"] for o in orgs)
    payload = {
        "version": "2.0",
        "updated": dt.date.today().isoformat(),
        "count": n,
        "mapped": sum(1 for o in orgs if o.get("lat")),
        "counts": {
            "serves": dict(collections.Counter(o["serves"] for o in orgs)),
            "type": dict(by_type),
            "svc": dict(collections.Counter(
                x for o in orgs for x in o.get("svc", []))),
            "pop": dict(collections.Counter(
                x for o in orgs for x in o.get("pop", []))),
            "gov": dict(collections.Counter(
                o.get("gov_funder", "") + "/" + o.get("gov_operator", "")
                for o in orgs)),
            "sido": dict(by_sido),
            "web_tier": dict(collections.Counter(
                o["web_tier"] for o in orgs if o["web"])),
            "density_eligible": sum(1 for o in orgs
                                    if o["type"] in DENSITY_TYPES
                                    and o["status"] != "closed"),
        },
        "density_types": sorted(DENSITY_TYPES),
        "frame_coverage": frame_cov,
        "orgs": orgs,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nwrote {args.out}: {n} orgs, "
          f"{payload['counts']['density_eligible']} density-eligible")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default=os.path.join(OUT, "frame_v2_geo.csv"))
    ap.add_argument("--websites", default=os.path.join(OUT, "website_verified.csv"))
    ap.add_argument("--socials", default=os.path.join(OUT, "socials_v2.csv"))
    ap.add_argument("--inclusion", default=os.path.join(OUT, "inclusion_coded.csv"))
    ap.add_argument("--out", default=os.path.join(DASH, "orgs.json"))
    sys.exit(main(ap.parse_args()))
