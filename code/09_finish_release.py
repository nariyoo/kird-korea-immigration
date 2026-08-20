"""Release finishing, from the exported CSVs to the audited bundle.

finalize_release is the single authority for the released schema: three MOIS
source corrections, the remaining English label columns, the multicultural
category_level flag, and the trim to the data descriptor's schema. The
segregation files are then recomputed over all districts, since the in-build
version drops Sejong, whose district row is labelled 총계; the bilingual
dictionary is regenerated and asserted against the files present; every table is
written as a labeled Stata .dta; and the audit closes the phase. It must end
AUDIT CLEAN before anything is uploaded.
"""
import csv
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

from kird import RELEASE
from kird import RELEASE as REL
from kird import RELEASE_DATA
from kird import RELEASE_DATA as DATA
from kird import ROOT


def norm(s):
    return re.sub(r"\s+", "", str(s))


# ---------- canonical English maps (mirror build_dashboard.py / export_dataset.py) ----------
REGION_EN = {
    "동아시아": "East Asia", "동남아시아": "Southeast Asia", "남아시아": "South Asia",
    "중앙아시아": "Central Asia", "서아시아": "West Asia", "유럽": "Europe",
    "북아메리카": "North America", "중남미": "Latin America", "오세아니아": "Oceania",
    "아프리카": "Africa", "기타": "Other",
}

VISA_LABEL_EN = {
    "A1": "Diplomatic", "A2": "Official Mission", "A3": "Treaty",
    "B1": "Visa Exemption", "B2": "Tourist Transit",
    "C1": "Temporary Coverage", "C2": "Short-term Business",
    "C3": "Short-term Visit", "C4": "Short-term Employment",
    "D1": "Culture & Arts", "D2": "Student", "D3": "Industrial Trainee",
    "D4": "General Trainee", "D5": "Journalism", "D6": "Religious Worker",
    "D7": "Intra-company Transferee", "D8": "Corporate Investment",
    "D9": "Trade Management", "D10": "Job Seeker",
    "E1": "Professor", "E2": "Foreign Language Instructor", "E3": "Researcher",
    "E4": "Technical Instructor", "E5": "Specialized Occupation",
    "E6": "Arts & Entertainment", "E7": "Specially Designated Activities",
    "E8": "Seasonal Worker", "E9": "Non-professional Employment",
    "E10": "Crew Employment",
    "F1": "Visiting Cohabitation", "F2": "Residential", "F3": "Dependent Family",
    "F4": "Overseas Korean", "F5": "Permanent Residence", "F6": "Marriage Migration",
    "G1": "Other (Miscellaneous)",
    "H1": "Working Holiday", "H2": "Visiting Employment",
    "T1": "Tourist Landing",
    "ETC": "Unclassified (SOFA / Treaty)", "E0": "Treaty Activity",
}

# Nationalities the source never paired with English (filled after whitespace norm).
COUNTRY_EN_FILL = {
    "그루지야": "Georgia", "마케도니아": "North Macedonia", "무국적": "Stateless",
    "벨로루시": "Belarus", "스와질란드": "Eswatini", "슬로바크": "Slovakia",
    "앤티카바부다": "Antigua and Barbuda", "영국외지민": "British Overseas Citizen",
    "터키": "Turkey", "홍콩거주난민": "Hong Kong refugee", "러시아": "Russia",
    "기타": "Other",
}

# Bare cities / counties / gu in the MOIS sub-district files (not in the MOJ-unit lut).
RESIDUAL_SGG_EN = {
    "고양시": "Goyang-si", "성남시": "Seongnam-si", "수원시": "Suwon-si",
    "안산시": "Ansan-si", "안양시": "Anyang-si", "용인시": "Yongin-si",
    "창원시": "Changwon-si", "포항시": "Pohang-si", "전주시": "Jeonju-si",
    "천안시": "Cheonan-si", "청주시": "Cheongju-si", "부천시": "Bucheon-si",
    "충주시": "Chungju-si", "군위군": "Gunwi-gun", "청원군": "Cheongwon-gun",
    "청송군": "Cheongsong-gun", "마산시": "Masan-si", "연기군": "Yeongi-gun",
    "포천군": "Pocheon-gun",
    "남구": "Nam-gu", "북구": "Buk-gu", "덕진구": "Deokjin-gu", "완산구": "Wansan-gu",
    "소사구": "Sosa-gu", "오정구": "Ojeong-gu", "원미구": "Wonmi-gu",
    "의창구": "Uichang-gu", "성산구": "Seongsan-gu", "마산합포구": "Masanhappo-gu",
    "마산회원구": "Masanhoewon-gu", "진해구": "Jinhae-gu",
    "부천시 소사구": "Bucheon-si Sosa-gu", "부천시 오정구": "Bucheon-si Ojeong-gu",
    "부천시 원미구": "Bucheon-si Wonmi-gu",
}

TYPO_FIX = {"청순군": "청송군", "충청북도충주시": "충주시"}

MC_CATEGORY_EN = {
    "합계": "Total",
    "한국인배우자": "Korean spouse",
    "결혼이민자귀화자_소계": "Marriage migrants & naturalized (subtotal)",
    "결혼이민자": "Marriage migrant",
    "귀화자등": "Naturalized",
    "자녀_소계": "Children (subtotal)",
    "자녀_국내출생": "Child (born in Korea)",
    "자녀_귀화인지외국국적": "Child (naturalized/foreign)",
    "기타동거인_소계": "Other cohabitants (subtotal)",
    "기타동거인_내국인": "Other cohabitant (Korean)",
    "기타동거인_외국인": "Other cohabitant (foreign)",
}
MC_LEVEL = {"합계": "total",
            "결혼이민자귀화자_소계": "subtotal", "자녀_소계": "subtotal",
            "기타동거인_소계": "subtotal"}


def files():
    return sorted(glob.glob(os.path.join(DATA, "*.csv")))


def read(path):
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str)


