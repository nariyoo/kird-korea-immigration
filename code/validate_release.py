# -*- coding: utf-8 -*-
"""Re-check the released files, using nothing but the released files.

The build pipeline has its own audit, but that audit runs inside the working tree
and can only be trusted by someone who can rebuild the dataset. This script takes
the deposited CSVs alone and re-derives every published index from the published
counts, so a reuser can confirm the numbers without the raw yearbooks, without the
boundary files, and without running the pipeline.

    python validate_release.py                 # ./data next to this file
    python validate_release.py path/to/data

Requires pandas and numpy only. Exit code 0 when every check passes, 1 otherwise;
every failure prints the file, the check, and the worst offending row.

What is checked

    inventory      every documented file present, no extras
    keys           each file's logical key is unique
    dictionary     data_dictionary.csv covers every column, both directions
    bilingual      an English value wherever a Korean one appears
    identities     broad_total = non_naturalized + naturalized + children, and
                   non_naturalized = its five components; no cell blank that
                   these identities, or multicultural_households' own, determine
    rates          foreign_share_pct, settlement_rate_pct and the three dependence
                   rates recompute from the published counts
    indices        shannon_H, evenness, HHI, index_base_k, n_nationalities_observed
                   and continent_H recomputed from nationality_by_sigungu
    segregation    dissimilarity_D, isolation, interaction_korean and
                   theil_segregation_H recomputed from the counts and resident_pop,
                   and region_segregation's D and isolation by continent
    enclaves       every ethnic_enclaves row re-derived from the district counts and
                   resident_pop (>= 200, LQ >= 2, >= 30%), with no pair missing
    cross-file     district sums reconcile with the sido and national tables, the
                   broad-definition columns included, exactly
    age bases      age_sex_national carries registered 2006- and stay 2011- as
                   two labelled series, each year on the bands its edition prints,
                   and each sums to nationality_national for the same population,
                   line and year (the lines that name no nationality included),
                   with T = M + F + X in every cell
    crosswalks     every standard nationality name has a row of its own, every
                   country a data file names has a row, every district-table line
                   carried on another district is listed, and every standard
                   name and every nationality line with people has a
                   language_weights row
    provinces      the 2006-2007 rows of nationality_by_sido add up to
                   summary_by_sido, and summary_by_sido's indices recompute from
                   nationality_by_sido in every year
    sub-districts  dependence rates are blank where their component is, and no
                   district's sub-districts add up to more than its broad_total;
                   broad_apportioned is True or False on every district row
    coverage       no README or dictionary line cites a year the data lacks

The Korean count convention, which the indices depend on: `resident_pop` is the
resident-registration population, a register of Korean nationals that never held
the foreign residents, so k_d = resident_pop and the district total is
t_d = resident_pop + registered_foreigners. Nothing is subtracted.
"""
import io
import math
import os
import re
import sys

import numpy as np
import pandas as pd

TOL = 5e-3          # 소수 셋째 자리로 실린 값이라 이만큼은 반올림 차이다
AGG = {"총계", "총합계", "소계", "계"}
# The yearbook's lines that hold people but name no nationality: 무국적, 미등록국가,
# 미상, a single 기타 line or column, and 한국. The national tables carry the status
# table's lines (2026-09-26) and the district files the district table's columns
# (2026-09-26, final audit), so every level adds up to the printed total. They are
# not nationalities: never counted as one, never ranked into the top 19.
# kept here on purpose, apart from kird.RESIDUAL_LINES, so the check does not
# inherit a pipeline slip; 국적불명, 국제연합 and 국제연합전문기구 (lines that name
# no country) joined both on 2026-09-26.
RESIDUAL_LINES = {"무국적", "기타", "미등록국가", "미상", "한국",
                  "국적불명", "국제연합", "국제연합전문기구"}

FILES = {
    "age_sex_national.csv": ["year", "population", "country", "gender", "age_group"],
    "children_by_age.csv": ["year", "sido", "sigungu", "age"],
    "crosswalk_country.csv": ["source_label"],
    "crosswalk_region.csv": None,
    "crosswalk_visa.csv": ["source_code"],
    "ethnic_enclaves.csv": ["year", "sido", "sigungu", "country"],
    "language_demand.csv": ["year", "scope", "sido", "sigungu", "language"],
    "language_weights.csv": ["country", "language"],
    "multicultural_households.csv": ["year", "sido", "sigungu", "eupmyeondong", "category"],
    "national_annual.csv": ["year"],
    "nationality_by_sido.csv": ["year", "sido", "country"],
    "nationality_by_sigungu.csv": ["year", "sido", "sigungu", "country"],
    "nationality_national.csv": ["year", "population", "country"],
    "naturalization_annual.csv": ["year", "type"],
    "naturalization_by_age.csv": ["year", "age", "type"],
    "naturalization_by_country.csv": ["year", "country", "type"],
    "region_segregation.csv": ["year", "continent"],
    "segregation_by_nationality.csv": ["year", "country"],
    "summary_by_eupmyeondong.csv": ["year", "sido", "sigungu", "eupmyeondong"],
    "summary_by_sido.csv": ["year", "sido"],
    "summary_by_sigungu.csv": ["year", "sido", "sigungu"],
    "visa_by_nationality.csv": ["year", "population", "country", "visa_code"],
    "diaspora_residence_by_sido.csv": ["year", "sido", "country"],
    "visa_by_sido.csv": ["year", "sido", "visa_code"],
    "visa_by_sigungu.csv": ["year", "sido", "sigungu", "visa_code"],
    "visa_national.csv": ["year", "population", "visa_code"],
}

FAILED = []
CHECKED = 0


def check(ok, label, detail=""):
    global CHECKED
    CHECKED += 1
    if ok:
        print("  ok    %s" % label)
    else:
        print("  FAIL  %s%s" % (label, ("  |  " + str(detail)) if detail else ""))
        FAILED.append(label)


def ent(vals):
    t = float(sum(vals))
    if t <= 0:
        return 0.0
    return -sum((v / t) * math.log(v / t) for v in vals if v > 0)


def worst(df, a, b, key_cols):
    d = (df[a] - df[b]).abs()
    i = d.idxmax()
    return "worst %s: published %s, recomputed %s" % (
        " ".join(str(df.loc[i, c]) for c in key_cols if c in df.columns),
        df.loc[i, a], round(float(df.loc[i, b]), 4))


# v1.1.0 이 쓰던 이름 -> 지금 이름. 옛 기탁본을 받은 사람도 그대로 돌릴 수 있게.
LEGACY_NAMES = {"national_annual.csv": "summary_national.csv"}


def find_file(data, name):
    """기탁본은 요약표 넷만 data/ 에 두고 나머지는 detailed_data/ 에 넣는다.
    한 단계 아래까지 찾고, 옛 이름도 받아 준다."""
    cands = [name]
    if name in LEGACY_NAMES:
        cands.append(LEGACY_NAMES[name])
    for c in cands:
        p = os.path.join(data, c)
        if os.path.exists(p):
            return p
    try:
        subs = [d for d in os.listdir(data)
                if os.path.isdir(os.path.join(data, d))]
    except OSError:
        subs = []
    for sub in sorted(subs):
        for c in cands:
            p = os.path.join(data, sub, c)
            if os.path.exists(p):
                return p
    return None


def resolve_data(path):
    """The folder the tables sit in. A downloaded deposit has README.md,
    data_dictionary.csv and data/ at its top and the tables under data/ and
    data/detailed_data/, two levels down, where find_file looks one level down. So
    pointed at that top folder, as the code README says to, this goes down to data/.
    3라운드 대조 (2026-09-27): run on the top folder the script reported 22 files
    missing and 3 checks failed; run on data/ it passed. Whichever of the folder and
    its data/ reaches more of the tables is used (the top folder reaches only the
    four summaries in data/), and data/ on a tie, as for the release folder."""
    sub = os.path.join(path, "data")
    if not os.path.isdir(sub):
        return path
    here = sum(find_file(path, f) is not None for f in FILES)
    there = sum(find_file(sub, f) is not None for f in FILES)
    return sub if there and there >= here else path


def load(data):
    out = {}
    missing = []
    for f in FILES:
        p = find_file(data, f)
        if p:
            out[f] = pd.read_csv(p, encoding="utf-8-sig")
        else:
            missing.append(f)
    if missing:
        print("  %d files not found: %s" % (len(missing), ", ".join(missing)))
    return out

# ---------------------------------------------------------------- checks
def check_inventory(data, d):
    """기탁본은 파일을 data/ 와 data/detailed_data/ 로 나눠 담으므로,
    한 단계 아래까지 세어야 한다. 기탁본에만 있는 난민 표 둘은 릴리스에
    없으므로 「문서에 없는 파일」로 세지 않는다."""
    have = set()
    for root, dirs, files in os.walk(data):
        if root.count(os.sep) - data.count(os.sep) > 1:
            continue
        have |= {f for f in files if f.endswith('.csv')}
    # v1.1.0 을 받은 사람의 폴더에는 옛 이름이 들어 있다. 지금 이름으로 세어 준다.
    for now, was in LEGACY_NAMES.items():
        if was in have:
            have.add(now)
    missing = sorted(set(FILES) - have)
    extra = sorted(f for f in have - set(FILES)
                   if not f.startswith('refugee_'))
    check(not missing, "inventory: every documented file present",
          "missing " + ", ".join(missing))
    check(not extra, "inventory: no undocumented file", "extra " + ", ".join(extra))


def check_keys(d):
    for f, key in FILES.items():
        if f not in d or not key:
            continue
        if any(k not in d[f].columns for k in key):
            check(False, "keys: %s" % f, "key column missing")
            continue
        n = int(d[f].duplicated(subset=key).sum())
        check(n == 0, "keys: %s unique on %s" % (f, "+".join(key)), "%d duplicates" % n)


def check_dictionary(data, d):
    p = os.path.join(data, "data_dictionary.csv")
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(data), "data_dictionary.csv")
    if not os.path.exists(p):
        check(False, "dictionary: data_dictionary.csv found")
        return
    dic = pd.read_csv(p, encoding="utf-8-sig")
    fcol = next((c for c in dic.columns if "file" in c.lower()), dic.columns[0])
    vcol = next((c for c in dic.columns if "variable" in c.lower() or "column" in c.lower()),
                dic.columns[1])
    documented = set()
    for _, r in dic.iterrows():
        for f in str(r[fcol]).replace("/", " ").split():
            f = f.strip()
            for v in str(r[vcol]).replace("/", " ").split():
                documented.add((f.replace(".csv", ""), v.strip().strip("()")))
    miss = []
    for f, df in d.items():
        stem = f.replace(".csv", "")
        for c in df.columns:
            base = c.replace("_en", "")
            if (stem, c) in documented or (stem, base) in documented:
                continue
            if any(stem.startswith(k) and (k, c) in documented for k, _ in documented):
                continue
            miss.append("%s.%s" % (stem, c))
    check(len(miss) <= 0, "dictionary: every released column documented",
          "%d undocumented: %s" % (len(miss), ", ".join(miss[:8])))


def check_bilingual(d):
    bad = []
    for f, df in d.items():
        for c in df.columns:
            if not c.endswith("_en"):
                continue
            ko = c[:-3]
            if ko not in df.columns:
                continue
            gap = df[ko].notna() & (df[ko].astype(str).str.strip() != "") & \
                (df[c].isna() | (df[c].astype(str).str.strip() == ""))
            if int(gap.sum()):
                bad.append("%s.%s %d rows" % (f, c, int(gap.sum())))
    check(not bad, "bilingual: an English value wherever a Korean one appears",
          "; ".join(bad[:6]))


def check_identities(d):
    for f in ("summary_by_sigungu.csv", "summary_by_sido.csv", "summary_by_eupmyeondong.csv"):
        df = d.get(f)
        if df is None or "broad_total" not in df.columns:
            continue
        parts = ["non_naturalized", "naturalized", "children"]
        if not all(c in df.columns for c in parts):
            continue
        sub = df.dropna(subset=["broad_total"] + parts)
        gap = (sub["broad_total"] - sub[parts].sum(axis=1)).abs()
        check(bool((gap <= 1).all()),
              "identity: %s broad_total = non_naturalized + naturalized + children" % f,
              "max gap %s" % (gap.max() if len(gap) else 0))
        comp = ["workers", "marriage_migrants", "students", "ethnic_koreans", "other_foreigners"]
        if all(c in df.columns for c in comp):
            sub = df.dropna(subset=["non_naturalized"] + comp)
            gap = (sub["non_naturalized"] - sub[comp].sum(axis=1)).abs()
            check(bool((gap <= 1).all()),
                  "identity: %s non_naturalized = its five components" % f,
                  "max gap %s" % (gap.max() if len(gap) else 0))


def check_determined_blanks(d):
    """No composition cell is blank where the published identities fix it.

    3라운드 대조 (2026-09-27). broad_total = non_naturalized + naturalized + children
    determines any one of the three that MOIS masks when the other two and the total
    are printed; the sub-district file left 394 such cells blank in 2016-2017 (2016
    강릉시 경포동: 303 - 290 - 11 = 2 naturalized), though it recovers a masked
    component under non_naturalized. And in multicultural_households the four
    household-member groups make 합계 and each two-part group its subtotal; the file
    carried none of the masked cells those identities fix (2022 강릉시 강동면: 결혼이민자
    13 - 9 = 4).
    """
    three = ["non_naturalized", "naturalized", "children"]
    for f in ("summary_by_sigungu.csv", "summary_by_sido.csv", "summary_by_eupmyeondong.csv"):
        df = d.get(f)
        if df is None or not all(c in df.columns for c in ["broad_total"] + three):
            continue
        blank = df[three].isna().sum(axis=1)
        bad = df[df["broad_total"].notna() & (blank == 1)]
        check(bad.empty, "identity: %s has no blank the broad_total identity determines" % f,
              "%d rows, e.g. %s" % (len(bad), bad[["year", "sigungu" if "sigungu" in bad
                                                   else "sido"] + three].head(2)
                                    .to_dict("records")))
    mc = d.get("multicultural_households.csv")
    if mc is None:
        return
    top = ["한국인배우자", "결혼이민자귀화자_소계", "자녀_소계", "기타동거인_소계"]
    pairs = [("결혼이민자귀화자_소계", "결혼이민자", "귀화자등"),
             ("자녀_소계", "자녀_귀화인지외국국적", "자녀_국내출생"),
             ("기타동거인_소계", "기타동거인_내국인", "기타동거인_외국인")]
    w = mc.pivot_table(index=["year", "sido", "sigungu", "eupmyeondong"], columns="category",
                       values="n", aggfunc="sum")
    for c in ["합계"] + top + [x for p in pairs for x in p]:
        if c not in w.columns:
            w[c] = np.nan
    have = w.notna()
    n_top = have[top].sum(axis=1)
    fixed = (have["합계"] & (n_top == 3)) | (~have["합계"] & (n_top == 4))
    for s, a, b in pairs:
        fixed |= (have[[s, a, b]].sum(axis=1) == 2)
    bad = w[fixed]
    check(bad.empty, "identity: multicultural_households has no absent cell its "
          "sub-district's printed cells determine",
          "%d dong-years, e.g. %s" % (len(bad), list(bad.index[:3])))


