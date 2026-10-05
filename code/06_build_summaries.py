"""The per-level summary files, and the MOIS tables as public CSVs.

The district and province summaries sit on the MOJ district grain, roughly 250
districts a year including the general districts of large cities. The
sub-district summary is MOIS only, since MOJ publishes nothing below the
district, and carries that year's official administrative code. The four MOIS
CSVs follow from the same reconciled JSON.
"""
from collections import defaultdict
import csv
import json
import math
import os
import re

from kird import SIDO_EN
from kird import RELEASE_DATA as OUT
from kird import ROOT
from kird import SITE_DATA as SITE


# The MOIS composition and the measures derived from it. One set of rules for the
# district and province summaries and for the sub-district summary: until
# 2026-09-26 (first-round fix) the sub-district file had its own copy, which read a
# masked category as 0, so a dependence rate came out 0.0 where the category was
# masked (and recoverable), and never recovered the one masked component the
# district files recover.
CNT = {"합계": "broad_total", "한국국적미취득_소계": "non_naturalized", "외국인근로자": "workers",
       "결혼이민자": "marriage_migrants", "유학생": "students", "외국국적동포": "ethnic_koreans",
       "기타외국인": "other_foreigners", "한국국적취득자": "naturalized", "외국인주민자녀": "children",
       # "외국인주민 세대수" (foreign resident households), the column the 2009-2015
       # editions print after the "자녀" (children) block
       # at every level they publish (province, district, and from 2014 sub-district).
       # It is a count of households, not people, so it is in no identity. Until
       # 2026-09-27 (second-round cross-check) the parser read it and no release file carried it.
       "세대수": "foreign_resident_households"}
COMP_KO = ["외국인근로자", "결혼이민자", "유학생", "외국국적동포", "기타외국인"]
DERIVED_COLS = ["settlement_rate_pct", "labor_dependence_pct", "marriage_dependence_pct",
                "study_dependence_pct", "settlement_type"]


def pct(n, d, dec=2):
    return round(100 * n / d, dec) if d else ""


def enrich(r):
    """Recover the canonical category keys from the pre-2009 MOIS labels.
    2007-2008 publish naturalized citizens as "혼인귀화자" + "기타귀화자" (no
    "한국국적취득자" key), and the non-naturalized subtotal is published only from
    2009, recovered via the source identity total(B) = non-naturalized(C) +
    naturalized(D) + children(E).
    Categories the source does not publish that year stay ABSENT (released as
    blank), never 0."""
    if not r: return r
    r = dict(r)
    # Exactly one masked (***) component under a SOURCE-published subtotal (2009+
    # schema) is arithmetically determined: subtotal minus the published siblings
    # (e.g. 2016 Haman-gun students *** = 4452 - 4452 = 0). Recover it instead of
    # treating it as 0 (v1.1.0 behavior, wrong when > 0) or blanking the derived
    # rates. Never applied when the subtotal itself is derived (pre-2009 schema,
    # where absent categories are genuinely unpublished, not masked).
    # Since 2026-09-27 the parser settles every masked cell the sheet's identities fix
    # (05_mois_layer.MaskTree: the row's own and the rows above it), so for 2016 on
    # these two rules find nothing left to do. A value that would come out negative
    # is left out, as MaskTree leaves it masked; it had been set to 0 (it never came
    # out negative, checked 2026-09-27 on every district and sub-district row).
    if "한국국적미취득_소계" in r:
        missing = [k for k in COMP_KO if k not in r]
        if len(missing) == 1:
            present = sum(r.get(k) or 0 for k in COMP_KO if k in r)
            if r["한국국적미취득_소계"] - present >= 0:
                r[missing[0]] = r["한국국적미취득_소계"] - present
    if "한국국적취득자" not in r and ("혼인귀화자" in r or "기타귀화자" in r):
        r["한국국적취득자"] = (r.get("혼인귀화자") or 0) + (r.get("기타귀화자") or 0)
    # The same one level up: total = non-naturalized subtotal + naturalized + children,
    # so under a published "합계" and "미취득_소계" (2009+ schema) one masked of
    # "한국국적취득자" and "외국인주민자녀" is the total less the other two. Third-round
    # cross-check (2026-09-27): the sub-district file left 1,443 such cells blank in
    # 2016-2024 (2016 Gangneung Gyeongpo-dong: 303 - 290 - 11 = 2 naturalized), though
    # the same file recovers a masked leaf under "미취득_소계".
    if r.get("합계") is not None and r.get("한국국적미취득_소계") is not None:
        top = [k for k in ("한국국적취득자", "외국인주민자녀") if r.get(k) is None]
        if len(top) == 1:
            other = "외국인주민자녀" if top[0] == "한국국적취득자" else "한국국적취득자"
            if r["합계"] - r["한국국적미취득_소계"] - r[other] >= 0:
                r[top[0]] = r["합계"] - r["한국국적미취득_소계"] - r[other]
    if "한국국적미취득_소계" not in r and all(k in r for k in ("합계", "한국국적취득자", "외국인주민자녀")):
        r["한국국적미취득_소계"] = r["합계"] - r["한국국적취득자"] - r["외국인주민자녀"]
    return r


