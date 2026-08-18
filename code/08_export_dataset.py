"""The tidy release CSVs, and language_demand.csv on the released basis.

The export writes every released table plus a draft of language_demand from the
untrimmed language block; the second pass replaces that draft with the released
version, top 20 languages per district, counts rounded to whole persons.
"""
import csv
import json
import os

import pandas as pd

from kird import SIDO_EN
from kird import ROOT


def export_dataset():
    """Export a clean, documented dataset release for data publication.

    Reads the processed long tables (03_cleaned_data/*.csv) and the computed
    indices (site/data/indices.json), and writes tidy CSVs + a data dictionary +
    a data-descriptor README + LICENSE + CITATION.cff into ./04_dataset_release/.

    This release is what gets pushed to the standalone dataset GitHub repo and
    deposited to Zenodo for a DOI (for the Scientific Data descriptor).
    """
    PROC = os.path.join(ROOT, "03_cleaned_data")
    SITE = os.path.join(ROOT, "05_dashboard", "data")
    OUT = os.path.join(ROOT, "04_dataset_release")
    OUTD = os.path.join(OUT, "data")
    os.makedirs(OUTD, exist_ok=True)

    AGG = {"총계", "총합계", "계", "소계"}

    # ---- English-label maps for international reuse ----
    # 일반구 (compound city districts): proper Revised Romanization "City-si District-gu"
    ILBAN_GU_EN = {
        "수원시 장안구": "Suwon-si Jangan-gu", "수원시 권선구": "Suwon-si Gwonseon-gu",
        "수원시 팔달구": "Suwon-si Paldal-gu", "수원시 영통구": "Suwon-si Yeongtong-gu",
        "성남시 수정구": "Seongnam-si Sujeong-gu", "성남시 중원구": "Seongnam-si Jungwon-gu",
        "성남시 분당구": "Seongnam-si Bundang-gu", "안양시 만안구": "Anyang-si Manan-gu",
        "안양시 동안구": "Anyang-si Dongan-gu", "안산시 상록구": "Ansan-si Sangnok-gu",
        "안산시 단원구": "Ansan-si Danwon-gu", "고양시 덕양구": "Goyang-si Deogyang-gu",
        "고양시 일산동구": "Goyang-si Ilsandong-gu", "고양시 일산서구": "Goyang-si Ilsanseo-gu",
        "용인시 처인구": "Yongin-si Cheoin-gu", "용인시 기흥구": "Yongin-si Giheung-gu",
        "용인시 수지구": "Yongin-si Suji-gu", "부천시 원미구": "Bucheon-si Wonmi-gu",
        "부천시 소사구": "Bucheon-si Sosa-gu", "부천시 오정구": "Bucheon-si Ojeong-gu",
        "청주시 상당구": "Cheongju-si Sangdang-gu", "청주시 서원구": "Cheongju-si Seowon-gu",
        "청주시 흥덕구": "Cheongju-si Heungdeok-gu", "청주시 청원구": "Cheongju-si Cheongwon-gu",
        "천안시 동남구": "Cheonan-si Dongnam-gu", "천안시 서북구": "Cheonan-si Seobuk-gu",
        "전주시 완산구": "Jeonju-si Wansan-gu", "전주시 덕진구": "Jeonju-si Deokjin-gu",
        "포항시 남구": "Pohang-si Nam-gu", "포항시 북구": "Pohang-si Buk-gu",
        "창원시 의창구": "Changwon-si Uichang-gu", "창원시 성산구": "Changwon-si Seongsan-gu",
        "창원시 마산합포구": "Changwon-si Masanhappo-gu", "창원시 마산회원구": "Changwon-si Masanhoewon-gu",
        "창원시 진해구": "Changwon-si Jinhae-gu",
    }
    # Source of truth: 03_cleaned_data/lang_ko_en.json built by build_lang_ko_en.py.
    # Falls back to a small inline map if the JSON is missing (e.g., a fresh checkout
    # that hasn't run build_lang_ko_en.py yet) so this script never crashes.
    _LANG_KO_EN_PATH = os.path.join(PROC, "lang_ko_en.json")
    if os.path.exists(_LANG_KO_EN_PATH):
        LANGUAGE_EN = json.load(open(_LANG_KO_EN_PATH, encoding="utf-8"))
    else:
        LANGUAGE_EN = {
            "중국어": "Chinese", "베트남어": "Vietnamese", "태국어": "Thai", "영어": "English",
            "러시아어": "Russian", "네팔어": "Nepali", "크메르어": "Khmer",
            "인도네시아어": "Indonesian", "미얀마어": "Burmese", "몽골어": "Mongolian",
            "우즈베크어": "Uzbek", "타갈로그어": "Tagalog/Filipino", "일본어": "Japanese",
            "기타": "Other",
        }


    def _load_en_lookups():
        """country_en (from data.json) + sigungu_en (geojson + 일반구 fixes)."""
        dd = json.load(open(os.path.join(SITE, "data.json"), encoding="utf-8"))
        country_en = dict(dd.get("country_en", {}))
        country_en.setdefault("국제연합전문기구", "UN Specialized Agencies")
        country_en.setdefault("국적불명", "Unknown nationality")
        geo = json.load(open(os.path.join(SITE, "korea_sigungu.json"), encoding="utf-8"))
        geo_en = {f["properties"]["match_key"]: f["properties"].get("name_eng", "")
                  for f in geo["features"]}

        def sigungu_en(sido, sigungu):
            if sigungu in AGG:
                return ""
            if sigungu in ILBAN_GU_EN:
                return ILBAN_GU_EN[sigungu]
            return geo_en.get(sido + "|" + str(sigungu).replace(" ", ""), "")

        return country_en, sigungu_en


    COUNTRY_EN, SIGUNGU_EN_FN = _load_en_lookups()


    def add_en(df, cols):
        """Insert English label columns next to their Korean counterparts.
        cols: list of 'sido' | 'sigungu' | 'country' | 'language'."""
        if "country" in cols:
            df.insert(df.columns.get_loc("country") + 1, "country_en",
                      df["country"].map(lambda c: COUNTRY_EN.get(c, "")))
        if "sido" in cols:
            df.insert(df.columns.get_loc("sido") + 1, "sido_en",
                      df["sido"].map(lambda s: SIDO_EN.get(s, "")))
        if "sigungu" in cols:
            df.insert(df.columns.get_loc("sigungu") + 1, "sigungu_en",
                      df.apply(lambda r: SIGUNGU_EN_FN(r["sido"], r["sigungu"]), axis=1))
        if "language" in cols:
            df.insert(df.columns.get_loc("language") + 1, "language_en",
                      df["language"].map(lambda l: LANGUAGE_EN.get(l, "")))
        return df


    def w(name, df):
        path = os.path.join(OUTD, name)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  {name}: {len(df):,} rows")


    # Administrative-transition consolidation, mirroring the dashboard fixes so every
    # sigungu-keyed file uses one continuous district label across the whole series:
    #   인천 남구 -> 미추홀구 (renamed 2018), 경북 군위군 -> 대구 군위군 (transferred 2023),
    #   부천 소사/오정/원미구 -> 부천시 (gu abolished 2016, re-created 2024). Pre-reorg
    #   names (여주군, 당진군, 연기군, 진해시, 청원군) are mapped to their post-reorg
    #   equivalent so their pre-reorg values land under the modern district names.
    #   창원시 / 마산시 are kept under their original name for 2008-2009 (when the
    #   post-merger gu rows don't yet exist); the figure layer renders the five
    #   Changwon gu polygons from these parent rows.
    _BUCHEON_GU = {"부천시 소사구", "부천시 오정구", "부천시 원미구"}
    # Year-aware strays: drop only when at or after `from_year`.
    _STRAYS = {
        ("경기도", "수원시"): 2008,
        ("경상남도", "창원시"): 2010,   # merged July 2010
        ("경상남도", "마산시"): 2010,   # merged July 2010
        ("세종특별자치시", "0"): 2008,
        # 포천군 became 포천시 in 2003; a stray 포천군 row (1 person) still appears in
        # the 2009 district-by-visa sheet. fix_subnational drops it on the dashboard
        # side, so drop it here too and keep the two panels on the same district set.
        ("경기도", "포천군"): 2008,
    }
    # 1:1 administrative renames. Apply BEFORE stray filtering.
    _RENAMES = {
        ("경기도", "여주군"):       ("경기도", "여주시"),
        ("충청남도", "당진군"):     ("충청남도", "당진시"),
        ("충청남도", "연기군"):     ("세종특별자치시", "세종시"),
        ("경상남도", "진해시"):     ("경상남도", "창원시 진해구"),
        ("충청북도", "청원군"):     ("충청북도", "청주시 청원구"),
    }


    def consolidate_admin(df, value_cols):
        df = df.copy()
        df["sigungu"] = df["sigungu"].astype(str)
        df.loc[(df["sido"] == "인천광역시") & (df["sigungu"] == "남구"), "sigungu"] = "미추홀구"
        df.loc[(df["sido"] == "경상북도") & (df["sigungu"] == "군위군"), "sido"] = "대구광역시"
        df.loc[(df["sido"] == "경기도") & (df["sigungu"].isin(_BUCHEON_GU)), "sigungu"] = "부천시"
        # 세종특별자치시 main row: MOIS lists it as 총계 (no sub-시군구); rename to 세종시
        # so it joins with the geo polygon.
        df.loc[(df["sido"] == "세종특별자치시") & (df["sigungu"].isin({"총계", "0"})),
               "sigungu"] = "세종시"
        # Apply 1:1 renames so pre-reorg row values inherit the post-reorg name.
        # Flag the rows this creates: 진해시 -> "창원시 진해구" and 청원군 -> "청주시 청원구"
        # look like 일반구 of a city that, in the pre-merger years, was still a separate
        # city. Without the flag the gu-total rule below reads them as real gu rows and
        # deletes the parent city's own 2008-2009 row (창원시 lost 22 visa rows a year).
        df["_renamed"] = False
        for (osido, osg), (nsido, nsg) in _RENAMES.items():
            mask = (df["sido"] == osido) & (df["sigungu"] == osg)
            df.loc[mask, "sido"] = nsido
            df.loc[mask, "sigungu"] = nsg
            df.loc[mask, "_renamed"] = True
        # Drop sub-office (출장소) rows. They list a sub-area population that is
        # also counted in the parent city's main row, so keeping them creates
        # phantom districts and double counts at the city total.
        df = df[~df["sigungu"].str.contains("출장소", na=False)]
        # Drop city-total rows for cities whose 일반구 rows already carry the
        # population. The full list is generic: any city that appears with both
        # a 2-word city total and 3-word "city gu" rows in the same year. The
        # build_dashboard population pipeline already does this for resident
        # population, but the visa-region table comes in separately and needs the
        # same treatment.
        df["_isgu"] = df["sigungu"].str.contains(" ", regex=False, na=False)
        df["_base"] = df["sigungu"].str.split().str[0]
        _real_gu = df["_isgu"] & ~df["_renamed"]
        if "year" in df.columns:
            gu_keys = set(map(tuple,
                df[_real_gu][["year", "sido", "_base"]].drop_duplicates().values.tolist()))
            keep_gu = df["_isgu"] | df.apply(
                lambda r: (r["year"], r["sido"], r["sigungu"]) not in gu_keys, axis=1)
        else:
            gu_keys = set(map(tuple,
                df[_real_gu][["sido", "_base"]].drop_duplicates().values.tolist()))
            keep_gu = df["_isgu"] | df.apply(
                lambda r: (r["sido"], r["sigungu"]) not in gu_keys, axis=1)
        df = df[keep_gu].drop(columns=["_isgu", "_base", "_renamed"])
        # Year-aware stray filter: drop the (sido, sigungu) row only for years
        # at or after the reorganization. Pre-reorg years are kept so 2008-2009
        # has a value to render.
        if "year" in df.columns:
            keep = df.apply(
                lambda r: not (
                    (r["sido"], r["sigungu"]) in _STRAYS
                    and r["year"] >= _STRAYS[(r["sido"], r["sigungu"])]
                ), axis=1)
        else:
            keep = ~df.apply(lambda r: (r["sido"], r["sigungu"]) in _STRAYS, axis=1)
        df = df[keep]
        keys = [c for c in df.columns if c not in value_cols]
        return df.groupby(keys, as_index=False)[value_cols].sum().sort_values(keys)


    def main():
        print("Exporting dataset release...")

        # 1) Foreign residents by visa (stay + registered), country x visa x year
        stay = pd.read_csv(os.path.join(PROC, "stay_long.csv"))
        reg = pd.read_csv(os.path.join(PROC, "reg_long.csv"))
        stay["population"] = "stay"          # 체류외국인 (long-term + short-term)
        reg["population"] = "registered"     # 등록외국인 (long-term, >90 days)
        visa = pd.concat([stay, reg], ignore_index=True)
        visa = visa[["year", "population", "country", "visa_code", "visa_label", "n"]]
        # Collapse rows that differ only by visa_label (2006-2010 F4 has both
        # "재외동포" and "재외동포(거소)" rows under the same F4 code; sum the
        # counts and keep the first label).
        visa = (visa.groupby(["year", "population", "country", "visa_code"],
                              as_index=False)
                    .agg({"visa_label": "first", "n": "sum"}))
        visa = visa.sort_values(["year", "population", "visa_code", "country"])
        w("foreign_residents_by_visa.csv", add_en(visa, ["country"]))

        # 2) Foreign residents by sigungu x country x year (built from the curated
        #    region.json so it carries the dashboard's subnational corrections:
        #    화성시 2014 re-parse, Bucheon/미추홀/군위 consolidation, stray removal)
        region_doc = json.load(open(os.path.join(SITE, "region.json"), encoding="utf-8"))
        rows = []
        for y, sidos in region_doc["by_sigungu"].items():
            for sido, sigs in sidos.items():
                for sg, nat in sigs.items():
                    if sg in AGG:
                        continue
                    for country, n in nat.items():
                        rows.append({"year": int(y), "sido": sido, "sigungu": sg,
                                     "country": country, "n": n})
        region = pd.DataFrame(rows).sort_values(["year", "sido", "sigungu", "country"])
        w("foreign_residents_by_sigungu.csv", add_en(region, ["sido", "sigungu", "country"]))

        # 2b) Foreign residents by sigungu x visa status x year (2017-2025 only;
        #     the district-by-visa source table is not published before 2017)
        vr_path = os.path.join(SITE, "visa_region.json")
        if os.path.exists(vr_path):
            vr = json.load(open(vr_path, encoding="utf-8"))
            # restore spaced sigungu names from region.json (visa_region keys drop spaces)
            spaced = {}
            for _, r in region.iterrows():
                spaced[(r["sido"], str(r["sigungu"]).replace(" ", ""))] = r["sigungu"]
            rows = []
            for y, blk in vr["data"].items():
                for key, codes in blk.items():
                    sido, sg_ns = key.split("|", 1)
                    sg = spaced.get((sido, sg_ns), sg_ns)
                    for code, n in codes.items():
                        rows.append({"year": int(y), "sido": sido, "sigungu": sg, "visa_code": code, "n": n})
            vrdf = consolidate_admin(pd.DataFrame(rows), ["n"])
            vrdf = vrdf.sort_values(["year", "sido", "sigungu", "visa_code"])
            w("foreign_residents_by_sigungu_visa.csv", add_en(vrdf, ["sido", "sigungu"]))

        # 3) Foreign residents by age x sex x country x year
        age = pd.read_csv(os.path.join(PROC, "age_long.csv"))
        age = age[["year", "country", "gender", "age_group", "n"]]
        # the intermediate age_long can carry repeated (year, country, gender,
        # age_group) rows from the multi-block source layout; collapse to one row
        # per key (values are identical across repeats) before export.
        age = (age.groupby(["year", "country", "gender", "age_group"], as_index=False)["n"].sum()
                  .sort_values(["year", "country", "age_group", "gender"]))
        w("foreign_residents_by_age_sex.csv", add_en(age, ["country"]))

        # 4) Resident registration population (MOIS denominator)
        pop = pd.read_csv(os.path.join(PROC, "population_long.csv"))
        pop = pop[~pop["sigungu"].isin(AGG - {"총계"})]  # keep 세종 총계
        pop = pop[["year", "sido", "sigungu", "total_pop", "male", "female"]]
        pop = consolidate_admin(pop, ["total_pop", "male", "female"]).sort_values(
            ["year", "sido", "sigungu"])
        w("resident_population_by_sigungu.csv", add_en(pop, ["sido", "sigungu"]))

        # ---- Computed indices from indices.json ----
        idx = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))["data"]

        # 5) Segregation / diversity indices by sigungu x year
        rows = []
        for y, arr in idx["by_sigungu"].items():
            for s in arr:
                rows.append({"year": int(y), "sido": s["sido"], "sigungu": s["sigungu"],
                             "foreign_total": s["foreign_total"], "total_pop": s.get("total_pop"),
                             "foreign_share_pct": s.get("foreign_share_pct"),
                             "shannon_H": s.get("shannon_H"),
                             "shannon_H_inclusive": s.get("shannon_H_inclusive"),
                             "continent_H": s.get("continent_H"),
                             "HHI": s.get("HHI"), "evenness": s.get("evenness"),
                             "n_nationalities": s.get("n_nationalities")})
        w("indices_by_sigungu.csv", add_en(pd.DataFrame(rows).sort_values(["year", "sido", "sigungu"]), ["sido", "sigungu"]))

        # 6) Indices by sido x year
        rows = []
        for y, arr in idx["by_sido"].items():
            for s in arr:
                rows.append({"year": int(y), "sido": s["sido"],
                             "foreign_total": s["foreign_total"], "total_pop": s.get("total_pop"),
                             "foreign_share_pct": s.get("foreign_share_pct"),
                             "shannon_H": s.get("shannon_H"),
                             "shannon_H_inclusive": s.get("shannon_H_inclusive"),
                             "continent_H": s.get("continent_H"),
                             "HHI": s.get("HHI"), "evenness": s.get("evenness"),
                             "n_nationalities": s.get("n_nationalities")})
        w("indices_by_sido.csv", add_en(pd.DataFrame(rows).sort_values(["year", "sido"]), ["sido"]))

        # 6b) Segregation indices by nationality x year (evenness + exposure)
        rows = []
        for y, arr in idx.get("by_nationality", {}).items():
            for s in arr:
                rows.append({"year": int(y), "country": s["country"],
                             "continent": s.get("continent"),
                             "national_total": s["national_total"],
                             "dissimilarity_D": s.get("D"),
                             "isolation": s.get("isolation"),
                             "interaction_korean": s.get("interaction_korean")})
        if rows:
            w("segregation_by_nationality.csv",
              add_en(pd.DataFrame(rows).sort_values(["year", "national_total"], ascending=[True, False]), ["country"]))

        # 6c) National annual summary (diversity + segregation time series)
        rows = []
        for y, s in idx.get("summary", {}).items():
            rows.append({"year": int(y),
                         "foreign_total": s.get("national_foreign_total"),
                         "total_pop": s.get("national_total_pop"),
                         "foreign_share_pct": s.get("national_share_pct"),
                         "shannon_H": s.get("national_shannon_H"),
                         "shannon_H_inclusive": s.get("national_shannon_H_inclusive"),
                         "continent_H": s.get("continent_H"),
                         "HHI": s.get("national_HHI"),
                         "evenness": s.get("national_evenness"),
                         "theil_segregation_H": s.get("theil_segregation_H"),
                         "morans_I_share": s.get("morans_I_share"),
                         "n_nationalities": s.get("n_nationalities"),
                         "n_enclaves": s.get("n_enclaves")})
        if rows:
            w("national_summary_annual.csv", pd.DataFrame(rows).sort_values("year"))

        # 6d) Region-of-origin segregation
        rows = []
        for y, blk in idx.get("region_seg", {}).items():
            for region, g in blk.items():
                rows.append({"year": int(y), "region": region, "total": g.get("total"),
                             "dissimilarity_D": g.get("D"), "isolation": g.get("isolation")})
        if rows:
            w("region_segregation.csv", pd.DataFrame(rows).sort_values(["year", "region"]))

        # 7) Ethnic enclaves
        rows = []
        for y, arr in idx["enclaves"].items():
            for e in arr:
                rows.append({"year": int(y), "sido": e["sido"], "sigungu": e["sigungu"],
                             "country": e["country"], "count": e["count"], "lq": e["lq"],
                             "share_of_foreign_pct": e["share_of_foreign_pct"],
                             "sigungu_foreign_total": e["sigungu_foreign_total"]})
        w("ethnic_enclaves.csv", add_en(pd.DataFrame(rows).sort_values(["year", "lq"], ascending=[True, False]), ["sido", "sigungu", "country"]))

        # 8) Language demand (national + per-sigungu)
        rows = []
        for y, blk in idx["language"].items():
            for x in blk["national"]:
                rows.append({"year": int(y), "scope": "national", "sido": "", "sigungu": "",
                             "language": x["language"], "count": x["count"]})
            for key, langs in blk["by_sigungu"].items():
                sido, sg = key.split("|", 1)
                for x in langs:
                    rows.append({"year": int(y), "scope": "sigungu", "sido": sido, "sigungu": sg,
                                 "language": x["language"], "count": x["count"]})
        w("language_demand.csv", add_en(pd.DataFrame(rows).sort_values(["year", "scope", "sido", "sigungu"]), ["sido", "sigungu", "language"]))

        # ---- Auxiliary datasets from data.json ----
        dd = json.load(open(os.path.join(SITE, "data.json"), encoding="utf-8"))

        # The non-spatiotemporal annual auxiliary series (naturalization, refugees,
        # refugee language demand, and North Korean defector entries) are available
        # in the interactive dashboard but are intentionally NOT part of this public
        # dataset release, which is scoped to the spatiotemporal foreign-resident
        # data and its derived residential measures.

        write_dictionary()
        write_readme()
        write_license_citation()
        print(f"\nDone -> {OUT}")


    def write_dictionary():
        fields = [
            ("foreign_residents_by_visa.csv", "year", "integer", "Reference year (2006-2025)"),
            ("foreign_residents_by_visa.csv", "population", "string", "stay = 체류외국인 (registered + short-term); registered = 등록외국인 (long-term, >90 days)"),
            ("(all files)", "*_en columns", "string", "English labels for international reuse: country_en, sido_en, sigungu_en (Revised Romanization), language_en, alongside each Korean column"),
            ("foreign_residents_by_visa.csv", "country", "string", "Nationality (Korean label, harmonized across years)"),
            ("foreign_residents_by_visa.csv", "country_en", "string", "Nationality in English"),
            ("foreign_residents_by_visa.csv", "visa_code", "string", "Visa/stay-status code (e.g., E9, F4); 2007-2009 sub-codes collapsed to parent"),
            ("foreign_residents_by_visa.csv", "visa_label", "string", "Korean label for the visa code"),
            ("foreign_residents_by_visa.csv", "n", "integer", "Number of foreign residents"),
            ("foreign_residents_by_sigungu.csv", "sido", "string", "Province / metropolitan city (harmonized)"),
            ("foreign_residents_by_sigungu.csv", "sigungu", "string", "District; cities with 일반구 use 'city gu' (e.g., 고양시 일산서구)"),
            ("foreign_residents_by_sigungu.csv", "n", "integer", "Registered foreign residents in that sigungu"),
            ("foreign_residents_by_sigungu_visa.csv", "visa_code", "string", "Visa/stay-status code (e.g., E9, F4); registered foreigners by district x visa, 2017-2025 (source table not published before 2017)"),
            ("foreign_residents_by_age_sex.csv", "gender", "string", "남성/여성/총계"),
            ("foreign_residents_by_age_sex.csv", "age_group", "string", "Age band (e.g., 0-9, 10-19, ...)"),
            ("resident_population_by_sigungu.csv", "total_pop", "integer", "MOIS resident registration total population (denominator)"),
            ("resident_population_by_sigungu.csv", "male/female", "integer", "Resident population by sex"),
            ("indices_by_sigungu.csv", "foreign_share_pct", "float", "registered foreigners / total_pop x 100"),
            ("indices_by_sigungu.csv", "shannon_H", "float", "Shannon diversity over nationalities within the foreign population: -sum p_i ln p_i"),
            ("indices_by_sigungu.csv", "shannon_H_inclusive", "float", "Shannon diversity treating Koreans as one group + each nationality"),
            ("indices_by_sigungu.csv", "HHI", "float", "Herfindahl-Hirschman index, sum p_i^2 (foreign nationalities)"),
            ("indices_by_sigungu.csv", "evenness", "float", "Pielou evenness = Shannon H / ln(n_nationalities); 0-1, higher = nationalities more evenly balanced"),
            ("indices_by_sigungu.csv", "n_nationalities", "integer", "Distinct nationalities present"),
            ("ethnic_enclaves.csv", "lq", "float", "Location Quotient: local share / national share (>=2 = enclave criterion)"),
            ("ethnic_enclaves.csv", "share_of_foreign_pct", "float", "Nationality's share of the sigungu's foreign population (>=30% = enclave criterion)"),
            ("language_demand.csv", "scope", "string", "national or sigungu"),
            ("language_demand.csv", "language", "string", "Public-service language label (Ethnologue 24 weighted L1 mapping; Korean excluded; major dialect variants merged to a parent language e.g. S'gaw Karen->Karen; minority languages kept individually, no '기타'/'Other' bucket)"),
            ("language_demand.csv", "count", "integer", "Estimated speakers: each nationality's population allocated across languages by L1 (mother-tongue) share of the source country"),
            ("indices_by_sigungu.csv", "continent_H", "float", "Continent-level (visible) diversity: Shannon H over world regions with Koreans counted as East Asian"),
            ("indices_by_sido.csv", "(all index columns)", "mixed", "Same index set as indices_by_sigungu (foreign_share_pct, shannon_H, shannon_H_inclusive, continent_H, HHI, evenness, n_nationalities), aggregated to province (sido) x year, 2006-2025"),
            ("segregation_by_nationality.csv", "continent", "string", "World region of the nationality"),
            ("segregation_by_nationality.csv", "national_total", "integer", "National foreign population of the nationality that year"),
            ("segregation_by_nationality.csv", "dissimilarity_D", "float", "Index of dissimilarity vs Koreans across districts: 0.5 sum |x_i/X - k_i/K| (evenness dimension)"),
            ("segregation_by_nationality.csv", "isolation", "float", "Own-group exposure: sum (x_i/X)(x_i/t_i)"),
            ("segregation_by_nationality.csv", "interaction_korean", "float", "Exposure to Koreans: sum (x_i/X)(korean_i/t_i)"),
            ("region_segregation.csv", "region", "string", "World region of origin (nationalities grouped)"),
            ("region_segregation.csv", "dissimilarity_D / isolation", "float", "Same segregation indices as segregation_by_nationality, computed per region of origin"),
            ("national_summary_annual.csv", "theil_segregation_H", "float", "Multigroup Theil entropy segregation (Reardon & Firebaugh 2002), national, over Koreans + each nationality"),
            ("national_summary_annual.csv", "morans_I_share", "float", "Moran's I of the foreign share across districts (spatial clustering dimension)"),
            ("national_summary_annual.csv", "n_enclaves", "integer", "Count of ethnic-enclave districts that year"),
        ]
        path = os.path.join(OUT, "data_dictionary.csv")
        if os.path.exists(path):
            print("  data_dictionary.csv SKIPPED (kept the curated file; "
                  "04_dataset_release/code/build_data_dictionary.py regenerates it)")
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f)
            wr.writerow(["file", "variable", "type", "description"])
            wr.writerows(fields)
        print("  data_dictionary.csv")


    def write_readme():
        txt = """# KIRD: Korea Immigration & Residential Diversity Dataset (2006-2025)

**DOI:** https://doi.org/10.5281/zenodo.20355728

A harmonized, multi-source spatiotemporal dataset of foreign residents in South
Korea, with derived residential-segregation, ethnic-diversity, ethnic-enclave,
and language-access measures at the sigungu (district) level. KIRD also backs
an interactive dashboard of the same name.

Curated by **[Nari Yoo, PhD](https://nariyoo.com)** (University of Michigan School of Social Work).

## Sources
- Ministry of Justice (MOJ) Korea Immigration Service Statistical Yearbook (출입국·외국인정책 통계연보), 2006-2025 — foreign residents by nationality x visa x district. Official yearbooks: https://www.immigration.go.kr/immigration/1570/subview.do
- Ministry of the Interior and Safety (MOIS) Resident Registration Population (denominator)

## Files (data/)
| File | Unit | Years |
|---|---|---|
| foreign_residents_by_visa.csv | population x nationality x visa x year | 2006-2025 |
| foreign_residents_by_sigungu.csv | sido x sigungu x nationality x year | 2009-2025 |
| foreign_residents_by_sigungu_visa.csv | sido x sigungu x visa status x year | 2008-2025 |
| foreign_residents_by_age_sex.csv | nationality x age x sex x year | 2009-2025 |
| resident_population_by_sigungu.csv | sido x sigungu x year (MOIS) | 2008-2025 |
| indices_by_sigungu.csv | sido x sigungu x year | 2009-2025 |
| indices_by_sido.csv | sido x year | 2006-2025 |
| segregation_by_nationality.csv | nationality x year (D, isolation, interaction) | 2014-2025 |
| region_segregation.csv | region of origin x year (D, isolation) | 2014-2025 |
| national_summary_annual.csv | year (diversity + Theil + Moran's I series) | 2009-2025 |
| ethnic_enclaves.csv | year x sigungu x nationality | 2009-2025 |
| language_demand.csv | year x scope x language | 2009-2025 |

All categorical fields are **bilingual**: every Korean label column is paired
with an English column (`country_en`, `sido_en`, `sigungu_en` in Revised
Romanization, `language_en`) for international reuse. See `data_dictionary.csv`
for variable definitions.

## Index definitions
- **Foreign share (%)** = registered foreigners / MOIS total population.
- **Shannon H** = -sum p_i ln(p_i) over nationalities (within foreigners).
- **Shannon H (inclusive)** = Koreans as one group + each foreign nationality.
- **Continent H (visible diversity)** = Shannon H over world regions with Koreans counted as East Asian; higher when groups from other continents are present.
- **HHI** = sum p_i^2.
- **Location Quotient (LQ)** = local share / national share.
- **Index of Dissimilarity (D)** = 0.5 sum |x_i/X - y_i/Y| vs Koreans (evenness).
- **Isolation / Korean interaction** = sum (x_i/X)(x_i/t_i) and sum (x_i/X)(korean_i/t_i) (exposure).
- **Theil multigroup segregation H** = sum t_i(E-E_i)/(T E) over Koreans + each nationality (national, per year; Reardon & Firebaugh 2002).
- **Ethnic enclave** = LQ >= 2 AND a single nationality >= 30% of the sigungu's
  foreign population (Wilson & Portes 1980; Logan, Zhang & Alba 2002).

## Harmonization & validation
KIS yearbook Excel layouts change ~6 times across 2006-2025; country names,
visa sub-codes, and province/district names are harmonized across years.

Validation against published official MOJ totals: registered-foreigner counts
reconcile to within ~0.2% every year 2006-2025 (e.g. 2007 -0.03%, 2024 exact);
total staying-foreigner (체류) counts to within ~0.7% (2010 -0.09%, 2024 -0.01%).
Two source quirks are handled: (1) 2007-2008 yearbooks list a category total
alongside its full sub-code breakdown for some statuses (e.g. D-3); exact
duplicates are removed by anchoring to each file's grand-total row; (2) for
2006-2010 the staying total is composed as 등록 + 단기 + 외국적동포 거소신고
(overseas-Korean residence reports), the third component the source keeps in a
separate table. Resident population totals match MOIS (~51.2-51.8M).

The district-level denominator used for foreign_share_pct was verified at the
sigungu level: total_pop in indices_by_sigungu matches the published MOIS
resident-registration population for the same district and the same year, with
no district exceeding a 100% foreign share. Spot checks across years and the
highest-foreign-share districts agree exactly (e.g. Ansan Danwon-gu 326,368 in
2014, 304,032 in 2018, 293,388 in 2024; Yeongam-gun 51,391 and Yeongdeungpo-gu
373,773 in 2024). A small number of districts in administrative-transition years
carry no denominator because the yearbook and the MOIS table adopted boundary
changes in different years (see Known limitations); these are left null rather
than matched to a wrong-boundary population.

District-level administrative transitions are harmonized to a single continuous
label across the whole series so each district's trend is unbroken: 부천시
(general districts abolished 2016, re-created 2024) is consolidated to one 부천시
unit; 인천 남구 is carried as its post-2018 name 미추홀구; 군위군 is placed under
대구광역시 for all years (transferred from 경상북도 in 2023); and residual rows of
dissolved/duplicated units (청원군 after its 2014 merger into 청주시, 연기군/세종
parse residue, gu-less city totals) are dropped. Sub-office (출장소) rows, which
are subdivisions already counted in their city's total, are not double-counted
(this corrects an earlier 화성시 2014 figure).

Known limitations:
- A few sigungu lack a population denominator in administrative-transition
  years because KIS and MOIS adopted boundary changes in different years; these
  rows are left with a null denominator rather than matched to a wrong-boundary
  population. Major merged cities are correctly carried.
- 2005 excluded (irregular source format with prior-year reference columns).

## License
CC BY 4.0. Underlying statistics are public Korean government data.

## Citation
Yoo, N. (2026). KIRD: Korea Immigration & Residential Diversity Dataset (2006-2025) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.20355728
"""
        # The deposit README was rewritten by hand for openICPSR (DOI, split of data
        # vs code, the 2026 file list). This generated draft is the older Zenodo-era
        # text, so a rebuild must not silently revert it.
        path = os.path.join(OUT, "README.md")
        if os.path.exists(path):
            print("  README.md SKIPPED (kept the curated deposit README)")
            return
        open(path, "w", encoding="utf-8").write(txt)
        print("  README.md")


    def write_license_citation():
        cff = """cff-version: 1.2.0
title: "KIRD: Korea Immigration & Residential Diversity Dataset (2006-2025)"
message: If you use this dataset, please cite it as below.
type: dataset
authors:
  - family-names: Yoo
    given-names: Nari
    affiliation: University of Michigan School of Social Work
    website: https://nariyoo.com
year: 2026
version: 1.1.0
date-released: 2026-05-28
doi: 10.5281/zenodo.20355728
identifiers:
  - type: doi
    value: 10.5281/zenodo.20355728
    description: Zenodo record for this dataset
license: CC-BY-4.0
"""
        # Same as the README: the live CITATION.cff carries the minted openICPSR DOI
        # and the final dataset title, which this draft predates.
        cff_path = os.path.join(OUT, "CITATION.cff")
        if os.path.exists(cff_path):
            print("  CITATION.cff SKIPPED (kept the curated file with the openICPSR DOI)")
        else:
            open(cff_path, "w", encoding="utf-8").write(cff)
        lic_path = os.path.join(OUT, "LICENSE")
        if not os.path.exists(lic_path):
            open(lic_path, "w", encoding="utf-8").write(
                "Creative Commons Attribution 4.0 International (CC BY 4.0)\n"
                "https://creativecommons.org/licenses/by/4.0/\n")
        print("  CITATION.cff, LICENSE")

    main()