def check_multicultural_codes(d):
    """multicultural_households has the adm_code of every sub-district
    summary_by_eupmyeondong codes, however MOIS spells it in the other sheet.

    3라운드 대조 (2026-09-27): MOIS prints 신천1·2동 and 벌용동 in sheet 11 (this file)
    and 신천1.2동 and 벌룡동 in sheet 1-3 (summary_by_eupmyeondong) in 2016-2019, and
    dots five 대구 dongs differently in 2023, so the exact name join left 14
    dong-years without the code their counterpart carries.
    """
    mc, e = d.get("multicultural_households.csv"), d.get("summary_by_eupmyeondong.csv")
    if mc is None or e is None or "adm_code" not in mc.columns:
        return
    sep = re.compile(r"[\s·.,・ㆍᆞ‧･]")
    same = {"벌룡동": "벌용동"}

    def loose(v):
        n = sep.sub("", str(v))
        return same.get(n, n)

    code = {}
    for y, sg, nm, c in zip(e["year"], e["sigungu_code"], e["eupmyeondong"], e["adm_code"]):
        if pd.notna(c) and str(c).strip():
            code.setdefault((int(y), _code(sg), loose(nm)), set()).add(str(c))
    b = mc[mc["adm_code"].isna()].drop_duplicates(["year", "sigungu_code", "eupmyeondong"])
    miss = [(int(r.year), r.sigungu, r.eupmyeondong) for r in b.itertuples()
            if len(code.get((int(r.year), _code(r.sigungu_code), loose(r.eupmyeondong)),
                            ())) == 1]
    check(not miss, "codes: multicultural_households carries the adm_code of every "
          "sub-district summary_by_eupmyeondong codes", "%d dong-years, e.g. %s"
          % (len(miss), miss[:4]))


def check_broad_levels(d):
    """The MOIS broad-definition columns of the districts add up to their province
    row exactly, each district in the province it belonged to that year.

    3라운드 대조 (2026-09-27): the general districts of 2008-2015 took their shares of
    the city's published row each rounded on its own, so a city's gu missed the city
    by 1-3 people in a field and the district sums the province row by up to 6
    (2014 용인시: broad_total 23,589 against 23,592). The shares are now split by the
    largest-remainder rule.
    """
    sg, ss = d.get("summary_by_sigungu.csv"), d.get("summary_by_sido.csv")
    if sg is None or ss is None or "sigungu_code" not in sg.columns:
        return
    cols = [c for c in ("broad_total", "non_naturalized", "workers", "marriage_migrants",
                        "students", "ethnic_koreans", "other_foreigners", "naturalized",
                        "children", "foreign_resident_households")
            if c in sg.columns and c in ss.columns]
    lo = sg.assign(_p=sg["sigungu_code"].map(lambda v: _code(v)[:2])) \
        .groupby(["year", "_p"])[cols].sum(min_count=1)
    hi = ss.assign(_p=ss["sido_code"].map(_code)).groupby(["year", "_p"])[cols].sum(min_count=1)
    hi = hi[hi.index.get_level_values(0).isin(set(lo.index.get_level_values(0)))]
    j = lo.join(hi, lsuffix="_d", rsuffix="_p", how="inner")
    bad = []
    for c in cols:
        x = j[[c + "_d", c + "_p"]].dropna()
        off = x[(x[c + "_d"] - x[c + "_p"]).abs() > 0]
        bad += ["%s %s %s: %s vs %s" % (y, p, c, r[c + "_d"], r[c + "_p"])
                for (y, p), r in off.iterrows()]
    check(len(j) > 0 and not bad, "cross-file: the districts' broad-definition columns "
          "add up to their province row exactly (%d province-years)" % len(j),
          "%d cells, e.g. %s" % (len(bad), bad[:3]))


def check_rates(d):
    for f in ("summary_by_sigungu.csv", "summary_by_sido.csv"):
        df = d.get(f)
        if df is None:
            continue
        sub = df.dropna(subset=["foreign_share_pct", "registered_foreigners", "resident_pop"])
        sub = sub[sub["resident_pop"] > 0].copy()
        sub["_calc"] = sub["registered_foreigners"] / sub["resident_pop"] * 100
        gap = (sub["foreign_share_pct"] - sub["_calc"]).abs()
        check(bool((gap <= TOL + 5e-3).all()),
              "rate: %s foreign_share_pct = registered_foreigners / resident_pop" % f,
              worst(sub.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                    "foreign_share_pct", "_calc", ["year", "sido", "sigungu"]))
        if "settlement_rate_pct" in sub.columns and "naturalized" in sub.columns:
            s2 = sub.dropna(subset=["settlement_rate_pct", "naturalized", "children",
                                    "broad_total"])
            s2 = s2[s2["broad_total"] > 0].copy()
            s2["_calc"] = (s2["naturalized"] + s2["children"]) / s2["broad_total"] * 100
            gap = (s2["settlement_rate_pct"] - s2["_calc"]).abs()
            check(bool((gap <= 0.06).all()),
                  "rate: %s settlement_rate_pct = (naturalized + children) / broad_total" % f,
                  "max gap %.3f" % (gap.max() if len(gap) else 0))


def district_counts(d):
    """year -> (sido, sigungu) -> {country: n}, aggregate rows dropped."""
    nat = d.get("nationality_by_sigungu.csv")
    if nat is None:
        return {}
    nat = nat[~nat["sigungu"].isin(AGG) & ~nat["sido"].isin(AGG)]
    out = {}
    for (y, sd, sg, c), n in nat.groupby(["year", "sido", "sigungu", "country"])["n"].sum().items():
        if n:
            out.setdefault(y, {}).setdefault((sd, sg), {})[c] = float(n)
    return out


def national_top19(cnt):
    """그 해 전국 합에서 고른 상위 19개국. 지수는 이 집합 위에서 계산된다.

    2008-2013 연감이 시군구 단위에서 상위 19개국과 잔여 한 칸만 싣기 때문에,
    2014 이후도 같은 밑변으로 줄여야 계열이 이어진다. 구마다 자기 상위 19개를
    고르는 것이 아니다.
    """
    out = {}
    for y, blk in cnt.items():
        agg = {}
        for cs in blk.values():
            for c, v in cs.items():
                agg[c] = agg.get(c, 0.0) + v
        # the lines that name no nationality (기타, 무국적, 미등록국가) are never
        # ranked; they sit in the residual bin
        out[y] = set([c for c, _ in sorted(agg.items(), key=lambda x: -x[1])
                      if c not in RESIDUAL_LINES][:19])
    return out


def check_indices(d):
    cnt = district_counts(d)
    sm = d.get("summary_by_sigungu.csv")
    if not cnt or sm is None:
        return
    tops = national_top19(cnt)
    rows = []
    for _, r in sm.iterrows():
        cs = cnt.get(r["year"], {}).get((r["sido"], r["sigungu"]))
        if not cs:
            continue
        top = tops.get(r["year"], set())
        base = [v for c, v in cs.items() if c in top]
        base.append(sum(v for c, v in cs.items() if c not in top))
        base = [v for v in base if v > 0]
        H = ent(base)
        S = len(base)
        rows.append({
            "year": r["year"], "sido": r["sido"], "sigungu": r["sigungu"],
            "shannon_H": r.get("shannon_H"), "_H": H,
            "evenness": r.get("evenness"), "_J": (H / math.log(S)) if S > 1 else 0.0,
            "HHI": r.get("HHI"), "_HHI": sum((v / sum(base)) ** 2 for v in base),
            "index_base_k": r.get("index_base_k"), "_k": S,
            "n_nationalities_observed": r.get("n_nationalities_observed"),
            # 기타는 나라가 아니라 잔여 칸이므로 세지 않는다. 무국적·미등록국가도
            # 국적이 아니다(2026-09-26부터 시군구 파일에 실린다).
            "_obs": len([1 for c, v in cs.items() if v > 0 and c not in RESIDUAL_LINES]),
        })
    df = pd.DataFrame(rows).dropna(subset=["shannon_H"])
    for pub, calc, tol, name in (("shannon_H", "_H", 6e-3, "shannon_H"),
                                 ("evenness", "_J", 6e-3, "evenness"),
                                 ("HHI", "_HHI", 6e-3, "HHI")):
        sub = df.dropna(subset=[pub])
        gap = (sub[pub] - sub[calc]).abs()
        check(bool((gap <= tol).all()),
              "index: summary_by_sigungu.%s recomputes from nationality_by_sigungu" % name,
              worst(sub.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                    pub, calc, ["year", "sido", "sigungu"]))
    for pub, calc, name in (("index_base_k", "_k", "index_base_k"),
                            ("n_nationalities_observed", "_obs", "n_nationalities_observed")):
        sub = df.dropna(subset=[pub])
        bad = int((sub[pub] != sub[calc]).sum())
        check(bad == 0, "count: summary_by_sigungu.%s recomputes" % name,
              "%d rows differ" % bad)


def check_continent(d):
    cnt = district_counts(d)
    sm = d.get("summary_by_sigungu.csv")
    seg = d.get("segregation_by_nationality.csv")
    if not cnt or sm is None or seg is None:
        return
    c2c = dict(zip(seg["country"], seg["continent"]))
    tops = national_top19(cnt)
    rows = []
    for _, r in sm.iterrows():
        cs = cnt.get(r["year"], {}).get((r["sido"], r["sigungu"]))
        pop = r.get("resident_pop")
        if not cs or not pop or pd.isna(pop) or pd.isna(r.get("continent_H")):
            continue
        top = tops.get(r["year"], set())
        by = {}
        for c, v in cs.items():
            region = c2c.get(c, "기타") if c in top else "기타"
            by[region] = by.get(region, 0.0) + v
        by["동아시아"] = by.get("동아시아", 0.0) + float(pop)   # 내국인은 주민등록 그대로
        rows.append({"year": r["year"], "sido": r["sido"], "sigungu": r["sigungu"],
                     "continent_H": r["continent_H"], "_C": ent(list(by.values()))})
    df = pd.DataFrame(rows)
    if df.empty:
        return
    gap = (df["continent_H"] - df["_C"]).abs()
    check(bool((gap <= 6e-3).all()),
          "index: summary_by_sigungu.continent_H recomputes with k = resident_pop",
          worst(df.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                "continent_H", "_C", ["year", "sido", "sigungu"]))


def check_segregation(d):
    cnt = district_counts(d)
    sm = d.get("summary_by_sigungu.csv")
    seg = d.get("segregation_by_nationality.csv")
    if not cnt or sm is None or seg is None:
        return
    pop = {(r["year"], r["sido"], r["sigungu"]): r["resident_pop"]
           for _, r in sm.iterrows() if not pd.isna(r.get("resident_pop"))}
    rows = []
    for y, blk in cnt.items():
        ks = [(sd, sg) for (sd, sg) in blk if (y, sd, sg) in pop]
        if not ks:
            continue
        k = {p: float(pop[(y,) + p]) for p in ks}
        t = {p: k[p] + sum(blk[p].values()) for p in ks}
        K = sum(k.values())
        nat_tot = {}
        for p in ks:
            for c, v in blk[p].items():
                nat_tot[c] = nat_tot.get(c, 0.0) + v
        for c, X in nat_tot.items():
            if X <= 0:
                continue
            D = 0.5 * sum(abs(blk[p].get(c, 0.0) / X - k[p] / K) for p in ks)
            iso = sum((blk[p].get(c, 0.0) / X) * (blk[p].get(c, 0.0) / t[p]) for p in ks)
            inter = sum((blk[p].get(c, 0.0) / X) * (k[p] / t[p]) for p in ks)
            rows.append({"year": y, "country": c, "_D": D, "_iso": iso, "_int": inter})
    calc = pd.DataFrame(rows)
    if calc.empty:
        return
    # The rows: every nationality with a national total of 100 or more that year over
    # the districts the indices use, and no other (1라운드 수정, 2026-09-26: the file
    # kept an old key set, so 아르헨티나 2018 (101) and 짐바브웨 2023 (105) had none).
    tots = {}
    for y, blk in cnt.items():
        for (sd, sg), cs in blk.items():
            if (y, sd, sg) not in pop:
                continue
            for c, v in cs.items():
                tots[(y, c)] = tots.get((y, c), 0.0) + v
    years = set(seg["year"].astype(int))
    want = {k for k, v in tots.items() if int(k[0]) in years and v >= 100
            and k[1] not in RESIDUAL_LINES}
    have = {(int(y), c) for y, c in zip(seg["year"], seg["country"])}
    want = {(int(y), c) for y, c in want}
    check(want == have,
          "segregation: one row per nationality of 100 or more, and no other",
          "missing %s; extra %s" % (sorted(want - have)[:6], sorted(have - want)[:6]))
    m = seg.merge(calc, on=["year", "country"], how="inner")
    for pub, cc, tol, name in (("dissimilarity_D", "_D", 1.5e-3, "dissimilarity_D"),
                               ("isolation", "_iso", 1.5e-4, "isolation"),
                               ("interaction_korean", "_int", 1.5e-4, "interaction_korean")):
        sub = m.dropna(subset=[pub])
        gap = (sub[pub] - sub[cc]).abs()
        check(bool((gap <= tol).all()),
              "segregation: %s recomputes" % name,
              worst(sub.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                    pub, cc, ["year", "country"]))


def check_theil(d):
    cnt = district_counts(d)
    sm = d.get("summary_by_sigungu.csv")
    na = d.get("national_annual.csv")
    if not cnt or sm is None or na is None or "theil_segregation_H" not in na.columns:
        return
    pop = {(r["year"], r["sido"], r["sigungu"]): r["resident_pop"]
           for _, r in sm.iterrows() if not pd.isna(r.get("resident_pop"))}
    rows = []
    for y, blk in cnt.items():
        ks = [(sd, sg) for (sd, sg) in blk if (y, sd, sg) in pop]
        if len(ks) < 10:
            continue
        agg = {}
        for p in ks:
            for c, v in blk[p].items():
                agg[c] = agg.get(c, 0.0) + v
        top = set([c for c, _ in sorted(agg.items(), key=lambda x: -x[1])
                   if c not in RESIDUAL_LINES][:19])
        grp, tot, mix = {}, {}, {}
        for p in ks:
            m = {c: v for c, v in blk[p].items() if c in top}
            m["기타"] = sum(v for c, v in blk[p].items() if c not in top)
            m["KOR"] = float(pop[(y,) + p])
            mix[p] = list(m.values())
            tot[p] = sum(m.values())
            for c, v in m.items():
                grp[c] = grp.get(c, 0.0) + v
        T = sum(tot.values())
        E = ent(list(grp.values()))
        H = sum((tot[p] / T) * (E - ent(mix[p])) for p in ks if tot[p] > 0) / E
        rows.append({"year": y, "_T": H})
    calc = pd.DataFrame(rows)
    m = na.merge(calc, on="year", how="inner").dropna(subset=["theil_segregation_H"])
    if m.empty:
        return
    gap = (m["theil_segregation_H"] - m["_T"]).abs()
    check(bool((gap <= 1.5e-4).all()),
          "segregation: national_annual.theil_segregation_H recomputes (top-19 basis)",
          worst(m.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                "theil_segregation_H", "_T", ["year"]))


