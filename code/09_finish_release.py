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

from kird import add_code_columns, unresolved
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
    "E8": "Seasonal Worker", "E8T": "Trainee Employment (former E-8, to 2009)",
    "E9": "Non-professional Employment",
    "E10": "Crew Employment",
    "F1": "Visiting Cohabitation", "F2": "Residential", "F3": "Dependent Family",
    "F4": "Overseas Korean", "F5": "Permanent Residence", "F6": "Marriage Migration",
    "G1": "Other (Miscellaneous)",
    "H1": "Working Holiday", "H2": "Visiting Employment",
    "T1": "Tourist Landing",
    "ETC": "Unclassified (SOFA / Treaty)", "E0": "Treaty Activity",
    "X00": "No status (0-0)",
}

# Nationalities the source never paired with English (filled after whitespace norm).
COUNTRY_EN_FILL = {
    "그루지야": "Georgia", "마케도니아": "North Macedonia", "무국적": "Stateless",
    "벨로루시": "Belarus", "스와질란드": "Eswatini", "슬로바크": "Slovakia",
    "앤티카바부다": "Antigua and Barbuda", "영국외지민": "British Overseas Citizen",
    "터키": "Turkey", "홍콩거주난민": "Hong Kong refugee", "러시아": "Russia",
    "미등록국가": "Unregistered country", "미상": "Unknown",
    "기타": "Other", "한국": "Republic of Korea",
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
    # 인접 이웃이 없으면 국지 Moran 이 정의되지 않는다. 두 분류 다 ns 로 둔다.
    for col in ("lisa", "lisa_fdr"):
        if col not in d.columns:
            continue
        m = (d[col].isna() | (d[col].astype(str).str.strip() == "")) & \
            d.apply(lambda r: (r["sido"], r["sigungu"]) in ISLANDS, axis=1)
        if m.any():
            d.loc[m, col] = "ns"
            write(d, p_sg)
            print(f"summary_by_sigungu.csv: {col} blank -> ns for {int(m.sum())} island rows")
    # 계산하지 않은 해를 비우던 블록은 없앴다. build_lisa 가 배포본 CSV 에서
    # 모든 해를 계산하므로 빌 자리가 없다.

    # ---- step 1f: visa_by_sigungu — restore pre-merger 창원시 (2008-2009) ----
    # The exporter's gu-less-city cleanup wrongly treated old 창원시 as the parent
    # of 창원시 진해구 (the backcast of pre-merger 진해시) and dropped it, leaving the
    # district visa sums 6,283 / 6,257 short. Values are the parsed source rows
    # (parent visa codes), inlined so this step is self-contained on ../data.
    CW = {
        "2008": {"D2": 128, "D3": 399, "D4": 24, "D6": 10, "D7": 3, "D8": 52, "D9": 6,
                 "E0": 2, "E1": 7, "E2": 181, "E3": 65, "E4": 2, "E6": 28, "E7": 51,
                 "E8T": 241, "E9": 2791, "F1": 100, "F2": 836, "F3": 47, "F5": 132,
                 "G1": 45, "H2": 1133},
        "2009": {"D2": 155, "D3": 307, "D4": 42, "D6": 8, "D7": 8, "D8": 43, "D9": 11,
                 "E0": 2, "E1": 8, "E2": 214, "E3": 56, "E4": 3, "E6": 43, "E7": 65,
                 "E8T": 170, "E9": 2887, "F1": 93, "F2": 811, "F3": 55, "F5": 172,
                 "G1": 38, "H1": 1, "H2": 1065},
    }
    p_vs = os.path.join(DATA, "visa_by_sigungu.csv")
    d = read(p_vs)
    if not ((d["year"] == "2008") & (d["sigungu"] == "창원시")).any():
        add = [{"year": y, "sido": "경상남도", "sido_en": "Gyeongsangnam-do",
                "sigungu": "창원시", "sigungu_en": "Changwon-si",
                "visa_code": c, "n": str(n)}
               for y, codes in CW.items() for c, n in codes.items()]
        # reindex, not [d.columns]: the restored rows carry the label columns only, and
        # the code columns are recomputed for every row by add_admin_codes below.
        d = pd.concat([d, pd.DataFrame(add).reindex(columns=d.columns.tolist())],
                      ignore_index=True)
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

    # ---- step 1h1: children_by_age — pure renames on one continuous label ----
    # The district panel carries 인천 남구 as 미추홀구, 여주군 as 여주시 and 당진군 as
    # 당진시 in every year (README, "District (sigungu) units"). The released file had
    # those labels from a one-off edit, and when 2026-09-25 made the pipeline write
    # the file again they came back under the old names. Same rule, in code.
    CONTINUOUS = {("인천광역시", "남구"): "미추홀구", ("경기도", "여주군"): "여주시",
                  ("충청남도", "당진군"): "당진시"}
    p_ca = os.path.join(DATA, "children_by_age.csv")
    d = read(p_ca)
    m = [(s, g) in CONTINUOUS for s, g in zip(d["sido"], d["sigungu"])]
    if any(m):
        d.loc[m, "sigungu"] = [CONTINUOUS[(s, g)] for s, g in
                               zip(d.loc[m, "sido"], d.loc[m, "sigungu"])]
        if "sigungu_en" in d.columns:
            d.loc[m, "sigungu_en"] = ""        # refilled from the panel's map below
        write(d, p_ca)
        print(f"children_by_age.csv: {sum(m)} rows onto the continuous district label")

    # ---- step 1h2: children_by_age — 부천시 is one district across the panel ----
    # 부천시 re-created its three general districts in 2024. Every other
    # district-keyed file publishes 부천시 as one unit in every year (the gu existed
    # for only part of the series), but this file carried the 2024 gu rows, all
    # three under sigungu_code 41190, so a (year, sigungu_code) join tripled. Sum
    # the gu into the city row, and check the sum against the city row MOIS prints
    # itself where there is one. 2026-09-25.
    p_ca = os.path.join(DATA, "children_by_age.csv")
    d = read(p_ca)
    gu = d["sigungu"].str.startswith("부천시 ")
    if gu.any():
        g = d[gu].copy()
        g["n_int"] = pd.to_numeric(g["n"], errors="coerce").fillna(0).astype(int)
        summed = g.groupby(["year", "sido", "age"], as_index=False)["n_int"].sum()
        city = d[(d["sigungu"] == "부천시")].copy()
        for _, r in summed.iterrows():
            m = (city["year"] == r["year"]) & (city["age"] == r["age"])
            if m.any():
                printed = int(pd.to_numeric(city.loc[m, "n"]).sum())
                if printed != int(r["n_int"]):
                    raise SystemExit(f"children_by_age 부천시 {r['year']} age {r['age']}: "
                                     f"gu sum {r['n_int']} != city row {printed}")
        keep = d[~gu & ~((d["sigungu"] == "부천시")
                         & d["year"].isin(set(summed["year"])))]
        tmpl = g.drop_duplicates(["year", "age"]).set_index(["year", "age"])
        add = []
        for _, r in summed.iterrows():
            row = tmpl.loc[(r["year"], r["age"])].to_dict()
            row.update({"year": r["year"], "age": r["age"], "sigungu": "부천시",
                        "n": str(int(r["n_int"]))})
            if "sigungu_en" in row:
                row["sigungu_en"] = "Bucheon-si"
            row.pop("n_int", None)
            add.append(row)
        d = pd.concat([keep, pd.DataFrame(add).reindex(columns=d.columns)],
                      ignore_index=True)
        d["_age"] = pd.to_numeric(d["age"], errors="coerce")
        d = d.sort_values(["year", "sido", "sigungu", "_age"]).drop(columns="_age")
        write(d, p_ca)
        print(f"children_by_age.csv: folded {int(gu.sum())} 부천시 gu rows into 부천시 "
              f"({len(add)} rows)")

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
    # 국지 Moran 은 시군구에서만 정의된다. 시도표에 빈 열로 남기지 않는다.
    drop = [c for c in ("lisa", "lisa_fdr") if c in d.columns
            and (d[c].fillna("").astype(str).str.strip() == "").all()]
    if drop:
        write(d.drop(columns=drop), p_sido)
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


    canonicalize_country_labels()
    recount_observed_nationalities()
    add_admin_codes()
    harmonize_district_labels()
    add_emd_code_to_multicultural()
    validate_code_join()


def canonicalize_country_labels():
    """국적 이름을 나라마다 하나로 맞춘다.

    표준화 규칙(kird.COUNTRY_CANONICAL)이 파서의 몇몇 길목에만 걸려 있어서, 같은
    나라가 파일에 따라 두 이름으로 남아 있었다. `age_sex_national` 은 2009-2013 을
    「그루지야·벨로루시·터키」로, 2014 이후를 「조지아·벨라루스·튀르키예」로 싣고,
    시군구·시도 국적표에도 2014년 한 줄씩 옛 이름이 남아 있다. 그대로 두면 그
    나라의 시계열이 중간에 끊긴다.

    바꾼 뒤 같은 열쇠로 겹치는 줄은 수를 더해 하나로 합친다. 검산기
    (validate_release.py) 의 국적 키 유일성 검사가 이 상태를 지킨다.
    """
    from kird import COUNTRY_CANONICAL
    KEYS = {
        "age_sex_national.csv": ["year", "population", "country", "gender", "age_group"],
        "nationality_by_sido.csv": ["year", "sido", "country"],
        "nationality_by_sigungu.csv": ["year", "sido", "sigungu", "country"],
        "nationality_national.csv": ["year", "population", "country"],
        "naturalization_by_country.csv": ["year", "country", "type"],
        "segregation_by_nationality.csv": ["year", "country"],
        "visa_by_nationality.csv": ["year", "population", "country", "visa_code"],
        "ethnic_enclaves.csv": ["year", "sido", "sigungu", "country"],
    }
    for name, key in KEYS.items():
        p = os.path.join(DATA, name)
        if not os.path.exists(p):
            continue
        d = read(p)
        if "country" not in d.columns:
            continue
        # 영문 짝을 크로스워크 하나에 맞춘다. 옛 이름이 남았는지와 무관하게 늘
        # 확인한다 — 이름은 이미 표준인데 영문만 그 해 연보의 표기(Turkey)로 남는
        # 일이 있었고(화성시 2014), 그때 아래의 「옛 이름이 있을 때만」 조건은
        # 발화하지 않는다(2026-08-26).
        cwp = os.path.join(DATA, "crosswalk_country.csv")
        if "country_en" in d.columns and os.path.exists(cwp):
            cw = pd.read_csv(cwp, encoding="utf-8-sig")
            enmap = dict(zip(cw["country"], cw["country_en"]))
            want = d["country"].map(enmap)
            bad = want.notna() & (want != d["country_en"].fillna(""))
            if bad.any():
                pairs = sorted({(a, b, c) for a, b, c in
                                zip(d.loc[bad, "country"],
                                    d.loc[bad, "country_en"], want[bad])})
                d.loc[bad, "country_en"] = want[bad]
                write(d, p)
                d = read(p)
                print("canonicalize_country_labels: %s 영문 이름 %d행 고침 %s"
                      % (name, int(bad.sum()), pairs[:3]))
        hit = d["country"].isin(COUNTRY_CANONICAL)
        if not hit.any():
            continue
        old_names = sorted(d.loc[hit, "country"].unique())
        d["country"] = d["country"].map(lambda c: COUNTRY_CANONICAL.get(c, c))
        # 이름을 바꾼 줄은 영문 짝도 그 이름의 것으로 바꾼다. 안 바꾸면 합치기가
        # 일어나지 않는 파일(시군구표는 열쇠에 시군구가 있어 안 겹친다)에 옛
        # 영문이 남아, 같은 국적이 영문 이름 둘을 갖는다 — 화성시 2014 튀르키예가
        # Turkey 로 남았다(2026-08-26). 영문은 같은 파일의 표준 이름 줄에서 얻고,
        # 파일 안에 없으면 크로스워크에서 얻는다.
        if "country_en" in d.columns:
            en = (d.loc[~hit].dropna(subset=["country_en"])
                   .drop_duplicates("country").set_index("country")["country_en"]
                   .to_dict())
            cwp = os.path.join(DATA, "crosswalk_country.csv")
            if os.path.exists(cwp):
                cw = pd.read_csv(cwp, encoding="utf-8-sig")
                for k, v in zip(cw["country"], cw["country_en"]):
                    en.setdefault(k, v)
            d.loc[hit, "country_en"] = d.loc[hit, "country"].map(en).fillna(
                d.loc[hit, "country_en"])
        before = len(d)
        if d.duplicated(subset=[k for k in key if k in d.columns]).any():
            # 세는 칸만 더한다.
            #
            # 이 자리에 버그가 두 개 있었다(2026-08-26에 찾음).
            #
            #   `read` 가 dtype=str 로 읽으므로 `is_numeric_dtype` 은 어떤 칸에도
            #   참이 아니다. 그래서 인원 칸이 문자 칸으로 분류돼 **더해지지 않고 첫
            #   줄만 남았다.** nationality_by_sido.csv 2014 경기도에서 71명이 이렇게
            #   사라졌다(튀르키예 67, 벨라루스 2, 조지아 2).
            #
            #   짝 칸(country_en)은 「첫 줄」을 골랐다. 옛 이름 줄이 앞에 있으면
            #   튀르키예가 Turkey 로 남는다. 실제로 화성시 2014가 그랬다.
            #
            # 값으로 숫자를 판정하지 않고 **이름으로 세는 칸만** 고른다. lq 나
            # dissimilarity_D 같은 지수는 더하면 안 되는 값이고, 어차피 뒤 단계가
            # 다시 계산한다.
            COUNT = {"n", "count"}
            num = [c for c in d.columns if c in COUNT and c not in key]
            txt = [c for c in d.columns if c not in key and c not in num]
            # 이미 표준 이름인 줄을 앞으로 보내, 문자 칸의 "first" 가 살아남는
            # 이름의 값을 고르게 한다.
            d = (d.assign(_canon=(~hit).astype(int))
                  .sort_values("_canon", ascending=False, kind="mergesort")
                  .drop(columns="_canon"))
            for c in num:
                d[c] = pd.to_numeric(d[c], errors="coerce")
            keep = float(d[num].sum().sum()) if num else 0.0
            agg = {c: "sum" for c in num}
            agg.update({c: "first" for c in txt})
            d = d.groupby([k for k in key if k in d.columns], as_index=False).agg(agg)
            got = float(d[num].sum().sum()) if num else 0.0
            if num and keep != got:
                raise SystemExit("canonicalize_country_labels: %s 합이 달라졌다 "
                                 "%r -> %r" % (name, keep, got))
            for c in num:
                d[c] = d[c].astype("Int64").astype(str).replace("<NA>", "")
            d = d[[c for c in read(p).columns if c in d.columns]]
        write(d, p)
        print("canonicalize_country_labels: %s %d행 -> %d행, 고친 이름 %s"
              % (name, before, len(d), ", ".join(old_names)))


def recount_observed_nationalities():
    """국적 이름을 합친 뒤 관측 국적 수를 다시 센다.

    `n_nationalities_observed` 는 04 단계에서 계산되는데, 그 뒤 09 의
    `canonicalize_country_labels` 가 같은 나라의 두 이름을 하나로 합친다. 그러면
    실린 수가 실제 국적 수보다 크다(2014년 전국: 실린 193, 시군구표에서 세면 190).
    합친 뒤에 다시 세어 층마다 맞춘다. 시군구는 04 가 각 구의 자기 표에서 세므로
    이미 맞지만, 같은 셈법으로 다시 확인한다.
    """
    nat_p = os.path.join(DATA, "nationality_by_sigungu.csv")
    if not os.path.exists(nat_p):
        return
    AGG = {"총계", "총합계", "소계", "계", "기타"}
    nat = read(nat_p)
    # read() 는 글자 그대로 읽으므로 수를 수로 만든다
    nat["n"] = pd.to_numeric(nat["n"], errors="coerce")
    nat = nat[~nat["country"].isin(AGG) & nat["n"].notna() & (nat["n"] > 0)]
    per_sgg = nat.groupby(["year", "sido", "sigungu"])["country"].nunique()
    per_sido = nat.groupby(["year", "sido"])["country"].nunique()
    per_nat = nat.groupby("year")["country"].nunique()

    for name, idx, src in (("summary_by_sigungu.csv", ["year", "sido", "sigungu"], per_sgg),
                           ("summary_by_sido.csv", ["year", "sido"], per_sido),
                           ("national_annual.csv", ["year"], per_nat)):
        p = os.path.join(DATA, name)
        if not os.path.exists(p):
            continue
        d = read(p)
        if "n_nationalities_observed" not in d.columns:
            continue
        key = [c for c in idx if c in d.columns]
        want = d.set_index(key).index.map(lambda k: src.get(k))
        new = [int(w) if w == w and w is not None else old
               for w, old in zip(want, d["n_nationalities_observed"])]
        def same(a, b):
            try:
                return int(float(a)) == int(b)
            except (TypeError, ValueError):
                return False
        moved = sum(1 for a, b in zip(d["n_nationalities_observed"], new) if not same(a, b))
        if moved:
            d["n_nationalities_observed"] = new
            write(d, p)
        print("recount_observed_nationalities: %s %d행을 고쳤다" % (name, moved))


def add_emd_code_to_multicultural():
    """multicultural_households 에 읍면동 코드를 붙인다 (심사 지적 C2).

    이 표는 시도·시군구 코드는 갖고 있었지만 읍면동은 이름으로만 붙일 수 있었다.
    이름은 해마다 바뀌고 같은 이름이 여러 시군구에 있어, 이름 조인은 이용자에게
    조용한 오류를 넘긴다. summary_by_eupmyeondong 이 이미 갖고 있는 `adm_code` 를
    (연도, 시군구 코드, 읍면동 이름)으로 옮겨 붙인다.
    """
    mc_p = os.path.join(DATA, "multicultural_households.csv")
    emd_p = os.path.join(DATA, "summary_by_eupmyeondong.csv")
    if not (os.path.exists(mc_p) and os.path.exists(emd_p)):
        return
    mc = read(mc_p)
    if "adm_code" in mc.columns:
        print("add_emd_code_to_multicultural: 이미 있다")
        return
    emd = read(emd_p)[["year", "sigungu_code", "eupmyeondong", "adm_code"]].dropna()
    emd = emd.drop_duplicates(subset=["year", "sigungu_code", "eupmyeondong"])
    key = ["year", "sigungu_code", "eupmyeondong"]
    merged = mc.merge(emd, on=key, how="left")
    got = merged["adm_code"].notna().sum()
    merged = insert_after(merged.drop(columns=["adm_code"]), "adm_code", "eupmyeondong",
                          merged["adm_code"].values)
    write(merged, mc_p)
    print("add_emd_code_to_multicultural: %d/%d 행에 읍면동 코드를 붙였다 (%.1f%%)"
          % (got, len(mc), 100.0 * got / len(mc)))


def add_admin_codes():
    """sido_code / sigungu_code on every released table that names a place.

    The codes are the 행정안전부 법정동코드 in force on 31 December of the row's year
    (2-digit province, 5-digit district), resolved by kird.py from the register
    kept in 01_raw_data/행정표준코드/. They are the language-neutral join key between
    the levels, and they survive the renames the Korean names do not: 인천 남구 and
    미추홀구 are both 28170 up to the 2018 rename and 28177 after it, and 군위군 is
    47720 while it sat in 경상북도 and 27720 once 대구 took it in 2023. A name the
    register cannot resolve leaves the cell blank and is listed here; no code is
    ever invented.
    """
    print("")
    print("admin codes (that year's 법정동코드):")
    for p in files():
        d = read(p)
        if "sido" not in d.columns or "year" not in d.columns:
            continue
        write(add_code_columns(d, os.path.basename(p)), p)
    u = unresolved()
    if u:
        print("  UNRESOLVED (left blank, no code invented):")
        for (level, year, sido, name), n in sorted(u.items()):
            print(f"    {level} {year} {sido} {name} x{n:,}")
    else:
        print("  every place name resolved")


def harmonize_district_labels():
    """One district name per (year, sigungu_code), the name the district files use.

    The MOJ district files carry one continuous label per district (미추홀구 through
    the whole panel, 부천시 as one unit, the post-merger names for 청원군 and the
    rest). The MOIS files copied whatever each edition printed: 남구 until 2017;
    수원시, 성남시 and the other general-district cities undivided in 2014 although
    each dong already carried its gu's code; 청원군 in 2011-2014; and Bucheon's dongs
    under 원미구/소사구/오정구 in 2015 and 2024 but under 부천시 in the other years.
    A filter or join on the sigungu text therefore dropped or split rows the code
    kept together (the audit of 2026-09-26 found Bucheon missing from 2015 and
    2024). The code is already right, so the name is taken from the district files
    for that code and year; the rows themselves do not change.
    """
    sgg = read(os.path.join(DATA, "summary_by_sigungu.csv"))
    if "sigungu_code" not in sgg.columns:
        return
    lab = (sgg.dropna(subset=["sigungu_code"])
              .groupby(["year", "sigungu_code"])[["sigungu", "sigungu_en"]]
              .agg(lambda v: sorted(set(v))))
    amb = lab[lab["sigungu"].map(len) > 1]
    if len(amb):
        raise SystemExit(f"summary_by_sigungu gives one code two names: {amb.head()}")
    name = {k: (r["sigungu"][0], r["sigungu_en"][0]) for k, r in lab.iterrows()}
    keys = {"summary_by_eupmyeondong.csv": ["year", "sido", "sigungu", "eupmyeondong"],
            "multicultural_households.csv": ["year", "sido", "sigungu", "eupmyeondong",
                                             "category"],
            "children_by_age.csv": ["year", "sido", "sigungu", "age"]}
    print("")
    print("district names harmonized onto the district files' label per code:")
    for p in files():
        fn = os.path.basename(p)
        d = read(p)
        if not {"year", "sigungu", "sigungu_code"} <= set(d.columns):
            continue
        new = [name.get((y, c)) for y, c in zip(d["year"], d["sigungu_code"])]
        m = [bool(n) and n[0] != s_ for n, s_ in zip(new, d["sigungu"])]
        if not any(m):
            continue
        changed = sorted({(d.at[i, "sigungu"], new[i][0]) for i in range(len(d)) if m[i]})
        d.loc[m, "sigungu"] = [new[i][0] for i in range(len(d)) if m[i]]
        if "sigungu_en" in d.columns:
            d.loc[m, "sigungu_en"] = [new[i][1] for i in range(len(d)) if m[i]]
        k = [c for c in keys.get(fn, ["year", "sido", "sigungu"]) if c in d.columns]
        if fn in keys and d.duplicated(k).any():
            raise SystemExit(f"{fn}: {int(d.duplicated(k).sum())} duplicate {k} after "
                             f"the relabel")
        write(d, p)
        print(f"  {fn}: {sum(m):,} rows, {len(changed)} name pairs, e.g. {changed[:4]}")


def validate_code_join():
    """The sub-district table has to join onto the district table on the code.

    Names never guaranteed that. The two levels disagreed on 40 (year, province,
    district) combinations: MOIS writes 남구 until the 2018 rename while the MOJ panel
    carries 미추홀구 throughout, MOIS reports 고양시 whole in 2014 while MOJ reports its
    three general districts, and 군위군 sits under 경상북도 in one table and
    대구광역시 in the other. On the code the two sets have to nest.
    """
    emd = read(os.path.join(DATA, "summary_by_eupmyeondong.csv"))
    sgg = read(os.path.join(DATA, "summary_by_sigungu.csv"))
    if "sigungu_code" not in emd.columns or "sigungu_code" not in sgg.columns:
        print("  (code join not checked: sigungu_code missing)")
        return []
    have = set(map(tuple, sgg[["year", "sigungu_code"]].drop_duplicates().values))
    keys = emd[["year", "sido", "sigungu", "sigungu_code"]].drop_duplicates()
    bad = [tuple(r) for r in keys.values if (r[0], r[3]) not in have]
    n_name = len(set(map(tuple, emd[["year", "sido", "sigungu"]].drop_duplicates().values))
                 - set(map(tuple, sgg[["year", "sido", "sigungu"]].drop_duplicates().values)))
    print(f"  level join: {n_name} (year, sido, sigungu) name mismatches -> "
          f"{len(bad)} on sigungu_code")
    for y, sd, sg, c in sorted(bad):
        print(f"    not in summary_by_sigungu: {y} {sd} {sg} -> {c or '(blank)'}")

    # adm_code 가 제 시군구의 대역 안에 있는가.
    #
    # 코드는 이름으로 붙인다. 그래서 「중앙동」이나 「정자1동」처럼 여러 시군구에
    # 있는 이름이 남의 시군구 코드를 가져갈 수 있다. sigungu_code 중첩 검사는
    # 이것을 못 잡는다 — 시군구 코드는 멀쩡하고 동 코드만 틀리기 때문이다.
    # 2026-08-26에 2024년 창원 성산구 중앙동이 진주시 대역(38030740)을 달고
    # 있었다. 그 구의 다른 동은 전부 3811 로 시작한다.
    #
    # **고친 자리는 상류다.** 06_build_summaries 의 대체 조회가 시군구를 빼고
    # (시도, 동이름) 으로 코드를 찾으면서 `setdefault` 로 먼저 읽힌 구의 것을
    # 주고 있었다. 이제 그 이름이 시도 안에서 유일할 때만 쓴다. 여기 검사는
    # 그것이 다시 무너지면 알리는 최후 방어선이고, 통과하는 것이 정상이다.
    #
    # 한 시군구 안에서 동 코드의 앞 네 자리는 하나여야 한다. 다수와 다른 행을
    # 알린다.
    if "adm_code" in emd.columns:
        e = emd.dropna(subset=["adm_code"]).copy()
        e["adm_code"] = e["adm_code"].astype(str).str.strip()
        e = e[e["adm_code"] != ""]
        e["p4"] = e["adm_code"].str[:4]
        mode = (e.groupby(["year", "sido", "sigungu"])["p4"]
                 .agg(lambda v: v.mode().iloc[0]).rename("mode4").reset_index())
        e = e.merge(mode, on=["year", "sido", "sigungu"])
        odd = e[e["p4"] != e["mode4"]]
        print(f"  adm_code prefix: {len(odd)} sub-district rows sit outside their "
              f"district's code block")
        for _, r in odd.sort_values(["year", "sido", "sigungu"]).iterrows():
            print(f"    {r['year']} {r['sido']} {r['sigungu']} {r['eupmyeondong']} "
                  f"-> {r['adm_code']} (district block {r['mode4']}xxxx)")
        # 비운다. 그 동의 진짜 코드는 모르고, **틀린 코드는 빈 칸보다 나쁘다** —
        # 경계 파일에 붙이면 남의 동 위에 그려진다. 코드는 지어내지 않는다는
        # add_admin_codes 의 규칙을 여기에도 적용한다.
        if len(odd):
            key = set(zip(odd["year"], odd["sido"], odd["sigungu"],
                          odd["eupmyeondong"]))
            m = [t in key for t in zip(emd["year"], emd["sido"], emd["sigungu"],
                                       emd["eupmyeondong"])]
            emd.loc[m, "adm_code"] = ""
            write(emd, os.path.join(DATA, "summary_by_eupmyeondong.csv"))
            print(f"    -> blanked {int(sum(m))} of them (a wrong code is worse "
                  f"than none)")
            e = e[e["p4"] == e["mode4"]]
        # (2014년 두 표기가 만들던 껍데기 중복은 05 의
        #  merge_eupmyeondong_spelling_variants 가 상류에서 합친다. 여기서는
        #  결과만 확인한다.)
        dup = (e[e.duplicated(["year", "adm_code"], keep=False)]
               .sort_values(["year", "adm_code"]))
        n_dup_recent = int((dup["year"].astype(int) >= 2016).sum())
        print(f"  adm_code uniqueness: {len(dup)} rows share a code with another "
              f"row in the same year ({n_dup_recent} of them 2016+)")
    return bad



def build_lisa():
    """외국인 비율의 국지 Moran 을 해마다 계산해 배포본과 지표 파일에 적는다.

    여기가 유일한 계산 자리다. 앞서는 03 과 04 가 각자 계산했고, 04 가 읽던 지표
    파일이 2014년부터라 2008-2013년이 비어 있었다. 배포본 CSV 는 시군구를 확정한
    뒤의 단위 집합이고 2008년부터 외국인 비율을 담으므로, 여기서 읽으면 모든 해를
    채울 수 있다.

    두 열을 쓴다. `lisa` 는 보정 없이 p<0.05, `lisa_fdr` 은 Benjamini-Hochberg 로
    위발견율을 q=0.05 에 묶은 것. 해마다 240곳 남짓을 한꺼번에 검정하므로 보정
    없이는 우연히 12곳가량이 걸린다.

    순열은 99,999회다. 999회면 최소 p 가 0.001 이라 BH 의 첫 문턱(0.05/242)보다
    커서, 보정을 걸면 군집이 있든 없든 0곳이 된다.

    이웃이 없는 시군구(도서)는 통계가 정의되지 않으므로 ns 로 둔다. 값이 비는
    자리는 남기지 않는다.
    """
    import json
    import numpy as np
    import libpysal
    import esda
    from collections import Counter

    adj_path = os.path.join(ROOT, "03_cleaned_data", "adjacency.json")
    if not os.path.exists(adj_path):
        print("build_lisa: adjacency.json 이 없다. 건너뛴다")
        return
    adj = json.load(open(adj_path, encoding="utf-8"))
    LAB = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}

    # 통합 이전 시군구는 지금 경계 파일에 없다. 후신 자치구들의 인접 관계에서
    # 옛 단위의 이웃을 도출한다. 옛 단위의 이웃 = 후신들의 이웃을 합친 것에서
    # 자기 후신을 뺀 것이고, 그중 다른 옛 단위의 후신은 그 옛 이름으로 되돌린다.
    # 2010년 창원 통합이 이 자료에서 유일한 사례다(진해시는 정리 단계에서 이미
    # 「창원시 진해구」로 이름이 바뀌어 인접표에 있다).
    PRE_MERGER = {
        "경상남도|마산시": {"경상남도|창원시마산합포구", "경상남도|창원시마산회원구"},
        "경상남도|창원시": {"경상남도|창원시의창구", "경상남도|창원시성산구"},
    }
    succ_of = {s: pre for pre, ss in PRE_MERGER.items() for s in ss}
    for pre, ss in PRE_MERGER.items():
        if pre in adj or not ss.issubset(adj):
            continue
        nb = set()
        for s in ss:
            nb |= set(adj[s])
        nb -= ss
        adj[pre] = sorted({succ_of.get(n, n) for n in nb})
    # 후신 자치구 자신의 이웃 목록은 건드리지 않는다. 2010년 이후에는 그것이
    # 맞는 단위이기 때문이다. 해마다 그 해에 실린 단위만 골라 쓰므로, 옛 이름과
    # 새 이름이 한 해에 섞이는 일은 없다.

    p_sg = os.path.join(DATA, "summary_by_sigungu.csv")
    d = read(p_sg)

    def key_of(sido, sigungu):
        return (str(sido) + "|" + str(sigungu)).replace(" ", "")

    d["_k"] = [key_of(a, b) for a, b in zip(d["sido"], d["sigungu"])]
    cls, clsf = {}, {}
    summary = {}
    for y, blk in d.groupby("year"):
        share = {}
        for k, v in zip(blk["_k"], blk["foreign_share_pct"]):
            if k in adj and pd.notna(v):
                share[k] = float(v)
        sset = set(share)
        sk = [k for k in share if any(n in sset for n in adj.get(k, []))]
        if len(sk) < 10:
            print("  %s: 이웃이 있는 단위가 %d개뿐이라 건너뛴다" % (y, len(sk)))
            continue
        sset = set(sk)
        W = libpysal.weights.W({k: [n for n in adj[k] if n in sset] for k in sk},
                               silence_warnings=True)
        W.transform = "r"
        order = W.id_order
        lm = esda.Moran_Local(np.array([share[k] for k in order]), W,
                              permutations=99999, seed=42)
        p = lm.p_sim
        m = len(order)
        raw = p < 0.05
        o = np.argsort(p)
        keep = p[o] <= 0.05 * (np.arange(1, m + 1) / m)
        kmax = int(np.max(np.where(keep)[0])) + 1 if keep.any() else 0
        fdr = np.zeros(m, bool)
        if kmax:
            fdr[o[:kmax]] = True
        for i, k in enumerate(order):
            cls[(str(y), k)] = LAB[lm.q[i]] if raw[i] else "ns"
            clsf[(str(y), k)] = LAB[lm.q[i]] if fdr[i] else "ns"
        # 이웃이 없어 검정에서 빠진 단위는 ns 로 둔다. 통계가 정의되지 않는다.
        for k in share:
            cls.setdefault((str(y), k), "ns")
            clsf.setdefault((str(y), k), "ns")
        summary[str(y)] = (int(raw.sum()), int(fdr.sum()), m)

    d["lisa"] = [cls.get((str(y), k), "") for y, k in zip(d["year"], d["_k"])]
    d["lisa_fdr"] = [clsf.get((str(y), k), "") for y, k in zip(d["year"], d["_k"])]
    blank = int((d["lisa"].astype(str).str.strip() == "").sum())
    d = d.drop(columns=["_k"])
    write(d, p_sg)
    for y in sorted(summary):
        n_raw, n_fdr, m = summary[y]
        print("  %s  단위 %3d  보정없음 %2d  FDR %2d" % (y, m, n_raw, n_fdr))
    print("  빈칸 %d행" % blank)

    # 화면이 읽는 지표 파일에도 같은 값을 적는다. 담고 있는 해에 대해서만.
    ip = os.path.join(ROOT, "05_dashboard", "data", "indices.json")
    if os.path.exists(ip):
        doc = json.load(open(ip, encoding="utf-8"))
        moved = 0
        for y, rows in doc["data"].get("by_sigungu", {}).items():
            for r in rows:
                k = key_of(r.get("sido"), r.get("sigungu"))
                a, b = cls.get((str(y), k)), clsf.get((str(y), k))
                if a is not None and r.get("lisa") != a:
                    moved += 1
                r["lisa"] = a
                r["lisa_fdr"] = b
        json.dump(doc, open(ip, "w", encoding="utf-8"), ensure_ascii=False)
        print("  indices.json: %d칸을 맞췄다" % moved)
        latest = max(doc["data"]["years"])
        print("  %s:" % latest,
              dict(Counter(r.get("lisa") for r in doc["data"]["by_sigungu"][str(latest)])))


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

    # 2026-09-26: the region of a nationality comes from kird.COUNTRY_REGION, the map
    # behind continent_H and crosswalk_country. It used to come from
    # segregation_by_nationality, which lists only nationalities of 100 or more, so
    # every smaller one fell into 기타: 2,483 people in 2024 where crosswalk_country
    # puts 58 there (국적불명, 국제연합, 국제연합전문기구), and every other region
    # was short by what it lost. The two maps must agree where both speak.
    from kird import COUNTRY_REGION, OTHER_REGION
    _seg_map = dict(seg[["country", "continent"]].dropna().drop_duplicates().values)
    _disagree = {c: (r, COUNTRY_REGION.get(c, OTHER_REGION)) for c, r in _seg_map.items()
                 if COUNTRY_REGION.get(c, OTHER_REGION) != r}
    if _disagree:
        raise SystemExit(f"segregation_by_nationality and COUNTRY_REGION disagree: {_disagree}")
    C2REGION = {c: COUNTRY_REGION.get(c, OTHER_REGION) for c in nat["country"].unique()}
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
        for r in reg[reg.year == y].continent:
            cols = bycol.get(r, [])
            x = piv[cols].sum(axis=1) if cols else pd.Series(0.0, index=k.index)
            D, iso, _ = indices(x, k, t)
            rrows.append({"year": y, "continent": r, "total": int(x.sum()),
                          "dissimilarity_D": round(D, 3), "isolation": round(iso, 4)})
    rnew = pd.DataFrame(rrows)
    rout = reg[["year", "continent", "continent_en"]].merge(rnew, on=["year", "continent"], how="left")
    rout = rout[["year", "continent", "continent_en", "total", "dissimilarity_D", "isolation"]]
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



