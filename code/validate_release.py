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
    "age_sex_national.csv": ["year", "country", "gender", "age_group"],
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
        print("  FAIL  %s%s" % (label, ("  |  " + detail) if detail else ""))
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
    check_coverage_text(data, d)
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