def export_language_demand():
    """language_demand.csv, written from the trimmed indices.json.

    Step 27 emits a draft of this file from the untrimmed language block; this step
    replaces it with the released version, top 20 languages per district on the same
    schema. English labels come from the existing language_demand.csv where one is
    already there, otherwise from 03_cleaned_data/lang_ko_en.json. The 기타 bucket is
    dropped upstream in step 26, so no row carries it.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    SITE = os.path.join(ROOT, "05_dashboard", "data")
    OUT = os.path.join(ROOT, "04_dataset_release", "data", "language_demand.csv")

    idx = json.load(open(os.path.join(SITE, "indices.json"), encoding="utf-8"))["data"]["language"]

    # en 라벨 룩업: 기존 CSV에서 먼저, lang_ko_en.json으로 보강
    sido_en, sg_en, lang_en = {}, {}, {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["sido"]:
                    sido_en.setdefault(r["sido"], r["sido_en"])
                if r["sigungu"]:
                    sg_en.setdefault((r["sido"], r["sigungu"]), r["sigungu_en"])
                if r["language"] and r["language_en"]:
                    lang_en.setdefault(r["language"], r["language_en"])
    try:
        LKE = json.load(open(os.path.join(ROOT, "03_cleaned_data", "lang_ko_en.json"), encoding="utf-8"))
        for k, v in LKE.items():
            lang_en.setdefault(k, v)
    except FileNotFoundError:
        pass

    # 한국어 라벨이 없는 소수어는 language 컬럼 자체가 Ethnologue 영문명 → language_en도 동일.
    def en_of(lab):
        return lang_en.get(lab) or lab

    # 추정화자 1명 미만(fractional) 행은 언어수요 의미가 없어 드롭(기타 버킷 대신 long-tail 정리).
    FLOOR = 1.0

    # 릴리스 CSV의 count는 정수(데이터 사전: "rounded to whole persons").
    # indices.json은 소수 1자리로 들고 있으므로 여기서 반올림해 내보낸다.
    def as_persons(v):
        return int(round(v))

    rows = []
    for y in sorted(idx, key=int):
        blk = idx[y]
        for x in blk.get("national", []):
            if x["count"] < FLOOR:
                continue
            rows.append((int(y), "national", "", "", "", "",
                         x["language"], en_of(x["language"]), as_persons(x["count"])))
        for key, langs in blk.get("by_sigungu", {}).items():
            sido, sg = key.split("|", 1)
            for x in langs:
                if x["count"] < FLOOR:
                    continue
                rows.append((int(y), "sigungu", sido, sido_en.get(sido, ""), sg, sg_en.get((sido, sg), ""),
                             x["language"], en_of(x["language"]), as_persons(x["count"])))

    # export_dataset와 동일 정렬: year, scope, sido, sigungu
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[4]))

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "scope", "sido", "sido_en", "sigungu", "sigungu_en", "language", "language_en", "count"])
        w.writerows(rows)

    n_kita = sum(1 for r in rows if r[6] == "기타")
    n_noen = len({r[6] for r in rows if not r[7]})
    print(f"wrote {OUT}: {len(rows)} rows | 기타행 {n_kita} | en없는 언어라벨 {n_noen}종")
    print("연도:", min(int(y) for y in idx), "~", max(int(y) for y in idx))


if __name__ == "__main__":
    export_dataset()
    export_language_demand()