def write(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig")


def insert_after(df, new_col, after, values):
    df = df.assign(**{new_col: values})
    cols = list(df.columns)
    cols.remove(new_col)
    cols.insert(cols.index(after) + 1, new_col)
    return df[cols]


def build_country_en_map():
    """normalized country -> country_en, harvested from already-populated values."""
    cmap = {}
    for p in files():
        d = read(p)
        if {"country", "country_en"}.issubset(d.columns):
            for c, e in d[["country", "country_en"]].dropna().drop_duplicates().values:
                if str(e).strip():
                    cmap.setdefault(norm(c), e)
    for ko, en in COUNTRY_EN_FILL.items():
        cmap.setdefault(norm(ko), en)
    return cmap


def build_sigungu_en_map():
    """(sido, normalized sigungu) -> sigungu_en, from files that carry it + residual."""
    lut = {}
    for p in files():
        d = read(p)
        if {"sido", "sigungu", "sigungu_en"}.issubset(d.columns):
            sub = d[["sido", "sigungu", "sigungu_en"]].dropna().drop_duplicates()
            for _, r in sub.iterrows():
                en = str(r["sigungu_en"]).strip()
                if en:
                    lut[(r["sido"], norm(r["sigungu"]))] = en
    return lut


def finalize_release():
    # ---- step 1+2: typo fix + country whitespace normalization (write back) ----
    for p in files():
        d = read(p)
        changed = False
        if "sigungu" in d.columns:
            new = d["sigungu"].replace(TYPO_FIX)
            if not new.equals(d["sigungu"]):
                d["sigungu"] = new; changed = True
        if "country" in d.columns:
            new = d["country"].map(lambda s: re.sub(r"\s+", "", s) if isinstance(s, str) else s)
            if not new.equals(d["country"]):
                d["country"] = new; changed = True
        if changed:
            write(d, p)

    # ---- step 1b: 2014 평창동 source typo (broad_total 505 -> 622; see docstring) ----
    p_emd = os.path.join(DATA, "summary_by_eupmyeondong.csv")
    d = read(p_emd)
    m = ((d["year"] == "2014") & (d["sigungu"] == "종로구")
         & (d["eupmyeondong"] == "평창동") & (d["broad_total"] == "505"))
    if m.any():
        d.loc[m, "broad_total"] = "622"
        d.loc[m, "settlement_rate_pct"] = "9.16"   # (17 + 40) / 622 * 100
        write(d, p_emd)
        print("summary_by_eupmyeondong.csv: 2014 평창동 broad_total 505 -> 622 (source typo)")

    # ---- step 1d: ethnic_enclaves — drop residual-category rows, resync the count ----
    # In 2008-2013 the district source publishes only the top 19 nationalities plus a
    # residual 기타 (Other); 기타 can mechanically clear the LQ/share thresholds (e.g.
    # 거제시 2013, LQ 16.4) but is not a nationality and not an enclave under the
    # Wilson-Portes / Logan criterion. Drop those rows and recompute
    # national_annual.n_enclaves from the file so the two stay consistent.
    p_enc = os.path.join(DATA, "ethnic_enclaves.csv")
    d = read(p_enc)
    if (d["country"] == "기타").any():
        n0 = len(d)
        d = d[d["country"] != "기타"]
        write(d, p_enc)
        print(f"ethnic_enclaves.csv: dropped {n0 - len(d)} residual-기타 rows ({len(d)} remain)")
    counts = d.groupby("year").size()
    p_na = os.path.join(DATA, "national_annual.csv")
    na = read(p_na)
    new_n = [str(counts.get(y, "")) if str(counts.get(y, "")) else na.loc[i, "n_enclaves"]
             for i, y in enumerate(na["year"])]
    if list(na["n_enclaves"]) != new_n:
        na["n_enclaves"] = new_n
        write(na, p_na)
        print("national_annual.csv: n_enclaves resynced to ethnic_enclaves.csv")

    # ---- step 1e: lisa — one convention for island districts across all years ----
    # The 2008-2013 builder labels the eight no-neighbor island districts "ns" while
    # the 2014+ path left them blank; harmonize to "ns" (matches Methods).
    ISLANDS = {("부산광역시", "영도구"), ("인천광역시", "강화군"), ("인천광역시", "옹진군"),
               ("전라남도", "완도군"), ("전라남도", "진도군"), ("경상북도", "울릉군"),
               ("경상남도", "거제시"), ("경상남도", "남해군")}
    p_sg = os.path.join(DATA, "summary_by_sigungu.csv")
    d = read(p_sg)
    m = (d["lisa"].isna() | (d["lisa"].astype(str).str.strip() == "")) &         d.apply(lambda r: (r["sido"], r["sigungu"]) in ISLANDS, axis=1)
    if m.any():
        d.loc[m, "lisa"] = "ns"
        write(d, p_sg)
        print(f"summary_by_sigungu.csv: lisa blank -> ns for {int(m.sum())} island rows")

    # ---- step 1f: visa_by_sigungu — restore pre-merger 창원시 (2008-2009) ----
    # The exporter's gu-less-city cleanup wrongly treated old 창원시 as the parent
    # of 창원시 진해구 (the backcast of pre-merger 진해시) and dropped it, leaving the
    # district visa sums 6,283 / 6,257 short. Values are the parsed source rows
    # (parent visa codes), inlined so this step is self-contained on ../data.
    CW = {
        "2008": {"D2": 128, "D3": 399, "D4": 24, "D6": 10, "D7": 3, "D8": 52, "D9": 6,
                 "E0": 2, "E1": 7, "E2": 181, "E3": 65, "E4": 2, "E6": 28, "E7": 51,
                 "E8": 241, "E9": 2791, "F1": 100, "F2": 836, "F3": 47, "F5": 132,
                 "G1": 45, "H2": 1133},
        "2009": {"D2": 155, "D3": 307, "D4": 42, "D6": 8, "D7": 8, "D8": 43, "D9": 11,
                 "E0": 2, "E1": 8, "E2": 214, "E3": 56, "E4": 3, "E6": 43, "E7": 65,
                 "E8": 170, "E9": 2887, "F1": 93, "F2": 811, "F3": 55, "F5": 172,
                 "G1": 38, "H1": 1, "H2": 1065},
    }
    p_vs = os.path.join(DATA, "visa_by_sigungu.csv")
    d = read(p_vs)
    if not ((d["year"] == "2008") & (d["sigungu"] == "창원시")).any():
        add = [{"year": y, "sido": "경상남도", "sido_en": "Gyeongsangnam-do",
                "sigungu": "창원시", "sigungu_en": "Changwon-si",
                "visa_code": c, "n": str(n)}
               for y, codes in CW.items() for c, n in codes.items()]
        d = pd.concat([d, pd.DataFrame(add)[d.columns.tolist()]], ignore_index=True)
        d = d.sort_values(["year", "sido", "sigungu", "visa_code"])
        write(d, p_vs)
        print(f"visa_by_sigungu.csv: restored pre-merger 창원시 ({len(add)} rows, 2008-2009)")

    # ---- step 1g: visa_by_sigungu — drop the stray 포천군 2009 parse artifact ----
    d = read(p_vs)
    m = (d["year"] == "2009") & (d["sigungu"] == "포천군")
    if m.any():
        d = d[~m]
        write(d, p_vs)
        print(f"visa_by_sigungu.csv: dropped stray 포천군 2009 artifact ({int(m.sum())} row)")

    # ---- step 1h: children_by_age — drop 연기군 duplicates of the Sejong backfill ----
    # The Sejong continuity backfill copies 연기군 2011-2012 onto 세종특별자치시/세종시
    # but the original 연기군 rows were left in place, so national sums double-count
    # those children (365 in 2011, 386 in 2012). Keep the Sejong-labelled series
    # (the panel's continuous unit) and drop the 연기군 originals.
    p_ca = os.path.join(DATA, "children_by_age.csv")
    d = read(p_ca)
    m = d["sigungu"] == "연기군"
    if m.any():
        d = d[~m]
        write(d, p_ca)
        print(f"children_by_age.csv: dropped {int(m.sum())} 연기군 rows duplicated by the Sejong backfill")

    # ---- step 1i: children_by_age — drop double-counted parent-city rows (2016+) ----
    # From 2016 the MOIS age sheet lists general-district cities BOTH as a city
    # aggregate row and as their gu; keeping both double-counts those children
    # (about 32,000 in 2016). Where a (year, city) also has gu rows, drop the
    # city aggregate and keep the gu grain (the panel's unit).
    p_ca = os.path.join(DATA, "children_by_age.csv")
    d = read(p_ca)
    has_gu = set()
    for (y, sd), grp in d.groupby(["year", "sido"]):
        for sgg in grp["sigungu"].unique():
            if " " in sgg and sgg.split(" ", 1)[1].endswith("구"):
                has_gu.add((y, sd, sgg.split(" ", 1)[0]))
    m = d.apply(lambda r: (r["year"], r["sido"], r["sigungu"]) in has_gu, axis=1)
    if m.any():
        d = d[~m]
        write(d, p_ca)
        print(f"children_by_age.csv: dropped {int(m.sum())} double-counted parent-city rows ({len(d)} remain)")

    # ---- step 2b: align the summary schema to the Scientific Data descriptor ----
    # (1) Drop the all-empty `lisa` column from summary_by_sido. LISA (local Moran) is a
    #     within-region clustering statistic computed only at the sigungu level; at the
    #     sido level it is never populated, so the column is removed (kept in sigungu).
    p_sido = os.path.join(DATA, "summary_by_sido.csv")
    d = read(p_sido)
    if "lisa" in d.columns and (d["lisa"].fillna("").astype(str).str.strip() == "").all():
        write(d.drop(columns=["lisa"]), p_sido)
        print("summary_by_sido.csv: dropped all-empty 'lisa' column")
    # (2) Drop `broad_share_pct` from all summary files: it is not a variable in the
    #     data descriptor, is trivially re-derivable as broad_total / resident_pop at
    #     the sido/sigungu level, and has no resident-population denominator at the
    #     eup/myeon/dong level (MOIS does not publish one from 2016).
    for nm in ("summary_by_sido.csv", "summary_by_sigungu.csv", "summary_by_eupmyeondong.csv"):
        p = os.path.join(DATA, nm)
        d = read(p)
        if "broad_share_pct" in d.columns:
            write(d.drop(columns=["broad_share_pct"]), p)
            print(f"{nm}: dropped 'broad_share_pct' (not in data descriptor; re-derivable)")

    # (3) Align the settlement_type English label to the data descriptor wording:
    #     the source label 다목적형 is described as "multi-purpose" in the paper, so the
    #     inline English "(Mixed)" is harmonized to "(Multi-purpose)".
    for nm in ("summary_by_sido.csv", "summary_by_sigungu.csv", "summary_by_eupmyeondong.csv"):
        p = os.path.join(DATA, nm)
        d = read(p)
        if "settlement_type" in d.columns and d["settlement_type"].astype(str).str.contains("(Mixed)", regex=False).any():
            d["settlement_type"] = d["settlement_type"].str.replace("(Mixed)", "(Multi-purpose)", regex=False)
            write(d, p)
            print(f"{nm}: settlement_type '(Mixed)' -> '(Multi-purpose)'")

    # ---- step 3: english backfills (need maps built AFTER normalization) ----
    cmap = build_country_en_map()
    lut = build_sigungu_en_map()
    res = {norm(k): v for k, v in RESIDUAL_SGG_EN.items()}

    def sgg_en(sido, sg):
        return lut.get((sido, norm(sg))) or res.get(norm(sg), "")

    report = []
    for p in files():
        d = read(p)
        name = os.path.basename(p)
        touched = []

        # country_en: add or backfill
        if "country" in d.columns:
            en = [cmap.get(norm(c), "") if isinstance(c, str) else "" for c in d["country"]]
            if "country_en" in d.columns:
                cur = d["country_en"].fillna("")
                merged = [n if (not str(c).strip()) else c for c, n in zip(cur, en)]
                if list(merged) != list(cur):
                    d["country_en"] = merged; touched.append("country_en")
            else:
                d = insert_after(d, "country_en", "country", en); touched.append("country_en+")
            blank = sum(1 for c, e in zip(d["country"], d["country_en"])
                        if isinstance(c, str) and c.strip() and not str(e).strip())
            if blank:
                report.append(f"  WARN {name}: country_en still blank x{blank}")

        # sigungu_en: add (sub-district files) or backfill blanks
        if "sigungu" in d.columns:
            vals = [sgg_en(s, g) if isinstance(g, str) else "" for s, g in zip(d.get("sido", [None]*len(d)), d["sigungu"])]
            if "sigungu_en" in d.columns:
                cur = d["sigungu_en"].fillna("")
                merged = [v if not str(c).strip() else c for c, v in zip(cur, vals)]
                if list(merged) != list(cur):
                    d["sigungu_en"] = merged; touched.append("sigungu_en")
            else:
                d = insert_after(d, "sigungu_en", "sigungu", vals); touched.append("sigungu_en+")

        # region_en / continent_en
        for ko in ("region", "continent"):
            if ko in d.columns and f"{ko}_en" not in d.columns:
                d = insert_after(d, f"{ko}_en", ko, [REGION_EN.get(x, "") for x in d[ko]])
                touched.append(f"{ko}_en+")

        # visa_label_en
        if "visa_label" in d.columns and "visa_label_en" not in d.columns:
            en = [VISA_LABEL_EN.get(str(c).strip()) or str(l)
                  for c, l in zip(d["visa_code"], d["visa_label"])]
            d = insert_after(d, "visa_label_en", "visa_label", en)
            touched.append("visa_label_en+")

        # multicultural: category_en fill + category_level
        if name == "multicultural_households.csv":
            new_en = [MC_CATEGORY_EN.get(c, "") for c in d["category"]]
            if "category_en" not in d.columns or list(d["category_en"].fillna("")) != new_en:
                d["category_en"] = new_en
                touched.append("category_en")
            new_lvl = [MC_LEVEL.get(c, "leaf") for c in d["category"]]
            if "category_level" not in d.columns:
                d = insert_after(d, "category_level", "category_en", new_lvl)
                touched.append("category_level+")
            elif list(d["category_level"]) != new_lvl:
                d["category_level"] = new_lvl
                touched.append("category_level")

        if touched:
            write(d, p)
            report.append(f"  {name}: {', '.join(touched)}")

    print("finalize_release applied:")
    print("\n".join(report) if report else "  (nothing to change — already finalized)")



def build_segregation():
    """Regenerate the segregation files from the released CSVs (self-contained on ../data).

    Definitions (also in the descriptor's supplementary formula table):
      k_i = resident_pop          (Korean nationals; the resident registry excludes foreigners)
      t_i = resident_pop + registered_foreigners   (total district population)
      D_g = 0.5 * sum_i | x_gi/X_g - k_i/K |
      isolation_g           = sum_i (x_gi/X_g) * (x_gi/t_i)
      interaction_korean_g  = sum_i (x_gi/X_g) * (k_i/t_i)
    computed over ALL districts in summary_by_sigungu (the prior release silently
    dropped Sejong), for the same (year, group) keys as already released, 2014-2024.

    national_annual.theil_segregation_H is recomputed on a uniform top-19-plus-residual
    basis for every year 2009-2024 (the prior series mixed top-19 before 2014 with the
    full nationality detail afterwards, straddling the granularity break the Shannon
    series is explicitly normalized against). Same k and t as above; groups are that
    year's top 19 nationalities, the residual, and Koreans.
    """
    sg = pd.read_csv(os.path.join(DATA, "summary_by_sigungu.csv"), encoding="utf-8-sig")
    nat = pd.read_csv(os.path.join(DATA, "nationality_by_sigungu.csv"), encoding="utf-8-sig")
    seg = pd.read_csv(os.path.join(DATA, "segregation_by_nationality.csv"), encoding="utf-8-sig")
    reg = pd.read_csv(os.path.join(DATA, "region_segregation.csv"), encoding="utf-8-sig")
    na = pd.read_csv(os.path.join(DATA, "national_annual.csv"), encoding="utf-8-sig")

    C2REGION = dict(seg[["country", "continent"]].dropna().drop_duplicates().values)
    C2REGEN = dict(seg[["continent", "continent_en"]].dropna().drop_duplicates().values)


    def frame(y):
        g = sg[sg.year == y].dropna(subset=["resident_pop", "registered_foreigners"])
        g = g.set_index(["sido", "sigungu"])
        k = g.resident_pop.astype(float)
        t = k + g.registered_foreigners.astype(float)
        n = nat[nat.year == y]
        piv = (n.pivot_table(index=["sido", "sigungu"], columns="country", values="n",
                             aggfunc="sum").reindex(g.index).fillna(0.0))
        return k, t, piv


    def indices(x, k, t):
        X, K = x.sum(), k.sum()
        if X == 0:
            return np.nan, np.nan, np.nan
        D = 0.5 * np.abs(x / X - k / K).sum()
        iso = ((x / X) * (x / t)).sum()
        inter = ((x / X) * (k / t)).sum()
        return D, iso, inter


    # ---------- segregation_by_nationality (same keys, recomputed values) ----------
    rows = []
    for y in sorted(seg.year.unique()):
        k, t, piv = frame(y)
        for c in seg[seg.year == y].country:
            x = piv[c] if c in piv.columns else pd.Series(0.0, index=k.index)
            D, iso, inter = indices(x, k, t)
            rows.append({"year": y, "country": c, "national_total": int(x.sum()),
                         "dissimilarity_D": round(D, 3), "isolation": round(iso, 4),
                         "interaction_korean": round(inter, 4)})
    new = pd.DataFrame(rows)
    out = seg[["year", "country", "country_en", "continent", "continent_en"]].merge(
        new, on=["year", "country"], how="left")
    out = out[["year", "country", "country_en", "continent", "continent_en",
               "national_total", "dissimilarity_D", "isolation", "interaction_korean"]]
    out.to_csv(os.path.join(DATA, "segregation_by_nationality.csv"),
               index=False, encoding="utf-8-sig")
    print(f"segregation_by_nationality.csv: {len(out)} rows recomputed")

    # ---------- region_segregation (same keys) ----------
    rrows = []
    for y in sorted(reg.year.unique()):
        k, t, piv = frame(y)
        bycol = {}
        for c in piv.columns:
            r = C2REGION.get(c, "기타")
            bycol.setdefault(r, []).append(c)
        for r in reg[reg.year == y].region:
            cols = bycol.get(r, [])
            x = piv[cols].sum(axis=1) if cols else pd.Series(0.0, index=k.index)
            D, iso, _ = indices(x, k, t)
            rrows.append({"year": y, "region": r, "total": int(x.sum()),
                          "dissimilarity_D": round(D, 3), "isolation": round(iso, 4)})
    rnew = pd.DataFrame(rrows)
    rout = reg[["year", "region", "region_en"]].merge(rnew, on=["year", "region"], how="left")
    rout = rout[["year", "region", "region_en", "total", "dissimilarity_D", "isolation"]]
    rout.to_csv(os.path.join(DATA, "region_segregation.csv"), index=False, encoding="utf-8-sig")
    print(f"region_segregation.csv: {len(rout)} rows recomputed")

    # ---------- national Theil, uniform top-19 basis ----------
    def ent(p):
        p = p[p > 0]
        return -(p * np.log(p)).sum()


    theil = {}
    for y in sorted(sg.year.unique()):
        if y < 2009:
            continue
        k, t, piv = frame(y)
        tot = piv.sum().sort_values(ascending=False)
        top = [c for c in tot.index if c != "기타"][:19]
        M = pd.DataFrame({c: piv[c] for c in top})
        M["기타"] = piv[[c for c in piv.columns if c not in top]].sum(axis=1)
        M["KOR"] = k
        T = t.sum()
        E = ent(M.sum() / M.sum().sum())
        Ei = M.div(M.sum(axis=1), axis=0).apply(lambda r: ent(r.values), axis=1)
        theil[y] = round(float(((t * (E - Ei)) / (T * E)).sum()), 4)

    na["theil_segregation_H"] = [theil.get(y, np.nan) if y >= 2009 else np.nan for y in na.year]
    na.to_csv(os.path.join(DATA, "national_annual.csv"), index=False, encoding="utf-8-sig")
    print("national_annual.csv: theil_segregation_H recomputed (top-19 basis, all years):")
    print(" ", theil)



def build_data_dictionary():
    """../data_dictionary.csv, from a curated bilingual column spec.

    The spec is asserted against the released files: it must document exactly the
    columns present in every CSV, with nothing missing and nothing extra, so the
    build fails rather than shipping an out-of-date dictionary.

    Runs after step 29. Output columns:
        file, variable, type, description_en, description_ko
    """
    ROOT = RELEASE
    DATA = RELEASE_DATA

    # Columns shared by the place-level summary files (documented once, applied to all
    # three; eupmyeondong is MOIS-only so it omits the MOJ/index columns).
    SUMMARY_FILES = "summary_by_sido.csv / summary_by_sigungu.csv / summary_by_eupmyeondong.csv"

    # spec: list of (file_label, variable, type, description_en, description_ko)
    SPEC = [
        # ---------- place-level summary files ----------
        (SUMMARY_FILES, "year", "integer",
         "Reference year. sido/sigungu 2006-2025; eupmyeondong 2014-2024.",
         "기준연도. sido/sigungu 2006-2025, eupmyeondong 2014-2024."),
        (SUMMARY_FILES, "sido / sido_en", "string",
         "Province or metropolitan city (Korean + English).",
         "광역시·도(한글+영문)."),
        ("summary_by_sigungu.csv / summary_by_eupmyeondong.csv", "sigungu / sigungu_en", "string",
         "District: an autonomous gu, a si (city), a gun (county), or a general gu of a "
         "large city, on the MOJ-published unit (Korean + English).",
         "시군구: 자치구·시·군 및 대도시 일반구. MOJ 발표 단위(한글+영문)."),
        ("summary_by_eupmyeondong.csv", "eupmyeondong", "string",
         "Sub-district (eup/myeon/dong) on that year's administrative boundaries "
         "(Korean only; use adm_code as the language-neutral join key).",
         "읍·면·동. 그 해 행정경계 기준(한글만; 언어중립 조인키는 adm_code)."),
        ("summary_by_eupmyeondong.csv", "adm_code", "string",
         "Official administrative-dong code for that year (7-digit for 2014/2015/2017; "
         "10-digit standard code for 2016 and 2018+; source: vuski/admdongkor). Blank "
         "for the ~1% of dong names with no boundary match that year.",
         "그 해 공식 행정동코드(2014/2015/2017=7자리, 2016·2018~=10자리 표준코드; 출처 "
         "vuski/admdongkor). 경계 미매칭 약 1%는 공백."),
        ("summary_by_sido.csv / summary_by_sigungu.csv", "registered_foreigners", "integer",
         "MOJ registered foreigners (long-term, >90 days). Not published at the "
         "eup/myeon/dong level. District (sigungu) values begin in 2008.",
         "MOJ 등록외국인(장기체류 >90일). 읍면동 미발행. 시군구는 2008년부터."),
        ("summary_by_sido.csv / summary_by_sigungu.csv", "resident_pop", "integer",
         "MOIS resident-registration population of Korean nationals: the common "
         "denominator for foreign_share_pct and every derived index, so "
         "foreign_share = registered_foreigners / resident_pop reproduces exactly.",
         "MOIS 내국인 주민등록인구(공통 분모). foreign_share·broad_share·모든 지표의 분모 → "
         "registered_foreigners/resident_pop로 재현 가능."),
        ("summary_by_sido.csv / summary_by_sigungu.csv", "foreign_share_pct", "float",
         "Registered foreigners / resident population x100 (MOJ basis).",
         "등록외국인/주민등록인구 x100 (MOJ 기준)."),
        (SUMMARY_FILES, "broad_total", "integer",
         "MOIS broad-definition foreign residents = non_naturalized + naturalized + "
         "children. Different population definition from MOJ; not directly comparable.",
         "MOIS 광의 외국인주민 = non_naturalized+naturalized+children. MOJ와 모집단 정의가 "
         "달라 직접비교 부적절."),
        (SUMMARY_FILES, "non_naturalized", "integer",
         "Foreign residents who have not acquired Korean nationality (subtotal).",
         "한국국적 미취득자 소계."),
        (SUMMARY_FILES, "workers / marriage_migrants / students / ethnic_koreans / other_foreigners",
         "integer",
         "Non-naturalized breakdown: foreign workers / marriage migrants / international "
         "students / overseas Koreans (foreign nationality) / other.",
         "미취득자 세부: 외국인근로자/결혼이민자/유학생/외국국적동포/기타."),
        (SUMMARY_FILES, "naturalized", "integer",
         "Residents who acquired Korean nationality (naturalized).",
         "한국국적 취득자(귀화)."),
        (SUMMARY_FILES, "children", "integer",
         "Children of foreign residents (MOIS multicultural-family children).",
         "외국인주민 자녀."),
        (SUMMARY_FILES, "settlement_rate_pct", "float",
         "Settlement rate = (naturalized + children) / broad_total x100.",
         "정주화율 = (naturalized+children)/broad_total x100."),
        (SUMMARY_FILES, "labor_dependence_pct / marriage_dependence_pct / study_dependence_pct",
         "float",
         "Share of the non-naturalized population in the labor / marriage / study "
         "category (each / non_naturalized x100).",
         "노동/결혼/유학 의존도 = 해당유형/non_naturalized x100."),
        (SUMMARY_FILES, "settlement_type", "string",
         "District settlement typology (Korean label with inline English): each "
         "dependence share is divided by a fixed reference share (workers 0.38, "
         "students 0.16, marriage 0.15); the largest ratio at or above 1 sets the label "
         "(ties broken industrial > university > marriage-settled), otherwise "
         "multi-purpose.",
         "정착유형: 각 의존도를 고정 기준치(근로 0.38, 유학 0.16, 결혼 0.15)로 나눠 1 이상인 "
         "최대 비율이 라벨 결정(동률은 산업>대학>결혼 순), 모두 1 미만이면 다목적형."),
        ("summary_by_sigungu.csv", "broad_apportioned", "string",
         "TRUE where the MOIS broad-definition columns of this general-district (gu) row "
         "are estimates apportioned from the parent city's published totals by each gu's "
         "MOJ registered-foreigner share (2008-2015, when MOIS publishes general-district "
         "cities only at the city level); FALSE where MOIS publishes the district "
         "directly; blank where no MOIS composition exists for the row.",
         "이 일반구 행의 MOIS 광의 구성이 부모 시 발행값을 구별 MOJ 등록외국인 비중으로 "
         "안분한 추정치이면 TRUE(2008-2015, MOIS가 일반구 시를 시 단위로만 발행), MOIS가 "
         "구를 직접 발행하면 FALSE, 해당 행에 MOIS 구성이 없으면 공란."),
        ("summary_by_sido.csv / summary_by_sigungu.csv",
         "shannon_H / shannon_H_inclusive / continent_H / HHI / evenness / n_nationalities",
         "float / integer",
         "MOJ-nationality-based diversity, concentration, and evenness indices; see "
         "README 'Index definitions'. Begin 2008/2009.",
         "MOJ 국적구성 기반 다양성·집중·균등 지표(정의는 README). 2008/2009~."),
        ("summary_by_sigungu.csv", "lisa", "string",
         "Local Moran cluster class of the district's foreign share: HH / LL / HL / LH "
         "(999-permutation significance, p<0.05) or ns. Island districts with no "
         "contiguous neighbor are ns. Sigungu only; not defined at the sido level.",
         "시군구 외국인비율의 국지적 Moran 군집 분류: HH/LL/HL/LH(999회 순열, p<0.05) 또는 "
         "ns. 인접 이웃이 없는 도서 시군구는 ns. 시군구 전용(시도엔 미정의)."),
        # ---------- MOJ breakdowns ----------
        ("nationality_by_sigungu.csv / visa_by_sigungu.csv / visa_by_nationality.csv / "
         "age_sex_national.csv / children_by_age.csv / multicultural_households.csv",
         "year", "integer", "Reference year.", "기준연도."),
        ("nationality_by_sigungu.csv / visa_by_sigungu.csv",
         "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English).", "시도·시군구(한글+영문)."),
        ("nationality_by_sigungu.csv", "country / country_en", "string",
         "Nationality (Korean + English).", "국적(한글+영문)."),
        ("nationality_by_sigungu.csv", "n", "integer",
         "MOJ registered foreigners of that nationality in that district-year (2009-2025).",
         "해당 시군구·연도·국적의 MOJ 등록외국인 수(2009-2025)."),
        ("visa_by_sigungu.csv", "visa_code", "string",
         "Visa/status-of-stay code, written without hyphens (E9, F4 = the source's "
         "E-9, F-4).", "체류자격(비자) 코드, 하이픈 없이 표기(E9, F4 = 원자료의 E-9, F-4)."),
        ("visa_by_sigungu.csv", "n", "integer",
         "MOJ registered foreigners on that visa in that district-year (2008-2025).",
         "해당 시군구·연도·비자의 MOJ 등록외국인 수(2008 및 2017-2025)."),
        ("visa_by_nationality.csv", "population", "string",
         "Population base (values: registered / stay): staying foreigners (체류) or registered foreigners (등록).",
         "모집단: 체류외국인 또는 등록외국인."),
        ("visa_by_nationality.csv", "country / country_en", "string",
         "Nationality (Korean + English).", "국적(한글+영문)."),
        ("visa_by_nationality.csv", "visa_code", "string",
         "Visa/status-of-stay code, written without hyphens (E9, F4 = the source's "
         "E-9, F-4).", "체류자격(비자) 코드, 하이픈 없이 표기(E9, F4 = 원자료의 E-9, F-4)."),
        ("visa_by_nationality.csv", "visa_label / visa_label_en", "string",
         "Visa category label (Korean + English). A few pre-2011 legacy codes carry no "
         "descriptive source label and mirror the code (e.g. M1).",
         "비자 분류 라벨(한글+영문). 2006-2011 일부 옛 코드는 원자료에 설명 라벨이 없어 코드를 "
         "그대로 둠(예 M1)."),
        ("visa_by_nationality.csv", "n", "integer",
         "Count for that population x nationality x visa x year (2006-2025).",
         "모집단×국적×비자×연도 인원(2006-2025)."),
        ("age_sex_national.csv", "country / country_en", "string",
         "Nationality (Korean + English).", "국적(한글+영문)."),
        ("age_sex_national.csv", "gender", "string",
         "Sex: M, F, or T for the published total. From the 2023 edition the source "
         "also publishes a 제3의성 (third sex) row, which is counted in T but is not "
         "carried here, so M + F falls short of T by a few people in some countries "
         "(14 nationwide in 2025, 9 in 2024). Use T for a total.",
         "성별(M 남성, F 여성, T 계). 2023년판부터 원자료에 제3의성 행이 있고 그 값은 "
         "T 에 들어 있으나 이 파일에는 따로 싣지 않으므로, 일부 국적에서 M + F 가 T 보다 "
         "몇 명 적습니다(2025년 전국 14명, 2024년 9명). 총계는 T 를 쓰십시오."),
        ("age_sex_national.csv", "age_group", "string", "Age band.", "연령대."),
        ("age_sex_national.csv", "n", "integer",
         "MOJ registered foreigners for that nationality x age x sex x year (2009-2025).",
         "국적×연령×성별×연도 MOJ 등록외국인 수(2009-2025)."),
        # ---------- MOIS breakdowns ----------
        ("children_by_age.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English).", "시도·시군구(한글+영문)."),
        ("children_by_age.csv", "age", "integer",
         "Single year of age, 0-18. No sex breakdown (not published by the source).",
         "연령(0-18세 단년). 성별 구분 없음(원자료 미발행)."),
        ("children_by_age.csv", "n", "integer",
         "MOIS children of foreign residents at that age (2011-2024). Covers ALL "
         "foreign-resident children (Korea-born plus naturalized/foreign-nationality), "
         "so sums exceed the summary files' children column, which counts Korea-born "
         "only from 2016. City grain for general-district cities before 2016; gu grain "
         "from 2016.",
         "해당 연령 외국인주민 자녀 수(2011-2024). 전체 자녀(국내출생+귀화·외국국적) 기준이라 "
         "합계가 summary의 children(2016년부터 국내출생만)보다 큼. 2016년 이전은 일반구 시를 "
         "시 단위로, 2016년부터 구 단위로 수록."),
        ("multicultural_households.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English).", "시도·시군구(한글+영문)."),
        ("multicultural_households.csv", "eupmyeondong", "string",
         "Sub-district (eup/myeon/dong), Korean only.", "읍·면·동(한글만)."),
        ("multicultural_households.csv", "category / category_en", "string",
         "Household-member type (Korean + English). The MOIS source is a 3-level "
         "hierarchy flattened into this file (see category_level), so totals and "
         "subtotals coexist with leaf categories.",
         "다문화가구원 유형(한글+영문). MOIS 원자료가 3단 계층이라 합계·소계·말단이 한 파일에 "
         "공존(category_level 참조)."),
        ("multicultural_households.csv", "category_level", "string",
         "Hierarchy level of the category: 'total' (합계), 'subtotal' (the three _소계), "
         "or 'leaf'. Filter to one level before summing to avoid double counting.",
         "카테고리 계층: 'total'(합계)/'subtotal'(3개 _소계)/'leaf'(말단). 합산 전 한 레벨만 "
         "골라야 중복집계 방지."),
        ("multicultural_households.csv", "n", "integer",
         "MOIS multicultural household members of that type (2016-2024).",
         "해당 유형 다문화가구원 수(2016-2024)."),
        # ---------- naturalization ----------
        ("naturalization_annual.csv / naturalization_by_country.csv / naturalization_by_age.csv",
         "year", "integer",
         "Reference year. The annual series runs 2011-2025; the by-country and by-age "
         "panels run 2009-2025, one year per yearbook edition.",
         "기준연도. 연도별 시계열 2011-2025, 국적별·연령별 패널 2009-2025(연보 1권당 1개 연도)."),
        ("naturalization_by_country.csv", "country / country_en", "string",
         "Former nationality (Korean + English).", "종전국적(한글+영문)."),
        ("naturalization_by_age.csv", "age", "string",
         "Ten-year age band, harmonized across editions by publication order because the "
         "source labels the same bins four different ways (0~10세 / 0~10 / a bare 10 / 0세~9세).",
         "10세 단위 연령대. 연보마다 표기가 달라(0~10세 / 0~10 / 10 / 0세~9세) 게재 순서로 통일."),
        ("naturalization_annual.csv / naturalization_by_country.csv / naturalization_by_age.csv",
         "type / type_en", "string",
         "Nationality-processing route (Korean + English). Editions before 2014 publish a "
         "single 귀화; later ones split it into general, simplified and special "
         "naturalization plus acquisition by family, and 귀화소계 is their sum, which is "
         "what the annual table calls 귀화.",
         "국적처리 유형(한글+영문). 2014년 이전 연보는 귀화 단일 컬럼, 이후는 일반·간이·특별귀화와 "
         "수반취득으로 분리되며 귀화소계는 그 합(연도별 표의 귀화와 동일 정의)."),
        ("naturalization_annual.csv / naturalization_by_country.csv / naturalization_by_age.csv",
         "n", "integer", "Count of cases.", "건수."),
        # ---------- derived ----------
        ("ethnic_enclaves.csv", "year", "integer", "Reference year (2008-2025).",
         "기준연도(2008-2025)."),
        ("ethnic_enclaves.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English).", "시도·시군구(한글+영문)."),
        ("ethnic_enclaves.csv", "country / country_en", "string",
         "Enclave-forming nationality (Korean + English).", "집거 형성 국적(한글+영문)."),
        ("ethnic_enclaves.csv", "count", "integer",
         "Registered foreigners of that nationality in that district.",
         "해당 시군구의 해당 국적 등록외국인 수."),
        ("ethnic_enclaves.csv", "lq", "float",
         "Location quotient on the resident-registry base: (n / district resident_pop) / (national n / national resident_pop); NOT the within-foreigner share.",
         "입지계수 = 지역 점유율 / 전국 점유율."),
        ("ethnic_enclaves.csv", "share_of_foreign_pct", "float",
         "That nationality's share of the district's total foreign population x100.",
         "해당 국적이 시군구 전체 외국인에서 차지하는 비율 x100."),
        ("ethnic_enclaves.csv", "sigungu_foreign_total", "integer",
         "Total foreign population of the district (the share denominator).",
         "시군구 전체 외국인 수(share 분모)."),
        ("language_demand.csv", "year", "integer", "Reference year (2006-2025).",
         "기준연도(2006-2025)."),
        ("language_demand.csv", "scope", "string",
         "'national' (all languages) or 'sigungu' (top ~20 languages per district).",
         "'national'(전체 언어) 또는 'sigungu'(시군구당 상위 ~20개)."),
        ("language_demand.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English); blank for national-scope rows.",
         "시도·시군구(한글+영문); national 행은 공백."),
        ("language_demand.csv", "language / language_en", "string",
         "Estimated first language (Korean + English).", "추정 모어(한글+영문)."),
        ("language_demand.csv", "count", "integer",
         "Estimated speakers = nationality count x that country's L1 (mother-tongue) "
         "speaker share (Ethnologue 24); rounded to whole persons. Korean excluded; "
         "estimates below 0.5 dropped.",
         "추정 화자수 = 국적별 인원 x 해당국 L1 모어 share(Ethnologue 24); 정수로 반올림. "
         "한국어 제외, 0.5 미만 추정치 드롭."),
        ("segregation_by_nationality.csv", "year", "integer", "Reference year (2014-2025).",
         "기준연도(2014-2025)."),
        ("segregation_by_nationality.csv", "country / country_en", "string",
         "Nationality (Korean + English).", "국적(한글+영문)."),
        ("segregation_by_nationality.csv", "continent / continent_en", "string",
         "World region of origin (Korean + English).", "출신 권역(한글+영문)."),
        ("segregation_by_nationality.csv", "national_total", "integer",
         "National count of that nationality (segregation base).",
         "해당 국적 전국 인원(분리지수 기준)."),
        ("segregation_by_nationality.csv", "dissimilarity_D", "float",
         "Index of dissimilarity (D) vs Koreans across districts (evenness).",
         "내국인 대비 비유사성 지수(D), 시군구 분포(균등성)."),
        ("segregation_by_nationality.csv", "isolation", "float",
         "Isolation index (own-group exposure).", "고립 지수(동족 노출)."),
        ("segregation_by_nationality.csv", "interaction_korean", "float",
         "Interaction with Koreans (cross-group exposure).", "내국인과의 접촉(이질 노출)."),
        ("region_segregation.csv", "year", "integer", "Reference year (2014-2025).",
         "기준연도(2014-2025)."),
        ("region_segregation.csv", "region / region_en", "string",
         "World region of origin (Korean + English).", "출신 권역(한글+영문)."),
        ("region_segregation.csv", "total", "integer",
         "National count of foreigners from that region.", "해당 권역 전국 외국인 수."),
        ("region_segregation.csv", "dissimilarity_D", "float",
         "Index of dissimilarity (D) vs Koreans across districts.",
         "내국인 대비 비유사성 지수(D)."),
        ("region_segregation.csv", "isolation", "float", "Isolation index.", "고립 지수."),
        ("national_annual.csv", "year", "integer", "Reference year (2008/2009-2025).",
         "기준연도(2008/2009-2025)."),
        ("national_annual.csv", "foreign_total", "integer",
         "National MOJ registered foreigners (= sum of summary_by_sigungu).",
         "전국 MOJ 등록외국인(= summary_by_sigungu 합)."),
        ("national_annual.csv", "total_pop", "integer",
         "National resident-registration population.", "전국 주민등록인구."),
        ("national_annual.csv", "foreign_share_pct", "float",
         "National foreign share x100.", "전국 외국인 비율 x100."),
        ("national_annual.csv",
         "shannon_H / shannon_H_inclusive / continent_H / HHI / evenness", "float",
         "National-level diversity, concentration, and evenness indices (see README).",
         "전국 수준 다양성·집중·균등 지표(README 참조)."),
        ("national_annual.csv", "theil_segregation_H", "float",
         "Theil multigroup segregation H over Koreans + each nationality (Reardon & "
         "Firebaugh 2002), on a uniform top-19-plus-residual basis every year, over all "
         "districts, with Korean count = resident_pop and district total = resident_pop "
         "+ registered_foreigners.",
         "내국인+국적별 Theil 다집단 분리지수 H(Reardon & Firebaugh 2002). 전 연도 동일한 "
         "top-19+잔여 기준, 전 시군구, 내국인=resident_pop, 분모=resident_pop+등록외국인."),
        ("national_annual.csv", "morans_I_share", "float",
         "Moran's I of the district foreign-share surface (spatial autocorrelation).",
         "시군구 외국인비율의 Moran's I(공간 자기상관)."),
        ("national_annual.csv", "n_nationalities", "integer",
         "Number of distinct nationalities.", "국적 수."),
        ("national_annual.csv", "n_enclaves", "integer",
         "Number of ethnic enclaves that year (LQ>=2 & single nationality >=30%).",
         "그 해 집거지 수(LQ>=2 & 단일국적>=30%)."),
        # ---------- cross-file note ----------
        ("(all files)", "*_en columns", "string",
         "Every Korean categorical column has an English partner (sido_en, sigungu_en, "
         "country_en, language_en, category_en, type_en, visa_label_en, region_en, "
         "continent_en). Files are UTF-8 with BOM: read with encoding='utf-8-sig'.",
         "모든 한글 범주 컬럼에 영문 병기. 파일은 UTF-8 BOM → encoding='utf-8-sig'로 읽기."),
    ]


    def expand(label):
        """Map a file label ('a.csv / b.csv') to the list of actual csv filenames."""
        if label == "(all files)":
            return [os.path.basename(p) for p in glob.glob(os.path.join(DATA, "*.csv"))]
        return [s.strip() for s in label.split("/") if s.strip().endswith(".csv")]


    def expand_vars(variable):
        return [v.strip() for v in variable.split("/")]


    def main():
        # write the dictionary
        out = os.path.join(ROOT, "data_dictionary.csv")
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["file", "variable", "type", "description_en", "description_ko"])
            for label, var, typ, en, ko in SPEC:
                w.writerow([label, var, typ, en, ko])
        print(f"wrote {out} ({len(SPEC)} rows)")

        # verify coverage: every actual column documented, nothing documented that is absent
        documented = {}  # file -> set(cols)
        for label, var, *_ in SPEC:
            if label == "(all files)":   # cross-file note, not a real per-file column
                continue
            for f in expand(label):
                documented.setdefault(f, set()).update(expand_vars(var))

        ok = True
        for path in sorted(glob.glob(os.path.join(DATA, "*.csv"))):
            f = os.path.basename(path)
            actual = set(pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns)
            doc = documented.get(f, set())
            missing = actual - doc          # real columns with no dictionary entry
            extra = doc - actual            # documented columns not in this file
            if missing:
                ok = False
                print(f"  [MISSING] {f}: {sorted(missing)}")
            if extra:
                ok = False
                print(f"  [EXTRA]   {f}: {sorted(extra)}")
        print("COVERAGE OK" if ok else "COVERAGE FAILED")

    main()



