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
import os
import re

from kird import SIDO_EN
from kird import RELEASE_DATA as OUT
from kird import ROOT
from kird import SITE_DATA as SITE


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
      counts across its districts by their share of total population.

    Districts absorbed by a merger (청원, 연기, 마산, 진해) are absent from indices.json
    and drop out on their own. Renames such as 인천 남구 to 미추홀구 have no effect,
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

    CNT = {"합계": "broad_total", "한국국적미취득_소계": "non_naturalized", "외국인근로자": "workers",
           "결혼이민자": "marriage_migrants", "유학생": "students", "외국국적동포": "ethnic_koreans",
           "기타외국인": "other_foreigners", "한국국적취득자": "naturalized", "외국인주민자녀": "children"}
    COMP_KO = ["외국인근로자", "결혼이민자", "유학생", "외국국적동포", "기타외국인"]
    # v1.2.0: the idx field n_nationalities holds the size of the index basis
    # (top 19 + residual), so it is released as index_base_k; the count its old
    # name promised is n_nationalities_observed. IDX lists the released column
    # names; IDX_SRC maps each to the field in indices.json.
    IDX = ["shannon_H", "shannon_H_inclusive", "continent_H", "HHI", "evenness",
           "index_base_k", "n_nationalities_observed", "lisa", "lisa_fdr"]
    IDX_SRC = {"index_base_k": "n_nationalities"}
    def pct(n, d, dec=2): return round(100 * n / d, dec) if d else ""
    def enrich(r):
        """Recover the canonical category keys from the pre-2009 MOIS labels.
        2007-2008 publish naturalized citizens as 혼인귀화자 + 기타귀화자 (no
        한국국적취득자 key), and the non-naturalized subtotal is published only from
        2009 — recovered via the source identity 합계(B) = 미취득(C) + 취득(D) + 자녀(E).
        Categories the source does not publish that year stay ABSENT (released as
        blank), never 0."""
        if not r: return r
        r = dict(r)
        # Exactly one masked (***) component under a SOURCE-published subtotal (2009+
        # schema) is arithmetically determined: subtotal minus the published siblings
        # (e.g. 2016 함안군 유학생 *** = 4452 - 4452 = 0). Recover it instead of
        # treating it as 0 (v1.1.0 behavior, wrong when > 0) or blanking the derived
        # rates. Never applied when the subtotal itself is derived (pre-2009 schema,
        # where absent categories are genuinely unpublished, not masked).
        if "한국국적미취득_소계" in r:
            missing = [k for k in COMP_KO if k not in r]
            if len(missing) == 1:
                present = sum(r.get(k) or 0 for k in COMP_KO if k in r)
                r[missing[0]] = max(r["한국국적미취득_소계"] - present, 0)
        if "한국국적취득자" not in r and ("혼인귀화자" in r or "기타귀화자" in r):
            r["한국국적취득자"] = (r.get("혼인귀화자") or 0) + (r.get("기타귀화자") or 0)
        if "한국국적미취득_소계" not in r and all(k in r for k in ("합계", "한국국적취득자", "외국인주민자녀")):
            r["한국국적미취득_소계"] = r["합계"] - r["한국국적취득자"] - r["외국인주민자녀"]
        return r
    def settle_type(r):
        u = r.get("한국국적미취득_소계")
        # the typology needs all three numerators; 유학생 is not published before 2008
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
    DERIVED_COLS = ["settlement_rate_pct", "labor_dependence_pct", "marriage_dependence_pct", "study_dependence_pct", "settlement_type"]

    SP = json.load(open(f"{SITE}/mois/sigungu_population.json", encoding="utf-8"))["by_sigungu"]
    IDXD = json.load(open(f"{SITE}/indices.json", encoding="utf-8"))["data"]

    def canon(sido, sg):
        return RENAME.get((sido, sg), (sg, None))[0]

    def write(fn, head, rows):
        with open(f"{OUT}/{fn}", "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f); wr.writerow(head); wr.writerows(rows)
        print(f"  {fn}: {len(rows)} rows")


    def mois_norm_lookup(y, sido):
        """sido별 {norm(sg): broad row}."""
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
        ("인천광역시", "남구"):   ("인천광역시", "미추홀구"),         # 인천 남구 -> 미추홀구 (2018 개명)
        ("충청남도", "당진군"):   ("충청남도", "당진시"),             # 당진군 -> 당진시 (2012 시 승격)
        ("경기도", "여주군"):     ("경기도", "여주시"),               # 여주군 -> 여주시 (2013 시 승격)
        ("경상북도", "군위군"):   ("대구광역시", "군위군"),           # 경북 군위군 -> 대구 (2023 편입)
        ("충청북도", "청원군"):   ("충청북도", "청주시 청원구"),       # 청원군 -> 청주 청원구 (2014 통합)
        ("경상남도", "마산시"):   ("경상남도", "창원시 마산합포구"),    # 마산시 -> 창원 (2010 통합)
        ("경상남도", "진해시"):   ("경상남도", "창원시 진해구"),        # 진해시 -> 창원 (2010 통합)
    }


    def add_broad(r, extra):
        """Add an enriched predecessor broad dict `extra` into `r` (both MOIS-Korean-
        keyed), component-wise on the published leaves, then rebuild the subtotal and
        total so the source identity 합계 = 미취득_소계 + 취득 + 자녀 holds exactly.
        Categories neither side publishes that year stay absent (released blank, never 0)."""
        out = dict(r)
        for k in COMP_KO + ["한국국적취득자", "외국인주민자녀"]:
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


    def build_extra(y):
        """{(succ_sido, succ_sigungu): enriched predecessor broad} for the residual
        old-name/merged units in year y (see RECOVER)."""
        spine = {(u["sido"], norm(u["sigungu"])) for u in IDXD["by_sigungu"].get(y, [])}
        out = {}
        for (ps, pg), (ts, tg) in RECOVER.items():
            row = SP.get(y, {}).get(ps, {}).get(pg)
            if row is None or (ps, norm(pg)) in spine:    # absent, or matched directly as its own spine unit
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
            units = IDXD["by_sigungu"][y]            # ≈250 시군구(일반구 포함)
            extra_y = build_extra(y)                 # boundary-change recovery for this year
            ml = mois_norm_lookup(y, None) if False else None
            # 일반구 부모 시별 자식 가중치 합(안분 분모용). 가중치는 MOJ 등록외국인:
            # 2016-2019 backcast에서 인구가중(중위 APE 20.4%, p90 98.5%) 대비
            # 등록외국인가중(중위 4.9%, p90 13.1%)이 외국인 정주 패턴을 따라가
            # 오차를 1/4로 줄임. 등록이 없으면 total_pop으로 fallback.
            child_reg = defaultdict(float)
            child_pop = defaultdict(float)
            # Standalone "X시" spine units (pre-merger cities) that ALSO have a sibling
            # "X시 ~구" the same year (only 창원 2008-2009: bare 창원시 + 창원시 진해구,
            # the backcast of pre-merger 진해시). For those, the gu is a separate former
            # city, so it must NOT apportion the bare parent's broad (that would double-
            # count MOIS 창원시); it is filled from its own predecessor (진해시) instead.
            bare_si = {(u["sido"], u["sigungu"]) for u in units
                       if " " not in u["sigungu"] and u["sigungu"].endswith("시")}
            for u in units:
                sg = u["sigungu"]
                if " " in sg and sg.split(" ", 1)[1].endswith("구") and sg.split(" ", 1)[0].endswith("시"):
                    key = (u["sido"], sg.split(" ", 1)[0])
                    child_reg[key] += (u.get("foreign_total") or 0)
                    child_pop[key] += (u.get("total_pop") or 0)
            for u in units:
                sido = u["sido"]; sg0 = u["sigungu"]
                sg = canon(sido, sg0)
                tp = u.get("total_pop")
                ml = mois_norm_lookup(y, sido)
                r = enrich(ml.get(norm(sg0)) or ml.get(norm(sg)))
                apportioned = False
                if r is None and " " in sg0 and sg0.split(" ", 1)[1].endswith("구") and sg0.split(" ", 1)[0].endswith("시") \
                        and (sido, sg0.split(" ", 1)[0]) not in bare_si:
                    # 일반구 구인데 MOIS엔 부모 시만(2008-2015) → 부모 시 광의를 구 등록외국인 비중으로 안분.
                    # 발행된 카테고리만 안분(미발행은 공란 유지). leaf를 먼저 반올림한 뒤
                    # 소계/합계를 그 합으로 재구성해 공개 항등식이 행 단위로 정확히 성립.
                    city = sg0.split(" ", 1)[0]
                    cr = enrich(ml.get(norm(city)))
                    w = u.get("foreign_total") or 0
                    denom = child_reg.get((sido, city), 0)
                    if not (w and denom):                      # fallback: 인구가중
                        w, denom = tp or 0, child_pop.get((sido, city), 0)
                    if cr and denom and w:
                        frac = w / denom
                        r = {k: round((cr[k] or 0) * frac) for k in CNT
                             if k in cr and k not in ("합계", "한국국적미취득_소계")}
                        comps = [k for k in COMP_KO if k in r]
                        if comps and "한국국적취득자" in r and "외국인주민자녀" in r:
                            r["한국국적미취득_소계"] = sum(r[k] for k in comps)
                            r["합계"] = r["한국국적미취득_소계"] + r["한국국적취득자"] + r["외국인주민자녀"]
                        elif "합계" in cr:
                            r["합계"] = round((cr["합계"] or 0) * frac)
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
                row += [("TRUE" if apportioned else "FALSE") if r else ""]
                row += [u.get(IDX_SRC.get(k, k), "") for k in IDX]
                rows.append(row)
        write("summary_by_sigungu.csv", head, rows)
        print(f"  (MOIS 광의 안분된 일반구-구 행: {napprox})")


    def build_sido():
        head = ["year", "sido", "sido_en", "registered_foreigners", "resident_pop", "foreign_share_pct"] \
            + list(CNT.values()) + ["broad_share_pct"] + DERIVED_COLS + IDX
        rows = []
        for y in sorted(IDXD.get("by_sido", {})):
            il = {rec["sido"]: rec for rec in IDXD["by_sido"][y]}
            # 광의: sido별 합(부모 시 중복 스킵). 행별 enrich로 pre-2009 라벨을 복원하고,
            # 그 해 소스에 발행되지 않은 카테고리는 합산에서 빠져 공란("")으로 출력된다(0 아님).
            # In 2012, MOIS still lists 충남 연기군 alongside the new 세종 세종시 with the
            # identical count (the Sejong launch duplicate). Once 세종 is its own province
            # (indices by_sido), its mass belongs to 세종, so drop the 충남 연기군 copy to
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

    The MOIS broad counts per 읍면동 joined by name to that year's administrative
    boundaries (SGIS via the admdongkor yearly snapshots), which supplies the official
    adm_code as a language-neutral key. MOJ publishes nothing below the district, so
    this file is MOIS only.

    summary_by_sigungu.csv and summary_by_sido.csv come from step 21 instead, which
    puts them on the MOJ district grain.
    """
    SEP = re.compile(r"[\s·.,・ㆍᆞ‧･]")
    norm = lambda s: re.sub(r"제(\d)", r"\1", SEP.sub("", s or ""))
    sido_en = lambda s: SIDO_EN.get(s, "")

    # MOIS 광의 count 필드(영문 컬럼) + 파생
    CNT = {"합계": "broad_total", "한국국적미취득_소계": "non_naturalized", "외국인근로자": "workers",
           "결혼이민자": "marriage_migrants", "유학생": "students", "외국국적동포": "ethnic_koreans",
           "기타외국인": "other_foreigners", "한국국적취득자": "naturalized", "외국인주민자녀": "children"}
    def pct(n, d, dec=2): return round(100 * n / d, dec) if d else ""
    def settle_type(r):
        u = (r.get("한국국적미취득_소계") or 0) or max((r.get("합계") or 0) - (r.get("한국국적취득자") or 0) - (r.get("외국인주민자녀") or 0), 0)
        if not u or not r.get("합계"): return ""
        w_, s_, m_ = (r.get("외국인근로자", 0) / u) / 0.38, (r.get("유학생", 0) / u) / 0.16, (r.get("결혼이민자", 0) / u) / 0.15
        mx = max(w_, s_, m_)
        return "다목적형(Multi-purpose)" if mx < 1 else ("산업형(Industrial)" if mx == w_ else ("대학·유학형(University)" if mx == s_ else "결혼정주형(Marriage-settled)"))
    def derived(r):
        tot = r.get("합계") or 0
        und = (r.get("한국국적미취득_소계") or 0) or max(tot - (r.get("한국국적취득자") or 0) - (r.get("외국인주민자녀") or 0), 0)
        return [pct((r.get("한국국적취득자", 0) + r.get("외국인주민자녀", 0)), tot), pct(r.get("외국인근로자", 0), und),
                pct(r.get("결혼이민자", 0), und), pct(r.get("유학생", 0), und), settle_type(r)]
    DERIVED_COLS = ["settlement_rate_pct", "labor_dependence_pct", "marriage_dependence_pct", "study_dependence_pct", "settlement_type"]

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
            # 시군구까지 맞은 조회(cs)가 정본. 시군구 이름이 MOIS 와 경계 파일에서
            # 다를 때(고양시 통째 대 세 구 등)를 위한 대체 조회(cl)는 **그 시도
            # 안에서 동 이름이 유일할 때만** 쓴다.
            #
            # 전에는 `setdefault` 로 먼저 읽힌 구의 코드를 주었다. 그래서 경남에
            # 중앙동이 여럿인데 창원 성산구 중앙동이 진주시 코드(38030740)를
            # 받았다. 이름이 겹치면 코드를 지어내지 말고 비운다 — 틀린 코드는
            # 빈 칸보다 나쁘다(2026-08-26).
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
    English label beside the Korean one. Source: 행정안전부 「지방자치단체 외국인주민현황」.

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
    # 기존 공개 CSV와 동일한 시도 영문 표기(도는 -do, 광역시·특별시는 약식).
    SGG_EN = REGION.get("sigungu_en", {})
    def sido_en(s): return SIDO_EN.get(s, "")
    def sgg_en(sido, sg):
        return SGG_EN.get(f"{sido}|{sg}") or SGG_EN.get(f"{sido}|{sg.replace(' ', '')}") or ""

    def w(fn, header, rows):
        with open(f"{OUT}/{fn}", "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f); wr.writerow(header); wr.writerows(rows)
        print(f"  {fn}: {len(rows)} rows")

    # ---------- 광의 유형 구성 + 파생지표 (시군구) ----------
    # 컬럼 의미: broad_total 광의 외국인주민 합계 = non_naturalized + naturalized + children
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

    # ---------- 읍면동 광의 + 그 해 공식 행정동코드 ----------
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

    # ---------- 자녀 연령별 ----------
    def export_children():
        ca = json.load(open(f"{SITE}/mois/children_age_sigungu.json", encoding="utf-8"))["by_sigungu"]
        rows = []
        for y in sorted(ca):
            for sido in ca[y]:
                for sg in ca[y][sido]:
                    for age, n in ca[y][sido][sg].items():
                        rows.append([y, sido, sido_en(sido), sg, sgg_en(sido, sg), age, n])
        w("mois_children_by_age.csv", ["year", "sido", "sido_en", "sigungu", "sigungu_en", "age", "n"], rows)

    # ---------- 다문화가구 ----------
    MC_EN = {"한국인배우자": "Korean spouse", "결혼이민자": "Marriage migrant", "귀화자등": "Naturalized",
             "자녀_국내출생": "Child (born in Korea)", "자녀_귀화인지외국국적": "Child (naturalized/foreign)",
             "기타동거인_내국인": "Other cohabitant (Korean)", "기타동거인_외국인": "Other cohabitant (foreign)"}
    def export_multicultural():
        mc = json.load(open(f"{SITE}/mois/multicultural_eupmyeondong.json", encoding="utf-8"))["by_eupmyeondong"]
        rows, agg = [], {}    # agg: (y,sido,sg,cat) -> n  (시군구 집계본)
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
    export_eupmyeondong_broad()   # 가장 큼(코드 join) — 마지막
    print("done.")


if __name__ == "__main__":
    summary_sigungu_and_sido()
    summary_eupmyeondong()
    export_mois_csvs()