def check_cross_file(d):
    sm = d.get("summary_by_sigungu.csv")
    nat = d.get("nationality_by_sigungu.csv")
    na = d.get("national_annual.csv")
    if sm is not None and nat is not None:
        a = nat[~nat["sigungu"].isin(AGG)].groupby(["year", "sido", "sigungu"])["n"].sum()
        b = sm.set_index(["year", "sido", "sigungu"])["registered_foreigners"]
        j = pd.concat([a.rename("nat"), b.rename("sum")], axis=1).dropna()
        gap = (j["nat"] - j["sum"]).abs()
        check(bool((gap <= 1).all()),
              "cross-file: nationality_by_sigungu sums to summary_by_sigungu.registered_foreigners",
              "max gap %s at %s" % (gap.max(), gap.idxmax() if len(gap) else ""))
    if sm is not None and na is not None:
        a = sm.groupby("year")["registered_foreigners"].sum()
        b = na.set_index("year")["foreign_total"]
        j = pd.concat([a.rename("dist"), b.rename("nat")], axis=1).dropna()
        gap = (j["dist"] - j["nat"]).abs()
        check(bool((gap <= 1).all()),
              "cross-file: national_annual.foreign_total = district sum",
              "max gap %s" % (gap.max() if len(gap) else 0))

    # 층 나란한 짝: 시도 표는 시군구 표를 그 도 안에서 더한 것이라고 문서가 적는다.
    # 총합만 보면 못 잡는다. 2026-08-26에 nationality_by_sido.csv 2014 경기도에서
    # 71명이 사라져 있었고(튀르키예 67, 벨라루스 2, 조지아 2), 그 해 총합 차이도
    # 71뿐이라 눈에 안 띄었다. **줄 단위로** 맞춰 본다.
    # 2026-09-26 (3차 대조): 시도 표는 시군구를 **그 해 속한 시도**(시군구 코드 앞
    # 2자리)로 더한 것이다. 이름으로 더하면 군위군이 2008-2022년 대구에 들어가고
    # (시군구 파일은 군위군을 모든 해 대구광역시로 적는다) 세종이 2012년 전에 시도가
    # 된다. 그래서 (연도, 시도 코드)로 맞춘다.
    for lo, hi, keys in (("nationality_by_sigungu.csv", "nationality_by_sido.csv",
                          ["year", "sido_code", "country"]),
                         ("visa_by_sigungu.csv", "visa_by_sido.csv",
                          ["year", "sido_code", "visa_code"])):
        a_, b_ = d.get(lo), d.get(hi)
        if a_ is None or b_ is None:
            continue
        a_ = a_[~a_["sigungu"].isin(AGG)].assign(
            sido_code=a_["sigungu_code"].map(lambda v: _code(v)[:2]))
        a = a_.groupby(keys)["n"].sum()
        # the years with a district table; nationality_by_sido's 2006-2007 rows are the
        # yearbook's province table (check_early_provinces holds them to the summary)
        b_ = b_[b_["year"].isin(set(a_["year"]))]
        b = b_.assign(sido_code=b_["sido_code"].map(_code)).groupby(keys)["n"].sum()
        j = pd.concat([a.rename("lo"), b.rename("hi")], axis=1).fillna(0)
        gap = (j["lo"] - j["hi"]).abs()
        n_bad = int((gap > 0).sum())
        check(n_bad == 0,
              "cross-file: %s summed by %s = %s"
              % (lo, "/".join(keys[1:]), hi),
              "%d rows differ, worst %s at %s"
              % (n_bad, gap.max() if len(gap) else 0,
                 gap.idxmax() if len(gap) else ""))




# Where the age table and the nationality table of the same edition disagree for
# a documented reason. Keys are (population, year, country); the value is the
# number by which the age table exceeds nationality_national on that line. Every
# other (population, year, country) must match exactly, the lines that name no
# nationality (무국적, 기타, 미등록국가, 미상, 한국) included: since 2026-09-26
# (1라운드 수정) the age file carries them as the status tables do, where it had
# dropped them (106-337 people a year) and this check had left them out.
#   stay 2022  The age table lists 홍콩거주난민 (17), which the release folds into
#              홍콩; the status table has no such row and holds those 17 in its
#              기타 line. The status table does not say which statuses they hold,
#              so they cannot be placed.
#   stay 2014-2016, 2018  The age table's printed grand total exceeds the sum of
#              its own rows by 4, 3, 2 and 1 persons (no row, no sex holds them);
#              the status table of the same edition counts them in its 기타 line.
# (stay 2014 used to be here for the 자격없음(0-0) column, 434 persons, which the
#  status parser did not read; it is now visa code X00. stay 2019 used to be here
#  for one person: the age table's 제3의성 row under 오스트레일리아, which the age
#  file now carries as gender X.)
AGE_BASE_KNOWN = {("stay", 2022, "홍콩"): 17, ("stay", 2022, "기타"): -17,
                  ("stay", 2014, "기타"): -4, ("stay", 2015, "기타"): -3,
                  ("stay", 2016, "기타"): -2, ("stay", 2018, "기타"): -1}



def check_age_bases(d):
    """age_sex_national 은 두 모집단을 따로 싣는다. 섞이면 안 된다.

    2026-09-25 까지 이 파일은 2009-2013 을 등록외국인 표에서, 2014 이후를 체류외국인
    표에서 가져와 한 계열로 싣고 있었다. 미국이 2013년 23,990 에서 2014년 136,663 이
    되었다. 그래서 (1) population 이 두 값만 갖는지, (2) 각 계열이 문서가 적는 해를
    빠짐없이 갖는지, (3) 해·모집단·국적마다 T 의 연령 합이 nationality_national 과
    같은지를 본다. 차이는 AGE_BASE_KNOWN 에 적은 원인만 봐준다.
    """
    a = d.get("age_sex_national.csv")
    n = d.get("nationality_national.csv")
    if a is None:
        return
    pops = set(a["population"].dropna().unique()) if "population" in a.columns else set()
    check(pops == {"registered", "stay"},
          "age bases: age_sex_national.population is registered / stay",
          "found %s" % sorted(pops))
    if pops != {"registered", "stay"}:
        return
    last = int(a["year"].max())
    # registered from the 2006 edition since 2026-09-27 (5라운드 대조): the raw tables
    # print the 2006-2008 registered population by nationality, age and sex, and
    # until then the file started in 2009
    FIRST = {"registered": 2006, "stay": 2011}
    for pop, first in FIRST.items():
        ys = set(a.loc[a["population"] == pop, "year"].astype(int))
        want = set(range(first, last + 1))
        check(ys == want, "age bases: %s covers %d-%d" % (pop, first, last),
              "missing %s, extra %s" % (sorted(want - ys), sorted(ys - want)))
    # Every year carries the bands its edition prints and no others: 0-4 ... 60+
    # from 2009; 0-5 ... 56-60 and an open band in 2006-2008, 60+ as the 2006 and
    # 2007 editions print it (60세이상), 61+ as the 2008 edition does (61세 이상)
    std = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
           "40-44", "45-49", "50-54", "55-59", "60+"]
    old = ["0-5", "6-10", "11-15", "16-20", "21-25", "26-30", "31-35", "36-40",
           "41-45", "46-50", "51-55", "56-60"]
    want_b = lambda y: set(std) if y >= 2009 else set(old) | {"61+" if y == 2008 else "60+"}
    got_b = a.groupby(["population", "year"])["age_group"].agg(lambda s: set(s))
    off = ["%s %d: extra %s, missing %s" % (p, y, sorted(g - want_b(y)), sorted(want_b(y) - g))
           for (p, y), g in got_b.items() if g != want_b(int(y))]
    check(not off, "age bases: each year on the 13 bands its edition prints "
          "(0-4 ... 60+ from 2009; 0-5 ... 56-60 and 60+ or 61+ in 2006-2008)", off[:4])
    if n is None:
        return
    t = (a[a["gender"] == "T"].groupby(["population", "year", "country"])["n"].sum())
    m = n.set_index(["population", "year", "country"])["n"]
    j = pd.concat([t.rename("age"), m.rename("nat")], axis=1)
    keep = [(p in FIRST and y >= FIRST[p]) for p, y, _ in j.index]
    j = j[keep].fillna(0)
    j["gap"] = j["age"] - j["nat"]
    bad = j[j["gap"] != 0]
    unexplained = ["%s %d %s: %+d" % (p, y, c, g) for (p, y, c), g in bad["gap"].items()
                   if AGE_BASE_KNOWN.get((p, int(y), c)) != g]
    have = {(p, int(y), c) for p, y, c in bad.index}
    missing = [k for k in AGE_BASE_KNOWN if k not in have]
    check(not unexplained and not missing,
          "age bases: T summed over ages = nationality_national, per population, "
          "year and country, the lines that name no nationality included",
          "unexplained %s; documented but absent %s" % (unexplained[:6], missing))
    # T = M + F + X on every line and band, X being the 제3의성 row the stay table
    # prints from 2019 (1라운드 수정: it was dropped, and 2019's derived total
    # missed the one person under 오스트레일리아).
    if "gender" in a.columns:
        w = a.pivot_table(index=["population", "year", "country", "age_group"],
                          columns="gender", values="n", aggfunc="sum").fillna(0)
        parts = [g for g in ("M", "F", "X") if g in w.columns]
        off = w[w.get("T", 0) != w[parts].sum(axis=1)] if parts else w.iloc[:0]
        odd = sorted(set(a["gender"].dropna()) - {"T", "M", "F", "X"})
        check(off.empty and not odd,
              "age bases: T = M + F + X in every cell (X = 제3의성)",
              "%d cells differ, e.g. %s; unknown sex codes %s"
              % (len(off), list(off.index[:3]), odd))


def check_country_labels(d):
    """`country_en` 은 `country` 의 함수여야 하고, 그 반대도 그래야 한다.

    한 국적이 파일 안에서 영문 이름 둘을 갖거나(age_sex_national 의 튀르키예가
    2009-2013 Turkey · 2014-2024 Türkiye 였다), 한 영문 이름이 한글 이름 둘을
    가리키면(자이르 · 콩고민주공화국이 둘 다 DR Congo 였다) 영문 라벨로 join 하는
    쪽에서 조용히 행이 늘거나 준다. 2026-08-26에 둘 다 찾아 고쳤다.
    """
    for name, df in sorted(d.items()):
        if name == "crosswalk_country.csv":
            continue
        if not {"country", "country_en"} <= set(df.columns):
            continue
        many_en = df.groupby("country")["country_en"].nunique()
        many_en = many_en[many_en > 1]
        many_ko = df.groupby("country_en")["country"].nunique()
        many_ko = many_ko[many_ko > 1]
        check(len(many_en) == 0 and len(many_ko) == 0,
              "labels: %s pairs country and country_en one to one" % name,
              "country with 2+ English %s; English with 2+ country %s"
              % (list(many_en.index)[:3], list(many_ko.index)[:3]))


def check_coverage_text(data, d):
    """산문이 자료에 없는 해를 연도 범위로 적고 있지 않은가.

    자료사전과 README 는 손으로 적은 연도 범위를 잔뜩 담고 있어서, 패널이 한 해
    줄거나 늘 때 조용히 낡는다. 실제로 실린 마지막 해를 자료에서 읽고, 그보다
    뒤의 해를 가리키는 「20xx-20yy」 꼴이 있으면 잡는다.
    """
    years = set()
    for df in d.values():
        if "year" in df.columns:
            years |= {int(v) for v in df["year"].dropna().unique()}
    if not years:
        check(False, "coverage: any year column found")
        return
    last = max(years)
    rng = re.compile(r'(?:19|20)\d{2}\s*[-\u2013~]\s*((?:19|20)\d{2})')
    bad = []
    for name in ("data_dictionary.csv", "data_dictionary_ko.csv", "README.md",
                 "datapackage.json"):
        for base in (data, os.path.dirname(data)):
            p = os.path.join(base, name)
            if not os.path.exists(p):
                continue
            txt = io.open(p, encoding="utf-8-sig", errors="replace").read()
            for m in rng.finditer(txt):
                if int(m.group(1)) > last:
                    a = max(0, m.start() - 40)
                    bad.append("%s: …%s…" % (name, " ".join(
                        txt[a:m.end() + 20].split())))
            break
    check(not bad, "coverage: no prose cites a year past %d" % last,
          "%d places: %s" % (len(bad), " | ".join(bad[:3])))

def check_visa_basis(data, d):
    """The subnational visa tables are registered-basis, so F-4 is zero in them.

    That zero looks like missing data and is not: holders of the F-4
    overseas-Korean status file a place-of-residence report under the Overseas
    Koreans Act rather than a foreign-resident registration, so they never enter
    the registered basis. Nationally they are the largest single status on the
    staying basis. The check holds the fact and its explanation together, so
    neither can drift away from the other without failing.
    """
    g = d.get("visa_by_sigungu.csv")
    n = d.get("visa_national.csv")
    if g is not None:
        f4 = float(g.loc[g["visa_code"] == "F4", "n"].sum())
        check(f4 == 0,
              "visa basis: F-4 absent from visa_by_sigungu, as the registered basis requires",
              "district tables now carry %g F-4, so the basis changed" % f4)
    if g is not None and n is not None and "population" in n.columns:
        reg = float(n[(n["population"] == "registered") & (n["year"] == 2024)]["n"].sum())
        dis = float(g[g["year"] == 2024]["n"].sum())
        gap = abs(reg - dis) / reg * 100 if reg else 0.0
        check(gap < 5,
              "visa basis: 2024 district sum reconciles with the registered national total",
              "%.1f%% apart (%g against %g)" % (gap, dis, reg))
    rd = os.path.join(os.path.dirname(os.path.abspath(data.rstrip("/\\"))), "README.md")
    txt = io.open(rd, encoding="utf-8").read() if os.path.exists(rd) else ""
    check("F-4" in txt and "거소신고" in txt,
          "visa basis: README explains why F-4 is absent from the district tables",
          "the zero is left to look like missing data")