# ---------- labeled Stata export, shared with the deposit staging ----------
# 10_stage_deposit.py imports these three so the deposit's .dta files are written
# exactly the way the release's are: every column labeled from the data dictionary,
# a dataset label, dictionary-driven numeric typing, Stata 14 / UTF-8. Anything that
# writes a KIRD .dta goes through write_labeled_dta, never a bare to_stata.
RELEASE_VERSION = "1.2.0"
STATA_VERSION = 118      # Stata 14, UTF-8, so Korean text survives
STATA_NAME_MAX = 32      # Stata's variable-name limit


def load_stata_dict(dict_path):
    """(file, variable) -> {'label': desc_en, 'numeric': bool}. The dictionary
    groups equivalent files/variables with ' / ', so expand every combination."""
    dd = pd.read_csv(dict_path, encoding="utf-8-sig")
    m = {}
    for _, r in dd.iterrows():
        fs = [f.strip() for f in str(r["file"]).split("/")]
        vars_ = [v.strip() for v in str(r["variable"]).split("/")]
        typ = str(r["type"]).lower()
        numeric = ("integer" in typ) or ("float" in typ)
        label = "" if pd.isna(r["description_en"]) else str(r["description_en"]).strip()
        for f in fs:
            for v in vars_:
                m[(f, v)] = {"label": label, "numeric": numeric}
    return m


