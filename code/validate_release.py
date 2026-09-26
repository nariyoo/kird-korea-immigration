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
                   non_naturalized = its five components
    rates          foreign_share_pct, settlement_rate_pct and the three dependence
                   rates recompute from the published counts
    indices        shannon_H, evenness, HHI, index_base_k, n_nationalities_observed
                   and continent_H recomputed from nationality_by_sigungu
    segregation    dissimilarity_D, isolation, interaction_korean and
                   theil_segregation_H recomputed from the counts and resident_pop
    cross-file     district sums reconcile with the sido and national tables
    age bases      age_sex_national carries registered 2009- and stay 2011- as
                   two labelled series, and each sums to nationality_national
                   for the same population, country and year
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
        out[y] = set([c for c, _ in sorted(agg.items(), key=lambda x: -x[1])
                      if c != "기타"][:19])
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
            # 기타는 나라가 아니라 잔여 칸이므로 세지 않는다
            "_obs": len([1 for c, v in cs.items() if v > 0 and c != "기타"]),
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
        top = set([c for c, _ in sorted(agg.items(), key=lambda x: -x[1]) if c != "기타"][:19])
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
    for lo, hi, keys in (("nationality_by_sigungu.csv", "nationality_by_sido.csv",
                          ["year", "sido", "country"]),
                         ("visa_by_sigungu.csv", "visa_by_sido.csv",
                          ["year", "sido", "visa_code"])):
        a_, b_ = d.get(lo), d.get(hi)
        if a_ is None or b_ is None:
            continue
        a = (a_[~a_["sigungu"].isin(AGG)].groupby(keys)["n"].sum()
             if "sigungu" in a_.columns else a_.groupby(keys)["n"].sum())
        b = b_.groupby(keys)["n"].sum()
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
# a documented reason. Keys are (population, year); the value is the total by
# which the age table exceeds nationality_national, summed over the countries
# that differ. Every other (population, year, country) must match exactly.
#   stay 2022  The age table lists 홍콩거주난민 (17), which the release folds into
#              홍콩; the status table has no such row and holds those 17 in its
#              기타 line (carried since 2026-09-26 as country 기타, which the age
#              table drops). The status table does not say which statuses they
#              hold, so they cannot be placed.
# (stay 2014 used to be here: the 자격없음(0-0) column, 434 persons, was not read
#  by the status parser. It is now read as visa code X00 and the gap is gone.)
#   stay 2019  The status table prints one 제3의성 (third sex) person under
#              오스트레일리아, counted since 2026-09-26; the age table of that edition
#              has no such row, so its M + F total is one lower.
AGE_BASE_KNOWN = {("stay", 2022): 17, ("stay", 2019): -1}

# The yearbook's nationality x status table prints lines that name no nationality;
# since 2026-09-26 the national tables carry them so each year adds up to the
# printed grand total. Nothing below the national level carries them.
RESIDUAL_LINES = {"무국적", "기타", "미등록국가", "미상", "한국"}


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
    for pop, first in (("registered", 2009), ("stay", 2011)):
        ys = set(a.loc[a["population"] == pop, "year"].astype(int))
        want = set(range(first, last + 1))
        check(ys == want, "age bases: %s covers %d-%d" % (pop, first, last),
              "missing %s, extra %s" % (sorted(want - ys), sorted(ys - want)))
    bands = set(a["age_group"].unique())
    want_b = {"0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
              "40-44", "45-49", "50-54", "55-59", "60+"}
    check(bands == want_b, "age bases: the 13 age bands and no others",
          "extra %s, missing %s" % (sorted(bands - want_b), sorted(want_b - bands)))
    if n is None:
        return
    t = (a[a["gender"] == "T"].groupby(["population", "year", "country"])["n"].sum())
    m = n[~n["country"].isin(RESIDUAL_LINES)].set_index(
        ["population", "year", "country"])["n"]
    j = pd.concat([t.rename("age"), m.rename("nat")], axis=1)
    keep = [(p == "registered" and y >= 2009) or (p == "stay" and y >= 2011)
            for p, y, _ in j.index]
    j = j[keep].fillna(0)
    j["gap"] = j["age"] - j["nat"]
    bad = j[j["gap"] != 0]
    by = bad.groupby(level=[0, 1])["gap"].agg(["sum", "min", "size"])
    unexplained = []
    for (p, y), r in by.iterrows():
        want = AGE_BASE_KNOWN.get((p, int(y)))
        if want is None or r["sum"] != want or (r["min"] < 0 and want >= 0):
            unexplained.append("%s %d: %+d over %d countries"
                               % (p, y, r["sum"], r["size"]))
    missing = [k for k in AGE_BASE_KNOWN if k not in by.index]
    check(not unexplained and not missing,
          "age bases: T summed over ages = nationality_national, per population, "
          "year and country",
          "unexplained %s; documented but absent %s" % (unexplained[:4], missing))


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
    t2a = {"국적회복": "회복", "국적판정": "국적판정", "국적상실": "국적상실",
           "국적이탈": "국적이탈", "국적취득(인지)": "국적취득 (인지)",
           "국적취득(재취득)": "국적취득 (재취득)", "국적선택": "국적선택", "국적보유": "국적보유"}
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
                ref = A.get((y, "국적취득 (인지)"), 0) + A.get((y, "국적취득 (재취득)"), 0)
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
        exp.append(("age_sex_national.csv", "age_group",
                    ["(%d bands in every year)" % a["age_group"].nunique()]))
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


def main():
    data = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    if not os.path.isdir(data):
        raise SystemExit("no such directory: %s" % data)
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
    check_region_totals(d)
    check_diaspora_labels(d)
    check_published_residuals(d)
    check_dictionary_numbers(data, d)
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