def check_naturalization(d):
    """국적별·연령별 패널을 더하면 연도별 추이 표의 귀화와 같아야 한다.

    2026-09-25: 2017년 국적별 합이 11,443 으로 연도별 표의 10,086 보다 1,357 많았다.
    그 해 연보의 중국 행이 「한국계 포함」인데 한국계중국인 행을 또 더했기 때문이다.
    README 는 그것을 「연보의 국적 행이 대륙 소계보다 많다」고 원자료 탓으로 적고
    있었다. 연보의 총계는 해마다 연도별 표와 같다. 그러니 차이는 0 이어야 한다.
    """
    ann = d.get("naturalization_annual.csv")
    if ann is None:
        return
    # One spelling per type across the three files, so they join on `type`. The
    # annual file printed its trend table's 회복 and 국적취득 (인지) / (재취득) until
    # 2026-09-26 (1라운드 수정); the panels print 국적회복 and 국적취득(인지) / (재취득).
    # 귀화 (the annual name for all routes) and the total row are the annual file's own.
    pt = set()
    for name in ("naturalization_by_country.csv", "naturalization_by_age.csv"):
        if d.get(name) is not None:
            pt |= set(d[name]["type"].unique())
    if pt:
        odd = sorted(set(ann["type"].unique()) - pt - {"귀화", "총합계", "총계", "합계", "계"})
        check(not odd, "naturalization: naturalization_annual names each type as the panels do",
              "annual-only spellings %s" % odd)
    a = ann[ann["type"] == "귀화"].set_index("year")["n"]
    for name, raw_ok in (("naturalization_by_country.csv", {}),
                         ("naturalization_by_age.csv", {2012: -1})):
        df = d.get(name)
        if df is None:
            continue
        sub = df[df["type"] == "귀화소계"].groupby("year")["n"].sum()
        old = df[df["type"] == "귀화"].groupby("year")["n"].sum()
        s = sub.combine_first(old)
        bad = {int(y): int(s[y] - a[y]) for y in a.index if y in s.index
               and s[y] - a[y] != raw_ok.get(int(y), 0)}
        check(not bad, "naturalization: %s all routes summed = naturalization_annual 귀화" % name,
              "year: gap %s" % bad)
    # 2026-09-26: every processing type, not only 귀화, and no year the annual series
    # cannot vouch for. The 2009 and 2010 editions' detail tables were cumulative
    # 1991-to-date and sat in the panels as if annual (7.3x and 9.6x the year's total).
    # The cells listed are differences between an edition's detail tables and the
    # newest edition's revised trend table, each read in the raw files (see
    # 07_build_naturalization.py).
    # the three files name a type alike since 2026-09-26 (1라운드 수정); the annual
    # file had printed the trend table's 회복 and 국적취득 (인지) / (재취득)
    t2a = {"국적회복": "국적회복", "국적판정": "국적판정", "국적상실": "국적상실",
           "국적이탈": "국적이탈", "국적취득(인지)": "국적취득(인지)",
           "국적취득(재취득)": "국적취득(재취득)", "국적선택": "국적선택", "국적보유": "국적보유"}
    known = {("naturalization_by_age.csv", 2012, "국적상실"): 1,
             ("naturalization_by_country.csv", 2013, "국적취득"): -343,
             ("naturalization_by_age.csv", 2013, "국적취득"): -343}
    for f in ("naturalization_by_country.csv", "naturalization_by_age.csv"):
        for t, dd in (("국적보유", -3), ("국적상실", 1), ("국적선택", -5), ("국적취득(인지)", -2)):
            known[(f, 2018, t)] = dd
    A = {(int(r.year), r.type): int(r.n) for r in ann.itertuples()}
    for name in ("naturalization_by_country.csv", "naturalization_by_age.csv"):
        df = d.get(name)
        if df is None:
            continue
        early = sorted(int(y) for y in df["year"].unique() if int(y) < int(ann["year"].min()))
        check(not early, "naturalization: %s starts no earlier than the annual series" % name,
              "years with no annual control: %s" % early)
        bad = {}
        for (y, t), n in df.groupby(["year", "type"])["n"].sum().items():
            y = int(y)
            if t == "국적취득":
                ref = A.get((y, "국적취득(인지)"), 0) + A.get((y, "국적취득(재취득)"), 0)
            elif t in t2a:
                ref = A.get((y, t2a[t]))
            else:
                continue
            if ref is None:
                continue
            if int(n) - ref != known.get((name, y, t), 0):
                bad[(y, t)] = int(n) - ref
        check(not bad, "naturalization: %s every processing type = naturalization_annual "
              "(11 raw-traced cells excepted)" % name, bad)
    c = d.get("naturalization_by_country.csv")
    if c is not None:
        k = c[c["type"].isin(["귀화소계", "귀화"])].pivot_table(
            index="year", columns="country", values="n", aggfunc="sum")
        if {"중국", "한국계중국인"} <= set(k.columns):
            r = (k["한국계중국인"] / k["중국"]).dropna()
            # 2017 is MOJ's own split (0.47), documented; every other year is 1.3-4.0
            odd = {int(y): round(v, 2) for y, v in r.items()
                   if not (1.0 <= v <= 5.0) and int(y) != 2017}
            check(not odd, "naturalization: Korean-Chinese / China ratio within 1-5 "
                  "(2017 documented)", odd)


# E-8 is two statuses: 연수취업 to 2009 (carried as E8T), 계절근로 from 2021.
VISA_ERAS = {"E8T": (None, 2009), "E8": (2021, None), "X00": (2014, 2014)}


def check_one_label_per_code(d):
    """한 해의 시군구 코드 하나는 모든 파일에서 한 이름을 가져야 한다.

    2026-09-26: 부천시(41190)가 시군구 층 파일에서는 해마다 「부천시」인데 읍면동 층
    두 파일에서는 2015·2024년에만 「부천시 원미구」 등 셋으로 갈라져, 이름으로
    거르거나 잇는 쪽에서 그 두 해의 부천이 사라졌다.
    """
    seen = {}
    for name, df in sorted(d.items()):
        if not {"year", "sigungu", "sigungu_code"} <= set(df.columns):
            continue
        sub = df[["year", "sigungu", "sigungu_code"]].dropna().drop_duplicates()
        for r in sub.itertuples():
            seen.setdefault((int(r.year), str(r.sigungu_code).split(".")[0]),
                            {}).setdefault(r.sigungu, set()).add(name)
    bad = {k: {lab: sorted(f) for lab, f in v.items()} for k, v in seen.items()
           if len(v) > 1}
    check(not bad, "labels: one sigungu name per (year, sigungu_code) across every file",
          "%d codes, e.g. %s" % (len(bad), list(bad.items())[:2]))


def check_single_district_province(d):
    """A province with one district is that district, in every year.

    2026-09-26 (4차 대조): 세종 2012 was 2,271 in summary_by_sido and 2,360 in
    summary_by_sigungu, 2013 2,462 against 2,475. The yearbook still printed a
    residual 연기군 line under 충청남도 in those two years; the district files counted
    it in 세종시 and the province file left it in 충청남도.
    """
    sd, sg = d.get("summary_by_sido.csv"), d.get("summary_by_sigungu.csv")
    if sd is None or sg is None:
        return
    sg = sg.assign(_p=sg["sigungu_code"].map(lambda v: _code(v)[:2]))
    sd = sd.assign(_p=sd["sido_code"].map(_code))
    one = sg.groupby(["year", "_p"]).filter(lambda g: len(g) == 1)
    j = one.merge(sd, on=["year", "_p"], suffixes=("_d", "_s"))
    cols = [c for c in ("registered_foreigners", "resident_pop") if c + "_d" in j.columns]
    bad = []
    for c in cols:
        a, b = j[c + "_d"], j[c + "_s"]
        m = ~((a == b) | (a.isna() & b.isna()))
        bad += ["%s %d %s: %s vs %s" % (r["sido_s"], r["year"], c, r[c + "_d"], r[c + "_s"])
                for _, r in j[m].iterrows()]
    check(len(j) > 0 and not bad,
          "cross-file: a single-district province equals its district every year "
          "(%d province-years)" % len(j), "; ".join(bad[:4]))


def check_visa_label_per_code(d):
    """One visa_label per (year, visa_code), in every file that carries labels.

    2026-09-26 (4차 대조): five F4 rows of visa_by_nationality (the 기타 line,
    2006-2010) read 재외동포(거소) while every other F4 row read 재외동포.
    """
    seen = {}
    for f in ("visa_by_nationality.csv", "visa_national.csv"):
        df = d.get(f)
        if df is None or "visa_label" not in df.columns:
            continue
        for (y, c), labs in df.groupby(["year", "visa_code"])["visa_label"]:
            seen.setdefault((int(y), str(c)), set()).update(labs.dropna().astype(str))
    bad = {k: sorted(v) for k, v in seen.items() if len(v) > 1}
    check(not bad, "labels: one visa_label per (year, visa_code) across the visa files",
          "%d codes, e.g. %s" % (len(bad), list(bad.items())[:3]))
    # 3라운드 대조 (2026-09-27): C2 (단기상용, 2006-2011) and M1 (군인, 2006-2009) had no
    # label, so the label column repeated the code, in English too for M1.
    bare = set()
    for f in ("visa_by_nationality.csv", "visa_national.csv", "crosswalk_visa.csv"):
        df = d.get(f)
        if df is None:
            continue
        for col in ("visa_label", "visa_label_en"):
            if col in df.columns:
                m = df[col].astype(str).str.strip() == df["visa_code"].astype(str).str.strip()
                bare |= {"%s %s" % (c, col) for c in df.loc[m, "visa_code"]}
    check(not bare, "labels: no visa_label or visa_label_en is the bare code", sorted(bare))


def check_visa_label_variants(d):
    """crosswalk_visa names the labels the editions print in place of the released one.

    4라운드 대조 (2026-09-27): the 2006-2012 editions print D-3 as 산업연수 and the
    release carries it as 기술연수, and crosswalk_visa had no row saying so; nine more
    codes are printed under another label in some edition. Each row that names one
    ('same code, label printed as ...') must carry its code's released label, and the
    ten printed labels must all be there. check_published_totals.status_variant_gate
    holds the rows to the raw tables edition by edition.
    """
    cv, vn = d.get("crosswalk_visa.csv"), d.get("visa_national.csv")
    if cv is None or vn is None:
        return
    head = "same code, label printed as "
    lab = vn.drop_duplicates("visa_code").set_index("visa_code")["visa_label"].to_dict()
    var = cv[cv["rule"].astype(str).str.startswith(head)]
    have = {(c, re.match(r"[^\s;,(]+", str(r)[len(head):]).group(0))
            for c, r in zip(var["visa_code"], var["rule"])}
    want = {("C3", "단기종합"), ("D3", "산업연수"), ("D7", "상사주재"), ("E10", "내항선원"),
            ("E2", "회화"), ("E2", "회화강사"), ("E7", "특정직업"), ("E8", "연수취업"),
            ("E9", "비취업"), ("G1", "기타")}
    off = [c for c, l in zip(var["visa_code"], var["visa_label"]) if lab.get(c) != l]
    check(want <= have and not off,
          "crosswalk_visa: every label an edition prints in place of the released one "
          "has a row, under the released label",
          "missing %s; label differs for %s" % (sorted(want - have), off))


def check_stata_labels(data):
    """The .dta files carry a label per column, and numbers as numbers.

    2026-09-26 (4차 대조): nationality_by_sido, nationality_national, visa_by_sido and
    visa_national each had one grouped dictionary row typed "mixed", so every column
    of the four .dta files carried the same label (the file's description, cut at 80
    characters) and n was stored as text.
    """
    p = os.path.join(data, "data_dictionary.csv")
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(data), "data_dictionary.csv")
    if not os.path.exists(p):
        return
    dic = pd.read_csv(p, encoding="utf-8-sig")
    odd = sorted(set(dic["type"].astype(str).str.lower()) - {"integer", "float", "string"})
    check(not odd, "dictionary: every row has one type (integer, float or string)", odd)
    numeric = set()
    for _, r in dic.iterrows():
        if str(r["type"]).lower() in ("integer", "float"):
            for f in str(r["file"]).split("/"):
                for v in str(r["variable"]).split("/"):
                    numeric.add((f.strip(), v.strip()))
    dtas = []
    for root, _dirs, files in os.walk(data):
        dtas += [os.path.join(root, f) for f in files if f.endswith(".dta")]
    if not dtas:
        return
    same, text = [], []
    for fp in sorted(dtas):
        name = os.path.basename(fp)[:-4] + ".csv"
        with pd.io.stata.StataReader(fp) as rd_:
            labs = rd_.variable_labels()
            df = rd_.read()
        vals = [labs.get(c, "") for c in df.columns]
        if len(vals) >= 3 and max(vals.count(v) for v in set(vals)) > len(vals) // 2:
            same.append(name)
        text += ["%s.%s" % (name, c) for c in df.columns
                 if (name, c) in numeric and not pd.api.types.is_numeric_dtype(df[c])]
    check(not same, "stata: no .dta gives most of its columns one shared label "
          "(%d files)" % len(dtas), same[:6])
    check(not text, "stata: columns the dictionary types as numbers are numeric in "
          "the .dta", text[:6])