def trim_label(s, n=80):
    """Stata variable labels max 80 chars; cut at a word boundary, no ellipsis."""
    s = " ".join(str(s).split())
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return cut[:sp] if sp > 40 else cut


def write_labeled_dta(csv_path, out_path, meta, dict_name=None,
                      version=RELEASE_VERSION, stem=None):
    """One released CSV -> one labeled .dta, with the schema taken from `meta`
    (load_stata_dict). `dict_name` is the file name the dictionary uses, which is
    the CSV's basename except where the deposit renames a file.

    Read everything as string with blanks preserved, then coerce the numerics the
    dictionary declares - that gives full control over missing values and avoids
    dtype-inference surprises. Over-long variable names are a hard error: Stata
    would truncate them, and a silently truncated column is a corrupted column.
    """
    fname = dict_name or os.path.basename(csv_path)
    stem = stem or os.path.basename(csv_path)[:-4]
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    too_long = [c for c in df.columns if len(c) > STATA_NAME_MAX]
    if too_long:
        raise SystemExit(f"{fname}: variable name(s) over {STATA_NAME_MAX} chars, "
                         f"Stata would truncate them: {too_long}")
    var_labels = {}
    for col in df.columns:
        info = meta.get((fname, col), {"label": "", "numeric": False})
        if info["numeric"]:
            v = pd.to_numeric(df[col].replace("", pd.NA), errors="coerce")
            # keep integer-valued columns as integers when there are no missings
            if v.notna().all() and (v == v.round()).all():
                v = v.astype("int64")
            df[col] = v
        else:
            df[col] = df[col].fillna("")  # string: blank = unreported, not "nan"
        if info["label"]:
            var_labels[col] = trim_label(info["label"])
    df.to_stata(
        out_path,
        write_index=False,
        version=STATA_VERSION,
        variable_labels=var_labels,
        data_label=trim_label(f"KIRD v{version} - {stem}"),
    )
    return df, var_labels