def settle_type(r):
    u = r.get("한국국적미취득_소계")
    # the typology needs all three numerators; "유학생" (students) is not published before 2008
    if not u or any(r.get(k) is None for k in ("외국인근로자", "유학생", "결혼이민자")): return ""
    w_, s_, m_ = (r["외국인근로자"] / u) / 0.38, (r["유학생"] / u) / 0.16, (r["결혼이민자"] / u) / 0.15
    mx = max(w_, s_, m_)
    return "다목적형(Multi-purpose)" if mx < 1 else ("산업형(Industrial)" if mx == w_ else ("대학·유학형(University)" if mx == s_ else "결혼정주형(Marriage-settled)"))


def derived(r):
    tot, nat, ch = r.get("합계"), r.get("한국국적취득자"), r.get("외국인주민자녀")
    und = r.get("한국국적미취득_소계")
    w, m, s = r.get("외국인근로자"), r.get("결혼이민자"), r.get("유학생")
    return [pct(nat + ch, tot) if (tot and nat is not None and ch is not None) else "",
            pct(w, und) if (und and w is not None) else "",
            pct(m, und) if (und and m is not None) else "",
            pct(s, und) if (und and s is not None) else "",
            settle_type(r)]


def summary_sigungu_and_sido():
    """summary_by_sigungu.csv and summary_by_sido.csv, on the MOJ district grain.

    The spine is indices.json, roughly 250 districts a year including the general
    districts of large cities, which is the unit MOJ publishes. Taking the MOIS
    district list as the spine instead would collapse those general districts into
    their parent city and would put the MOIS resident-registration count, which
    includes registered foreigners, in the denominator of the foreign share.

      registered_foreigners, the diversity indices and resident_pop come from
      indices.json, where resident_pop is the Korean-national registration count.
      The MOIS broad composition and settlement measures join from
      sigungu_population on (sido, normalized sigungu). MOIS carries the general
      districts only from 2016, so 2008-2015 apportions the parent city's broad
      counts across its districts by each district's share of the city's MOJ
      registered foreigners, falling back to its share of total population only
      where a district has no registered foreigners (build_sigungu() below gives
      the backcast error of both weightings, which is why this one was chosen).

    Districts absorbed by a merger (Cheongwon, Yeongi, Masan, Jinhae) are absent from
    indices.json and drop out on their own. Renames such as Incheon Nam-gu to
    Michuhol-gu have no effect,
    since indices.json is already canonical.
    """
    SITE = os.path.join(ROOT, "05_dashboard", "data")
    OUT = os.path.join(ROOT, "04_dataset_release", "data")
    SEP = re.compile(r"[\s·.,・ㆍᆞ‧･]")
    norm = lambda s: re.sub(r"제(\d)", r"\1", SEP.sub("", s or ""))
    REGION = json.load(open(f"{SITE}/region.json", encoding="utf-8"))
    SGG_EN = REGION.get("sigungu_en", {})
    sido_en = lambda s: SIDO_EN.get(s, "")
    RENAME = {("인천광역시", "남구"): ("미추홀구", "Michuhol-gu"),
              ("충청남도", "당진군"): ("당진시", "Dangjin-si"),
              ("경기도", "여주군"): ("여주시", "Yeoju-si")}
    def sgg_en(sido, sg):
        if (sido, sg) in RENAME:
            return RENAME[(sido, sg)][1]
        return SGG_EN.get(f"{sido}|{sg}") or SGG_EN.get(f"{sido}|{sg.replace(' ', '')}") or ""

    # v1.2.0: the idx field n_nationalities holds the size of the index basis
    # (top 19 + residual), so it is released as index_base_k; the count its old
    # name promised is n_nationalities_observed. IDX lists the released column
    # names; IDX_SRC maps each to the field in indices.json.
    IDX = ["shannon_H", "shannon_H_inclusive", "continent_H", "HHI", "evenness",
           "index_base_k", "n_nationalities_observed", "lisa", "lisa_fdr"]
    IDX_SRC = {"index_base_k": "n_nationalities"}

    SP = json.load(open(f"{SITE}/mois/sigungu_population.json", encoding="utf-8"))["by_sigungu"]
    IDXD = json.load(open(f"{SITE}/indices.json", encoding="utf-8"))["data"]

    def canon(sido, sg):
        return RENAME.get((sido, sg), (sg, None))[0]

    def write(fn, head, rows):
        with open(f"{OUT}/{fn}", "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f); wr.writerow(head); wr.writerows(rows)
        print(f"  {fn}: {len(rows)} rows")


    def mois_norm_lookup(y, sido):
        """{norm(sg): broad row} for one sido."""
        return {norm(sg): r for sg, r in SP.get(y, {}).get(sido, {}).items()}


    # ---- boundary-change recovery -------------------------------------------------
    # Old-name / merged districts the indices spine canonicalized, whose MOIS broad
    # would otherwise be dropped from the sigungu panel (the sido/national totals sum
    # the raw MOIS leaves, so they already carry this mass; only the spine join misses
    # it). Each predecessor's broad is added to its successor spine district so that
    # Σsigungu broad == sido == national. Applied ONLY when the predecessor is not
    # itself a spine unit that year (otherwise it matches directly). Successor targets
    # verified present in the spine for every year the predecessor appears; the mass is
    # added at the exact grain (no apportionment), so no double counting.
    RECOVER = {
        ("인천광역시", "남구"):   ("인천광역시", "미추홀구"),         # Incheon Nam-gu -> Michuhol-gu (renamed 2018)
        ("충청남도", "당진군"):   ("충청남도", "당진시"),             # Dangjin-gun -> Dangjin-si (city status 2012)
        ("경기도", "여주군"):     ("경기도", "여주시"),               # Yeoju-gun -> Yeoju-si (city status 2013)
        ("경상북도", "군위군"):   ("대구광역시", "군위군"),           # Gyeongbuk Gunwi-gun -> Daegu (transferred 2023)
        ("충청북도", "청원군"):   ("충청북도", "청주시 청원구"),       # Cheongwon-gun -> Cheongju Cheongwon-gu (merged 2014)
        ("경상남도", "마산시"):   ("경상남도", "창원시 마산합포구"),    # Masan-si -> Changwon (merged 2010)
        ("경상남도", "진해시"):   ("경상남도", "창원시 진해구"),        # Jinhae-si -> Changwon (merged 2010)
    }


    # ---- MOIS rows that straddle a merger ------------------------------------------
    # MOIS counts as of 1 January, MOJ as of 31 December, so in a merger year the two
    # describe different districts, and before a merger the spine may carry a
    # predecessor under its successor's name. For these (year, province) the MOIS rows
    # named here are pooled and apportioned across the spine units named with them, by
    # MOJ registered foreigners, as a general-district city's total is; a single unit
    # takes its pool whole and is not flagged as apportioned. Until 2026-09-26
    # (first-round fix) the city-name rule apportioned Cheongju-si across the
    # Cheongwon-gu unit too and then added all of Cheongwon-gun on top of it, and
    # apportioned the old Changwon-si across all five of the new city's gu before adding
    # Masan-si to Masanhappo-gu and Jinhae-si to Jinhae-gu: Cheongju Cheongwon-gu read
    # 4,969 in 2008 where Cheongwon-gun alone published 3,000, and Changwon Jinhae-gu
    # read 4,421 in 2010 where Jinhae-si published 3,053.
    TRANSITION = {}
    # Changwon + Masan + Jinhae became the new Changwon-si on 2010-07-01. Its five gu
    # follow the old city lines: Masanhappo-gu + Masanhoewon-gu are the old Masan-si,
    # Seongsan-gu + Uichang-gu the old Changwon-si, Jinhae-gu the old Jinhae-si. MOIS
    # 2010 still lists the three cities.
    TRANSITION[("2010", "경상남도")] = [
        (("마산시",), ("창원시 마산합포구", "창원시 마산회원구")),
        (("창원시",), ("창원시 성산구", "창원시 의창구")),
        (("진해시",), ("창원시 진해구",))]
    # Cheongwon-gun was a county of its own until 2014-07-01. The spine carries it as
    # "청주시 청원구" (its lineage, with Cheongwon-gun's code 43710), beside the two gu
    # the old Cheongju-si had.
    for _y in range(2008, 2014):
        TRANSITION[(str(_y), "충청북도")] = [
            (("청주시",), ("청주시 상당구", "청주시 흥덕구")),
            (("청원군",), ("청주시 청원구",))]
    # MOIS 2014 still lists Cheongju-si and Cheongwon-gun; MOJ 2014 the merged city's four gu, each of
    # which took ground from both. The two rows are the one city's total.
    TRANSITION[("2014", "충청북도")] = [
        (("청주시", "청원군"),
         ("청주시 상당구", "청주시 서원구", "청주시 청원구", "청주시 흥덕구"))]


    def split_count(total, weights):
        """`total` whole persons split over the units in proportion to `weights` by the
        largest-remainder rule: each unit takes the whole part of its share, and the
        persons left go one each to the largest fractions (ties to the larger weight,
        then the name), so the parts add up to `total` exactly."""
        W = float(sum(weights.values()))
        raw = {u: total * w / W for u, w in weights.items()}
        got = {u: int(math.floor(v + 1e-9)) for u, v in raw.items()}
        left = int(total) - sum(got.values())
        for u in sorted(weights, key=lambda u: (-(raw[u] - got[u]), -weights[u], u))[:max(left, 0)]:
            got[u] += 1
        return got


    def split_exact(cr, weights):
        """The enriched MOIS row `cr` split over the units in `weights` ({unit:
        weight}): every published leaf by split_count, so the units add up to the
        row's published value in every field, then each unit's subtotal and total
        rebuilt from its own leaves, so the source identity holds row by row too.
        Categories the row does not publish stay absent.

        Until 2026-09-27 (third-round cross-check) each unit rounded its own share of
        each field, so a city's gu missed the city's published value by 1-3 people in a
        field (2014 Yongin-si: broad_total 23,589 against 23,592); the exact split moved 181
        district cells of 2008-2015 by 1 to 3."""
        out = {u: {} for u in weights}
        for k in CNT:
            if k not in cr or k in ("합계", "한국국적미취득_소계"):
                continue
            for u, n in split_count(int(round(cr[k] or 0)), weights).items():
                out[u][k] = n
        full = all(k in cr for k in ("한국국적취득자", "외국인주민자녀")) and \
            any(k in cr for k in COMP_KO)
        if full:
            for r in out.values():
                r["한국국적미취득_소계"] = sum(r[k] for k in COMP_KO if k in r)
                r["합계"] = r["한국국적미취득_소계"] + r["한국국적취득자"] + r["외국인주민자녀"]
        elif "합계" in cr:
            for u, n in split_count(int(round(cr["합계"] or 0)), weights).items():
                out[u]["합계"] = n
        return out


    def add_broad(r, extra):
        """Add an enriched predecessor broad dict `extra` into `r` (both MOIS-Korean-
        keyed), component-wise on the published leaves, then rebuild the subtotal and
        total so the source identity total = non-naturalized subtotal + naturalized +
        children holds exactly.
        Categories neither side publishes that year stay absent (released blank, never 0)."""
        out = dict(r)
        for k in COMP_KO + ["한국국적취득자", "외국인주민자녀", "세대수"]:
            if r.get(k) is None and extra.get(k) is None:
                continue
            out[k] = (r.get(k) or 0) + (extra.get(k) or 0)
        comps = [k for k in COMP_KO if k in out]
        if comps:
            out["한국국적미취득_소계"] = sum(out[k] for k in comps)
        elif r.get("한국국적미취득_소계") is not None or extra.get("한국국적미취득_소계") is not None:
            out["한국국적미취득_소계"] = (r.get("한국국적미취득_소계") or 0) + (extra.get("한국국적미취득_소계") or 0)
        nn, nz, ch = out.get("한국국적미취득_소계"), out.get("한국국적취득자"), out.get("외국인주민자녀")
        if nn is not None and nz is not None and ch is not None:
            out["합계"] = nn + nz + ch
        elif r.get("합계") is not None or extra.get("합계") is not None:
            out["합계"] = (r.get("합계") or 0) + (extra.get("합계") or 0)
        return out


    def build_transition(y, units):
        """{(sido, spine sigungu): (broad dict, apportioned)} for the TRANSITION units
        of year y, and the set of (sido, MOIS row) it consumed."""
        out, used = {}, set()
        for (ty, sd), groups in TRANSITION.items():
            if ty != y:
                continue
            ml = mois_norm_lookup(y, sd)
            w_of = {u["sigungu"]: (u.get("foreign_total") or 0) for u in units if u["sido"] == sd}
            for srcs, dsts in groups:
                rows_ = [enrich(ml.get(norm(m))) for m in srcs]
                if not all(rows_) or not all(d in w_of for d in dsts):
                    raise SystemExit(f"{y} {sd}: TRANSITION rows {srcs} or units {dsts} "
                                     f"missing from MOIS or the spine")
                pool = rows_[0]
                for e in rows_[1:]:
                    pool = add_broad(pool, e)
                if len(dsts) == 1:
                    out[(sd, dsts[0])] = (dict(pool), False)
                else:
                    parts = split_exact(pool, {d: w_of[d] for d in dsts})
                    for d in dsts:
                        out[(sd, d)] = (parts[d], True)
                used |= {(sd, m) for m in srcs}
        return out, used


    def build_extra(y, skip=()):
        """{(succ_sido, succ_sigungu): enriched predecessor broad} for the residual
        old-name/merged units in year y (see RECOVER). A predecessor a TRANSITION
        group already placed (`skip`) is not added again."""
        spine = {(u["sido"], norm(u["sigungu"])) for u in IDXD["by_sigungu"].get(y, [])}
        out = {}
        for (ps, pg), (ts, tg) in RECOVER.items():
            row = SP.get(y, {}).get(ps, {}).get(pg)
            if row is None or (ps, norm(pg)) in spine:    # absent, or matched directly as its own spine unit
                continue
            if (ps, pg) in skip:
                continue
            assert (ts, norm(tg)) in spine, f"{y}: recover target {ts}|{tg} missing from spine"
            e = enrich(row)
            out[(ts, tg)] = add_broad(out[(ts, tg)], e) if (ts, tg) in out else e
        return out


    def build_sigungu():
        head = ["year", "sido", "sido_en", "sigungu", "sigungu_en",
                "registered_foreigners", "resident_pop", "foreign_share_pct"] \
            + list(CNT.values()) + ["broad_share_pct"] + DERIVED_COLS + ["broad_apportioned"] + IDX
        rows = []
        napprox = 0
        for y in sorted(IDXD["by_sigungu"]):
            units = IDXD["by_sigungu"][y]            # ≈250 districts (general districts included)
            trans, trans_used = build_transition(y, units)   # merger-year MOIS rows
            extra_y = build_extra(y, trans_used)     # boundary-change recovery for this year
            ml = mois_norm_lookup(y, None) if False else None
            # Sum of child weights per parent city of general districts (the denominator
            # for apportioning). The weight is MOJ registered foreigners: in the
            # 2016-2019 backcast, registered-foreigner weighting (median APE 4.9%, p90
            # 13.1%) follows foreign settlement patterns and cuts the error to a quarter
            # of population weighting (median APE 20.4%, p90 98.5%). Falls back to
            # total_pop where there are no registrations.
            child_reg = defaultdict(float)
            child_pop = defaultdict(float)
            # Standalone "X-si" spine units (pre-merger cities) that ALSO have a sibling
            # "X-si ~-gu" the same year (only Changwon 2008-2009: bare "창원시" +
            # "창원시 진해구", the backcast of pre-merger Jinhae-si). For those, the gu is a separate
            # former city, so it must NOT apportion the bare parent's broad (that would
            # double-count MOIS Changwon-si); it is filled from its own predecessor
            # (Jinhae-si) instead.
            bare_si = {(u["sido"], u["sigungu"]) for u in units
                       if " " not in u["sigungu"] and u["sigungu"].endswith("시")}
            # A bare "X-si" unit beside real "X-si ~-gu" units, with no resident
            # population, is the line the MOJ table prints under the city name for
            # people it places in the city and in none of its gu (fifth cross-check,
            # 2026-09-26: Yongin-si 2008-2011, Changwon-si 2010-2015, ...). It is not the city:
            # the MOIS city row must not land on it, the gu keep their apportioned
            # shares of that row as before, and the line carries MOJ counts only.
            gu_parent = {(u["sido"], u["sigungu"].split(" ", 1)[0]) for u in units
                         if " " in u["sigungu"] and u["sigungu"].split(" ", 1)[1].endswith("구")}
            residual_si = {k for k in bare_si if k in gu_parent and not any(
                u.get("total_pop") for u in units if (u["sido"], u["sigungu"]) == k)}
            bare_si -= residual_si
            city_gu = defaultdict(dict)
            for u in units:
                sg = u["sigungu"]
                if " " in sg and sg.split(" ", 1)[1].endswith("구") and sg.split(" ", 1)[0].endswith("시"):
                    key = (u["sido"], sg.split(" ", 1)[0])
                    child_reg[key] += (u.get("foreign_total") or 0)
                    child_pop[key] += (u.get("total_pop") or 0)
                    city_gu[key][sg] = u
            gu_split = {}

            def city_split(sido, city, cr):
                """The city's MOIS row split over every gu of the city at once, by
                registered foreigners, or by resident population where the city has
                none. A gu with no registered foreigners in a city that has some
                would take no share, where the per-gu rule gave it a population
                share; none occurs, and the build stops if one does."""
                gus = city_gu[(sido, city)]
                w = {g: (u.get("foreign_total") or 0) for g, u in gus.items()}
                if not sum(w.values()):
                    w = {g: (u.get("total_pop") or 0) for g, u in gus.items()}
                elif not all(w.values()):
                    raise SystemExit(f"{y} {sido} {city}: a gu without registered "
                                     f"foreigners, {w}; decide its share before splitting")
                return split_exact(cr, w) if sum(w.values()) else {}

            for u in units:
                sido = u["sido"]; sg0 = u["sigungu"]
                sg = canon(sido, sg0)
                tp = u.get("total_pop")
                ml = mois_norm_lookup(y, sido)
                r = None if (sido, sg0) in residual_si else enrich(ml.get(norm(sg0)) or ml.get(norm(sg)))
                apportioned = False
                if (sido, sg0) in trans:
                    r, apportioned = trans[(sido, sg0)]
                    r = dict(r)
                    napprox += int(apportioned)
                elif r is None and " " in sg0 and sg0.split(" ", 1)[1].endswith("구") and sg0.split(" ", 1)[0].endswith("시") \
                        and (sido, sg0.split(" ", 1)[0]) not in bare_si:
                    # A general district (gu) for which MOIS has only the parent city
                    # (2008-2015) -> apportion the parent city's broad counts by the gu's
                    # share of registered foreigners. Only published categories are
                    # apportioned (unpublished ones stay blank). All gu of one city are
                    # split at once (largest remainder), so the gu sum equals the city's
                    # published value in every cell, and subtotal/total are rebuilt from
                    # the gu's leaf sums so the published identity holds exactly row by
                    # row too (2026-09-27).
                    city = sg0.split(" ", 1)[0]
                    cr = enrich(ml.get(norm(city)))
                    if cr:
                        if (sido, city) not in gu_split:
                            gu_split[(sido, city)] = city_split(sido, city, cr)
                        part = gu_split[(sido, city)].get(sg0)
                        if part is not None:
                            r = dict(part)
                            napprox += 1
                            apportioned = True
                r = r or {}
                if (sido, sg) in extra_y:            # fold a predecessor district's broad onto its successor
                    r = add_broad(r, extra_y[(sido, sg)])
                row = [y, sido, sido_en(sido), sg, sgg_en(sido, sg0),
                       u.get("foreign_total", ""), tp if tp else "", u.get("foreign_share_pct", "")]
                row += [round(r.get(k, "")) if isinstance(r.get(k), float) else r.get(k, "") for k in CNT]
                row += [pct(r.get("합계", 0), tp) if (r.get("합계") and tp) else ""]   # broad_share = broad/total_pop
                row += derived(r)
                # a city line (residual_si) carries no broad values and none apportioned:
                # False, so the column stays a clean boolean for readers (a blank
                # beside True/False made pandas warn on mixed types, fifth cross-check)
                row += [("True" if apportioned else "False") if (r or (sido, sg0) in residual_si) else ""]   # the dictionary's spelling; 10 wrote True/False and this wrote TRUE/FALSE until 2026-09-26
                row += [u.get(IDX_SRC.get(k, k), "") for k in IDX]
                rows.append(row)
        write("summary_by_sigungu.csv", head, rows)
        print(f"  (general-district gu rows with apportioned MOIS broad counts: {napprox})")
        transition_gate(rows, head)


    def transition_gate(rows, head):
        """GATE (first-round fix, 2026-09-26): each TRANSITION group's spine units hold
        exactly the MOIS rows the group names, to rounding (a unit's rounded leaves),
        so no merger-year row leaks into a unit on the other side of the old city line.
        The province sums could not see the old leak, which only moved people within
        Chungcheongbuk-do and Gyeongsangnam-do."""
        ix = {c: i for i, c in enumerate(head)}
        got = {(r[ix["year"]], r[ix["sido"]], r[ix["sigungu"]]): r for r in rows}
        reg = {(r[ix["year"]], r[ix["sido"]], r[ix["sigungu"]]): float(r[ix["registered_foreigners"]] or 0)
               for r in rows}
        bad = []
        for (y, sd), groups in TRANSITION.items():
            ml = mois_norm_lookup(y, sd)
            for srcs, dsts in groups:
                for k in CNT:
                    want = sum((enrich(ml.get(norm(m))) or {}).get(k) or 0 for m in srcs)
                    have = sum(float(got[(y, sd, d)][ix[CNT[k]]] or 0) for d in dsts)
                    tol = 0 if len(dsts) == 1 else len(dsts) * (1 if k not in ("합계", "한국국적미취득_소계") else len(COMP_KO) + 2)
                    if abs(have - want) > tol:
                        bad.append((y, sd, srcs, CNT[k], want, have))
                # and within a group, each unit's share follows its MOJ registered
                # foreigners (the 2014 Cheongju rows once gave one gu all of Cheongwon-gun)
                W = sum(reg[(y, sd, d)] for d in dsts)
                pool = sum((enrich(ml.get(norm(m))) or {}).get("합계") or 0 for m in srcs)
                for d in dsts:
                    exp = pool * reg[(y, sd, d)] / W if W else 0
                    if abs(float(got[(y, sd, d)][ix["broad_total"]] or 0) - exp) > len(COMP_KO) + 3:
                        bad.append((y, sd, d, "share", round(exp), got[(y, sd, d)][ix["broad_total"]]))
        if bad:
            raise SystemExit("summary_by_sigungu: merger-year MOIS rows landed outside "
                             "their units: %s" % bad[:6])
        print(f"  gate: {sum(len(g) for g in TRANSITION.values())} merger-year MOIS groups "
              f"hold exactly their own rows")


    def build_sido():
        head = ["year", "sido", "sido_en", "registered_foreigners", "resident_pop", "foreign_share_pct"] \
            + list(CNT.values()) + ["broad_share_pct"] + DERIVED_COLS + IDX
        rows = []
        for y in sorted(IDXD.get("by_sido", {})):
            il = {rec["sido"]: rec for rec in IDXD["by_sido"][y]}
            # Broad counts: sum per sido (skipping parent cities that would double count).
            # enrich restores the pre-2009 labels row by row, and categories the source
            # did not publish that year drop out of the sum and are written blank (""),
            # not 0. In 2012, MOIS still lists Chungnam Yeongi-gun alongside the new
            # Sejong-si with the identical count (the Sejong launch duplicate). Once
            # Sejong is its own province (indices by_sido), its mass belongs to Sejong,
            # so drop the Chungnam Yeongi-gun copy to
            # avoid double-counting it into the national total.
            sejong_province = any(rec["sido"] == "세종특별자치시" for rec in IDXD["by_sido"].get(y, []))
            agg = {}
            for sido in SP.get(y, {}):
                a = agg.setdefault(sido, {})
                for sg, r0 in SP[y][sido].items():
                    if " " not in sg and any(k.startswith(sg + " ") for k in SP[y][sido]):
                        continue
                    if sejong_province and sido == "충청남도" and sg == "연기군":
                        continue
                    r = enrich(r0)
                    for k in list(CNT) + ["주민등록인구"]:
                        if k in r and r[k] is not None:
                            a[k] = a.get(k, 0) + r[k]
            for sido, ix in il.items():
                r = agg.get(sido, {})
                tp = ix.get("total_pop")
                row = [y, sido, sido_en(sido), ix.get("foreign_total", ""), tp if tp else "", ix.get("foreign_share_pct", "")]
                row += [r.get(k, "") for k in CNT]
                row += [pct(r.get("합계", 0), tp) if (r.get("합계") and tp) else ""]
                row += derived(r)
                row += [ix.get(IDX_SRC.get(k, k), "") for k in IDX]
                rows.append(row)
        write("summary_by_sido.csv", head, rows)

    build_sido(); build_sigungu()
    print("done.")



def summary_eupmyeondong():
    """summary_by_eupmyeondong.csv, the MOIS sub-district file.

    The MOIS broad counts per sub-district (eup/myeon/dong) joined by name to that year's administrative
    boundaries (SGIS via the admdongkor yearly snapshots), which supplies the official
    adm_code as a language-neutral key. MOJ publishes nothing below the district, so
    this file is MOIS only.

    summary_by_sigungu.csv and summary_by_sido.csv come from step 21 instead, which
    puts them on the MOJ district grain.
    """
    SEP = re.compile(r"[\s·.,・ㆍᆞ‧･]")
    norm = lambda s: re.sub(r"제(\d)", r"\1", SEP.sub("", s or ""))
    sido_en = lambda s: SIDO_EN.get(s, "")
    # The composition columns and the derived measures follow the module-level rules
    # the district summaries use (enrich, derived, settle_type): one masked component
    # under a published subtotal is recovered, and a rate whose numerator is still
    # unreported is blank, never 0.0 (first-round fix, 2026-09-26).

    def w(fn, head, rows):
        with open(f"{OUT}/{fn}", "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f); wr.writerow(head); wr.writerows(rows)
        print(f"  {fn}: {len(rows)} rows")

    def emd_label(y): return "2014" if y <= 2014 else ("2024" if y >= 2024 else str(y))
    def emd_geo(l): return f"{SITE}/korea_emd.json" if l == "2024" else f"{SITE}/emd_years/korea_emd_{l}.json"

    def build_eupmyeondong():
        ep = json.load(open(f"{SITE}/mois/eupmyeondong_population.json", encoding="utf-8"))["by_eupmyeondong"]
        rows = []
        for y in sorted(ep):
            g = json.load(open(emd_geo(emd_label(int(y))), encoding="utf-8"))
            # The lookup matched down to the district (cs) is authoritative. The
            # fallback lookup (cl), for when the district name differs between MOIS and
            # the boundary file (Goyang-si as a whole vs its three gu, etc.), is used
            # **only when the dong name is unique within that sido**.
            #
            # Before, `setdefault` gave the code of whichever gu was read first. So,
            # with several Jungang-dong in Gyeongnam, Jungang-dong in Changwon
            # Seongsan-gu got the Jinju-si code (38030740). When names collide, leave
            # the code blank rather than invent one: a wrong code is worse than a blank
            # (2026-08-26).
            cs, seen = {}, {}
            for f in g["features"]:
                p = f["properties"]
                cs[(p["sido"], norm(p["sg"]), norm(p["dong"]))] = p.get("code", "")
                seen.setdefault((p["sido"], norm(p["dong"])), set()).add(p.get("code", ""))
            cl = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
            for sido in ep[y]:
                for sg in ep[y][sido]:
                    for dong, r in ep[y][sido][sg].items():
                        code = cs.get((sido, norm(sg), norm(dong))) or cl.get((sido, norm(dong)), "")
                        r = enrich(r) or {}
                        row = [y, sido, sido_en(sido), sg, dong, code]
                        row += [r.get(k, "") for k in CNT]
                        row += derived(r)
                        rows.append(row)
        head = ["year", "sido", "sido_en", "sigungu", "eupmyeondong", "adm_code"] \
            + list(CNT.values()) + DERIVED_COLS
        w("summary_by_eupmyeondong.csv", head, rows)

    build_eupmyeondong()
    print("done.")



def export_mois_csvs():
    """The MOIS broad-definition layer as four public CSVs.

    Written from the reconciled dashboard JSON, with every category column carrying an
    English label beside the Korean one. Source: MOIS, "지방자치단체 외국인주민현황" (foreign
    residents by local government).

      mois_broad_residents_by_sigungu.csv       type composition and the derived
                                                settlement measures, province x
                                                district x year
      mois_broad_residents_by_eupmyeondong.csv  sub-district x year, with that year's
                                                official adm_code
      mois_children_by_age.csv                  children by age and sex, district x year
      mois_multicultural_households.csv         household member types, sub-district x year
    """
    SEP = re.compile(r"[\s·.,・ㆍᆞ‧･]")
    norm = lambda s: re.sub(r"제(\d)", r"\1", SEP.sub("", s or ""))

    REGION = json.load(open(f"{SITE}/region.json", encoding="utf-8"))
    # Province English names as in the existing public CSVs (provinces as -do,
    # metropolitan and special cities in short form).
    SGG_EN = REGION.get("sigungu_en", {})
    def sido_en(s): return SIDO_EN.get(s, "")
    def sgg_en(sido, sg):
        return SGG_EN.get(f"{sido}|{sg}") or SGG_EN.get(f"{sido}|{sg.replace(' ', '')}") or ""

    def w(fn, header, rows):
        with open(f"{OUT}/{fn}", "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f); wr.writerow(header); wr.writerows(rows)
        print(f"  {fn}: {len(rows)} rows")

    # ---------- broad type composition + derived measures (district) ----------
    # Column meaning: broad_total, the broad foreign resident total = non_naturalized + naturalized + children
    F = {"합계": "broad_total", "한국국적미취득_소계": "non_naturalized", "외국인근로자": "workers",
         "결혼이민자": "marriage_migrants", "유학생": "students", "외국국적동포": "ethnic_koreans",
         "기타외국인": "other_foreigners", "한국국적취득자": "naturalized", "외국인주민자녀": "children",
         "주민등록인구": "resident_pop"}
    CNT = list(F.keys())
    def settlement_type(r):
        u = (r.get("한국국적미취득_소계") or 0) or max((r.get("합계") or 0) - (r.get("한국국적취득자") or 0) - (r.get("외국인주민자녀") or 0), 0)
        if not u or not r.get("합계"): return ""
        w_, s_, m_ = (r.get("외국인근로자", 0) / u) / 0.38, (r.get("유학생", 0) / u) / 0.16, (r.get("결혼이민자", 0) / u) / 0.15
        mx = max(w_, s_, m_)
        return "다목적형(Multi-purpose)" if mx < 1 else ("산업형(Industrial)" if mx == w_ else ("대학·유학형(University)" if mx == s_ else "결혼정주형(Marriage-settled)"))
    def pct(num, den, dec=2): return round(100 * num / den, dec) if den else ""

    def export_sigungu_broad():
        sp = json.load(open(f"{SITE}/mois/sigungu_population.json", encoding="utf-8"))["by_sigungu"]
        rows = []
        for y in sorted(sp):
            for sido in sp[y]:
                for sg, r in sp[y][sido].items():
                    tot = r.get("합계") or 0
                    und = (r.get("한국국적미취득_소계") or 0) or max(tot - (r.get("한국국적취득자") or 0) - (r.get("외국인주민자녀") or 0), 0)
                    rows.append([y, sido, sido_en(sido), sg, sgg_en(sido, sg)]
                                + [r.get(k, "") for k in CNT]
                                + [pct((r.get("한국국적취득자", 0) + r.get("외국인주민자녀", 0)), tot),
                                   pct(r.get("외국인근로자", 0), und), pct(r.get("결혼이민자", 0), und),
                                   pct(r.get("유학생", 0), und), settlement_type(r)])
        head = ["year", "sido", "sido_en", "sigungu", "sigungu_en"] + list(F.values()) \
            + ["settlement_rate_pct", "labor_dependence_pct", "marriage_dependence_pct",
               "study_dependence_pct", "settlement_type"]
        w("mois_broad_residents_by_sigungu.csv", head, rows)

    # ---------- sub-district broad counts + that year's official adm_code ----------
    def emd_label(y): return "2014" if y <= 2014 else ("2024" if y >= 2024 else str(y))
    def emd_geojson(label): return f"{SITE}/korea_emd.json" if label == "2024" else f"{SITE}/emd_years/korea_emd_{label}.json"
    def export_eupmyeondong_broad():
        ep = json.load(open(f"{SITE}/mois/eupmyeondong_population.json", encoding="utf-8"))["by_eupmyeondong"]
        rows = []
        for y in sorted(ep):
            g = json.load(open(emd_geojson(emd_label(int(y))), encoding="utf-8"))
            code_strict, code_loose = {}, {}
            for f in g["features"]:
                p = f["properties"]; c = p.get("code", "")
                code_strict[(p["sido"], norm(p["sg"]), norm(p["dong"]))] = c
                code_loose.setdefault((p["sido"], norm(p["dong"])), c)
            for sido in ep[y]:
                for sg in ep[y][sido]:
                    for dong, r in ep[y][sido][sg].items():
                        code = code_strict.get((sido, norm(sg), norm(dong))) or code_loose.get((sido, norm(dong)), "")
                        rows.append([y, sido, sido_en(sido), sg, dong, code] + [r.get(k, "") for k in CNT])
        head = ["year", "sido", "sido_en", "sigungu", "eupmyeondong", "adm_code"] + list(F.values())
        w("mois_broad_residents_by_eupmyeondong.csv", head, rows)

    # ---------- children by age ----------
    def export_children():
        ca = json.load(open(f"{SITE}/mois/children_age_sigungu.json", encoding="utf-8"))["by_sigungu"]
        rows = []
        for y in sorted(ca):
            for sido in ca[y]:
                for sg in ca[y][sido]:
                    for age, n in ca[y][sido][sg].items():
                        rows.append([y, sido, sido_en(sido), sg, sgg_en(sido, sg), age, n])
        w("mois_children_by_age.csv", ["year", "sido", "sido_en", "sigungu", "sigungu_en", "age", "n"], rows)

    # ---------- multicultural households ----------
    MC_EN = {"한국인배우자": "Korean spouse", "결혼이민자": "Marriage migrant", "귀화자등": "Naturalized",
             "자녀_국내출생": "Child (born in Korea)", "자녀_귀화인지외국국적": "Child (naturalized/foreign)",
             "기타동거인_내국인": "Other cohabitant (Korean)", "기타동거인_외국인": "Other cohabitant (foreign)"}
    def export_multicultural():
        mc = json.load(open(f"{SITE}/mois/multicultural_eupmyeondong.json", encoding="utf-8"))["by_eupmyeondong"]
        rows, agg = [], {}    # agg: (y,sido,sg,cat) -> n  (district aggregate)
        for y in sorted(mc):
            for sido in mc[y]:
                for sg in mc[y][sido]:
                    for dong in mc[y][sido][sg]:
                        for cat, n in mc[y][sido][sg][dong].items():
                            rows.append([y, sido, sido_en(sido), sg, dong, cat, MC_EN.get(cat, ""), n])
                            k = (y, sido, sg, cat); agg[k] = agg.get(k, 0) + (n or 0)
        w("mois_multicultural_households.csv", ["year", "sido", "sido_en", "sigungu", "eupmyeondong", "category", "category_en", "n"], rows)
        srows = [[y, sido, sido_en(sido), sg, sgg_en(sido, sg), cat, MC_EN.get(cat, ""), n]
                 for (y, sido, sg, cat), n in agg.items()]
        w("mois_multicultural_households_by_sigungu.csv",
          ["year", "sido", "sido_en", "sigungu", "sigungu_en", "category", "category_en", "n"], srows)

    export_sigungu_broad()
    export_children()
    export_multicultural()
    export_eupmyeondong_broad()   # largest (code join), so last
    print("done.")


if __name__ == "__main__":
    summary_sigungu_and_sido()
    summary_eupmyeondong()
    export_mois_csvs()