def dictionary_facts(data):
    """The data-dependent numbers the dictionary prose quotes, read from `data`.

    validate_release.check_dictionary_numbers re-derives the same numbers from a
    downloaded deposit, so the two must stay in step.
    """
    def rd(name, **kw):
        return pd.read_csv(os.path.join(data, name), encoding="utf-8-sig", **kw)

    def pct(x):
        return "%.1f%%" % x

    def years_text(ys):
        ys = sorted(int(y) for y in ys)
        if not ys:
            return "no year"
        runs, a = [], ys[0]
        for p, q in zip(ys, ys[1:] + [None]):
            if q != p + 1:
                runs.append(str(a) if a == p else "%d-%d" % (a, p))
                a = q
        return ", ".join(runs[:-1]) + (" and " if len(runs) > 1 else "") + runs[-1]

    F = {}
    emd = rd("summary_by_eupmyeondong.csv", dtype={"adm_code": str})
    b = emd["adm_code"].isna() | (emd["adm_code"].astype(str).str.strip() == "")
    rate = b.groupby(emd["year"]).mean() * 100
    F["adm_2014"], F["adm_2015"] = pct(rate.get(2014, 0)), pct(rate.get(2015, 0))
    F["adm_later_max"] = pct(rate[rate.index >= 2016].max())

    sg = rd("summary_by_sigungu.csv")
    F["last"] = last = int(sg["year"].max())
    n_class = sg.dropna(subset=["lisa"]).groupby("year").size()
    F["lisa_n"] = int(round(n_class.mean()))
    F["lisa_chance"] = int(round(0.05 * F["lisa_n"]))
    L = sg[sg["year"] == last]
    sig = {"HH", "LL", "HL", "LH"}
    F["unc_sig"] = int(L["lisa"].isin(sig).sum())
    F["unc_hh"] = int((L["lisa"] == "HH").sum())
    F["fdr_sig"] = int(L["lisa_fdr"].isin(sig).sum())
    F["fdr_hh"] = int((L["lisa_fdr"] == "HH").sum())

    vbn = rd("visa_by_nationality.csv")
    reg = vbn[vbn["population"] == "registered"]
    F["stateless_years"] = years_text(reg.loc[reg["country"] == "무국적", "year"].unique())
    F["unreg_years"] = years_text(reg.loc[reg["country"].isin(["미등록국가", "미상"]),
                                          "year"].unique())
    F["other_years"] = years_text(reg.loc[reg["country"] == "기타", "year"].unique())
    F["korea_years"] = years_text(vbn.loc[vbn["country"] == "한국", "year"].unique())
    x00 = vbn[(vbn["visa_code"] == "X00") & (vbn["population"] == "stay")]["n"].sum()
    F["x00"] = format(int(x00), ",")

    F["age_bands"] = int(rd("age_sex_national.csv")["age_group"].nunique())

    ann = rd("naturalization_annual.csv")
    F["nat_annual_span"] = "%d-%d" % (ann["year"].min(), ann["year"].max())
    pc = rd("naturalization_by_country.csv")
    F["nat_panel_span"] = "%d-%d" % (pc["year"].min(), pc["year"].max())
    F["nat_revised_cells"] = 11     # the KNOWN_REVISIONS of 07_build_naturalization

    rs = rd("region_segregation.csv")
    F["region_other"] = format(int(rs.loc[(rs["year"] == last) & (rs["continent"] == "기타"),
                                          "total"].sum()), ",")

    dia = rd("diaspora_residence_by_sido.csv")
    k = dia[dia["country"] != "기타"].groupby("year")["country"].nunique()
    F["diaspora_names"] = (int(k.min()), int(k.max()), int(k.min()), int(k.idxmin()),
                           int(k.max()), int(k.idxmax()))
    vn = rd("visa_national.csv")
    f4 = vn[(vn["population"] == "stay") & (vn["visa_code"] == "F4")].groupby("year")["n"].sum()
    dt = dia.groupby("year")["n"].sum()
    j = pd.concat([dt, f4], axis=1, keys=["d", "f"]).dropna()
    F["diaspora_f4_gap"] = pct(float(((j["d"] - j["f"]).abs() / j["f"] * 100).max()))
    return F


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

    def files_with(col):
        """The released files that carry `col`, as one ' / ' label for the spec."""
        return " / ".join(os.path.basename(q) for q in sorted(glob.glob(os.path.join(DATA, "*.csv")))
                          if col in pd.read_csv(q, encoding="utf-8-sig", nrows=0).columns)

    SIDO_CODE_FILES = files_with("sido_code")
    SIGUNGU_CODE_FILES = files_with("sigungu_code")

    # ---- the numbers the prose quotes, read from the files (2026-09-26) ----
    # Until this date they were typed in and went stale: lisa_fdr said "52 and 16
    # uncorrected" where the file gave 51 and 14, region_segregation said 2,501 where
    # it held 2,483, adm_code said "~1%" where 2014 was 3.7%. validate_release.py
    # re-derives each of them from the deposited files and fails on a mismatch.
    F = dictionary_facts(DATA)

    # spec: list of (file_label, variable, type, description_en, description_ko)
    SPEC = [
        # ---------- place-level summary files ----------
        (SUMMARY_FILES, "year", "integer",
         "Reference year. sido/sigungu 2006-2024; eupmyeondong 2014-2024.",
         "기준연도. sido/sigungu 2006-2024, eupmyeondong 2014-2024."),
        (SUMMARY_FILES, "sido / sido_en", "string",
         "Province or metropolitan city (Korean + English), on one fixed set of names "
         "for every year of the panel. Two cases need care. 세종특별자치시 (Sejong, "
         "established July 2012) has no province row before 2012: at the sido level its "
         "2008-2011 residents are counted inside 충청남도, and only the district file "
         "carries 세종시 as a continuous unit from 2008. 강원도 and 전라북도 keep these "
         "short names in every year, although the register renamed them "
         "강원특별자치도 (2023) and 전북특별자치도 (2024); sido_code follows the register "
         "and the name does not. The source spellings, year by year, are in "
         "crosswalk_region.csv; the raw files are listed in raw_input_manifest.csv in "
         "the GitHub repository (https://github.com/nariyoo/kird-korea-immigration).",
         "광역시·도(한글+영문). 모든 해에 하나의 고정된 이름 집합을 씁니다. 두 경우를 "
         "주의하십시오. 세종특별자치시(2012년 7월 출범)는 2012년 전에는 시도 행이 없고, "
         "시도 층에서는 2008-2011년 주민이 충청남도 안에 들어 있으며, 시군구 파일만 세종시를 "
         "2008년부터 한 단위로 잇습니다. 강원도와 전라북도는 대장이 강원특별자치도(2023)와 "
         "전북특별자치도(2024)로 이름을 바꾼 뒤에도 모든 해에 짧은 이름을 씁니다. "
         "sido_code 는 대장을 따르고 이름은 따르지 않습니다. 해마다 원자료가 쓴 표기는 "
         "crosswalk_region.csv 에, 원자료 목록은 GitHub 저장소의 raw_input_manifest.csv 에 "
         "있습니다(https://github.com/nariyoo/kird-korea-immigration)."),
        (SIDO_CODE_FILES, "sido_code", "string",
         "Official two-digit province code (행정안전부 법정동코드) in force on 31 December "
         "of that year: the language-neutral join key at the province level, stable "
         "under renaming. The code follows the register even where the name column "
         "does not: 강원도 is 42 through 2022 and 51 from 2023, the year the register "
         "made it 강원특별자치도, and 전라북도 is 45 through 2023 and 52 from 2024 "
         "(전북특별자치도), while sido/sido_en keep 강원도 and 전라북도 throughout. Blank "
         "where the register has no province for that year.",
         "그 해 12월 31일 기준 공식 시도 코드 2자리(행정안전부 법정동코드). 이름과 무관한 "
         "시도 층 조인 키다. 이름 칸이 따르지 않는 곳에서도 코드는 대장을 따른다. 강원도는 "
         "2022년까지 42, 대장이 강원특별자치도로 바꾼 2023년부터 51이고, 전라북도는 "
         "2023년까지 45, 2024년부터 52(전북특별자치도)다. sido/sido_en 은 내내 강원도와 "
         "전라북도로 적는다. 그 해 대장에 없는 시도는 공백."),
        (SIGUNGU_CODE_FILES, "sigungu_code", "string",
         "Official five-digit district code (행정안전부 법정동코드) in force on 31 December "
         "of that year: the language-neutral join key between the district and "
         "sub-district tables, and the key that survives the renames the Korean names "
         "do not. 인천 남구 and 미추홀구 are the same district, 28170 up to the 2018 "
         "rename and 28177 after it; 군위군 is 47720 while it sat in 경상북도 and 27720 "
         "once 대구 took it in 2023; 창원시 마산합포구 is 48125 from the 2010 merger. The "
         "general districts of 부천시, abolished in 2016 and re-created in 2024, carry "
         "the 부천시 code 41190 throughout, because the release publishes 부천시 as one "
         "district across the panel. Blank where the register cannot resolve the name.",
         "그 해 12월 31일 기준 공식 시군구 코드 5자리(행정안전부 법정동코드). 시군구 표와 "
         "읍면동 표를 잇는 언어중립 조인 키이고, 한글 이름이 못 견디는 개명을 견딘다. "
         "인천 남구와 미추홀구는 같은 시군구로 2018년 개명 전 28170, 이후 28177이다. "
         "군위군은 경상북도 시절 47720, 2023년 대구 편입 뒤 27720이다. 창원시 마산합포구는 "
         "2010년 통합 이후 48125다. 2016년 폐지되고 2024년 다시 생긴 부천시 일반구는 공개본이 "
         "부천시 한 칸으로 내므로 전 기간 부천시 코드 41190을 단다. 대장에서 못 푼 이름은 공백."),
        ("summary_by_sigungu.csv / summary_by_eupmyeondong.csv", "sigungu / sigungu_en", "string",
         "District: an autonomous gu, a si (city), a gun (county), or a general gu of a "
         "large city, on the MOJ-published unit (Korean + English).",
         "시군구: 자치구·시·군 및 대도시 일반구. MOJ 발표 단위(한글+영문)."),
        ("summary_by_eupmyeondong.csv", "eupmyeondong", "string",
         "Sub-district (eup/myeon/dong) on that year's administrative boundaries "
         "(Korean only; use adm_code as the language-neutral join key).",
         "읍·면·동. 그 해 행정경계 기준(한글만; 언어중립 조인키는 adm_code)."),
        ("summary_by_eupmyeondong.csv", "adm_code", "string",
         "Official administrative-dong code for that year, as the year's boundary "
         "snapshot carries it (source: vuski/admdongkor): 7-digit for 2014/2015/2017, "
         "10-digit standard code for 2016 and 2018-2023, 8-digit statistical (SGIS) code "
         "for 2024. Join to the boundary file of the same year. Blank where the dong "
         "name has no boundary match that year: %s of rows in 2014, %s in 2015, "
         "and at most %s in any later year." % (F["adm_2014"], F["adm_2015"],
                                                F["adm_later_max"]),
         "그 해 경계 스냅숏(vuski/admdongkor)이 싣는 행정동코드. 2014/2015/2017=7자리, "
         "2016·2018-2023=10자리 표준코드, 2024=8자리 통계(SGIS) 코드. 같은 해의 경계 "
         "파일에 붙이십시오. 그 해 경계와 이름이 맞지 않는 동은 공백: 2014년 %s, "
         "2015년 %s, 그 뒤로는 해마다 %s 이하." % (F["adm_2014"], F["adm_2015"],
                                                  F["adm_later_max"])),
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
         "Written as True / False (pandas reads the CSV column as boolean; the .dta "
         "holds the strings 'True' / 'False'). True where the MOIS broad-definition "
         "columns of this general-district (gu) row "
         "are estimates apportioned from the parent city's published totals by each gu's "
         "MOJ registered-foreigner share (2008-2015, when MOIS publishes general-district "
         "cities only at the city level); False where MOIS publishes the district "
         "directly; blank where no MOIS composition exists for the row.",
         "True / False 로 적는다(pandas 는 CSV 칸을 논리형으로, .dta 는 문자열 'True' / "
         "'False' 로 읽는다). 이 일반구 행의 MOIS 광의 구성이 부모 시 발행값을 구별 MOJ "
         "등록외국인 비중으로 안분한 추정치이면 True(2008-2015, MOIS가 일반구 시를 시 "
         "단위로만 발행), MOIS가 구를 직접 발행하면 False, 해당 행에 MOIS 구성이 없으면 공란."),
        ("summary_by_sido.csv / summary_by_sigungu.csv",
         "shannon_H / shannon_H_inclusive / continent_H / HHI / evenness",
         "float",
         "MOJ-nationality-based diversity, concentration, and evenness indices; see "
         "README 'Index definitions'. Begin 2008/2009. Indices are recomputed at each "
         "level with the unit treated as one whole; they are never averaged from the "
         "level below.",
         "MOJ 국적구성 기반 다양성·집중·균등 지표(정의는 README). 2008/2009~. 지수는 "
         "층마다 그 단위를 하나로 보고 다시 계산하며, 아래 층의 평균이 아니다."),
        ("summary_by_sido.csv / summary_by_sigungu.csv", "index_base_k", "integer",
         "Number of categories the diversity indices are computed over: the top 19 nationalities of that year plus one residual bin. It is 20 wherever at least 20 nationalities are present, so it describes the index basis, not the unit. Carried the name n_nationalities through v1.1.0.", "다양성 지수를 계산한 칸 수. 그 해 상위 19개국과 잔여 한 칸이며, 국적이 20개 이상인 곳은 모두 20이다. 그 지역의 성질이 아니라 지수의 밑변이다. v1.1.0 까지 n_nationalities 라는 이름으로 실렸다."),
        ("summary_by_sido.csv / summary_by_sigungu.csv", "n_nationalities_observed",
         "integer", "Distinct nationalities the source lists for that unit and year, with the residual bin excluded. Capped at 19 for 2008-2013, when the yearbook publishes only the top 19 plus a residual at the district level; full detail from 2014.", "그 단위·그 해에 연감이 싣는 국적 수(잔여 칸 제외). 연감이 시군구 단위에서 전체 국적을 싣기 시작한 해가 2014년이라 2008-2013 은 19에서 막힌다."),
        ("summary_by_sigungu.csv", "lisa", "string",
         "Local Moran cluster class of the district's foreign share: HH / LL / HL / LH "
         "(99,999-permutation conditional randomization, p<0.05, no multiple-comparison "
         "correction) or ns. About %d districts carry a class each year, so about %d "
         "reach p<0.05 by chance; use lisa_fdr for a corrected reading. Island "
         "districts with no contiguous neighbor are ns, since the statistic is not "
         "defined there. Every year of the panel is computed, including the years "
         "before 2014: the statistic needs only the foreign share, which this file "
         "carries from 2008. Sigungu only." % (F["lisa_n"], F["lisa_chance"]),
         "시군구 외국인비율의 국지적 Moran 군집 분류: HH/LL/HL/LH(99,999회 순열, p<0.05, "
         "다중비교 보정 없음) 또는 ns. 해마다 약 %d곳에 분류가 붙으므로 우연히 %d곳가량이 "
         "p<0.05 에 걸린다. 보정된 판정은 lisa_fdr 을 쓰십시오. 인접 이웃이 없는 도서 "
         "시군구는 ns(통계가 정의되지 않음). 2014년 이전을 포함해 모든 해를 계산합니다. "
         "이 통계에 필요한 것은 외국인 비율뿐이고 이 파일이 2008년부터 담습니다. 시군구 전용."
         % (F["lisa_n"], F["lisa_chance"])),
        ("summary_by_sigungu.csv", "lisa_fdr", "string",
         "The same local Moran classes after a Benjamini-Hochberg false-discovery-rate "
         "correction at q=0.05 across the districts tested that year, or ns. Far fewer "
         "districts survive: in %d, %d do (%d of them high-high), against %d (%d "
         "high-high) uncorrected. The 99,999 permutations exist so that this correction "
         "is possible at all; with 999 the smallest attainable p exceeds the first "
         "Benjamini-Hochberg threshold and nothing can pass."
         % (F["last"], F["fdr_sig"], F["fdr_hh"], F["unc_sig"], F["unc_hh"]),
         "같은 분류에 Benjamini-Hochberg 위발견율 보정(q=0.05)을 걸어 남은 것, 아니면 ns. "
         "훨씬 적게 남는다. %d년은 %d곳이고 그중 고-고는 %d곳이다(보정 전 %d곳, 고-고 %d곳). "
         "순열을 99,999회로 둔 것이 이 보정을 가능하게 하려는 것이다. 999회면 최소 p 가 "
         "BH 의 첫 문턱보다 커서 아무것도 통과하지 못한다."
         % (F["last"], F["fdr_sig"], F["fdr_hh"], F["unc_sig"], F["unc_hh"])),
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
         "MOJ registered foreigners of that nationality in that district-year (2008-2024).",
         "해당 시군구·연도·국적의 MOJ 등록외국인 수(2008-2024)."),
        ("visa_by_sigungu.csv", "visa_code", "string",
         "Visa/status-of-stay code, written without hyphens (E9, F4 = the source's "
         "E-9, F-4).", "체류자격(비자) 코드, 하이픈 없이 표기(E9, F4 = 원자료의 E-9, F-4)."),
        ("visa_by_sigungu.csv", "n", "integer",
         "MOJ registered foreigners on that visa in that district-year (2008-2024).",
         "해당 시군구·연도·비자의 MOJ 등록외국인 수(2008-2024)."),
        ("visa_by_nationality.csv", "population", "string",
         "Population base (values: registered / stay): staying foreigners (체류) or registered foreigners (등록).",
         "모집단: 체류외국인 또는 등록외국인."),
        ("visa_by_nationality.csv", "country / country_en", "string",
         "Nationality (Korean + English), plus the lines the yearbook prints that name "
         "no nationality: 무국적 (Stateless) in %s, 미등록국가 (Unregistered country) "
         "and 미상 (Unknown) in %s, a single 기타 (Other) line in %s, when the "
         "yearbook prints no stateless line, and 한국 (Republic of Korea) in %s. They "
         "are carried so that each year adds "
         "up to the yearbook's printed grand total; no index, crosswalk region or "
         "district table uses them." % (F["stateless_years"], F["unreg_years"],
                                        F["other_years"], F["korea_years"]),
         "국적(한글+영문). 연보가 국적이 아닌 줄로 싣는 것도 함께 싣습니다: 무국적 "
         "(%s), 미등록국가·미상(%s), 무국적을 따로 싣지 않는 해의 기타 한 줄(%s), 한국(%s). 해마다 "
         "연보가 인쇄한 총계와 맞도록 싣는 것이며, 어떤 지수나 권역, 시군구 표도 이 줄을 "
         "쓰지 않습니다." % (F["stateless_years"], F["unreg_years"], F["other_years"],
                              F["korea_years"])),
        ("visa_by_nationality.csv", "visa_code", "string",
         "Visa/status-of-stay code, written without hyphens (E9, F4 = the source's "
         "E-9, F-4).", "체류자격(비자) 코드, 하이픈 없이 표기(E9, F4 = 원자료의 E-9, F-4)."),
        ("visa_by_nationality.csv", "visa_label / visa_label_en", "string",
         "Visa category label (Korean + English). A few pre-2011 legacy codes carry no "
         "descriptive source label and mirror the code (e.g. M1). E8T is the "
         "연수취업 (trainee employment) status the 2006-2009 editions print as E-8; "
         "E8 from 2021 on is 계절근로 (seasonal worker), a different status that reused "
         "the code, and no edition prints E-8 from 2010 to 2020. X00 is 자격없음 (0-0), "
         "people the 2014 stay table records with no status (%s)." % F["x00"],
         "비자 분류 라벨(한글+영문). 2006-2011 일부 옛 코드는 원자료에 설명 라벨이 없어 코드를 "
         "그대로 둠(예 M1). E8T 는 2006-2009년판이 E-8 로 싣는 연수취업이고, 2021년판부터의 "
         "E8 은 같은 코드를 다시 쓴 다른 자격인 계절근로다. 2010-2020년판에는 E-8 칸이 없다. "
         "X00 은 2014년 체류외국인 표의 자격없음(0-0), %s명." % F["x00"]),
        ("visa_by_nationality.csv", "n", "integer",
         "Count for that population x nationality x visa x year (2006-2024).",
         "모집단×국적×비자×연도 인원(2006-2024)."),
        ("age_sex_national.csv", "population", "string",
         "Population base: registered (등록외국인, 2009-2024) or stay (체류외국인, "
         "2011-2024). registered comes from the yearbook table 국적(지역) 및 연령별 "
         "등록외국인 현황. stay adds short-term sojourners and F-4 residence reports to "
         "the registered population and comes from 국적(지역) 및 연령별 체류외국인 현황, "
         "which the yearbook first publishes in its 2011 edition. The two are different populations: "
         "filter to one before summing or comparing years, and never splice one onto "
         "the other. Each matches nationality_national.csv for the same population, "
         "nationality by nationality; nationality_national also carries the "
         "yearbook's non-nationality lines (무국적, 기타, 미등록국가, 미상, 한국), which this "
         "table does not.",
         "모집단(값: registered / stay). registered = 등록외국인, 연보 「국적(지역) 및 "
         "연령별 등록외국인 현황」, 2009-2024. stay = 체류외국인(등록 + 단기체류 + "
         "재외동포 거소신고), 「국적(지역) 및 연령별 체류외국인 현황」, 2011-2024(연보가 "
         "2011년판부터 싣습니다). 서로 다른 모집단이므로 합하거나 연도를 견주기 전에 "
         "하나로 거르고, 한 계열을 다른 계열에 잇지 마십시오. 각 계열은 같은 모집단의 "
         "nationality_national.csv 와 국적마다 맞습니다. nationality_national 은 연보의 "
         "국적 아닌 줄(무국적·기타·미등록국가·미상·한국)도 싣지만 이 표는 싣지 않습니다."),
        ("age_sex_national.csv", "country / country_en", "string",
         "Nationality (Korean + English).", "국적(한글+영문)."),
        ("age_sex_national.csv", "gender", "string",
         "Sex: M, F, or T for the published total. From the 2022 edition the stay "
         "table also publishes a 제3의성 (third sex) row, which is counted in T but is "
         "not carried here, so on the stay basis M + F falls short of T by a few "
         "people (3 nationwide in 2022, 7 in 2023, 9 in 2024). The registered table "
         "has no such row. Use T for a total.",
         "성별(M 남성, F 여성, T 계). 2022년판부터 체류외국인 표에 제3의성 행이 있고 그 "
         "값은 T 에 들어 있으나 이 파일에는 따로 싣지 않으므로, stay 에서는 M + F 가 T "
         "보다 몇 명 적습니다(전국 2022년 3명, 2023년 7명, 2024년 9명). 등록외국인 표에는 "
         "그 행이 없습니다. 총계는 T 를 쓰십시오."),
        ("age_sex_national.csv", "age_group", "string",
         "Age band: 0-4, 5-9, ... 55-59, 60+ (%d bands in every year)." % F["age_bands"],
         "연령대: 0-4, 5-9, ... 55-59, 60+ (모든 해 13구간)."),
        ("age_sex_national.csv", "n", "integer",
         "MOJ count for that population x nationality x age x sex x year: registered "
         "foreigners 2009-2024 or staying foreigners 2011-2024, as `population` says. "
         "Cells the source prints as zero are omitted.",
         "모집단×국적×연령×성별×연도 MOJ 인원. population 에 따라 등록외국인"
         "(2009-2024) 또는 체류외국인(2011-2024). 원자료가 0으로 적은 칸은 싣지 않습니다."),
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
         "from 2016, except 부천시, which is one district in every year as in every other "
         "district file (its 2024 general districts are summed). A district-year is "
         "absent, not blank, where the source masks every single-age cell: 울릉군 "
         "(47940) 2016-2024 is the only case, and its total is in summary_by_sigungu.children.",
         "해당 연령 외국인주민 자녀 수(2011-2024). 전체 자녀(국내출생+귀화·외국국적) 기준이라 "
         "합계가 summary의 children(2016년부터 국내출생만)보다 큼. 2016년 이전은 일반구 시를 "
         "시 단위로, 2016년부터 구 단위로 수록하되 부천시는 다른 시군구 파일처럼 모든 해에 한 "
         "단위(2024년 일반구를 합침). 원자료가 모든 연령 칸을 가린 시군구·연도는 빈 행이 아니라 "
         "행이 없다. 울릉군(47940) 2016-2024 가 유일하며 합계는 summary_by_sigungu.children 에 "
         "있다."),
        ("multicultural_households.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English).", "시도·시군구(한글+영문)."),
        ("multicultural_households.csv", "adm_code", "string",
         "Administrative-dong code of the eupmyeondong for that year, the same code "
         "summary_by_eupmyeondong carries (joined on year, sigungu_code and the dong "
         "name); blank where the sub-district could not be matched that year. Added in "
         "v1.2.0 so this file joins on a code and not a name.",
         "그 해 읍면동의 행정동코드. summary_by_eupmyeondong 과 같은 코드를 (연도, "
         "sigungu_code, 동 이름)으로 옮겨 붙였고, 그 해에 짝을 못 찾은 곳은 공백이다. 이름이 "
         "아니라 코드로 붙이라고 v1.2.0 에서 넣었다."),
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
         "Reference year. The annual series runs %s; the by-country and by-age "
         "panels run %s, one year per yearbook edition. They start with the 2011 "
         "edition because the 2009 and 2010 editions print these two tables "
         "cumulatively, from 1991 to the edition year (363,131 and 405,170 cases "
         "against 49,820 and 42,039 in the year itself); those two editions are not "
         "used." % (F["nat_annual_span"], F["nat_panel_span"]),
         "기준연도. 연도별 시계열 %s, 국적별·연령별 패널 %s(연보 1권당 1개 연도). "
         "2009·2010년판의 이 두 표는 1991년부터 그 해까지의 누계(363,131건과 405,170건. "
         "그 해만은 49,820건과 42,039건)라 쓰지 않고, 패널은 2011년판부터다."
         % (F["nat_annual_span"], F["nat_panel_span"])),
        ("naturalization_by_country.csv", "country / country_en", "string",
         "Former nationality (Korean + English). Three labels are not nationalities "
         "of crosswalk_country.csv. 한국 (Republic of Korea) appears only under the "
         "nationality-status types (국적상실, 국적선택, 국적이탈, 국적보유, 국적판정, "
         "국적취득): people resolving a Korean nationality they already held, never "
         "naturalization. 중국+한국계중국인 and 러시아(연방)+한국계러시아인 are 2018 only: "
         "that edition prints China and Russia with their Korean-descent subgroups "
         "folded in and no split, so the combined unit is kept apart rather than "
         "entered as China or Russia. In every other year 중국 excludes 한국계중국인.",
         "종전국적(한글+영문). 세 이름은 crosswalk_country.csv 의 국적이 아닙니다. 한국은 "
         "국적 상태 유형(국적상실·국적선택·국적이탈·국적보유·국적판정·국적취득)에만 나오며, "
         "이미 지닌 한국 국적을 정리한 사람이지 귀화가 아닙니다. 중국+한국계중국인과 "
         "러시아(연방)+한국계러시아인은 2018년에만 있습니다. 그 해 연보가 한국계를 나누지 "
         "않고 중국·러시아에 넣어 싣기 때문에 합친 단위로 따로 둡니다. 다른 해의 중국에는 "
         "한국계중국인이 들어 있지 않습니다."),
        ("naturalization_by_age.csv", "age", "string",
         "Ten-year age band (0-9, 10-19, ..., 80-89, 90+), read from each row's own "
         "label. The editions print the same ten bands five ways: 0~10세 / 11~20 / ... "
         "/ 91세이상 (2011, 2017), 0-10세 / 11~20 (2020), 0~10 / 10~20 / ... / 80~90 "
         "(2012-2013), 0세~9세 / 10세~19세 / ... / 90세이상 (2021-2022), and bare "
         "numerals 10, 20, ... 90, 99 (2014-2016, 2018-2019, 2023-2024). A bare numeral "
         "is the band's upper bound (10 = 0-9, 90 = 80-89, 99 = 90 and over): the "
         "editions with explicit labels print the same table, and acquisition by a "
         "parent's naturalization (수반취득, minors) sits in the bare-10 row exactly as "
         "it sits in the 0세~9세 row. The build stops if an edition's labels do not "
         "give ten bands in this order.",
         "10세 단위 연령대(0-9, 10-19, ..., 80-89, 90+). 행마다 제 라벨에서 읽는다. 연보는 "
         "같은 열 칸을 다섯 가지로 적는다: 0~10세/11~20/…/91세이상(2011, 2017), "
         "0-10세/11~20(2020), 0~10/10~20/…/80~90(2012-2013), 0세~9세/…/90세이상"
         "(2021-2022), 숫자만 10, 20, …, 90, 99(2014-2016, 2018-2019, 2023-2024). 숫자만 "
         "적은 것은 그 칸의 위 끝이다(10 = 0-9세, 90 = 80-89세, 99 = 90세 이상). 라벨을 "
         "다 적은 판이 같은 표를 싣고, 부모의 귀화에 따른 수반취득(미성년)이 그 판의 "
         "0세~9세 칸에 있듯 숫자 10 칸에 있다. 한 판의 라벨이 이 순서의 열 칸을 주지 "
         "않으면 빌드가 멈춘다."),
        ("naturalization_annual.csv / naturalization_by_country.csv / naturalization_by_age.csv",
         "type / type_en", "string",
         "Nationality-processing route (Korean + English). Editions before 2014 publish a "
         "single 귀화; later ones split it into general, simplified and special "
         "naturalization plus acquisition by family, and 귀화소계 is their sum, which is "
         "what the annual table calls 귀화. In naturalization_by_age the 2014 edition "
         "prints 귀화소계 without the four routes, which start in 2015. Summed over "
         "countries or ages, 귀화소계 (귀화 before 2014) equals naturalization_annual's "
         "귀화 in every year, except naturalization_by_age 2012 (10,539 against "
         "10,540). 국적회복, 국적판정 and 국적이탈 equal the annual series in every "
         "year in both panels. The other types differ in %d cells, each read in the "
         "raw editions: the annual series is the newest edition's trend table, which "
         "MOJ revises, while each panel year is that year's edition. 2018 in both "
         "panels: 국적보유 86 (annual 89), 국적상실 26,608 (26,607), 국적선택 1,714 "
         "(1,719), 국적취득 (인지) 504 (506). 2012 naturalization_by_age: 국적상실 "
         "17,642 (17,641), and 귀화 above. 2013 in both panels: the edition's 국적취득 "
         "column holds re-acquisition only (419), without the 343 acquisitions by "
         "recognition the annual series adds." % F["nat_revised_cells"],
         "국적처리 유형(한글+영문). 2014년 이전 연보는 귀화 단일 컬럼, 이후는 일반·간이·특별귀화와 "
         "수반취득으로 분리되며 귀화소계는 그 합(연도별 표의 귀화와 동일 정의). "
         "naturalization_by_age 의 2014년판은 귀화소계만 싣고 네 경로는 2015년부터다. 국적이나 "
         "연령을 더한 귀화소계(2014년 전은 귀화)는 해마다 naturalization_annual 의 "
         "귀화와 같고, 예외는 naturalization_by_age 2012년(10,539 대 10,540)이다. "
         "국적회복·국적판정·국적이탈은 두 패널 모두 해마다 같다. 나머지 유형은 %d칸이 "
         "다르며 모두 원자료에서 확인했다. 연도별 표는 법무부가 고치는 최신판의 추이표이고 "
         "패널의 각 해는 그 해의 판이기 때문이다. 2018년 두 패널: 국적보유 86(연도별 89), "
         "국적상실 26,608(26,607), 국적선택 1,714(1,719), 국적취득(인지) 504(506). "
         "2012년 연령별: 국적상실 17,642(17,641)와 위의 귀화. 2013년 두 패널: 그 판의 "
         "국적취득 칸은 재취득(419)만 담고 연도별 표가 더하는 인지 343건이 없다."
         % F["nat_revised_cells"]),
        ("naturalization_annual.csv / naturalization_by_country.csv / naturalization_by_age.csv",
         "n", "integer", "Count of cases.", "건수."),
        # ---------- derived ----------
        ("ethnic_enclaves.csv", "year", "integer", "Reference year (2008-2024).",
         "기준연도(2008-2024)."),
        ("ethnic_enclaves.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English).", "시도·시군구(한글+영문)."),
        ("ethnic_enclaves.csv", "country / country_en", "string",
         "Enclave-forming nationality (Korean + English). A row is one district x "
         "nationality pair with LQ>=2, share>=30% and count>=200; the residual 기타 is "
         "never flagged.",
         "집거 형성 국적(한글+영문). 한 행은 LQ>=2, 점유율>=30%, 200명 이상인 시군구×국적 "
         "조합이며 잔여 범주 기타는 넣지 않는다."),
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
        # --- 조화 규칙 표 (v1.2.0 추가; 심사 지적 C1, C7) ---
        ("crosswalk_country.csv", "source_label", "string",
         "Nationality label as it appears in a source yearbook edition.",
         "연감 판본에 실린 국적 표기."),
        ("crosswalk_country.csv", "country / country_en", "string",
         "Canonical nationality this dataset uses, Korean and English.",
         "이 자료가 쓰는 표준 국적 이름(한글+영문)."),
        ("crosswalk_country.csv", "continent / continent_en", "string",
         "World region the canonical nationality is assigned to.",
         "그 국적이 속한 세계 지역."),
        ("crosswalk_country.csv", "rule", "string",
         "'source label variant' where two labels were merged, 'unchanged' otherwise.",
         "두 표기를 합친 자리는 'source label variant', 아니면 'unchanged'."),
        ("crosswalk_region.csv", "level", "string",
         "Administrative level the row applies to: sido, sigungu, eupmyeondong, or "
         "'lineage' for a boundary-change record.",
         "행이 가리키는 층: sido, sigungu, eupmyeondong, 또는 경계변경 기록 'lineage'."),
        ("crosswalk_region.csv", "source_sido / source_name", "string",
         "Province and place name as the source writes it.", "원자료의 시도·지명 표기."),
        ("crosswalk_region.csv", "sido / name", "string",
         "Province and place name this dataset uses. The province names are the panel's "
         "fixed set, so 강원도 and 전라북도 stay under those names after their "
         "2023 / 2024 renames (sido_code changes, the name does not).",
         "이 자료가 쓰는 시도·지명. 시도 이름은 패널의 고정 집합이라 강원도와 전라북도는 "
         "2023년·2024년 개칭 뒤에도 그 이름으로 남는다(sido_code 는 바뀐다)."),
        ("crosswalk_region.csv", "rule", "string",
         "Why the two differ: renamed, promoted, moved between provinces, folded into "
         "a city total, or a boundary-lineage record in JSON.",
         "다른 이유: 개명, 승격, 시도 이동, 시 총계로 합침, 또는 JSON 으로 적은 경계 이력."),
        ("crosswalk_visa.csv", "source_code", "string",
         "Visa code as a source edition lists it, including pre-2010 sub-codes.",
         "연감 판본의 체류자격 코드. 2010년 이전 하위 코드를 포함한다."),
        ("crosswalk_visa.csv", "visa_code / visa_label / visa_label_en", "string",
         "Parent code this dataset reports, with its Korean and English name.",
         "이 자료가 싣는 부모 코드와 그 한글·영문 이름."),
        ("crosswalk_visa.csv", "rule", "string",
         "'sub-code collapsed to parent', 'unchanged', or, for E-8 in the 2006-2009 "
         "editions, 'same source code, different status' (carried as E8T).",
         "'sub-code collapsed to parent', 'unchanged', 또는 2006-2009년판의 E-8 에 "
         "'same source code, different status'(E8T 로 싣는다)."),
        ("language_weights.csv", "country", "string",
         "Nationality, in the canonical label.", "표준 국적 이름."),
        ("language_weights.csv", "language / language_en", "string",
         "A first language spoken in that country of origin.",
         "그 출신국에서 쓰이는 제1언어."),
        ("language_weights.csv", "share", "float",
         "Fraction of that country's population speaking the language as a first "
         "language; the weights language_demand allocates each nationality with. "
         "Derived from Ethnologue, which is not redistributed here.",
         "그 나라 인구 가운데 그 언어를 모어로 쓰는 비율. language_demand 가 국적을 "
         "나눌 때 쓰는 가중치다. Ethnologue 에서 파생했고 원본은 재배포하지 않는다."),
        ("language_weights.csv", "note", "string",
         "'no first-language shares available' where the source has no entry.",
         "출처에 항목이 없는 나라는 'no first-language shares available'."),
        ("language_demand.csv", "year", "integer", "Reference year (2006-2024).",
         "기준연도(2006-2024)."),
        ("language_demand.csv", "scope", "string",
         "'national' (all languages, computed from the published national "
         "staying-foreigners composition, the nationalities of nationality_national "
         "population='stay'), "
         "'sido' (all languages per province, computed from the registered "
         "district-assigned sums in nationality_by_sido; added in v1.2.0), or "
         "'sigungu' (top ~20 languages per district, from nationality_by_sigungu). "
         "The national scope therefore sits on the broader staying-population "
         "basis while the subnational scopes sit on the registered "
         "district-assigned basis; the scopes are not nested sums.",
         "'national'(전체 언어; 공표 전국 체류외국인 구성, nationality_national 의 "
         "population='stay' 에서 계산), 'sido'(시도별 전체 언어; nationality_by_sido "
         "의 등록·시군구 배정 합에서 계산, v1.2.0 추가), 'sigungu'(시군구당 상위 "
         "~20개; nationality_by_sigungu 에서). 전국은 체류 기준, 시도·시군구는 "
         "등록(시군구 배정) 기준이라 scope 간 합산 관계가 아니다."),
        ("language_demand.csv", "sido / sido_en / sigungu / sigungu_en", "string",
         "Province and district (Korean + English); blank for national-scope rows.",
         "시도·시군구(한글+영문); national 행은 공백."),
        ("language_demand.csv", "language / language_en", "string",
         "Estimated first language (Korean + English).", "추정 모어(한글+영문)."),
        ("language_demand.csv", "count", "integer",
         "Estimated speakers = nationality count x that country's L1 (mother-tongue) "
         "speaker share (Ethnologue 24); rounded to whole persons. Korean excluded; "
         "estimates below one person are dropped before rounding.",
         "추정 화자수 = 국적별 인원 x 해당국 L1 모어 share(Ethnologue 24); 정수로 반올림. "
         "한국어 제외, 1명 미만 추정치는 반올림 전에 드롭."),
        ("segregation_by_nationality.csv", "year", "integer", "Reference year (2014-2024).",
         "기준연도(2014-2024)."),
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
        # ---------- v1.2.0 level-parallel companions ----------
        ("nationality_by_sido.csv", "year / sido / sido_en / country / country_en / n",
         "mixed",
         "nationality_by_sigungu summed within the province, 2008-2024: registered "
         "foreigners of that nationality in that province-year. Allocated basis "
         "(people the yearbook records without a district are absent), so province "
         "sums run slightly below the national tables.",
         "nationality_by_sigungu 를 시도 안에서 더한 것(2008-2024). 시군구가 적히지 "
         "않은 사람이 빠지는 배분 기준이라 전국 표보다 조금 적다."),
        ("nationality_national.csv",
         "year / population / country / country_en / n", "mixed",
         "visa_by_nationality summed over visa_code, 2006-2024: the published "
         "national count of that nationality, for both population bases, with the "
         "yearbook's non-nationality lines (see visa_by_nationality.country). Each "
         "year sums to the grand total the yearbook prints, on both bases (staying "
         "basis from 2011; 2006-2010 is composed from three tables).",
         "visa_by_nationality 를 자격에 대해 더한 것(2006-2024). 그 국적의 공표 전국 "
         "수이며 두 인구 기준을 모두 싣고, 연보의 국적 아닌 줄도 싣는다"
         "(visa_by_nationality.country 참조). 해마다 두 기준 모두 연보가 인쇄한 총계와 "
         "같다(체류 기준은 2011년부터, 2006-2010은 세 표를 합친 값)."),
        ("visa_by_sido.csv", "year / sido / sido_en / visa_code / n", "mixed",
         "visa_by_sigungu summed within the province, 2008-2024. Allocated basis, "
         "as nationality_by_sido.",
         "visa_by_sigungu 를 시도 안에서 더한 것(2008-2024). 배분 기준은 "
         "nationality_by_sido 와 같다."),
        ("visa_national.csv",
         "year / population / visa_code / visa_label / visa_label_en / n", "mixed",
         "visa_by_nationality summed over country, 2006-2024: the published "
         "national count under that status, for both population bases.",
         "visa_by_nationality 를 국적에 대해 더한 것(2006-2024). 그 자격의 공표 전국 "
         "수이며 두 인구 기준을 모두 싣는다."),
        ("national_annual.csv",
         "broad_total / non_naturalized / workers / marriage_migrants / students / "
         "ethnic_koreans / other_foreigners / naturalized / children", "integer",
         "The MOIS settlement-composition block the sido and sigungu summaries "
         "carry, summed to the national level (added in v1.2.0). A year is filled "
         "only when every province reports; otherwise blank, never 0.",
         "시도·시군구 요약이 싣는 행정안전부 정착 구성 블록을 전국으로 더한 것"
         "(v1.2.0 추가). 모든 시도가 보고한 해만 채우고, 아니면 0이 아니라 공란이다."),
        ("national_annual.csv",
         "settlement_rate_pct / labor_dependence_pct / marriage_dependence_pct / "
         "study_dependence_pct", "float",
         "Derived from the national sums with the same formulas as the sido and "
         "sigungu summaries.",
         "전국 합에서 시도·시군구 요약과 같은 식으로 계산한 값."),
        ("region_segregation.csv", "year", "integer", "Reference year (2014-2024).",
         "기준연도(2014-2024)."),
        ("region_segregation.csv", "continent / continent_en", "string",
         "Continent / world region of origin (Korean + English). Named region / "
         "region_en through v1.1.0; the values are continents, not places in Korea.",
         "출신 대륙·권역(한글+영문). v1.1.0 까지 region 이라는 이름이었다. 값은 한국의 "
         "지역이 아니라 출신 대륙이다."),
        ("region_segregation.csv", "total", "integer",
         "National count of registered foreigners from that region: every nationality "
         "in nationality_by_sigungu, summed by the continent crosswalk_country assigns "
         "it (the same map continent_H uses), so it equals that sum exactly. 기타 "
         "(Other) holds only the labels that name no country (국적불명, 국제연합, "
         "국제연합전문기구): %s people in %d. Until the 2026-09-26 build the regions were "
         "formed from segregation_by_nationality, which lists nationalities of 100 or "
         "more, and every smaller nationality fell into 기타 (2,483 people in 2024)."
         % (F["region_other"], F["last"]),
         "그 권역의 전국 등록외국인 수. nationality_by_sigungu 의 모든 국적을 "
         "crosswalk_country 의 대륙(continent_H 와 같은 대응표)으로 더한 것이라 그 합과 "
         "정확히 같다. 기타에는 나라가 아닌 이름(국적불명, 국제연합, 국제연합전문기구)만 "
         "들어가며 %d년 %s명이다. 2026-09-26 빌드 전에는 권역을 "
         "segregation_by_nationality(100명 이상 국적만 실음)에서 만들어, 그보다 작은 "
         "국적이 모두 기타로 들어갔다(2024년 2,483명)." % (F["last"], F["region_other"])),
        ("region_segregation.csv", "dissimilarity_D", "float",
         "Index of dissimilarity (D) vs Koreans across districts.",
         "내국인 대비 비유사성 지수(D)."),
        ("region_segregation.csv", "isolation", "float", "Isolation index.", "고립 지수."),
        ("national_annual.csv", "year", "integer", "Reference year (2008/2009-2024).",
         "기준연도(2008/2009-2024)."),
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
        ("national_annual.csv", "index_base_k", "integer",
         "Number of categories the diversity indices are computed over: the top 19 nationalities of that year plus one residual bin. It is 20 wherever at least 20 nationalities are present, so it describes the index basis, not the unit. Carried the name n_nationalities through v1.1.0.", "다양성 지수를 계산한 칸 수. 그 해 상위 19개국과 잔여 한 칸이며, 국적이 20개 이상인 곳은 모두 20이다. 그 지역의 성질이 아니라 지수의 밑변이다. v1.1.0 까지 n_nationalities 라는 이름으로 실렸다."),
        ("national_annual.csv", "n_nationalities_observed", "integer",
         "Distinct nationalities the source lists for that unit and year, with the residual bin excluded. Capped at 19 for 2008-2013, when the yearbook publishes only the top 19 plus a residual at the district level; full detail from 2014.", "그 단위·그 해에 연감이 싣는 국적 수(잔여 칸 제외). 연감이 시군구 단위에서 전체 국적을 싣기 시작한 해가 2014년이라 2008-2013 은 19에서 막힌다."),
        ("national_annual.csv", "n_enclaves", "integer",
         "Number of ethnic enclaves that year: district x nationality pairs with LQ>=2, "
         "the nationality >=30% of the district's foreign population, and >=200 people; "
         "equals that year's row count in ethnic_enclaves.csv.",
         "그 해 집거지 수: LQ>=2, 시군구 외국인의 30% 이상, 200명 이상인 시군구×국적 조합의 "
         "수. ethnic_enclaves.csv 의 그 해 행 수와 같다."),
        # ---------- 재외동포 거소신고 (v1.2.0) ----------
        # 2026-09-25: 이 네 줄이 여기 없어서 09 가 사전을 다시 쓸 때마다 재외동포 줄이
        # 빠지고 감사가 COVERAGE FAILED 로 멈췄다. 릴리스의 사전은 손으로 덧붙인 것이었다.
        ("diaspora_residence_by_sido.csv", "year", "integer",
         "Reference year (2008-2024).", "기준연도(2008-2024)."),
        ("diaspora_residence_by_sido.csv", "sido / sido_en", "string",
         "Province or metropolitan city (Korean + English), on the same fixed name set "
         "the rest of the panel uses.",
         "광역시·도(한글+영문). 다른 파일과 같은 고정 이름 집합을 씁니다."),
        ("diaspora_residence_by_sido.csv", "country / country_en", "string",
         "Nationality of the overseas Korean, with its English name. The yearbook names "
         "between %d and %d nationalities a year (%d in %d, %d in %d). Everyone in "
         "the table is ethnic Korean, so its China and Russia columns are the "
         "Korean-Chinese and Korean-Russian populations; the editions head them 중국 "
         "and 러시아 through 2017 and 한국계 중국인 and 한국계 러시아인 later (Russia "
         "already in 2014-2015), and the file writes 한국계중국인 and 한국계러시아인 in "
         "every year so each series runs unbroken. The residual 기타 is not read from "
         "the source but computed as the province total minus the named "
         "nationalities, because the 2011 sheet's own residual cell is inconsistent "
         "with its province rows." % F["diaspora_names"],
         "재외동포의 국적(한글+영문). 연보는 해마다 %d~%d개 국적을 적습니다(%d개 %d년, "
         "%d개 %d년). 표의 모든 사람이 동포이므로 중국·러시아 칸은 한국계중국인·"
         "한국계러시아인입니다. 연보는 2017년까지 중국·러시아, 그 뒤로 한국계 중국인·"
         "한국계 러시아인이라 적고(러시아는 2014-2015년에도), 이 파일은 계열이 끊기지 "
         "않도록 모든 해에 한국계중국인·한국계러시아인으로 씁니다. "
         "잔여 항목 「기타」는 원본에서 읽지 않고 시도 "
         "총계에서 명시된 국적의 합을 뺀 값으로 계산합니다. 2011년 시트의 기타 칸이 그 시도 "
         "행들과 어긋나 있기 때문입니다." % F["diaspora_names"]),
        ("diaspora_residence_by_sido.csv", "n", "integer",
         "Number of overseas-Korean residence reports (거소신고). These are holders of the "
         "F-4 status, who file a place-of-residence report under the Overseas Koreans Act "
         "instead of a foreign-resident registration, and therefore never appear in "
         "visa_by_sigungu or visa_by_sido. The yearly totals sit within %s of the F-4 "
         "count in visa_national on the staying basis. The source publishes this at "
         "province level only, so there is no district file." % F["diaspora_f4_gap"],
         "외국적동포 거소신고 인원. F-4 자격자로, 재외동포법에 따라 외국인등록이 아니라 "
         "거소신고를 하므로 visa_by_sigungu 와 visa_by_sido 에는 나오지 않습니다. 연도별 "
         "합계는 visa_national 의 체류 기준 F-4 와 %s 안에서 일치합니다. 원본이 시도 "
         "단위로만 공표하므로 시군구 파일은 없습니다." % F["diaspora_f4_gap"]),
        # ---------- cross-file note ----------
        ("(all files)", "*_en columns", "string",
         "Every Korean categorical column has an English partner (sido_en, sigungu_en, "
         "country_en, language_en, category_en, type_en, visa_label_en, "
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
    # Stata stamps each file with its write time, so two builds of the same data
    # differed in one header byte and a rebuild could never be shown identical.
    # A fixed stamp (the date of the v1.2.0 build) makes the .dta reproducible.
    # 2026-09-26.
    import datetime as _dt
    df.to_stata(
        out_path,
        write_index=False,
        time_stamp=_dt.datetime(2026, 9, 26, 0, 0),
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
      1.  file inventory (exactly the documented CSVs)
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
        "age_sex_national.csv":        ["year", "population", "country", "gender",
                                        "age_group"],
        "children_by_age.csv":         ["year", "sido", "sigungu", "age"],
        # 재외동포 거소신고. 2026-08-28에 기탁본에 넣고도 이 목록에 등록하지
        # 않아, 감사가 「25개를 기대했는데 26개」로 실패했다. 파일을 더하는
        # 자리는 셋이다 — 목록, 자료 사전, 그리고 단계 목록(run_pipeline).
        "diaspora_residence_by_sido.csv": ["year", "sido", "country"],
        # 조화 규칙 표. 자료가 아니라 자료를 만든 규칙이라 다른 검사는 건너뛴다
        "crosswalk_country.csv":       ["source_label"],
        "crosswalk_region.csv":        None,   # 규칙 표라 유일 열쇠가 없다
        "crosswalk_visa.csv":          ["source_code"],
        "language_weights.csv":        ["country", "language"],
        "ethnic_enclaves.csv":         ["year", "sido", "sigungu", "country"],
        "language_demand.csv":         ["year", "scope", "sido", "sigungu", "language"],
        "multicultural_households.csv": ["year", "sido", "sigungu", "eupmyeondong", "category"],
        "national_annual.csv":         ["year"],
        "naturalization_annual.csv":   ["year", "type"],
        "naturalization_by_age.csv":   ["year", "age", "type"],
        "naturalization_by_country.csv": ["year", "country", "type"],
        "nationality_by_sigungu.csv":  ["year", "sido", "sigungu", "country"],
        "nationality_by_sido.csv":     ["year", "sido", "country"],
        "nationality_national.csv":    ["year", "population", "country"],
        "region_segregation.csv":      ["year", "continent"],
        "segregation_by_nationality.csv": ["year", "country"],
        "summary_by_eupmyeondong.csv": ["year", "sido", "sigungu", "eupmyeondong"],
        "summary_by_sido.csv":         ["year", "sido"],
        "summary_by_sigungu.csv":      ["year", "sido", "sigungu"],
        "visa_by_nationality.csv":     ["year", "population", "country", "visa_code"],
        "visa_by_sido.csv":            ["year", "sido", "visa_code"],
        "visa_by_sigungu.csv":         ["year", "sido", "sigungu", "visa_code"],
        "visa_national.csv":           ["year", "population", "visa_code"],
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
        if not key:
            continue
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

    # ------------------------------------------- 7b. that year's official codes
    # Every named district has to carry the code the government used that year, and
    # the sub-district table has to nest inside the district table on it. Names do
    # not guarantee either: they disagreed on 40 (year, province, district) pairs.
    for f, df in dfs.items():
        if "sigungu" not in df.columns:
            continue
        named = df["sigungu"].notna() & (df["sigungu"].astype(str).str.strip() != "")
        blank = named & (df["sigungu_code"].isna()
                         | (df["sigungu_code"].astype(str).str.strip().isin(["", "nan"])))
        if blank.any():
            print(df.loc[blank, ["year", "sido", "sigungu"]].drop_duplicates()
                  .head(40).to_string())
        check(not blank.any(), f"{f}: sigungu_code present on every named district "
                               f"({int(blank.sum())} blank)")
    emd, sgg = dfs["summary_by_eupmyeondong.csv"], dfs["summary_by_sigungu.csv"]
    have = set(map(tuple, sgg[["year", "sigungu_code"]].drop_duplicates().values))
    miss = sorted({tuple(r) for r in emd[["year", "sido", "sigungu", "sigungu_code"]]
                   .drop_duplicates().values if (r[0], r[3]) not in have})
    for row in miss[:40]:
        print(f"  [detail] eupmyeondong district absent from summary_by_sigungu: {row}")
    check(not miss, "summary_by_eupmyeondong (year, sigungu_code) nests inside "
                    f"summary_by_sigungu ({len(miss)} outside)")

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



def reconcile_indices():
    """기탁본과 화면이 같은 분리지수를 말하게 한다.

    분리지수 계열은 두 곳에서 계산됐다. 01 이 지표 파일(indices.json)에 쓰고,
    여기 build_segregation 이 릴리스 CSV 를 만든다. 그래서 같은 이름의 지표가
    두 값을 갖고 있었다(2014년 Theil 0.0965 대 0.0886, D 는 1,169쌍 중 1,112쌍이
    달랐다). 논문은 지표 파일을, 이용자는 기탁본을 읽으니 서로 다른 수를
    인용하게 된다.

    01 의 내국인 셈법과 노출지수 분모를 고쳐 정의는 같아졌지만, 01 은 **04 가
    시군구를 정리하기 전의 단위 집합**에서 계산한다(부천 일반구, 세종). LISA
    에서와 같은 되먹임이다. 여기서 릴리스 값을 지표 파일에 적어 넣어, 화면과
    논문과 기탁본이 한 수를 말하게 한다.

    Theil 은 기준도 일부러 다르다. 여기는 모든 해를 상위 19개국+잔여로
    통일한다(연감이 2014년에 시군구 단위 국적 상세를 싣기 시작해 생긴 단절을
    건너뛰려는 것). 그 값이 기탁본에 실리므로 그대로 옮긴다.
    """
    import json
    ipath = os.path.join(ROOT, "05_dashboard", "data", "indices.json")
    if not os.path.exists(ipath):
        print("reconcile_indices: indices.json 이 없다. 건너뛴다")
        return
    doc = json.load(open(ipath, encoding="utf-8"))
    d = doc["data"]

    def num(v):
        return None if v is None or v != v else float(v)

    # --- 국적별 D / isolation / interaction_korean ---
    seg = pd.read_csv(os.path.join(DATA, "segregation_by_nationality.csv"))
    rel = {(str(int(r.year)), r.country): r for r in seg.itertuples()}
    PAIRS = [("D", "dissimilarity_D"), ("isolation", "isolation"),
             ("interaction_korean", "interaction_korean")]
    moved, missing = 0, 0
    for y, rows in d.get("by_nationality", {}).items():
        for row in rows:
            r = rel.get((y, row.get("country")))
            if r is None:
                missing += 1
                continue
            for a, b in PAIRS:
                v = num(getattr(r, b, None))
                if v is None:
                    continue
                if row.get(a) != v:
                    moved += 1
                row[a] = v
    print("  by_nationality: 기탁본 값으로 %d칸을 맞췄다" % moved
          + (", 기탁본에 없는 %d쌍은 그대로 두었다" % missing if missing else ""))

    # --- 대륙별 D / isolation ---
    rp = os.path.join(DATA, "region_segregation.csv")
    if os.path.exists(rp):
        rs = pd.read_csv(rp)
        relr = {(str(int(r.year)), r.continent): r for r in rs.itertuples()}
        rmoved = 0
        for y, blk in d.get("region_seg", {}).items():
            for cont, row in blk.items():
                r = relr.get((y, cont))
                if r is None:
                    continue
                for a, b in (("D", "dissimilarity_D"), ("isolation", "isolation")):
                    v = num(getattr(r, b, None))
                    if v is not None:
                        if row.get(a) != v:
                            rmoved += 1
                        row[a] = v
        print("  region_seg: %d칸을 맞췄다" % rmoved)

    # --- 관측 국적 수 (2026-09-26) ---
    # recount_observed_nationalities 가 이름을 합친 뒤 배포본에서 다시 센다. 그
    # 값이 지표 파일로 돌아가지 않아, 화면은 2014년 전국 193(배포본 190), 경기도
    # 153(150)을 싣고 있었다. 배포본의 해만 옮기고 그 뒤의 해는 01 의 값을 둔다.
    omoved = 0
    for name, block, key in (("national_annual.csv", "summary", None),
                             ("summary_by_sido.csv", "by_sido", ("sido",)),
                             ("summary_by_sigungu.csv", "by_sigungu", ("sido", "sigungu"))):
        p = os.path.join(DATA, name)
        if not os.path.exists(p):
            continue
        t = pd.read_csv(p, encoding="utf-8-sig")
        if "n_nationalities_observed" not in t.columns:
            continue
        for r in t.dropna(subset=["n_nationalities_observed"]).itertuples():
            y = str(int(r.year))
            v = int(r.n_nationalities_observed)
            blk = d.get(block, {}).get(y)
            if blk is None:
                continue
            if key is None:
                targets = [blk] if isinstance(blk, dict) else []
            else:
                want = tuple(getattr(r, k) for k in key)
                targets = [e for e in blk if tuple(e.get(k) for k in key) == want]
            for e in targets:
                if e.get("n_nationalities_observed") != v:
                    omoved += 1
                e["n_nationalities_observed"] = v
    print("  n_nationalities_observed: %d칸을 배포본 값으로 맞췄다" % omoved)

    # --- 전국 Theil ---
    na = pd.read_csv(os.path.join(DATA, "national_annual.csv"))
    tmoved = 0
    for _, r in na.iterrows():
        y = str(int(r["year"]))
        v = num(r.get("theil_segregation_H"))
        if v is not None and y in d.get("summary", {}):
            if d["summary"][y].get("theil_segregation_H") != round(v, 4):
                tmoved += 1
            d["summary"][y]["theil_segregation_H"] = round(v, 4)
    json.dump(doc, open(ipath, "w", encoding="utf-8"), ensure_ascii=False)
    print("  theil_segregation_H: %d개 해를 맞췄다" % tmoved)


if __name__ == "__main__":
    finalize_release()
    build_lisa()
    build_segregation()
    reconcile_indices()
    # 분리지수를 다 짓고 지표 파일에 되쓴 다음 자른다. 순서가 바뀌면 화면의
    # 마지막 해만 01 이 계산한 값으로 남아 계열의 앞뒤가 갈린다.
    from kird import cut_release_years
    cut_release_years()
    from crosswalks import build_all as build_crosswalks
    build_crosswalks(DATA)
    build_data_dictionary()
    export_stata()
    audit_release()