def export_stata():
    """Export every released CSV to a labeled Stata .dta (data/stata/*.dta).

    Reads the published CSVs in data/ and the schema authority data_dictionary.csv,
    then writes one Stata 14 (version 118, UTF-8 / Unicode-safe for Korean) .dta per
    file with:
      - a variable label on every column (English description from the dictionary,
        trimmed to Stata's 80-character limit; the full text stays in the dictionary),
      - a dataset label naming the release + file,
      - numeric columns typed from the dictionary (integer / float), string columns
        kept as readable text (the categorical fields are bilingual, so they are
        self-labeling and need no value-label encoding).

    Run after the CSVs and data_dictionary.csv are final (i.e. after finalize_release.py
    -> build_data_dictionary.py). Idempotent; safe to re-run.

        python code/export_stata.py
    """
    OUT = os.path.join(DATA, "stata")
    DICT = os.path.join(REL, "data_dictionary.csv")

    def main():
        os.makedirs(OUT, exist_ok=True)
        meta = load_stata_dict(DICT)
        csvs = sorted(f for f in os.listdir(DATA) if f.endswith(".csv"))
        if not csvs:
            raise SystemExit(f"no released CSVs in {DATA}: nothing to export")
        print(f"Exporting {len(csvs)} files -> {os.path.relpath(OUT, REL)}/")
        for fname in csvs:
            stem = fname[:-4]
            df, _ = write_labeled_dta(os.path.join(DATA, fname),
                                      os.path.join(OUT, stem + ".dta"), meta)
            print(f"  {stem}.dta: {len(df):>7,} rows x {len(df.columns)} cols")
        print("done.")

    main()