def _code(v):
    """숫자로 읽힌 코드(27.0)와 빈칸(NaN)을 글자로 맞춘다."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).split(".")[0].strip()


def check_province_labels(d):
    """시도 이름과 시도 코드가 줄마다, 파일마다 같은 곳을 가리키는가.

    2026-09-26 (3차 대조). 두 가지가 걸렸다.
      * 세종시(시군구) 2008-2011 줄이 sido=세종특별자치시 에 sido_code=44(충청남도)를
        달아, 한 해 한 파일에서 44 가 두 이름을 가졌다.
      * 군위군(47720)이 법무부 시군구 파일에서는 모든 해 대구광역시, 행안부 파일
        (children_by_age, multicultural_households, summary_by_eupmyeondong)에서는
        2011-2022 경상북도라, 한 시군구 코드가 해마다 두 시도에 속했다.
    그리고 crosswalk_region 의 시도 대상 이름(강원특별자치도, 전북특별자치도)이
    자료에 한 번도 안 나오는 이름이었다.
    """
    pair, by_sgg, names = {}, {}, set()
    for name, df in sorted(d.items()):
        if not {"year", "sido", "sido_code"} <= set(df.columns):
            continue
        cols = ["year", "sido", "sido_code"] + (["sigungu_code"] if "sigungu_code"
                                               in df.columns else [])
        sub = df[cols].drop_duplicates()
        for r in sub.itertuples(index=False):
            y, sd, sc = int(r.year), str(r.sido), _code(r.sido_code)
            names.add(sd)
            pair.setdefault(("name", y, sd), {}).setdefault(sc, set()).add(name)
            if sc:
                pair.setdefault(("code", y, sc), {}).setdefault(sd, set()).add(name)
            if len(cols) == 4 and _code(r.sigungu_code):
                by_sgg.setdefault((y, _code(r.sigungu_code)), {})                       .setdefault((sd, sc), set()).add(name)
    bad = {k: {a: sorted(b) for a, b in v.items()} for k, v in pair.items() if len(v) > 1}
    check(not bad, "labels: one sido_code per (year, sido) and one sido per (year, "
          "sido_code) across every file",
          "%d, e.g. %s" % (len(bad), list(bad.items())[:2]))
    bad = {k: {a: sorted(b) for a, b in v.items()} for k, v in by_sgg.items() if len(v) > 1}
    check(not bad, "labels: one province per (year, sigungu_code) across every file",
          "%d, e.g. %s" % (len(bad), list(bad.items())[:2]))
    cw = d.get("crosswalk_region.csv")
    if cw is not None and names:
        tgt = set(cw.loc[cw["level"].isin(["sido", "sigungu"]), "sido"].dropna())
        stray = sorted(tgt - names)
        check(not stray, "crosswalk_region: every target province name is one the data "
              "uses", "not in any file: %s" % stray)


def check_crosswalk_country(d):
    """crosswalk_country 의 표준 이름 하나에 영문 하나, 영문 하나에 표준 이름 하나.

    2026-09-26 (3차 대조): 대만 -> 대만(unchanged)과 타이완 -> 타이완 이 둘 다
    Taiwan 으로 실려, 어느 파일에도 없는 「대만」이 따로 선 나라처럼 보였다.
    """
    cw = d.get("crosswalk_country.csv")
    if cw is None:
        return
    x = cw.dropna(subset=["country_en"])
    x = x[x["country_en"].astype(str).str.strip() != ""]
    g = x.groupby("country_en")["country"].nunique()
    bad = sorted(g[g > 1].index)
    check(not bad, "crosswalk_country: one standard name per English name",
          "%s" % {e: sorted(set(x.loc[x.country_en == e, "country"])) for e in bad[:3]})
    # 1라운드 수정 (2026-09-26): every standard name is also a source label of its own,
    # the spelling the editions print; 미국, 영국, 타이, 타이완, 러시아(연방) and 13 more
    # appeared only as the target of a retired spelling. And every nationality a data
    # file carries has its row.
    std = set(cw["country"]) - set(cw["source_label"])
    check(not std, "crosswalk_country: every standard name has a row under its own "
          "spelling", sorted(std)[:8])
    used = set()
    for f in ("nationality_national.csv", "nationality_by_sido.csv",
              "nationality_by_sigungu.csv", "visa_by_nationality.csv",
              "age_sex_national.csv", "segregation_by_nationality.csv",
              "language_weights.csv"):
        if d.get(f) is not None:
            used |= set(d[f]["country"].dropna())
    miss = sorted(used - set(cw["country"]))
    check(not miss, "crosswalk_country: every country a data file names has a row",
          miss[:8])


def check_region_crosswalk(d):
    """crosswalk_region lists every line the district files carry on another district.

    1라운드 수정 (2026-09-26): the 화성시 동부출장소 line (added to 화성시) and the
    마산시 line printed after the 2010 merger (carried on the 창원시 city line) were
    applied in the build and missing from the crosswalk, as was the 2010 split of
    마산시 and the old 창원시 into the new city's gu. 4라운드 대조 (2026-09-27): so was
    진해시, which the 2008-2009 tables print as a district and the 2011-2012 tables as a
    residual line, all of it carried on 창원시 진해구 (check_published_totals.
    district_label_gate reads every label the raw district tables print).
    """
    cr = d.get("crosswalk_region.csv")
    if cr is None:
        return
    rows = {(r.source_sido, str(r.source_name).replace(" ", ""), r.sido, str(r.name).replace(" ", ""))
            for r in cr[cr["level"] == "sigungu"].itertuples()}
    want = {("경기도", "화성시동부출장소", "경기도", "화성시"),
            ("경상남도", "마산시", "경상남도", "창원시"),
            ("경상남도", "진해시", "경상남도", "창원시진해구"),
            ("충청북도", "청원군", "충청북도", "청주시청원구"),
            ("충청남도", "당진군", "충청남도", "당진시"),
            ("충청남도", "연기군", "세종특별자치시", "세종시")}
    lin = " ".join(cr.loc[cr["level"] == "lineage", "rule"].astype(str))
    check(want <= rows and "창원시 마산합포구" in lin and "창원시 성산구" in lin,
          "crosswalk_region: every district-table line carried on another district, "
          "and the 2010 Changwon split",
          "missing %s" % sorted(want - rows))
    # 2026-09-27 (2라운드 대조): every province the files carry has a row under its own
    # name, the full name the 2008-2009 and later tables print; only 강원도, 전라북도
    # and 제주특별자치도 had one.
    names = set()
    for f, x in d.items():
        if x is not None and "sido" in x.columns and f != "crosswalk_region.csv":
            names |= set(x["sido"].dropna().astype(str))
    names -= {"기타", ""}
    src = set(cr.loc[cr["level"] == "sido", "source_sido"].astype(str))
    check(not (names - src), "crosswalk_region: every province name the files carry "
          "has a row of its own", sorted(names - src))


def check_early_provinces(d):
    """2006-2007: nationality_by_sido carries the province table the yearbook prints
    (five named nationalities and 기타), and summary_by_sido's counts and diversity
    indices for those years come from it.

    1라운드 수정 (2026-09-26): the table was carried nowhere, though the indices were
    built on it, and the 2006 indices were built on the first line of each cell alone
    (거주 residents; the province rows print (거주)/(기타) with no 계 line), so Seoul
    counted 36 Americans of 11,890.
    """
    ns, ss = d.get("nationality_by_sido.csv"), d.get("summary_by_sido.csv")
    nb = d.get("nationality_by_sigungu.csv")
    if ns is None or ss is None:
        return
    early = sorted(set(ss["year"].astype(int)) - set(nb["year"].astype(int))) if nb is not None else []
    if not early:
        return
    x = ns[ns["year"].isin(early)]
    tot = x.groupby(["year", "sido"])["n"].sum()
    reg = ss[ss["year"].isin(early)].set_index(["year", "sido"])["registered_foreigners"]
    j = pd.concat([tot.rename("nat"), reg.rename("reg")], axis=1)
    bad = j[j["nat"].fillna(-1) != j["reg"].fillna(-2)]
    check(bad.empty and len(j) > 0,
          "provinces %s: nationality_by_sido sums to summary_by_sido.registered_foreigners"
          % "-".join(str(y) for y in (early[0], early[-1])),
          "%d province-years differ, e.g. %s" % (len(bad), bad.head(3).to_dict("index")))
    # The indices of these years are held with every other province-year by
    # check_province_indices. Until 2026-09-27 this check held them to the five named
    # nationalities alone, the rule the 3라운드 대조 found departing from every other
    # level (the residual bin, 기타, was left out).


def check_province_indices(d):
    """summary_by_sido's diversity indices re-derive from nationality_by_sido, every year.

    3라운드 대조 (2026-09-27). The province indices of 2006-2013 were computed on the
    nationalities the province table names without its Other column, where the
    district and national indices keep the residual as one more group (2010 강원도:
    shannon_H 2.220 over the 19 named, 2.303 with the 605 in Other; index_base_k 5 in
    2006-2007 and 18-19 in 2008-2013). Rebuilt here from nationality_by_sido:
    every index on the year's national top 19 (ranked on the district table) plus one
    residual bin, and in 2006-2007, which have no district table, on the five named
    nationalities plus 기타; shannon_H_inclusive and continent_H with resident_pop as
    the Korean group.

    4라운드 대조 (2026-09-27): HHI and shannon_H_inclusive had been held to the full
    nationality detail here, "as the province series has always kept them", so the
    province series read 19 named groups plus Other through 2013 and every nationality
    from 2014 (HHI up to 0.017 lower at that break for coverage alone), and the 6e-3
    tolerance let the difference pass at most rows. They are on the basis every other
    index uses now, and each column is held to its rounding: 3-dp columns within 6e-4,
    evenness 8e-4 (H is rounded before the division), 4-dp columns within 1e-4.
    """
    ns, ss, cw = (d.get(f) for f in ("nationality_by_sido.csv", "summary_by_sido.csv",
                                     "crosswalk_country.csv"))
    if ns is None or ss is None:
        return
    tops = national_top19(district_counts(d))
    c2c = dict(zip(cw["country"], cw["continent"])) if cw is not None else {}
    rows = []
    for (y, sd), g in ns.groupby(["year", "sido"]):
        cs = {c: float(v) for c, v in zip(g["country"], g["n"]) if v > 0}
        s_ = ss[(ss["year"] == y) & (ss["sido"] == sd)]
        if s_.empty or not cs:
            continue
        r = s_.iloc[0]
        top = tops.get(y) or {c for c in cs if c not in RESIDUAL_LINES}
        base = {c: v for c, v in cs.items() if c in top}
        rest = sum(v for c, v in cs.items() if c not in top)
        vals = list(base.values()) + ([rest] if rest > 0 else [])
        H, k = ent(vals), len(vals)
        pop = r.get("resident_pop")
        by = {}
        for c, v in base.items():
            by[c2c.get(c, "기타")] = by.get(c2c.get(c, "기타"), 0.0) + v
        if rest > 0:
            by["기타"] = by.get("기타", 0.0) + rest
        if pd.notna(pop):
            by["동아시아"] = by.get("동아시아", 0.0) + float(pop)
        rows.append({
            "year": y, "sido": sd,
            "shannon_H": r["shannon_H"], "_H": H,
            "evenness": r["evenness"], "_J": H / math.log(k) if k > 1 else float("nan"),
            "index_base_k": r["index_base_k"], "_k": k,
            "HHI": r["HHI"], "_HHI": sum((v / sum(vals)) ** 2 for v in vals),
            "shannon_H_inclusive": r["shannon_H_inclusive"],
            "_I": ent(vals + [float(pop)]) if pd.notna(pop) else float("nan"),
            "continent_H": r["continent_H"],
            "_C": ent(list(by.values())) if pd.notna(pop) else float("nan"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        check(False, "index: summary_by_sido recomputes from nationality_by_sido", "no rows")
        return
    for pub, calc, tol in (("shannon_H", "_H", 6e-4), ("evenness", "_J", 8e-4),
                           ("HHI", "_HHI", 1e-4), ("shannon_H_inclusive", "_I", 6e-4),
                           ("continent_H", "_C", 1e-4)):
        sub = df.dropna(subset=[pub, calc])
        gap = (sub[pub] - sub[calc]).abs()
        check(len(sub) > 0 and bool((gap <= tol).all()),
              "index: summary_by_sido.%s recomputes from nationality_by_sido on the "
              "index basis, %d-%d (%d province-years)"
              % (pub, df["year"].min(), df["year"].max(), len(sub)),
              worst(sub.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                    pub, calc, ["year", "sido"]) + "; %d off" % int((gap > tol).sum()))
    bad = df[df["index_base_k"] != df["_k"]]
    check(bad.empty, "count: summary_by_sido.index_base_k recomputes, every year",
          "%d rows differ, e.g. %s" % (len(bad), bad[["year", "sido", "index_base_k", "_k"]]
                                       .head(3).to_dict("records")))


def check_national_indices(d):
    """national_annual's diversity indices re-derive from nationality_by_sigungu.

    4라운드 대조 (2026-09-27). No check held the national indices to the counts, and
    national_annual.HHI was computed on the national registered-by-nationality table
    with every nationality a group of its own, while its four sibling columns and
    index_base_k sit on the year's top 19 plus one residual bin (2024: 0.0940 against
    0.1004 on that basis). Here the district counts are summed over the country and
    reduced to that basis: shannon_H, evenness, HHI and index_base_k on it, and
    shannon_H_inclusive and continent_H with national_annual.total_pop as the Korean
    group (counted in 동아시아 for continent_H), every year. The national
    continent_H and shannon_H_inclusive go through the 3-dp entropy of kird.shannon,
    so 3-dp tolerances apply to them.
    """
    cnt, na, cw = district_counts(d), d.get("national_annual.csv"), d.get("crosswalk_country.csv")
    if not cnt or na is None:
        return
    tops = national_top19(cnt)
    c2c = dict(zip(cw["country"], cw["continent"])) if cw is not None else {}
    rows = []
    for y, blk in sorted(cnt.items()):
        r_ = na[na["year"] == y]
        if r_.empty:
            continue
        r = r_.iloc[0]
        agg = {}
        for cs in blk.values():
            for c, v in cs.items():
                agg[c] = agg.get(c, 0.0) + v
        top = tops.get(y, set())
        base = {c: v for c, v in agg.items() if c in top and v > 0}
        rest = sum(v for c, v in agg.items() if c not in top)
        vals = list(base.values()) + ([rest] if rest > 0 else [])
        H, k = ent(vals), len(vals)
        pop = float(r["total_pop"])
        by = {}
        for c, v in base.items():
            by[c2c.get(c, "기타")] = by.get(c2c.get(c, "기타"), 0.0) + v
        if rest > 0:
            by["기타"] = by.get("기타", 0.0) + rest
        by["동아시아"] = by.get("동아시아", 0.0) + pop
        rows.append({"year": y,
                     "shannon_H": r["shannon_H"], "_H": H,
                     "evenness": r["evenness"], "_J": H / math.log(k) if k > 1 else float("nan"),
                     "HHI": r["HHI"], "_HHI": sum((v / sum(vals)) ** 2 for v in vals),
                     "shannon_H_inclusive": r["shannon_H_inclusive"], "_I": ent(vals + [pop]),
                     "continent_H": r["continent_H"], "_C": ent(list(by.values())),
                     "index_base_k": r["index_base_k"], "_k": k})
    df = pd.DataFrame(rows)
    if df.empty:
        check(False, "index: national_annual recomputes from nationality_by_sigungu", "no rows")
        return
    for pub, calc, tol in (("shannon_H", "_H", 6e-4), ("evenness", "_J", 8e-4),
                           ("HHI", "_HHI", 1e-4), ("shannon_H_inclusive", "_I", 6e-4),
                           ("continent_H", "_C", 6e-4)):
        sub = df.dropna(subset=[pub, calc])
        gap = (sub[pub] - sub[calc]).abs()
        check(len(sub) == len(df) and bool((gap <= tol).all()),
              "index: national_annual.%s recomputes from nationality_by_sigungu on the "
              "index basis, %d-%d" % (pub, df["year"].min(), df["year"].max()),
              worst(sub.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                    pub, calc, ["year"]) + "; %d years off" % int((gap > tol).sum()))
    bad = df[df["index_base_k"] != df["_k"]]
    check(bad.empty, "count: national_annual.index_base_k recomputes, every year",
          "%d years differ" % len(bad))


def check_subdistrict_rates(d):
    """summary_by_eupmyeondong: a dependence rate is the component over non_naturalized
    where the component is reported, and blank where it is not; the district summaries
    use the same rule.

    1라운드 수정 (2026-09-26): the sub-district file read a masked component as 0, so
    3,524 masked cells in 2022-2024 alone gave a rate of 0.0 while the component
    itself was blank (1,968 of them hid a person or more), and the one masked component
    under a published subtotal was never recovered, as it is for the districts.
    """
    e = d.get("summary_by_eupmyeondong.csv")
    if e is None:
        return
    bad = {}
    for comp, rate in (("workers", "labor_dependence_pct"),
                       ("marriage_migrants", "marriage_dependence_pct"),
                       ("students", "study_dependence_pct")):
        if comp not in e.columns or rate not in e.columns:
            continue
        orphan = e[e[comp].isna() & e[rate].notna()]
        x = e.dropna(subset=[comp, rate, "non_naturalized"])
        x = x[x["non_naturalized"] > 0]
        g = (x[rate] - 100 * x[comp] / x["non_naturalized"]).abs()
        n_bad = len(orphan) + int((g > 0.006).sum())
        if n_bad:
            bad[rate] = n_bad
    check(not bad,
          "subdistrict rates: dependence rates recompute and are blank where the component is",
          "rows off %s" % bad)


def check_subdistrict_sums(d):
    """summary_by_eupmyeondong summed over a district's sub-districts is at most the
    district's broad_total, wherever MOIS publishes the district directly (MOIS omits
    or masks some sub-district rows, so the sum can fall short, never exceed).

    1라운드 수정 (2026-09-26): every Sejong sub-district in 2014 and 2015 carried twice
    its published count (the parser summed the total, male and female rows), which
    the 0.5% national tolerance of final_qc did not see.
    """
    e, s = d.get("summary_by_eupmyeondong.csv"), d.get("summary_by_sigungu.csv")
    if e is None or s is None or "sigungu_code" not in e.columns:
        return
    key = lambda df: df["sigungu_code"].map(lambda v: "" if v != v else str(v).split(".")[0])
    es = e.assign(_c=key(e)).groupby(["year", "_c"])["broad_total"].sum()
    direct = s[s["broad_apportioned"].astype(str).str.lower() == "false"]
    ss = direct.assign(_c=key(direct)).groupby(["year", "_c"])["broad_total"].sum()
    j = pd.concat([es.rename("emd"), ss.rename("sgg")], axis=1).dropna()
    over = j[j["emd"] > j["sgg"]]
    check(len(j) > 0 and over.empty,
          "subdistrict sums: no district's sub-districts add up to more than its broad_total",
          "%d district-years over, e.g. %s" % (len(over), over.head(3).to_dict("index")))
    # 2026-09-27 (2라운드 대조). 2014-2015 print no masked sub-district, so there a
    # district's sub-districts add up to its broad_total, and a city printed without
    # its gu (the gu apportioned) to the sum of its gu rows, to the rounding of the
    # apportioned rows (four a gu) and the few people by which the 2014 sheet's own
    # district lines exceed their sub-district lines (up to five: 영등포구 58,927
    # against 58,922). The 2014 창원시 block prints three sub-districts named 중앙동;
    # keyed on the city and the name they overwrote one another and 1,198 people went
    # missing, and two 지소 lines under 인천 중구 (70) were dropped as unclassified,
    # which the check above (never more) could not see.
    x = s[s["year"].isin([2014, 2015])].assign(_c=key(s[s["year"].isin([2014, 2015])]))
    app = x["broad_apportioned"].astype(str).str.lower() == "true"
    city = {(y, c): c[:4] for y, c, a in zip(x["year"], x["_c"], app) if a}
    grp = lambda y, c: city.get((y, c), c)
    xs = x.assign(_g=[grp(y, c) for y, c in zip(x["year"], x["_c"])])
    n_app = xs[app].groupby(["year", "_g"]).size()
    sg_ = xs.groupby(["year", "_g"])["broad_total"].sum(min_count=1)
    ee = e[e["year"].isin([2014, 2015])]
    ee = ee.assign(_c=key(ee))
    ee = ee.assign(_g=[grp(y, c) for y, c in zip(ee["year"], ee["_c"])])
    em_ = ee.groupby(["year", "_g"])["broad_total"].sum(min_count=1)
    jj = pd.concat([em_.rename("emd"), sg_.rename("sgg")], axis=1).dropna()
    tol = (n_app.reindex(jj.index).fillna(0) * 4).clip(lower=5)
    off = jj[(jj["emd"] - jj["sgg"]).abs() > tol]
    check(len(jj) > 0 and off.empty,
          "subdistrict sums: 2014-2015 sub-districts add up to their district (a city "
          "printed without its gu: to the sum of its gu rows)",
          "%d district-years off, e.g. %s" % (len(off), off.head(3).to_dict("index")))


def check_language_weights(d):
    """Every nationality line a count file carries has a language_weights row: its
    first-language shares, or an explicit row saying there are none.

    1라운드 수정 (2026-09-26): 미등록국가 (9, 15 and 32 people in the 2014-2016
    district tables) had no row, so its people fell out of language_demand with
    nothing to say so; 미상 and 한국 were in the same state.
    """
    lw = d.get("language_weights.csv")
    if lw is None:
        return
    used = set()
    for f in ("nationality_national.csv", "nationality_by_sido.csv",
              "nationality_by_sigungu.csv"):
        if d.get(f) is not None:
            used |= set(d[f].loc[d[f]["n"] > 0, "country"].dropna())
    miss = sorted(used - set(lw["country"]))
    check(not miss, "language_weights: a row for every nationality line with people",
          miss[:8])
    # 5라운드 대조 (2026-09-27): the dictionary promises a row for every standard name
    # crosswalk_country lists, and 북한, 케이맨제도 and 한국계미국인, standard names
    # with no people in the nationality files, had none. Both directions: no row for a
    # name the crosswalk does not list either.
    cw = d.get("crosswalk_country.csv")
    if cw is not None:
        names = set(cw["country"].dropna())
        have = set(lw["country"].dropna())
        check(names == have, "language_weights: a row for every standard name "
              "crosswalk_country lists, and for no other name",
              "missing %s; not in the crosswalk %s"
              % (sorted(names - have)[:8], sorted(have - names)[:8]))


def check_language_demand(d):
    """Every row of language_demand re-derives from the released counts and
    language_weights.csv, and the labels readers see are Korean where they matter.

    2026-09-27 (2라운드 대조). The national and district scopes were read from a
    block already rounded to one decimal and rounded again, so about 5% of those rows
    were one person off (카메룬 2014 x Aghem 0.0039 = 2.52, released as 2) and some
    estimates under one person passed the one-person floor. Here each scope is rebuilt
    the way the dictionary states it: persons x share, in units of 1/10,000 so the
    sum is exact, rounded once half up, a language dropped when its sum before
    rounding is under one person;
    national from nationality_national (stay), sido from nationality_by_sido,
    sigungu from nationality_by_sigungu keeping each district's 20 largest (ties by
    label). The same date: the Korean column repeated the English name for most
    languages (1,049 of 1,460 national labels in 2024, 따이어 5,782 among them); a
    language of the district scope, or one reaching 500 speakers in some year, must
    now carry a Korean label.
    """
    ld, lw = d.get("language_demand.csv"), d.get("language_weights.csv")
    if ld is None or lw is None:
        return
    U = 10000
    w = lw.dropna(subset=["language"])
    w = w[w["language"].astype(str).str.len() > 0]
    sh = {}
    for c, lang, s in zip(w["country"], w["language"], w["share"]):
        sh.setdefault(c, []).append((lang, int(round(float(s) * U))))

    def est(counts):
        out = {}
        for c, n in counts:
            for lang, u in sh.get(c, ()):
                out[lang] = out.get(lang, 0) + int(n) * u
        return out

    want = {}

    def put(key, e, top=None):
        items = sorted(e.items(), key=lambda kv: (-kv[1], kv[0]))
        for lang, u in (items[:top] if top else items):
            if u >= U:
                want[key + (lang,)] = (u + U // 2) // U

    years = set(ld["year"].astype(int))
    nn = d.get("nationality_national.csv")
    if nn is not None:
        x = nn[(nn["population"] == "stay") & nn["year"].isin(
            set(ld.loc[ld["scope"] == "national", "year"]))]
        for y, g in x.groupby("year"):
            put((int(y), "national", "", ""), est(zip(g["country"], g["n"])))
    ns = d.get("nationality_by_sido.csv")
    if ns is not None:
        x = ns[ns["year"].isin(set(ld.loc[ld["scope"] == "sido", "year"]))]
        for (y, sd), g in x.groupby(["year", "sido"]):
            put((int(y), "sido", sd, ""), est(zip(g["country"], g["n"])))
    nb = d.get("nationality_by_sigungu.csv")
    if nb is not None:
        x = nb[nb["year"].isin(set(ld.loc[ld["scope"] == "sigungu", "year"]))]
        for (y, sd, sg), g in x.groupby(["year", "sido", "sigungu"]):
            put((int(y), "sigungu", sd, sg), est(zip(g["country"], g["n"])), top=20)
    got = {(int(r.year), r.scope, "" if r.sido != r.sido else r.sido,
            "" if r.sigungu != r.sigungu else r.sigungu, r.language): int(r.count)
           for r in ld.itertuples()}
    off = [(k, want.get(k), got.get(k)) for k in set(want) | set(got)
           if want.get(k) != got.get(k)]
    by = {}
    for k, _, _ in off:
        by[k[1]] = by.get(k[1], 0) + 1
    check(bool(not off and len(got) > 0 and years),
          "language_demand: every row re-derives from the released counts x "
          "language_weights (%d rows)" % len(got),
          "%d rows differ %s, e.g. %s" % (len(off), by, sorted(off, key=str)[:3]))
    hang = ld["language"].astype(str).str.contains("[가-힣]")
    mx = ld.groupby("language")["count"].transform("max")
    need = (ld["scope"] == "sigungu") | (mx >= 500)
    bad = sorted(set(ld.loc[need & ~hang, "language"]))
    check(not bad, "language_demand: a Korean label for every language of the district "
          "scope and every language reaching 500 speakers", bad[:8])


def check_households(d):
    """The MOIS 외국인주민 세대수 column the 2009-2015 editions print is carried.

    2026-09-27 (2라운드 대조): the parser read it at every level and no released file
    carried it. Every province row of 2009-2015 has it, the districts of a province
    add up to it (to the apportioning of general districts, one household per gu),
    and national_annual is the province sum.
    """
    ss, sg, na = (d.get(f) for f in ("summary_by_sido.csv", "summary_by_sigungu.csv",
                                     "national_annual.csv"))
    if ss is None:
        return
    col = "foreign_resident_households"
    have = all(x is not None and col in x.columns for x in (ss, sg, na))
    check(have, "households: foreign_resident_households on the sido, sigungu and "
          "national summaries", "")
    if not have:
        return
    yrs = ss[ss["year"].between(2009, 2015)]
    check(bool(len(yrs)) and bool(yrs[col].notna().all()),
          "households: every province row of 2009-2015 carries the MOIS household count",
          "%d blank" % int(yrs[col].isna().sum()))
    nat = na.set_index("year")[col].dropna()
    prov = ss.groupby("year")[col].sum(min_count=1).reindex(nat.index)
    check(bool(len(nat)) and bool((nat == prov).all()),
          "households: national_annual equals the province sum", "")
    if "sigungu_code" in sg.columns and "sido_code" in ss.columns:
        p_ = sg.assign(_p=sg["sigungu_code"].map(lambda v: _code(v)[:2]))
        lo = p_.groupby(["year", "_p"])[col].sum(min_count=1)
        hi = ss.assign(_p=ss["sido_code"].map(_code)).groupby(["year", "_p"])[col].sum(min_count=1)
        j = pd.concat([lo.rename("lo"), hi.rename("hi")], axis=1).dropna()
        # exactly, since the general districts' shares are split by the largest-
        # remainder rule (3라운드 대조, 2026-09-27; it allowed one household per gu)
        bad = j[(j["lo"] - j["hi"]).abs() > 0]
        check(len(j) > 0 and bad.empty, "households: the districts of a province add up "
              "to it exactly",
              "%d province-years off, e.g. %s" % (len(bad), bad.head(3).to_dict("index")))


def check_region_totals(d):
    """region_segregation.total 은 모든 국적을 crosswalk_country 의 대륙으로 더한 것.

    2026-09-26: 권역을 segregation_by_nationality(100명 이상 국적만)에서 만들어,
    작은 국적 2,425명이 전부 기타로 갔다(2024년 기타 2,483, 나라 아닌 이름은 58).
    """
    rs, nb, cw = (d.get(f) for f in ("region_segregation.csv",
                                     "nationality_by_sigungu.csv", "crosswalk_country.csv"))
    if rs is None or nb is None or cw is None:
        return
    cont = dict(cw[["country", "continent"]].drop_duplicates("country").values)
    x = nb.assign(continent=nb["country"].map(cont).fillna("기타"))
    x = x[x["year"].isin(set(rs["year"]))]
    want = x.groupby(["year", "continent"])["n"].sum()
    got = rs.set_index(["year", "continent"])["total"]
    j = pd.concat([got.rename("got"), want.rename("want")], axis=1).fillna(0)
    bad = j[j["got"] != j["want"]]
    check(bad.empty, "region totals: region_segregation.total = nationality_by_sigungu "
          "summed by crosswalk_country continent",
          "%d cells, e.g. %s" % (len(bad), bad.head(3).to_dict("index")))


def check_apportioned_flag(d):
    """broad_apportioned 는 모든 행에서 True 나 False 이고, True 는 MOIS 칸이 있는 행에만.

    5라운드 대조 (2026-09-27): 사전은 MOIS 구성이 없는 행을 공란이라 적었는데, 파일은
    2026-09-26 다섯째 대조부터 그 행(그 시의 구 옆에 시 이름만으로 찍힌 줄 21 행)에
    False 를 적는다. 사전을 파일에 맞췄고, 이 검사가 그 규칙을 지킨다.
    """
    s = d.get("summary_by_sigungu.csv")
    if s is None or "broad_apportioned" not in s.columns:
        return
    f = s["broad_apportioned"]
    vals = set(map(str, f.dropna().unique()))
    ok = not f.isna().any() and vals <= {"True", "False"}
    app = f.astype(str) == "True"
    bad = s[app & s["broad_total"].isna()]
    check(ok and bad.empty,
          "broad_apportioned: True or False on every row, never blank, and True only "
          "where the MOIS columns are filled",
          "%d blank; values %s; %d True rows without broad_total"
          % (int(f.isna().sum()), sorted(vals), len(bad)))


def check_region_segregation(d):
    """region_segregation 의 dissimilarity_D 와 isolation 을 공개된 수에서 다시 얻는다.

    5라운드 대조 (2026-09-27): segregation_by_nationality 에는 재산출 관문이 있는데 이
    파일은 total 만 보았다(check_region_totals). 같은 정의(09_finish_release.
    build_segregation): the districts of summary_by_sigungu with a resident_pop,
    k = resident_pop, t = k + registered_foreigners, x = the continent's registered
    foreigners in the district (nationality_by_sigungu summed by crosswalk_country's
    continent), D = 0.5 sum |x/X - k/K|, isolation = sum (x/X)(x/t). Also one row per
    continent with people that year, and no other.
    """
    rs, nb, sm, cw = (d.get(f) for f in ("region_segregation.csv", "nationality_by_sigungu.csv",
                                         "summary_by_sigungu.csv", "crosswalk_country.csv"))
    if rs is None or nb is None or sm is None or cw is None:
        return
    cont = dict(cw[["country", "continent"]].drop_duplicates("country").values)
    nb = nb[~nb["sigungu"].isin(AGG) & ~nb["sido"].isin(AGG)]
    nb = nb.assign(continent=nb["country"].map(cont).fillna("기타"))
    years = sorted(set(rs["year"].astype(int)))
    tot = nb[nb["year"].isin(years)].groupby(["year", "continent"])["n"].sum()
    want = {(int(y), c) for (y, c), v in tot.items() if v > 0}
    have = {(int(y), c) for y, c in zip(rs["year"], rs["continent"])}
    check(want == have, "region segregation: one row per continent with people that "
          "year, and no other",
          "missing %s; extra %s" % (sorted(want - have)[:6], sorted(have - want)[:6]))
    rows = []
    for y in years:
        g = sm[(sm["year"] == y)].dropna(subset=["resident_pop", "registered_foreigners"])
        g = g.set_index(["sido", "sigungu"])
        k = g["resident_pop"].astype(float)
        t = k + g["registered_foreigners"].astype(float)
        piv = (nb[nb["year"] == y].pivot_table(index=["sido", "sigungu"], columns="continent",
                                               values="n", aggfunc="sum")
               .reindex(g.index).fillna(0.0))
        for c in rs.loc[rs["year"] == y, "continent"]:
            x = piv[c] if c in piv.columns else pd.Series(0.0, index=k.index)
            X, K = x.sum(), k.sum()
            D = 0.5 * (x / X - k / K).abs().sum() if X else np.nan
            iso = ((x / X) * (x / t)).sum() if X else np.nan
            rows.append({"year": y, "continent": c, "_D": D, "_iso": iso})
    m = rs.merge(pd.DataFrame(rows), on=["year", "continent"], how="left")
    # the file rounds D to three decimals and isolation to four
    for pub, cc, tol, name in (("dissimilarity_D", "_D", 5e-4 + 1e-9, "dissimilarity_D"),
                               ("isolation", "_iso", 5e-5 + 1e-9, "isolation")):
        both_nan = m[pub].isna() & m[cc].isna()
        gap = (m[pub] - m[cc]).abs().where(~both_nan, 0.0).fillna(np.inf)
        check(bool((gap <= tol).all()),
              "region segregation: %s recomputes from the counts (to its rounding)" % name,
              worst(m.assign(_g=gap).sort_values("_g", ascending=False).head(1),
                    pub, cc, ["year", "continent"]))


def check_ethnic_enclaves(d):
    """ethnic_enclaves 의 모든 행과 칸을 공개된 수에서 다시 얻는다.

    5라운드 대조 (2026-09-27): 이 파일에는 키 검사만 있었다. The rule (README Index
    definitions; 04_reconcile_districts.recompute_enclaves): a district x nationality
    pair is an enclave when the nationality has at least 200 registered foreigners
    in the district, a location quotient of at least 2 and at least 30% of the
    district's registered foreigners. LQ = (x / resident_pop_d) / (X / sum of
    resident_pop), X being the nationality's total over every district row that year
    and the resident population summed over the districts that have one. The lines
    that name no nationality are never enclaves. Every row must re-derive, with its
    count, lq, share_of_foreign_pct and sigungu_foreign_total, and no pair the rule
    selects may be missing.
    """
    e, sm = d.get("ethnic_enclaves.csv"), d.get("summary_by_sigungu.csv")
    cnt = district_counts(d)
    if e is None or sm is None or not cnt:
        return
    pop = {(int(r.year), r.sido, r.sigungu): float(r.resident_pop)
           for r in sm.itertuples() if not pd.isna(r.resident_pop) and r.resident_pop > 0}
    natpop = {}
    for (y, _, _), v in pop.items():
        natpop[y] = natpop.get(y, 0.0) + v
    calc = {}
    for y in sorted(set(e["year"].astype(int))):
        blk = cnt.get(y, {})
        X = {}
        for cs in blk.values():
            for c, v in cs.items():
                X[c] = X.get(c, 0.0) + v
        for (sd, sg), cs in blk.items():
            tp = pop.get((y, sd, sg))
            tot = sum(cs.values())
            if not tp or tot <= 0 or not natpop.get(y):
                continue
            for c, x in cs.items():
                if c in RESIDUAL_LINES or x < 200 or X.get(c, 0) <= 0:
                    continue
                lq = (x / tp) / (X[c] / natpop[y])
                share = x / tot
                if lq >= 2.0 and share >= 0.30:
                    calc[(y, sd, sg, c)] = (x, lq, share * 100, tot)
    have = {(int(r.year), r.sido, r.sigungu, r.country): r for r in e.itertuples()}
    miss, extra = sorted(set(calc) - set(have)), sorted(set(have) - set(calc))
    check(not miss and not extra,
          "ethnic enclaves: exactly the district x nationality pairs the rule selects "
          "(>= 200, LQ >= 2, >= 30%% of the district's foreigners), %d rows" % len(calc),
          "missing %s; extra %s" % (miss[:4], extra[:4]))
    off = []
    for k in set(calc) & set(have):
        x, lq, sh, tot = calc[k]
        r = have[k]
        if (int(r.count) != int(x) or int(r.sigungu_foreign_total) != int(tot)
                or abs(float(r.lq) - lq) > 0.05 + 1e-9
                or abs(float(r.share_of_foreign_pct) - sh) > 0.05 + 1e-9):
            off.append("%s: published %s/%s/%s/%s, recomputed %d/%.3f/%.3f/%d"
                       % (k, r.count, r.lq, r.share_of_foreign_pct,
                          r.sigungu_foreign_total, x, lq, sh, tot))
    check(not off, "ethnic enclaves: count, lq, share_of_foreign_pct and "
          "sigungu_foreign_total recompute from the counts (to their rounding)",
          "%d rows, e.g. %s" % (len(off), off[:2]))


def check_diaspora_labels(d):
    """재외동포 표에서 한 인구가 두 이름으로 갈리지 않는가.

    2026-09-26: 연보가 2017년까지 중국·러시아, 2018년부터 한국계 중국인·한국계
    러시아인이라 적은 것을 그대로 옮겨, 같은 계열이 해에 따라 두 이름이었다.
    """
    x = d.get("diaspora_residence_by_sido.csv")
    if x is None:
        return
    both = sorted(set(x["country"]) & {"중국", "러시아(연방)", "러시아"})
    check(not both, "diaspora: China and Russia carried as the Korean-descent subgroup "
          "in every year", "parent labels present: %s" % both)


def check_published_residuals(d):
    """전국 표가 연보의 국적 아닌 줄을 싣는가(2026-09-26부터).

    인쇄 총계와의 일치는 원자료가 있어야 볼 수 있으므로 check_published_totals.py
    가 본다. 여기서는 그 줄이 빠지지 않았는지만 본다: 연보는 해마다 무국적 또는
    기타 줄을 싣는다.
    """
    n = d.get("nationality_national.csv")
    if n is None:
        return
    r = n[n["population"] == "registered"]
    ys = set(r["year"].astype(int))
    have = set(r.loc[r["country"].isin(RESIDUAL_LINES), "year"].astype(int))
    check(ys == have, "national tables: every registered year carries the yearbook's "
          "무국적 / 기타 line", "years without: %s" % sorted(ys - have))


def check_dictionary_numbers(data, d):
    """사전 산문이 인용하는 수를 자료에서 다시 얻어 사전 글과 맞댄다.

    2026-09-26: lisa_fdr 이 「보정 전 52곳, 고-고 16곳」이라 적었는데 자료는
    51과 14였다. region_segregation 은 2,501, adm_code 는 「약 1%」였다.
    09_finish_release.dictionary_facts 가 쓰는 것과 같은 수를 여기서 따로 얻는다.
    """
    p = os.path.join(data, "data_dictionary.csv")
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(os.path.abspath(data.rstrip("/\\"))),
                         "data_dictionary.csv")
    if not os.path.exists(p):
        return
    dic = pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False)

    def row(file_has, var):
        m = dic[dic["file"].str.contains(file_has, regex=False) & (dic["variable"] == var)]
        return " ".join(m["description_en"]) + " " + " ".join(m["description_ko"])

    exp = []
    emd = d.get("summary_by_eupmyeondong.csv")
    if emd is not None:
        a = emd["adm_code"].astype(str).str.strip()
        b = emd["adm_code"].isna() | a.isin(["", "nan"])
        rate = b.groupby(emd["year"]).mean() * 100
        exp.append(("summary_by_eupmyeondong.csv", "adm_code",
                    ["%.1f%%" % rate.get(2014, 0), "%.1f%%" % rate.get(2015, 0),
                     "%.1f%%" % rate[rate.index >= 2016].max()]))
    sg = d.get("summary_by_sigungu.csv")
    if sg is not None and "lisa_fdr" in sg.columns:
        last = int(sg["year"].max())
        n_class = int(round(sg.dropna(subset=["lisa"]).groupby("year").size().mean()))
        L = sg[sg["year"] == last]
        sig = {"HH", "LL", "HL", "LH"}
        exp.append(("summary_by_sigungu.csv", "lisa",
                    ["About %d districts" % n_class, "about %d " % round(0.05 * n_class)]))
        exp.append(("summary_by_sigungu.csv", "lisa_fdr",
                    ["in %d, %d do (%d of them high-high), against %d (%d high-high)"
                     % (last, L["lisa_fdr"].isin(sig).sum(), (L["lisa_fdr"] == "HH").sum(),
                        L["lisa"].isin(sig).sum(), (L["lisa"] == "HH").sum())]))
    rs = d.get("region_segregation.csv")
    if rs is not None and sg is not None:
        last = int(sg["year"].max())
        v = int(rs.loc[(rs["year"] == last) & (rs["continent"] == "기타"), "total"].sum())
        exp.append(("region_segregation.csv", "total",
                    ["%s people in %d" % (format(v, ","), last)]))
    vbn = d.get("visa_by_nationality.csv")
    if vbn is not None:
        x = int(vbn[(vbn["visa_code"] == "X00") & (vbn["population"] == "stay")]["n"].sum())
        exp.append(("visa_by_nationality.csv", "visa_label / visa_label_en",
                    ["with no status (%s)" % format(x, ",")]))
    a = d.get("age_sex_national.csv")
    if a is not None:
        per = a.groupby(["population", "year"])["age_group"].nunique()
        fm = lambda v: format(int(v), ",")
        rt = a[(a["population"] == "registered") & (a["gender"] == "T")]
        need = ["(%d bands in every year)" % per.max() if per.nunique() == 1
                else "(bands vary by year: %s)" % sorted(set(per))]
        # the 2006-2008 bands and the numbers the note on them quotes (2026-09-27)
        if (rt["year"] == 2008).any() and (rt["year"] == 2009).any():
            need += ["the same %s people" % fm(rt.loc[rt["year"] == 2008, "n"].sum()),
                     "0-5 %s here" % fm(rt.loc[(rt["year"] == 2008)
                                               & (rt["age_group"] == "0-5"), "n"].sum()),
                     "(0-4 %s in 2009)" % fm(rt.loc[(rt["year"] == 2009)
                                                    & (rt["age_group"] == "0-4"), "n"].sum())]
        exp.append(("age_sex_national.csv", "age_group", need))
    dia, vn = d.get("diaspora_residence_by_sido.csv"), d.get("visa_national.csv")
    if dia is not None and vn is not None:
        k = dia[dia["country"] != "기타"].groupby("year")["country"].nunique()
        f4 = (vn[(vn["population"] == "stay") & (vn["visa_code"] == "F4")]
              .groupby("year")["n"].sum())
        j = pd.concat([dia.groupby("year")["n"].sum(), f4], axis=1, keys=["d", "f"]).dropna()
        gap = float(((j["d"] - j["f"]).abs() / j["f"] * 100).max())
        exp.append(("diaspora_residence_by_sido.csv", "country / country_en",
                    ["between %d and %d nationalities a year (%d in %d, %d in %d)"
                     % (k.min(), k.max(), k.min(), k.idxmin(), k.max(), k.idxmax())]))
        exp.append(("diaspora_residence_by_sido.csv", "n", ["within %.1f%%" % gap]))
    ann, pc = d.get("naturalization_annual.csv"), d.get("naturalization_by_country.csv")
    if ann is not None and pc is not None:
        exp.append(("naturalization_annual.csv", "year",
                    ["annual series runs %d-%d" % (ann["year"].min(), ann["year"].max()),
                     "panels run %d-%d" % (pc["year"].min(), pc["year"].max())]))
    # the long tail of languages that keep their English label (2026-09-27)
    ld = d.get("language_demand.csv")
    if ld is not None:
        last_ = int(ld["year"].max())
        ln = ld[(ld["scope"] == "national") & (ld["year"] == last_)]
        ko_ = ln["language"].astype(str).str.contains("[가-힣]")
        exp.append(("language_demand.csv", "language / language_en",
                    ["%s of the %s national labels of %d, %.1f%%"
                     % (format(int((~ko_).sum()), ","), format(len(ln), ","), last_,
                        100 * ln.loc[~ko_, "count"].sum() / ln["count"].sum())]))
    # the district table's columns that name no nationality (2026-09-26, final audit)
    nb = d.get("nationality_by_sigungu.csv")
    if nb is not None:
        r = nb[(nb["n"] > 0) & (nb["country"].isin(["무국적", "미등록국가", "미상", "한국"])
                                | ((nb["country"] == "기타") & (nb["year"] >= 2014)))]
        if len(r):
            per = r.groupby("year")["n"].sum()
            exp.append(("nationality_by_sigungu.csv", "country / country_en",
                        ["%s to %s people a year" % (format(int(per.min()), ","),
                                                     format(int(per.max()), ","))]))
    # the city lines, the rows under a bare city name beside that city's gu: how many,
    # how large, how many the visa file carries, and whom the Theil H and the two
    # segregation files leave out (2026-09-26, final audit; they were typed by hand)
    na, seg, vb = (d.get(f) for f in ("national_annual.csv",
                                      "segregation_by_nationality.csv",
                                      "visa_by_sigungu.csv"))
    if sg is not None and "resident_pop" in sg.columns:
        cl = sg[sg["resident_pop"].isna() & (sg["registered_foreigners"] > 0)]
        if len(cl):
            fm = lambda v: format(int(v), ",")
            exp.append(("summary_by_sigungu.csv", "sigungu / sigungu_en",
                        ["%d district-years" % len(cl),
                         "%s to %s people" % (fm(cl["registered_foreigners"].min()),
                                              fm(cl["registered_foreigners"].max()))]))
            keys = list(map(tuple, cl[["year", "sido", "sigungu"]].values.tolist()))
            if vb is not None:
                vk = set(map(tuple, vb.loc[vb["n"] > 0, ["year", "sido", "sigungu"]]
                             .drop_duplicates().values.tolist()))
                exp.append(("visa_by_sigungu.csv", "sido / sido_en / sigungu / sigungu_en",
                            ["carries %d of the %d city rows"
                             % (sum(1 for k in keys if k in vk), len(cl))]))
            if na is not None:
                th = set(na.loc[na["theil_segregation_H"].notna(), "year"])
                per = cl[cl["year"].isin(th)].groupby("year")["registered_foreigners"].sum()
                if len(per):
                    exp.append(("national_annual.csv", "theil_segregation_H",
                                ["(%s to %s people a year in " % (fm(per.min()), fm(per.max()))]))
            if seg is not None:
                sc = cl[cl["year"].isin(set(seg["year"]))].sort_values(["year", "sido", "sigungu"])
                en = ["%s in %d %s" % (fm(r.registered_foreigners), r.year, r.sigungu)
                      for r in sc.itertuples()]
                if en:
                    en[0] = en[0].replace(" in ", " people in " if en[0].split()[0] != "1"
                                          else " person in ", 1)
                    txt = (", ".join(en[:-1]) + " and " + en[-1]) if len(en) > 1 else en[0]
                    exp.append(("segregation_by_nationality.csv", "national_total", [txt]))
                    exp.append(("region_segregation.csv", "dissimilarity_D", [txt]))
    bad = []
    for f, var, needles in exp:
        text = row(f, var)
        if not text.strip():
            bad.append("%s.%s: no row" % (f, var))
            continue
        for nd in needles:
            if nd not in text:
                bad.append("%s.%s lacks %r" % (f, var, nd))
    check(not bad, "dictionary numbers: every number the prose quotes re-derives from "
          "the files (%d claims)" % sum(len(e[2]) for e in exp), "; ".join(bad[:4]))


def check_visa_eras(d):
    """한 코드가 제 시대 밖의 해에 값을 갖지 않는가. 2026-09-25 까지 E8 은 2006-2009
    의 연수취업과 2021 의 계절근로를 한 줄로 잇고 「Seasonal Worker」라 불렀다."""
    for name in ("visa_national.csv", "visa_by_nationality.csv", "visa_by_sido.csv",
                 "visa_by_sigungu.csv"):
        df = d.get(name)
        if df is None:
            continue
        bad = []
        for code, (lo, hi) in VISA_ERAS.items():
            ys = set(df.loc[(df["visa_code"] == code) & (df["n"] > 0), "year"].astype(int))
            out = sorted(y for y in ys if (lo and y < lo) or (hi and y > hi))
            if out:
                bad.append("%s in %s" % (code, out))
        check(not bad, "visa eras: %s keeps each code inside its era" % name, "; ".join(bad))


def _codes(data, name, cols=None):
    """같은 파일을 코드 칸을 글자로 다시 읽는다. load() 는 형을 짐작하므로
    빈칸이 있는 파일에서 42150 이 42150.0 이 된다."""
    p = find_file(data, name)
    if p is None:
        return None
    return pd.read_csv(p, encoding="utf-8-sig", usecols=cols, keep_default_na=False,
                       dtype={"sido_code": str, "sigungu_code": str, "adm_code": str,
                              "year": int})


# 일반구를 둔 시. 광역시·특별시 밖에서 이 구 이름이 시 이름 없이 홀로 적히면
# 어느 시의 구인지 이름만으로 알 수 없다(포항 남구 / 광역시의 남구).
GENERAL_GU = {
    "고양시": ("덕양구", "일산동구", "일산서구"), "부천시": ("소사구", "오정구", "원미구"),
    "성남시": ("분당구", "수정구", "중원구"), "수원시": ("권선구", "영통구", "장안구", "팔달구"),
    "안산시": ("단원구", "상록구"), "안양시": ("동안구", "만안구"),
    "용인시": ("기흥구", "수지구", "처인구"), "전주시": ("덕진구", "완산구"),
    "창원시": ("마산합포구", "마산회원구", "성산구", "의창구", "진해구"),
    "천안시": ("동남구", "서북구"), "청주시": ("상당구", "서원구", "청원구", "흥덕구"),
    "포항시": ("남구", "북구"),
}


def check_subdistrict_codes(data, d):
    """읍면동 코드가 한 해 안에서 한 곳만 가리키는가, 두 표가 같은 코드를 주는가.

    2026-09-25: multicultural_households 가 2023년 하남시 풍산동에 고양시 일산동구
    풍산동의 코드(4128554000)를, 2024년 창원 성산구 중앙동에 진주 중앙동의 코드
    (38030740)를 달고 있었다. summary_by_eupmyeondong 은 8월 26일에 상류에서 고쳤는데
    이 표는 파이프라인이 다시 짓지 않아(쓰는 코드가 없었다) 옛 코드를 그대로 싣고
    있었다. 두 표가 같은 동에 같은 코드를 주는지까지 본다.
    """
    mc = _codes(data, "multicultural_households.csv",
                ["year", "sido", "sigungu", "sigungu_code", "eupmyeondong", "adm_code"])
    em = _codes(data, "summary_by_eupmyeondong.csv",
                ["year", "sido", "sigungu", "sigungu_code", "eupmyeondong", "adm_code"])
    for name, df in (("multicultural_households.csv", mc),
                     ("summary_by_eupmyeondong.csv", em)):
        if df is None:
            continue
        u = df[df["adm_code"] != ""].drop_duplicates(
            ["year", "sido", "sigungu", "eupmyeondong", "adm_code"])
        dup = u[u.duplicated(["year", "adm_code"], keep=False)]
        check(dup.empty, "sub-district codes: %s gives each adm_code to one place a year" % name,
              "%d rows, e.g. %s" % (len(dup), dup.head(2).values.tolist()))
        loose = []
        for city, gus in GENERAL_GU.items():
            bare = df[df["sigungu"].isin(gus) & ~df["sido"].str.contains("광역시|특별시")]
            if len(bare):
                loose.append("%s %s" % (sorted(set(bare["year"]))[0], bare["sigungu"].iloc[0]))
        check(not loose, "sub-district codes: %s names every general gu with its city" % name,
              "bare gu: %s" % loose[:5])
    if mc is not None:
        # 2016 on, a district name is one district: one sigungu_code per (year, name).
        # The 2023 하남시 풍산동 row carried 고양시 일산동구's 41285 beside 하남시's
        # 41450; the (year, adm_code) check above caught the dong code, not this.
        many = mc.groupby(["year", "sido", "sigungu"])["sigungu_code"].nunique()
        many = many[many > 1]
        check(many.empty, "sub-district codes: multicultural_households gives each "
              "district name one sigungu_code a year", str(list(many.index[:4])))
    if mc is not None and em is not None:
        k = ["year", "sigungu_code", "eupmyeondong"]
        j = mc.drop_duplicates(k + ["adm_code"]).merge(
            em.drop_duplicates(k), on=k, how="inner", suffixes=("", "_emd"))
        bad = j[j["adm_code"] != j["adm_code_emd"]]
        check(bad.empty, "sub-district codes: multicultural_households and "
              "summary_by_eupmyeondong give the same dong the same adm_code",
              "%d disagree, e.g. %s" % (len(bad), bad.head(2)[k + ["adm_code", "adm_code_emd"]]
                                        .values.tolist()))


def check_children_grain(data, d):
    """children_by_age 는 시군구 요약과 같은 단위로 한 줄씩이어야 한다.

    2026-09-25: 2024년 부천시가 소사구·오정구·원미구 세 줄로 실려 모두 41190 을 달고
    있었다. 이름 열쇠로는 유일해서 기존 검사를 통과했다. 코드로 본다.
    """
    ca = _codes(data, "children_by_age.csv", ["year", "sigungu", "sigungu_code", "age"])
    sg = _codes(data, "summary_by_sigungu.csv", ["year", "sigungu_code"])
    if ca is None:
        return
    n = int(ca.duplicated(["year", "sigungu_code", "age"]).sum())
    check(n == 0, "children grain: children_by_age unique on year+sigungu_code+age",
          "%d duplicates, e.g. %s" % (n, ca[ca.duplicated(["year", "sigungu_code", "age"],
                                                          keep=False)].head(3).values.tolist()))
    if sg is not None:
        have = set(zip(sg["year"], sg["sigungu_code"]))
        # 2016 년 전에는 일반구 시를 시 단위로 싣는다(사전에 적힌 대로). 그 뒤로는
        # 요약과 같은 단위여야 한다.
        extra = sorted({(y, c) for y, c in zip(ca["year"], ca["sigungu_code"])
                        if y >= 2016 and (y, c) not in have})
        check(not extra, "children grain: from 2016 every children_by_age district is a summary_by_sigungu district",
              "%d (year, code) not in the summary, e.g. %s" % (len(extra), extra[:4]))


def check_dictionary_years(data, d):
    """사전에 괄호로 적은 연도 범위가 그 파일의 실제 범위와 같은가.

    2026-09-25: nationality_by_sigungu.n 이 「(2009-2024)」라고 적고 있었는데 파일은
    2008년부터다. visa_by_sigungu.n 은 영문이 2008-2024, 국문이 「2008 및
    2017-2024」로 서로 달랐다. 변수 하나, 파일 하나를 설명하는 줄에서 괄호 안의
    범위가 하나뿐이면 그 범위를 파일과 맞대고, 국문의 범위가 영문과 같은지도 본다.
    """
    p = os.path.join(data, "data_dictionary.csv")
    if not os.path.exists(p):
        p = os.path.join(os.path.dirname(data), "data_dictionary.csv")
    if not os.path.exists(p):
        return
    dic = pd.read_csv(p, encoding="utf-8-sig", keep_default_na=False)
    rng = re.compile(r"\(((?:19|20)\d{2})\s*[-\u2013]\s*((?:19|20)\d{2})\)")
    bad = []
    for _, r in dic.iterrows():
        f = str(r["file"]).strip()
        if "/" in f or f not in d or "year" not in d[f].columns:
            continue
        en = rng.findall(str(r["description_en"]))
        ko = rng.findall(str(r["description_ko"]))
        if en and sorted(set(en)) != sorted(set(ko)):
            bad.append("%s.%s en %s ko %s" % (f, r["variable"], en, ko))
        if len(set(en)) != 1:
            continue
        a, b = map(int, en[0])
        ys = d[f]["year"].dropna().astype(int)
        if "population" in d[f].columns:      # 모집단마다 범위가 다른 표는 넘긴다
            continue
        if (a, b) != (int(ys.min()), int(ys.max())):
            bad.append("%s.%s says %d-%d, file %d-%d"
                       % (f, r["variable"], a, b, ys.min(), ys.max()))
    check(not bad, "dictionary years: every (YYYY-YYYY) in a one-file row matches the file",
          "; ".join(bad[:4]))


# Where the district-by-visa and district-by-nationality tables of one edition place
# a person differently, read in the raw files (year, sido, sigungu): visa total minus
# nationality total. The 2015 nationality table prints a bare 창원시 line (1 person)
# above 창원시 마산합포구 (2,159); the visa table prints no 창원시 line and 2,160 for
# 마산합포구. The 2015 visa table prints a 화성시 동부출장소 line (1 person), which the
# release adds to 화성시; the nationality table prints no such line and holds that
# person only in its 경기도 소계 (369,665 against 369,664 over its district lines),
# which is the one person the nationality files fall short of the national total.
TABLES_DIFFER = {(2015, "경상남도", "창원시"): -1, (2015, "경상남도", "창원시 마산합포구"): 1,
                 (2015, "경기도", "화성시"): 1}


def check_district_tables_agree(d):
    """The district visa and nationality files hold the same people, district by
    district, and every district row of the summary has detail rows behind it.

    2026-09-26 (final audit). The two files come from two tables of one edition that
    print the same registered population by district. Until this date the
    nationality file dropped the table's columns that name no nationality, so from
    2014 a district's visa total could exceed its nationality total and no check
    compared the two below the national sum. The reverse join (a summary row with no
    detail rows) was not checked either: summary_by_sigungu's 2015 창원시 row (1
    person) has no visa row, because the visa table prints no such line.
    """
    nb, vb, sm = (d.get(f) for f in ("nationality_by_sigungu.csv", "visa_by_sigungu.csv",
                                     "summary_by_sigungu.csv"))
    if nb is None or vb is None or sm is None:
        return
    k = ["year", "sido", "sigungu"]
    a = nb.groupby(k)["n"].sum().rename("nat")
    b = vb.groupby(k)["n"].sum().rename("visa")
    j = pd.concat([a, b], axis=1).fillna(0)
    j["gap"] = j["visa"] - j["nat"]
    known = dict(TABLES_DIFFER)
    off = {key: int(g) for key, g in j["gap"].items()
           if int(g) != known.get(tuple(key), 0)}
    missing = [key for key in known if int(j["gap"].get(key, 0)) != known[key]]
    check(not off and not missing,
          "cross-file: visa_by_sigungu and nationality_by_sigungu hold the same people "
          "in every district-year (%d documented differences)" % len(known),
          "%d district-years differ, e.g. %s; documented but absent %s"
          % (len(off), list(off.items())[:4], missing[:3]))
    have = sm[sm["registered_foreigners"] > 0].set_index(k).index
    for name, frame in (("nationality_by_sigungu.csv", nb), ("visa_by_sigungu.csv", vb)):
        rows = set(map(tuple, frame[frame["n"] > 0][k].drop_duplicates().values.tolist()))
        lack = sorted(set(map(tuple, have.tolist())) - rows)
        allowed = {key for key, g in known.items()
                   if name == "visa_by_sigungu.csv" and g < 0
                   and int(j.loc[key, "visa"]) == 0}
        bad = [key for key in lack if key not in allowed]
        check(not bad, "cross-file: every summary_by_sigungu row with registered "
              "foreigners has %s rows behind it" % name,
              "%d without, e.g. %s" % (len(bad), bad[:4]))


def check_national_reach(d):
    """The district files add up to the published national registered total.

    2026-09-26 (final audit): national_annual.foreign_total, the sum of the districts,
    sat 126-183 below the registered total of nationality_national every year from
    2014, because the district files dropped the district table's columns that name
    no nationality. The table's printed grand total equals the national one in every
    year; the only gap left is 2015, where the table's 경기도 소계 holds one person
    none of its district lines does.
    """
    na, nn = d.get("national_annual.csv"), d.get("nationality_national.csv")
    if na is None or nn is None:
        return
    reg = nn[nn["population"] == "registered"].groupby("year")["n"].sum()
    dist = na.set_index("year")["foreign_total"]
    gap = (reg - dist).dropna()
    gap = {int(y): int(g) for y, g in gap.items() if int(y) >= 2008}
    bad = {y: g for y, g in gap.items() if g != {2015: 1}.get(y, 0)}
    check(bool(gap) and not bad,
          "cross-file: national_annual.foreign_total = nationality_national registered "
          "total every year from 2008 (2015: one person short)", "gap by year %s" % bad)


def check_naturalization_grid(d):
    """Each naturalization panel year is a full grid: every country (age band) the
    panel carries that year has a row for every processing type it carries that year.

    2026-09-26 (final audit): the 2019, 2020 and 2024 by-country tables and the 2019,
    2020, 2023 and 2024 by-age tables leave zero cells empty, and an empty cell wrote
    no row, so a missing row meant zero in those years and nothing in the others
    (2019 by country: 409 rows over 103 countries, 1,339 in 2018).
    """
    for name, unit in (("naturalization_by_country.csv", "country"),
                       ("naturalization_by_age.csv", "age")):
        df = d.get(name)
        if df is None:
            continue
        bad = {}
        for y, g in df.groupby("year"):
            per = g.groupby(unit)["type"].nunique()
            k = g["type"].nunique()
            if (per != k).any():
                bad[int(y)] = "%d of %d %s short" % (int((per != k).sum()), len(per), unit)
        check(not bad, "naturalization: %s is a full %s x type grid in every year"
              % (name, unit), bad)


def main():
    data = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if not os.path.isdir(data):
        raise SystemExit("no such directory: %s" % data)
    data = resolve_data(data)
    print("validate_release: %s" % data)
    d = load(data)
    print("  %d released files read" % len(d))
    print()
    check_inventory(data, d)
    check_keys(d)
    check_dictionary(data, d)
    check_bilingual(d)
    check_identities(d)
    check_rates(d)
    check_indices(d)
    check_continent(d)
    check_segregation(d)
    check_theil(d)
    check_cross_file(d)
    check_age_bases(d)
    check_country_labels(d)
    check_coverage_text(data, d)
    check_visa_basis(data, d)
    check_subdistrict_codes(data, d)
    check_children_grain(data, d)
    check_dictionary_years(data, d)
    check_naturalization(d)
    check_visa_eras(d)
    check_one_label_per_code(d)
    check_province_labels(d)
    check_crosswalk_country(d)
    check_region_crosswalk(d)
    check_language_weights(d)
    check_language_demand(d)
    check_households(d)
    check_early_provinces(d)
    check_province_indices(d)
    check_national_indices(d)
    check_determined_blanks(d)
    check_multicultural_codes(d)
    check_broad_levels(d)
    check_subdistrict_rates(d)
    check_subdistrict_sums(d)
    check_region_totals(d)
    check_region_segregation(d)
    check_ethnic_enclaves(d)
    check_apportioned_flag(d)
    check_diaspora_labels(d)
    check_published_residuals(d)
    check_dictionary_numbers(data, d)
    check_single_district_province(d)
    check_visa_label_per_code(d)
    check_visa_label_variants(d)
    check_stata_labels(data)
    check_district_tables_agree(d)
    check_national_reach(d)
    check_naturalization_grid(d)
    print()
    if FAILED:
        print("%d of %d checks FAILED:" % (len(FAILED), CHECKED))
        for f in FAILED:
            print("   %s" % f)
        return 1
    print("all %d checks passed." % CHECKED)
    return 0


if __name__ == "__main__":
    sys.exit(main())