def audit_release():
    """Integrity audit of the public release package (04_dataset_release).

    Re-checkable any time before a Zenodo upload. Validates, against the released
    files only (no pipeline reruns):
      1.  file inventory (exactly the 17 documented CSVs)
      2.  data_dictionary.csv coverage in both directions (grouped rows expanded),
          bilingual descriptions all filled
      3.  no '*' masking, no whitespace-padded labels
      4.  no negative values in count/share columns (Moran's I exempt: can be < 0)
      5.  duplicate rows on each file's logical key
      6.  *_en bilingual completeness (English present wherever Korean is)
      7.  dropped columns stay dropped (broad_share_pct)
      8.  the 2009 national continent_H regression (must be ~0.0498, not 0.092)
      9.  multicultural hierarchy: 합계 == the three _소계 + 한국인배우자 (complete groups)
      10. settlement_type label tokens (Multi-purpose, no legacy 'Mixed')
      11. additive identities: broad_total == non_naturalized + naturalized + children
          and non_naturalized == the five components, on rows where all terms present
      12. derived rates recompute from the published values (foreign_share,
          settlement/dependence rates)
      13. cross-file: national_annual.foreign_total == summary_by_sigungu sums (its
          documented definition); sido-vs-national offset within the documented bound
      14. blank-cell inventory (compare against README "Where blank cells appear")

    Exit code 0 = all checks pass (inventory/offset reports are informational).
    """
    REL = os.path.join(ROOT, "04_dataset_release")
    DATA = os.path.join(REL, "data")

    EXPECTED = {
        "age_sex_national.csv":        ["year", "country", "gender", "age_group"],
        "children_by_age.csv":         ["year", "sido", "sigungu", "age"],
        "ethnic_enclaves.csv":         ["year", "sido", "sigungu", "country"],
        "language_demand.csv":         ["year", "scope", "sido", "sigungu", "language"],
        "multicultural_households.csv": ["year", "sido", "sigungu", "eupmyeondong", "category"],
        "national_annual.csv":         ["year"],
        "naturalization_annual.csv":   ["year", "type"],
        "naturalization_by_age.csv":   ["year", "age", "type"],
        "naturalization_by_country.csv": ["year", "country", "type"],
        "nationality_by_sigungu.csv":  ["year", "sido", "sigungu", "country"],
        "region_segregation.csv":      ["year", "region"],
        "segregation_by_nationality.csv": ["year", "country"],
        "summary_by_eupmyeondong.csv": ["year", "sido", "sigungu", "eupmyeondong"],
        "summary_by_sido.csv":         ["year", "sido"],
        "summary_by_sigungu.csv":      ["year", "sido", "sigungu"],
        "visa_by_nationality.csv":     ["year", "population", "country", "visa_code"],
        "visa_by_sigungu.csv":         ["year", "sido", "sigungu", "visa_code"],
    }

    NEG_OK = {"morans_I_share"}        # Moran's I is legitimately negative
    COMP = ["workers", "marriage_migrants", "students", "ethnic_koreans", "other_foreigners"]

    failures = []
    def check(ok, msg):
        print(f"[{'PASS' if ok else 'FAIL'}] {msg}")
        if not ok:
            failures.append(msg)

    def info(msg):
        print(f"[info] {msg}")

    # ---------------------------------------------------------------- 1. inventory
    present = sorted(f for f in os.listdir(DATA) if f.endswith(".csv"))
    check(present == sorted(EXPECTED), f"inventory: {len(EXPECTED)} expected CSVs, found {len(present)}")
    dfs = {f: pd.read_csv(os.path.join(DATA, f), encoding="utf-8-sig") for f in present}
    for f, df in dfs.items():
        yr = f", years {int(df['year'].min())}-{int(df['year'].max())}" if "year" in df.columns else ""
        info(f"{f}: {len(df):,} rows{yr}")
        check(len(df) > 0, f"{f}: non-empty")

    # ---------------------------------------------------------------- 2. dictionary
    dd = pd.read_csv(os.path.join(REL, "data_dictionary.csv"), encoding="utf-8-sig")
    info(f"data_dictionary.csv: {len(dd)} rows")
    covered, phantom = set(), []
    for _, r in dd.iterrows():
        fls = [x.strip() for x in str(r["file"]).split(" / ")]
        cols = [x.strip() for x in str(r["variable"]).split(" / ")]
        if fls == ["(all files)"]:
            continue                       # the generic *_en row
        for fl in fls:
            for c in cols:
                covered.add((fl, c))
                if fl in dfs and c not in dfs[fl].columns and not c.endswith("columns"):
                    phantom.append((fl, c))
    data_pairs = set((f, c) for f, df in dfs.items() for c in df.columns)
    miss = {p for p in data_pairs if p not in covered and not p[1].endswith("_en")}
    check(not miss, f"dictionary covers every released column ({sorted(miss) if miss else 'all'})")
    check(not phantom, f"dictionary references only real columns ({phantom if phantom else 'all'})")
    for col in ("description_en", "description_ko"):
        blank = dd[col].isna() | (dd[col].astype(str).str.strip() == "")
        check(not blank.any(), f"dictionary {col} all filled")

    # ----------------------------------------------------- 3. masking / whitespace
    for f, df in dfs.items():
        obj = df.select_dtypes(include="object")
        check(not (obj == "*").any().any(), f"{f}: no '*' masked cells")
        padded = any((obj[c].dropna().astype(str) != obj[c].dropna().astype(str).str.strip()).any()
                     for c in obj.columns)
        check(not padded, f"{f}: no whitespace-padded labels")

    # ---------------------------------------------------------------- 4. negatives
    neg = [(f, c, int((df[c] < 0).sum()))
           for f, df in dfs.items()
           for c in df.select_dtypes(include="number").columns
           if c not in NEG_OK and (df[c] < 0).any()]
    check(not neg, f"no negative values outside Moran's I ({neg if neg else 'clean'})")

    # ----------------------------------------------------------- 5. duplicate keys
    for f, key in EXPECTED.items():
        ndup = int(dfs[f].duplicated(subset=key).sum())
        check(ndup == 0, f"{f}: unique on {key}")

    # ------------------------------------------------------- 6. bilingual columns
    for f, df in dfs.items():
        for c in df.columns:
            if not c.endswith("_en") or c[:-3] not in df.columns:
                continue
            ko_ok = df[c[:-3]].notna() & (df[c[:-3]].astype(str).str.strip() != "")
            n_miss = int((ko_ok & (df[c].isna() | (df[c].astype(str).str.strip() == ""))).sum())
            check(n_miss == 0, f"{f}.{c}: English filled wherever Korean is")

    # ------------------------------------------------------------ 7. dropped cols
    bad_cols = [f for f, df in dfs.items() if "broad_share_pct" in df.columns]
    check(not bad_cols, "broad_share_pct absent from all files")

    # -------------------------------------------------------- 8. 2009 continent_H
    na = dfs["national_annual.csv"]
    v = float(na.loc[na["year"] == 2009, "continent_H"].iloc[0])
    check(0.045 <= v <= 0.055, f"national_annual 2009 continent_H = {v} (~0.0498 expected)")

    # --------------------------------------------- 9. multicultural hierarchy
    mc = dfs["multicultural_households.csv"]
    check(set(mc["category_level"].dropna().unique()) <= {"total", "subtotal", "leaf"},
          "multicultural: category_level values valid")
    piv = mc.pivot_table(index=["year", "sido", "sigungu", "eupmyeondong"],
                         columns="category", values="n", aggfunc="first")
    parts = ["결혼이민자귀화자_소계", "기타동거인_소계", "자녀_소계", "한국인배우자"]
    have = piv[["합계"] + parts].dropna()
    bad = int((have["합계"] != have[parts].sum(axis=1)).sum())
    check(bad == 0, f"multicultural: 합계 == 3 subtotals + 한국인배우자 on {len(have):,} complete groups")

    # ------------------------------------------------------- 10. settlement labels
    toks = set()
    for f in ("summary_by_eupmyeondong.csv", "summary_by_sido.csv", "summary_by_sigungu.csv"):
        toks |= set(dfs[f]["settlement_type"].dropna().unique())
    check(not any("Mixed" in t for t in toks), "settlement_type: no legacy 'Mixed' label")
    check(any("Multi-purpose" in t for t in toks), "settlement_type: 'Multi-purpose' present")

    # --------------------------------------------------- 11. additive identities
    for f in ("summary_by_eupmyeondong.csv", "summary_by_sido.csv", "summary_by_sigungu.csv"):
        df = dfs[f]
        m = df[COMP + ["non_naturalized"]].notna().all(axis=1)
        bad = int((df.loc[m, COMP].sum(axis=1) != df.loc[m, "non_naturalized"]).sum())
        check(bad == 0, f"{f}: non_naturalized == sum(5 components) ({int(m.sum()):,} complete rows)")
        m2 = df[["non_naturalized", "naturalized", "children", "broad_total"]].notna().all(axis=1)
        bad2 = int((df.loc[m2, ["non_naturalized", "naturalized", "children"]].sum(axis=1)
                    != df.loc[m2, "broad_total"]).sum())
        check(bad2 == 0, f"{f}: broad_total == non_naturalized+naturalized+children ({int(m2.sum()):,} rows)")

    # --------------------------------------------------- 12. derived recomputation
    for f in ("summary_by_sido.csv", "summary_by_sigungu.csv"):
        df = dfs[f]
        m = df["registered_foreigners"].notna() & (df["resident_pop"] > 0)
        diff = (df.loc[m, "registered_foreigners"] / df.loc[m, "resident_pop"] * 100
                - df.loc[m, "foreign_share_pct"]).abs()
        check(float(diff.max()) <= 0.011, f"{f}: foreign_share_pct recomputes (max diff {diff.max():.4f})")
    for f in ("summary_by_eupmyeondong.csv", "summary_by_sido.csv", "summary_by_sigungu.csv"):
        df = dfs[f]
        m = (df[["non_naturalized", "naturalized", "children", "broad_total"]].notna().all(axis=1)
             & (df["broad_total"] > 0) & df["settlement_rate_pct"].notna())
        rec = (df.loc[m, "naturalized"] + df.loc[m, "children"]) / df.loc[m, "broad_total"] * 100
        d = (rec - df.loc[m, "settlement_rate_pct"]).abs()
        check(float(d.max()) <= 0.011, f"{f}: settlement_rate_pct recomputes (max diff {d.max():.4f})")
        for num, col in (("workers", "labor_dependence_pct"), ("marriage_migrants", "marriage_dependence_pct"),
                         ("students", "study_dependence_pct")):
            m = df[num].notna() & (df["non_naturalized"] > 0) & df[col].notna()
            d = (df.loc[m, num] / df.loc[m, "non_naturalized"] * 100 - df.loc[m, col]).abs()
            check(float(d.max()) <= 0.011, f"{f}: {col} recomputes (max diff {d.max():.4f})")

    # ------------------------------------------------------ 13. cross-file totals
    sg_sum = dfs["summary_by_sigungu.csv"].groupby("year")["registered_foreigners"].sum()
    for y, tot in na.set_index("year")["foreign_total"].items():
        if y in sg_sum.index:
            check(int(sg_sum[y]) == int(tot),
                  f"national_annual.foreign_total == sigungu sum ({y}: {int(tot):,})")
    sd_sum = dfs["summary_by_sido.csv"].groupby("year")["registered_foreigners"].sum()
    worst = 0.0
    for y, tot in na.set_index("year")["foreign_total"].items():
        if y in sd_sum.index and tot:
            worst = max(worst, abs(sd_sum[y] - tot) / tot * 100)
    # the published province table's own grand total exceeds the sum of the yearbook's
    # district rows (district-unattributable residents); worst year is 2010 at 0.75%
    check(worst < 0.8, f"sido-table vs national offset (separately published province table): worst {worst:.2f}% < 0.8%")
    vn = dfs["visa_by_nationality.csv"]
    vtot = vn[vn["population"] == "registered"].groupby("year")["n"].sum()
    rel = max(abs(vtot[y] - t) / t * 100 for y, t in na.set_index("year")["foreign_total"].items() if y in vtot.index)
    info(f"visa_by_nationality (published national table) vs district-reconciled foreign_total: "
         f"worst {rel:.2f}% — definitional, foreign_total is documented as the sigungu sum")

    # ----------------------------------------------------- 14. blank-cell inventory
    print("\n----- blank-cell inventory (compare against README 'Where blank cells appear') -----")
    for f, df in dfs.items():
        for c in df.columns:
            nblank = int(df[c].isna().sum())
            if nblank:
                print(f"  {f}.{c}: {nblank:,} blank of {len(df):,}")

    print("\n" + "=" * 70)
    if failures:
        print(f"AUDIT FAILED — {len(failures)} failing checks:")
        for msg in failures:
            print("  -", msg)
        sys.exit(1)
    print("AUDIT CLEAN — all checks passed.")


if __name__ == "__main__":
    finalize_release()
    build_segregation()
    build_data_dictionary()
    export_stata()
    audit_release()
