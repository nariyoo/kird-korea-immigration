"""The MOIS layer, end to end.

행정안전부 외국인주민통계 counts a broader population than MOJ: it adds naturalized
residents and the Korean-born children of foreign residents. The raw files are
parsed upstream by scripts_mois; this step builds the join keys and the
administrative codes on them, cross-checks the counts against MOJ, assembles the
layer, patches Sejong into it, and packages the result as CSV and Parquet.

Sejong needs patching because the parsers key on 시군구 and Sejong has none, and
because MOIS lists it only from 2013, so 2006-2012 comes from the predecessor
연기군.
"""
from collections import defaultdict
from pathlib import Path
import json
import os
import shutil
import sys

import pandas as pd

from kird import ROOT

# 일반구 by parent 시, every district these twelve cities have carried 2006-2024,
# including the ones since abolished (부천시 2019) and the ones added on a merger
# (청주시 2014, 창원시 2010). Mirrors scripts_mois/mois_common.GU_BY_CITY, which the
# parsers use; it is repeated here because the published bundle ships this step and
# not the parsers, so the layer has to be able to canonicalize the keys it is handed.
GU_BY_CITY = {
    "고양시": ("덕양구", "일산동구", "일산서구"),
    "부천시": ("소사구", "오정구", "원미구"),
    "성남시": ("분당구", "수정구", "중원구"),
    "수원시": ("권선구", "영통구", "장안구", "팔달구"),
    "안산시": ("단원구", "상록구"),
    "안양시": ("동안구", "만안구"),
    "용인시": ("기흥구", "수지구", "처인구"),
    "전주시": ("덕진구", "완산구"),
    "창원시": ("마산합포구", "마산회원구", "성산구", "의창구", "진해구"),
    "천안시": ("동남구", "서북구"),
    "청주시": ("상당구", "서원구", "청원구", "흥덕구"),
    "포항시": ("남구", "북구"),
}
_EMD_SUFFIXES = ("동", "읍", "면", "리", "출장소")


def _strip_gu_prefix(name, sigungu):
    """Drop a 일반구 that the source printed in front of a 읍면동 name.

    ('덕양구고양동', '고양시')       -> '고양동'   (2014 sheets: 시 only in sigungu)
    ('덕양구고양동', '고양시 덕양구') -> '고양동'   (2015 sheets: 구 in both places)
    ('구서1동', '금정구')            -> '구서1동'  (금정구 is a 자치구, not a 일반구)

    Only a district of the row's own 시 is stripped, and only when what is left is
    still a 읍/면/동/출장소, so a 동 whose own name opens with a 구 syllable is safe.
    """
    if not name or not sigungu:
        return name
    city = str(sigungu).split(" ")[0]
    for gu in sorted(GU_BY_CITY.get(city, ()), key=len, reverse=True):
        if name.startswith(gu) and len(name) > len(gu):
            rest = name[len(gu):]
            if rest.endswith(_EMD_SUFFIXES):
                return rest
    return name


def canonicalize_eupmyeondong_names():
    """Put a 일반구 the 2014-2015 sources printed inside the 읍면동 name back in sigungu.

    The 2014 and 2015 행정안전부 읍면동 sheets write the sub-district of a city with
    general districts as '덕양구 고양동', and the parser's whitespace strip glues that
    into '덕양구고양동'. In 2015 the district is also in `sigungu` ('고양시 덕양구'), so
    the glued copy is a mislabelled but single row; in 2014 `sigungu` is the bare city,
    so the glued name is a *second* key for a 동 that already exists, carrying only the
    세대수 the auxiliary sheet supplies and none of the population the main 유형별 sheet
    does. That is where the 434 value-less 2014 rows in summary_by_eupmyeondong.csv came
    from: 창원 62, 성남 48, 수원 40, 고양 39, 부천 36, 전주 33, and the rest.

    Names are canonicalized here, on the tidy tables, because this step owns the MOIS
    join keys and because the released `04_dataset_release/mois/` CSVs are copies of
    them. The parsers in scripts_mois now emit the canonical form directly, so on a
    build that re-parses the yearbooks this pass finds nothing and rewrites nothing.

    A row that collides with an existing unstripped row once its district is removed is
    dropped: that is the 2014 세대수, which the auxiliary sheet 6 repeats for a 동 the
    main sheet already reported, and the main sheet is the one every other category
    comes from. Rows whose stripped name matches nothing (청주 강서1동, the 출장소
    branch offices) stay, value-less, as they were.
    """
    DATA = Path(ROOT) / "03_cleaned_data"
    # Every tidy MOIS table keyed by 읍면동. mois_region_keys*.csv are rebuilt from
    # mois_population.csv by the next function, so they are not listed here.
    FILES = [
        "mois_population.csv",          # + the collision rule, below
        "mois_total_pop.csv",
        "mois_nationality.csv",
        "mois_children_parent.csv",
        "mois_multicultural.csv",
        "mois_eupmyeondong_indices.csv",
        "mois_eupmyeondong_enclaves.csv",
    ]
    KEY = ["year", "level", "sido", "sigungu", "eupmyeondong", "category", "sex"]

    def renamed(chunk):
        new = [_strip_gu_prefix(e, s)
               for e, s in zip(chunk["eupmyeondong"].astype(str), chunk["sigungu"].astype(str))]
        n = int((pd.Series(new, index=chunk.index) != chunk["eupmyeondong"]).sum())
        chunk = chunk.copy()
        chunk["eupmyeondong"] = new
        return chunk, n

    print("\n===== canonicalize 읍면동 names (일반구 out of eupmyeondong) =====")
    for fn in FILES:
        p = DATA / fn
        if not p.exists():
            print(f"  {fn:<34s} MISSING")
            continue
        read = dict(dtype=str, keep_default_na=False, encoding="utf-8-sig", low_memory=False)
        if fn == "mois_population.csv":
            df = pd.read_csv(p, **read)
            if "eupmyeondong" not in df.columns:
                print(f"  {fn:<34s} no eupmyeondong column"); continue
            keep_keys = set(map(tuple, df.loc[
                [_strip_gu_prefix(e, s) == e for e, s in
                 zip(df["eupmyeondong"], df["sigungu"])], KEY].values))
            out, n_renamed = renamed(df)
            dup = pd.Series([tuple(r) in keep_keys for r in out[KEY].values], index=out.index)
            dup &= pd.Series([a != b for a, b in zip(out["eupmyeondong"], df["eupmyeondong"])],
                             index=out.index)
            n_dropped = int(dup.sum())
            if n_renamed == 0 and n_dropped == 0:
                print(f"  {fn:<34s} already canonical")
                continue
            out[~dup].to_csv(p, index=False, encoding="utf-8-sig")
            print(f"  {fn:<34s} {n_renamed:,} names fixed, "
                  f"{n_dropped:,} duplicate rows dropped ({len(out) - n_dropped:,} rows)")
            continue
        # Everything else: count first on two columns, and only rewrite if a name really
        # changes, so a canonical build does no IO. The rewrite streams, because the
        # nationality table is 318 MB and does not need to be resident.
        head = pd.read_csv(p, nrows=0, encoding="utf-8-sig")
        if "eupmyeondong" not in head.columns:
            print(f"  {fn:<34s} no eupmyeondong column")
            continue
        total = 0
        for chunk in pd.read_csv(p, chunksize=400_000, usecols=["sigungu", "eupmyeondong"], **read):
            total += renamed(chunk)[1]
        if not total:
            print(f"  {fn:<34s} already canonical")
            continue
        tmp = p.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
            for i, chunk in enumerate(pd.read_csv(p, chunksize=400_000, **read)):
                renamed(chunk)[0].to_csv(fh, index=False, header=(i == 0), lineterminator="\r\n")
        os.replace(tmp, p)
        print(f"  {fn:<34s} {total:,} names fixed")


def region_keys_and_validation():
    """Region keys for the MOIS layer, the codes on them, and the cross-check against MOJ.

    Three passes over the same tables, which only ever run together:

      1. A stable internal join key, `sido|sigungu|eupmyeondong`, on normalized names.
         MOIS publishes no official 행정동 code, so the key is name-based.
      2. The 행정구역코드 (BCNT, 7 digits) from the in-house 2015 lookup, which covers
         most regions in 2014-2024. Names that do not match get a blank code.
      3. MOIS 한국국적미취득자 against MOJ 등록외국인 at district level. The two are
         close but not equal by construction, since MOJ counts immigration registries
         and MOIS counts resident registries.
    """
    def build_region_keys():
        """Build stable region keys for MOIS data.

        Status: name-only normalization (no official 행정동 BCNT 5-digit code).
        True 행정동 코드 매핑은 외부 lookup 필요:
          - 행정안전부 표준 행정동 코드 (BCNT): https://www.code.go.kr/
          - 통계청 KOSTAT 코드: https://kssc.kostat.go.kr/
          - SGIS API (행정동 경계 자료): https://sgis.kostat.go.kr/

        This script generates a stable internal key for downstream joins:
          region_key = f"{canonical_sido}|{sigungu}|{eupmyeondong}"

        Outputs:
        - 03_cleaned_data/mois_region_keys.csv
          Columns: region_key, level (sigungu/eupmyeondong), sido, sigungu, eupmyeondong,
                   first_year, last_year, n_years_seen
        - 03_cleaned_data/mois_region_keys_dedup.csv:  unique (region_key, level) only

        Use this CSV as the join key between MOIS data and any geometry / external coding.
        A follow-up script (TBD) can later attach BCNT 5-digit codes by joining on
        canonical names to a KOSTAT lookup table.
        """
        HERE = os.path.dirname(os.path.abspath(__file__))
        DATA = os.path.join(ROOT, "03_cleaned_data")

        SIDO_CANON = {
            "강원도": "강원도",
            "강원특별자치도": "강원도",
            "전라북도": "전라북도",
            "전북특별자치도": "전라북도",
            "제주도": "제주특별자치도",
            "제주특별자치도": "제주특별자치도",
            "세종시": "세종특별자치시",
            "세종특별자치시": "세종특별자치시",
        }


        def canon(s):
            return SIDO_CANON.get(s, s)


        def main():
            pop = pd.read_csv(os.path.join(DATA, "mois_population.csv"))
            sigungu = pop[pop["level"] == "sigungu"][
                ["year", "sido", "sigungu"]].drop_duplicates()
            emd = pop[pop["level"] == "eupmyeondong"][
                ["year", "sido", "sigungu", "eupmyeondong"]].drop_duplicates()

            sigungu["sido_canon"] = sigungu["sido"].map(canon)
            emd["sido_canon"] = emd["sido"].map(canon)

            sigungu["region_key"] = (sigungu["sido_canon"] + "|" + sigungu["sigungu"]
                                      + "|" )
            emd["region_key"] = (emd["sido_canon"] + "|" + emd["sigungu"] + "|"
                                  + emd["eupmyeondong"])

            sigungu["level"] = "sigungu"; sigungu["eupmyeondong"] = ""
            emd["level"] = "eupmyeondong"

            cols = ["region_key", "level", "sido_canon", "sigungu", "eupmyeondong",
                    "year"]
            full = pd.concat([sigungu[cols], emd[cols]], ignore_index=True)
            full = full.rename(columns={"sido_canon": "sido"})

            # Aggregate
            grouped = full.groupby(["region_key", "level", "sido", "sigungu",
                                      "eupmyeondong"]).agg(
                first_year=("year", "min"),
                last_year=("year", "max"),
                n_years_seen=("year", "nunique"),
            ).reset_index()

            grouped = grouped.sort_values(["level", "sido", "sigungu", "eupmyeondong"])
            grouped.to_csv(os.path.join(DATA, "mois_region_keys.csv"),
                            index=False, encoding="utf-8-sig")
            # Also a unique-only version
            grouped[["region_key", "level", "sido", "sigungu", "eupmyeondong"]].to_csv(
                os.path.join(DATA, "mois_region_keys_dedup.csv"),
                index=False, encoding="utf-8-sig")

            print(f"Total unique region keys: {len(grouped):,}")
            print(grouped.groupby("level").size().rename("n_keys"))
            print()
            print(f"Examples (eupmyeondong, first 10):")
            print(grouped[grouped.level == "eupmyeondong"].head(10).to_string(index=False))

        main()



    def attach_bcnt_codes():
        """Attach 행정구역코드 (BCNT 7-digit) to MOIS region_keys.

        Uses the in-house lookup at 03_cleaned_data/mois_bcnt_codes_inhouse.csv
        (extracted from 2015 행안부 source files by scripts_mois/extract_bcnt_codes.py).

        The 2015 codes cover most regions present in 2014-2024 — code drift mainly
        comes from 2014→2024 boundary changes (Bucheon merger, 청주시 통합 등). For
        unmatched names we just emit blank `bcnt_code` and print a sample to console.

        If you obtain a fresh / authoritative external BCNT table from
        https://www.code.go.kr (행정안전부 표준 행정구역코드), drop it as
        external/bcnt_codes_external.csv with cols (sido, sigungu, eupmyeondong, code)
        — that takes precedence over the in-house lookup.

        Output: 03_cleaned_data/mois_region_keys_with_bcnt.csv
        """
        root = Path(ROOT)
        DATA = root / "03_cleaned_data"
        EXTERNAL = root / "external" / "bcnt_codes_external.csv"

        SIDO_CANON = {
            "강원도": "강원도", "강원특별자치도": "강원도",
            "전라북도": "전라북도", "전북특별자치도": "전라북도",
            "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
            "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
        }


        def canon(s):
            return SIDO_CANON.get(s, s) if isinstance(s, str) else s


        def _norm_name(s):
            return s.replace(" ", "") if isinstance(s, str) else s


        def main():
            keys = pd.read_csv(DATA / "mois_region_keys.csv")
            print(f"MOIS region keys: {len(keys):,} rows")

            # In-house lookup
            inhouse = pd.read_csv(DATA / "mois_bcnt_codes_inhouse.csv", dtype={"bcnt_code": str})
            print(f"In-house BCNT lookup: {len(inhouse):,} rows")

            # Optional external override
            if EXTERNAL.exists():
                ext = pd.read_csv(EXTERNAL, dtype={"code": str})
                ext = ext.rename(columns={"code": "bcnt_code"})
                ext["level"] = ext["eupmyeondong"].fillna("").apply(
                    lambda x: "eupmyeondong" if x else "sigungu"
                )
                for c in ("sido", "sigungu", "eupmyeondong"):
                    if c not in ext.columns:
                        ext[c] = ""
                # Combine: external first (precedence), then in-house
                merged_lookup = pd.concat(
                    [ext[["bcnt_code", "level", "sido", "sigungu", "eupmyeondong"]], inhouse],
                    ignore_index=True,
                ).drop_duplicates(subset=["level", "sido", "sigungu", "eupmyeondong"],
                                  keep="first")
                print(f"  (using external override: +{len(ext):,} external rows)")
            else:
                merged_lookup = inhouse

            # Normalize for join
            for d in (keys, merged_lookup):
                d["sido_canon"] = d["sido"].map(canon)
                d["sigungu_norm"] = d["sigungu"].fillna("").map(_norm_name)
                d["eupmyeondong_norm"] = d.get("eupmyeondong", "").fillna("").map(_norm_name)

            # Merge by level
            out_parts = []
            for level in ("sido", "sigungu", "eupmyeondong"):
                kk = keys[keys["level"] == level].copy()
                ll = merged_lookup[merged_lookup["level"] == level].copy()
                if level == "sido":
                    join_cols = ["sido_canon"]
                elif level == "sigungu":
                    join_cols = ["sido_canon", "sigungu_norm"]
                else:
                    join_cols = ["sido_canon", "sigungu_norm", "eupmyeondong_norm"]
                merged = kk.merge(ll[join_cols + ["bcnt_code"]], on=join_cols, how="left")
                n_match = merged["bcnt_code"].notna().sum()
                print(f"  {level}: {n_match:,}/{len(merged):,} ({n_match/len(merged)*100:.1f}%) matched")
                out_parts.append(merged)

            out = pd.concat(out_parts, ignore_index=True)
            out = out.drop(columns=["sido_canon", "sigungu_norm", "eupmyeondong_norm"])
            out.to_csv(DATA / "mois_region_keys_with_bcnt.csv",
                        index=False, encoding="utf-8-sig")
            print(f"\nWrote {DATA / 'mois_region_keys_with_bcnt.csv'}")

            # Spot-check unmatched
            unmatched = out[out["bcnt_code"].isna()]
            if len(unmatched):
                print(f"\nUnmatched: {len(unmatched):,} rows. Examples:")
                print(unmatched[["level", "sido", "sigungu", "eupmyeondong"]].head(15).to_string(index=False))

        main()



    def validate_against_moj():
        """Cross-validate MOIS 한국국적미취득자 against MOJ 등록외국인 at 시군구 level.

        Definitions:
        - MOJ = "등록외국인" (registered foreign nationals per 출입국통계연보, KIRD core).
        - MOIS 한국국적미취득_소계 = "한국국적을 가지지 않은 자" = roughly equivalent to MOJ
          registered foreigners, but counted via local government registries (resident
          registration), not immigration registries.

        The two should be CLOSE but not identical — they differ in:
        - short-term visitors / unregistered (MOJ has, MOIS does not)
        - residential vs immigration registration timing
        - different reference dates (MOJ: Dec 31; MOIS: Nov 1 since 2015)

        Output:
        - 03_cleaned_data/mois_moj_validation.csv: year, sido, sigungu, moj_n, mois_n, diff, pct_diff
        - console summary: median pct diff per year, top 20 districts with largest gap
        """
        HERE = os.path.dirname(os.path.abspath(__file__))
        DATA = os.path.join(ROOT, "03_cleaned_data")
        SITE = os.path.join(ROOT, "05_dashboard", "data")

        # Canonicalize sido names — KIRD (MOJ) uses old names; MOIS uses new specialty names from 2023+.
        SIDO_CANON = {
            "강원도": "강원도",
            "강원특별자치도": "강원도",
            "전라북도": "전라북도",
            "전북특별자치도": "전라북도",
            "제주도": "제주특별자치도",
            "제주특별자치도": "제주특별자치도",
            "세종시": "세종특별자치시",
            "세종특별자치시": "세종특별자치시",
        }


        def canon(s):
            return SIDO_CANON.get(s, s)


        def main():
            # ---- Load MOJ region.json ----
            with open(os.path.join(SITE, "region.json"), encoding="utf-8") as f:
                region = json.load(f)["by_sigungu"]

            moj_rows = []
            AGG = {"총계", "계", "소계", "총합계"}
            for year, sidos in region.items():
                for sido, sigungus in sidos.items():
                    for sigungu, countries in sigungus.items():
                        if sigungu in AGG:
                            continue
                        total = sum(v for k, v in countries.items() if k not in AGG)
                        moj_rows.append({"year": int(year), "sido": canon(sido),
                                         "sigungu": sigungu, "moj_n": total})
            moj = pd.DataFrame(moj_rows)
            print(f"MOJ rows: {len(moj):,}, years {moj['year'].min()}–{moj['year'].max()}")

            # ---- Load MOIS 시군구 한국국적미취득 ----
            mois = pd.read_csv(os.path.join(DATA, "mois_population.csv"))
            mois_nat = mois.query(
                "level == 'sigungu' and category == '한국국적미취득_소계' and sex == 'total'"
            )[["year", "sido", "sigungu", "n"]].rename(columns={"n": "mois_n"})
            mois_nat["sido"] = mois_nat["sido"].map(canon)
            print(f"MOIS rows: {len(mois_nat):,}, years {mois_nat['year'].min()}–{mois_nat['year'].max()}")

            # ---- Merge ----
            merged = moj.merge(mois_nat, on=["year", "sido", "sigungu"], how="outer")
            merged["diff"] = merged["mois_n"] - merged["moj_n"]
            merged["pct_diff"] = (merged["diff"] / merged["moj_n"] * 100).round(2)
            print(f"Merged: {len(merged):,} rows.  matched: {merged.dropna(subset=['moj_n','mois_n']).shape[0]:,}")

            merged = merged.sort_values(["year", "sido", "sigungu"])
            merged.to_csv(os.path.join(DATA, "mois_moj_validation.csv"),
                          index=False, encoding="utf-8-sig")

            # ---- Summary ----
            print("\n=== Summary ===")
            print("Median pct_diff (MOIS vs MOJ) by year — MOIS counts as % above/below MOJ:")
            by_yr = merged.dropna(subset=["pct_diff"]).groupby("year")["pct_diff"].describe()[
                ["count", "mean", "50%", "min", "max"]
            ]
            print(by_yr.round(2).to_string())

            # ---- Unmatched rows ----
            only_moj = merged[merged["mois_n"].isna()][["year", "sido", "sigungu"]]
            only_mois = merged[merged["moj_n"].isna()][["year", "sido", "sigungu"]]
            print(f"\nOnly in MOJ (no MOIS match): {len(only_moj):,} district-years")
            if len(only_moj):
                print(only_moj.head(10).to_string(index=False))
            print(f"\nOnly in MOIS (no MOJ match): {len(only_mois):,} district-years")
            if len(only_mois):
                print(only_mois.head(10).to_string(index=False))

            # ---- Top 20 largest gaps for latest year ----
            last_yr = int(merged["year"].max())
            big = merged[(merged["year"] == last_yr) & merged["moj_n"].notna() &
                          merged["mois_n"].notna()].copy()
            big["abs_diff"] = big["diff"].abs()
            print(f"\nTop 15 largest absolute gaps in {last_yr}:")
            print(big.nlargest(15, "abs_diff")[["sido", "sigungu", "moj_n", "mois_n", "diff", "pct_diff"]].to_string(index=False))

        main()

    build_region_keys()
    attach_bcnt_codes()
    validate_against_moj()



def build_layer():
    """Build the MOIS sibling layer for the KIRD dashboard.

    Reads from 03_cleaned_data/mois_*.csv (already generated by scripts_mois/),
    writes JSON files to site/data/mois/ with shapes compatible with the existing
    dashboard's loaders.

    This is the orchestrator. Two upstream scripts are dependencies:
    - scripts/mois_validate_against_moj.py   (validation report)
    - scripts/mois_eupmyeondong_indices.py   (read-only; writes its own indices JSON)

    Output files:
      site/data/mois/sigungu_population.json
      site/data/mois/eupmyeondong_population.json
      site/data/mois/sigungu_nationality.json
      site/data/mois/eupmyeondong_nationality.json   (2014-2015 only)
      site/data/mois/children_age_sigungu.json
      site/data/mois/residence_period_sigungu.json
      site/data/mois/multicultural_eupmyeondong.json
      site/data/mois/summary.json
      site/data/mois/manifest.json    (lists all available datasets + years)

    Shape convention (matches KIRD's region.json pattern):
      by_sigungu: { year: { sido: { sigungu: { key: value, ... }, ... }, ... }, ... }
      by_eupmyeondong: { year: { sido: { sigungu: { eupmyeondong: {...} } } } }
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    DATA = os.path.join(ROOT, "03_cleaned_data")
    SITE = os.path.join(ROOT, "05_dashboard", "data", "mois")
    os.makedirs(SITE, exist_ok=True)

    SIDO_CANON = {
        "강원도": "강원도", "강원특별자치도": "강원도",
        "전라북도": "전라북도", "전북특별자치도": "전라북도",
        "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
        "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    }


    def canon(s):
        return SIDO_CANON.get(s, s)


    def nested():
        return defaultdict(nested)


    def to_dict(d):
        if isinstance(d, defaultdict):
            d = {k: to_dict(v) for k, v in d.items()}
        return d


    def _dump(path, obj):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  wrote {os.path.basename(path)}  ({os.path.getsize(path)/1024:.1f} KB)")


    def _load_population():
        return pd.read_csv(os.path.join(DATA, "mois_population.csv"))


    def _load_nationality():
        return pd.read_csv(os.path.join(DATA, "mois_nationality.csv"))


    def build_sigungu_population():
        raw = _load_population()
        df = raw[(raw["level"] == "sigungu") & (raw["sex"] == "total")].copy()
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.category] = int(r.n)
        # 세종특별자치시: the source labels its city row 세종특별자치시, so the parsers
        # emit it at sido level only and no sigungu row exists. Copy the published sido
        # row in as 세종시 (the city IS the province). Do NOT sum its eup/myeon/dong
        # instead — that drops the masked (***) cells and undercounts the components.
        sj = raw[(raw["level"] == "sido") & (raw["sex"] == "total")
                 & (raw["sido"].map(canon) == "세종특별자치시")]
        for _, r in sj.iterrows():
            nest[int(r.year)]["세종특별자치시"]["세종시"].setdefault(r.category, int(r.n))
        # Merge in 주민등록인구 from mois_total_pop.csv if available
        tp_path = os.path.join(DATA, "mois_total_pop.csv")
        if os.path.exists(tp_path):
            tp = pd.read_csv(tp_path)
            tp = tp[tp["level"] == "sigungu"].copy()
            tp["sido"] = tp["sido"].map(canon)
            for _, r in tp.iterrows():
                nest[int(r.year)][r.sido][r.sigungu]["주민등록인구"] = int(r.total_pop)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "sigungu_population.json"), out)


    def build_eupmyeondong_population():
        df = _load_population()
        df = df[(df["level"] == "eupmyeondong")]
        df = df[df["sex"].isna() | (df["sex"] == "total")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong][r.category] = int(r.n)
        # Merge in 주민등록인구 (total_pop) as additional category if available
        tp_path = os.path.join(DATA, "mois_total_pop.csv")
        if os.path.exists(tp_path):
            tp = pd.read_csv(tp_path)
            tp = tp[tp["level"] == "eupmyeondong"].copy()
            tp["sido"] = tp["sido"].map(canon)
            for _, r in tp.iterrows():
                nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong]["주민등록인구"] = int(r.total_pop)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_eupmyeondong": to_dict(nest)}
        _dump(os.path.join(SITE, "eupmyeondong_population.json"), out)


    def build_sigungu_nationality():
        df = _load_nationality()
        df = df[(df["level"] == "sigungu") & (df["sex"] == "total") &
                (df["group"] == "all_foreign")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.country] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "sigungu_nationality.json"), out)


    def build_eupmyeondong_nationality():
        df = _load_nationality()
        df = df[(df["level"] == "eupmyeondong") & (df["sex"] == "total") &
                (df["group"] == "all_foreign")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong][r.country] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_eupmyeondong": to_dict(nest)}
        _dump(os.path.join(SITE, "eupmyeondong_nationality.json"), out)


    def build_children_age_sigungu():
        df = pd.read_csv(os.path.join(DATA, "mois_children_age.csv"))
        df = df[(df["level"] == "sigungu") & (df["sex"] == "total")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][str(int(r.age))] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "children_age_sigungu.json"), out)


    def build_residence_period_sigungu():
        df = pd.read_csv(os.path.join(DATA, "mois_immigration_dynamics.csv"))
        df = df[(df["dimension"] == "residence_period") & (df["sex"] == "total")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.dim_value] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "residence_period_sigungu.json"), out)


    def build_multicultural_eupmyeondong():
        df = pd.read_csv(os.path.join(DATA, "mois_multicultural.csv"))
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong][r.category] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_eupmyeondong": to_dict(nest)}
        _dump(os.path.join(SITE, "multicultural_eupmyeondong.json"), out)


    def build_summary():
        """Top-line annual summary for landing-page use. Sums 시도-level data."""
        pop = _load_population()
        sido = pop[(pop["level"] == "sido") & (pop["sex"] == "total") &
                    (pop["category"] == "합계")].copy()
        sido["sido"] = sido["sido"].map(canon)
        by_year_national = sido.groupby("year")["n"].sum().astype(int).to_dict()

        breakdown_cats = ["한국국적미취득_소계", "한국국적취득자", "외국인주민자녀"]
        s2 = pop[(pop["level"] == "sido") & (pop["sex"] == "total") &
                  (pop["category"].isin(breakdown_cats))].copy()
        s2["sido"] = s2["sido"].map(canon)
        breakdown = (s2.groupby(["year", "category"])["n"].sum().unstack()
                       .fillna(0).astype(int))

        out = {
            "national_total_by_year": {int(k): int(v) for k, v in by_year_national.items()},
            "breakdown_by_year": {
                int(y): breakdown.loc[y].to_dict() for y in breakdown.index
            },
        }
        _dump(os.path.join(SITE, "summary.json"), out)


    def build_manifest():
        files = sorted(os.listdir(SITE))
        manifest = {
            "datasets": [],
            "source": "행정안전부 「지방자치단체 외국인주민 현황」 (Ministry of the Interior and Safety)",
            "note": "MOIS broad-definition 외국인주민 (외국인 + 한국국적 취득자 + 외국인주민 자녀). NOT directly comparable to MOJ 등록외국인. See mois_moj_validation.csv for cross-source comparison.",
        }
        for f in files:
            if f == "manifest.json" or not f.endswith(".json"):
                continue
            path = os.path.join(SITE, f)
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            manifest["datasets"].append({
                "file": f,
                "size_kb": round(os.path.getsize(path) / 1024, 1),
                "years": d.get("years") if isinstance(d, dict) else None,
            })
        _dump(os.path.join(SITE, "manifest.json"), manifest)


    def main():
        print("Building MOIS sibling layer for KIRD dashboard…\n")
        build_sigungu_population()
        build_eupmyeondong_population()
        build_sigungu_nationality()
        build_eupmyeondong_nationality()
        build_children_age_sigungu()
        build_residence_period_sigungu()
        build_multicultural_eupmyeondong()
        build_summary()
        build_manifest()
        print(f"\nAll JSON files in {SITE}")

    main()



def sejong_patches():
    """세종특별자치시 patches on the MOIS layer.

    Sejong is a self-governing city with no districts below it, so the MOIS parsers
    skip it wherever they key on 시군구, and MOIS lists Sejong only from 2013. Three
    patches put it back, and they have to run in this order because the first two
    both write `children_age_sigungu.json`:

      1. 연기군 backfill. Sejong was created 2012-07-01, mostly out of 연기군 plus
         parts of 공주시 and 청원군. 2006-2012 sigungu_population and 2011-2012
         children_age are copied from 연기군, and the real 2013 Sejong row is pulled
         off the province sheet, where it had been filed for want of a district.
         연기군 stays under 충청남도, which is the historical fact; only the Sejong
         copy is added. The sub-district and multicultural layers start in 2014 and
         2016, so there is no 연기군 predecessor to backfill them from.
      2. Sub-districts. Sejong's 읍면동 rows, extracted with the same parsers and
         injected into `eupmyeondong_population.json`.
      3. Children by age and multicultural households, same treatment.

    No other province is touched by any of the three.
    """
    sys.path.insert(0, os.path.join(ROOT, "02_code", "scripts_mois"))
    import parse_2014_2015  # noqa: E402
    import parse_2016plus as P16  # noqa: E402
    import parse_children_age as PCA  # noqa: E402
    from mois_common import RAW_DIR  # noqa: E402
    from parse_2014_2015 import _parse_sigungu_or_sido_sheet  # noqa: E402

    MOIS = os.path.join(ROOT, "05_dashboard", "data", "mois")
    SP = os.path.join(MOIS, "sigungu_population.json")
    CA = os.path.join(MOIS, "children_age_sigungu.json")
    EMD = os.path.join(MOIS, "eupmyeondong_population.json")
    MC = os.path.join(MOIS, "multicultural_eupmyeondong.json")


    def load(p):
        return json.load(open(p, encoding="utf-8"))


    def save(obj, p):
        json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


    def backfill_from_yeongi():
        print("1) 연기군 -> 세종 backfill")
        sp = load(SP)
        BY = sp["by_sigungu"]
        n_bf = 0
        for y in [str(x) for x in range(2006, 2013)]:
            yg = (BY.get(y, {}).get("충청남도", {}) or {}).get("연기군")
            if yg is None:
                continue
            BY[y].setdefault("세종특별자치시", {})["세종시"] = dict(yg)
            n_bf += 1
        # the real 2013 Sejong, off the province sheet
        rows = _parse_sigungu_or_sido_sheet(RAW_DIR / "2013_외국인주민통계.xlsx", 2013,
                                            "1.조사총괄표(시도)", level="sido")
        rec13 = {r["category"]: r["n"] for r in rows
                 if r.get("sido") == "세종특별자치시" and r.get("sex") == "total"}
        # the province sheet carries only the total; the district sheet's col1
        # (주민등록인구) is 113,117
        rec13.setdefault("주민등록인구", 113117)
        if "세종특별자치시" not in BY.get("2013", {}) and rec13.get("합계"):
            BY.setdefault("2013", {}).setdefault("세종특별자치시", {})["세종시"] = rec13
            print("   sigungu_population 2013 세종:", rec13.get("합계"))
        print(f"   sigungu_population backfilled {n_bf} years (2006-2012)")
        save(sp, SP)

        ca = load(CA)
        CBY = ca["by_sigungu"]
        n_ca = 0
        for y in ["2011", "2012"]:
            yg = (CBY.get(y, {}).get("충청남도", {}) or {}).get("연기군")
            if yg is None:
                continue
            CBY[y].setdefault("세종특별자치시", {})["세종시"] = dict(yg)
            n_ca += 1
        print(f"   children_age backfilled {n_ca} years (2011-2012)")
        save(ca, CA)


    def inject_eupmyeondong():
        print("2) 세종 읍면동 -> eupmyeondong_population.json")
        def collect(rows):
            out = {}
            for r in rows:
                if r.get("sido") != "세종특별자치시":
                    continue
                d = out.setdefault(r["eupmyeondong"], {})
                d[r["category"]] = d.get(r["category"], 0) + r["n"]
            return out

        by_year = {}
        for y in range(2016, 2026):
            # MOIS publishes later than MOJ, so the newest years have no source file
            try:
                by_year[y] = collect(P16.parse_year(y).get("eupmyeondong", []))
            except FileNotFoundError:
                print(f"   skip {y}: no MOIS source file yet")
        by_year[2014] = collect(parse_2014_2015.parse_2014().get("eupmyeondong", []))
        by_year[2015] = collect(parse_2014_2015.parse_2015().get("eupmyeondong", []))

        j = load(EMD)
        emd = j["by_eupmyeondong"]
        added = 0
        for y, dongs in by_year.items():
            yk = str(y)
            if yk not in emd or not dongs:
                if dongs:
                    print(f"   ! year {yk} not in JSON, skipping {len(dongs)} 세종 dongs")
                continue
            emd[yk].setdefault("세종특별자치시", {})["세종시"] = {
                d: {k: v for k, v in vals.items()} for d, vals in dongs.items()}
            added += len(dongs)
            print(f"   {yk}: 세종 {len(dongs)} dongs")
        save(j, EMD)
        print(f"   total dong-years injected: {added}")


    def inject_children_and_multicultural():
        print("3) 세종 children_age + multicultural")
        ca = load(CA)
        ca_added = 0
        for y, info in PCA.AGE_SHEETS.items():
            yk = str(y)
            if yk not in ca["by_sigungu"]:
                continue
            fname, sido_sheet, sg = info
            if isinstance(sg, tuple):
                path, sheet = PCA.RAW_DIR / sg[0], sg[1]
            else:
                path, sheet = PCA.RAW_DIR / fname, sg
            if not sheet:
                continue
            try:
                rows = PCA._parse_age_sheet(path, y, sheet, emit_levels=("sigungu",))
            except Exception as e:
                print(f"   WARN children_age {yk}: {e}")
                continue
            ages = {}
            for r in rows:
                if r["sido"] != "세종특별자치시" or r.get("sex") != "total":
                    continue
                ages[r["age"]] = max(ages.get(r["age"], 0), r["n"])  # duplicate rows: keep the max
            if ages:
                ca["by_sigungu"][yk].setdefault("세종특별자치시", {})["세종시"] = ages
                ca_added += 1
                print(f"   children_age {yk}: 세종 {len(ages)} ages")
        save(ca, CA)

        mc = load(MC)
        mc_added = 0
        for y in range(2016, 2026):
            yk = str(y)
            if yk not in mc["by_eupmyeondong"]:
                continue
            try:
                rows = P16.parse_year(y).get("multicultural", [])
            except Exception as e:
                print(f"   WARN multicultural {yk}: {e}")
                continue
            dongs = {}
            for r in rows:
                if r["sido"] != "세종특별자치시":
                    continue
                dongs.setdefault(r["eupmyeondong"], {})[r["category"]] = r["n"]
            if dongs:
                mc["by_eupmyeondong"][yk].setdefault("세종특별자치시", {})["세종시"] = dongs
                mc_added += 1
                print(f"   multicultural {yk}: 세종 {len(dongs)} dongs")
        save(mc, MC)
        print(f"   children_age years +{ca_added}, multicultural years +{mc_added}")

    backfill_from_yeongi()
    inject_eupmyeondong()
    inject_children_and_multicultural()
    print("done.")



def package_for_release():
    """The MOIS layer packaged for release, as CSV and as Parquet.

    The CSVs stay in 03_cleaned_data for anyone loading them with pandas; the
    release folder also carries Parquet, which is around a tenth of the size and
    faster to read column-wise. The MOIS layer is released beside the KIRD core
    rather than inside it, because it counts a different population.
    """
    def package_release():
        """Package the MOIS layer as a separate `04_dataset_release/mois/` for public release
        (parallel to KIRD core; separate Zenodo DOI recommended due to definition gap).
        """
        root = Path(ROOT)
        DATA = root / "03_cleaned_data"
        OUT = root / "04_dataset_release" / "mois"
        OUT_DATA = OUT / "data"

        TIDY_FILES = [
            "mois_population.csv",
            "mois_nationality.csv",
            "mois_children_age.csv",
            "mois_children_parent.csv",
            "mois_multicultural.csv",
            "mois_immigration_dynamics.csv",
            "mois_eupmyeondong_indices.csv",
            "mois_eupmyeondong_enclaves.csv",
            "mois_region_keys.csv",
            "mois_moj_validation.csv",
            "mois_coverage.csv",
        ]


        def copy_data():
            OUT_DATA.mkdir(parents=True, exist_ok=True)
            for fn in TIDY_FILES:
                src = DATA / fn
                if not src.exists():
                    print(f"  MISSING: {fn}")
                    continue
                shutil.copy2(src, OUT_DATA / fn)
                size_kb = (OUT_DATA / fn).stat().st_size / 1024
                print(f"  copied {fn:<45s} ({size_kb:.1f} KB)")


        README_MD = """# KIRD-MOIS: Korean Foreign Resident Statistics (행정안전부 외국인주민통계) Tidy Dataset, 2006-2024

A long-format, analyst-ready re-release of the 행정안전부 「지방자치단체 외국인주민 현황」
(MOIS Foreign Resident Statistics) covering 2006-2024 at the sub-district level.

**This is a sibling layer to the KIRD core dataset** (which is built on Ministry
of Justice 출입국통계연보). The two should NOT be merged: MOJ counts registered
foreign nationals only; MOIS counts the broader 외국인주민 population which also
includes naturalized Koreans and their domestically-born children.

- **DOI:** TBD (separate Zenodo release recommended)
- **Source:** Ministry of the Interior and Safety (MOIS) annual 외국인주민 현황 surveys
- **Population definition:** 외국인주민 = 한국국적 미취득자 (foreign nationals) +
  한국국적 취득자 (naturalized) + 외국인주민 자녀 (children born to immigrant parents)

## Files (data/)

| File | Unit | Years | Rows |
|---|---|---|---|
| `mois_population.csv` | year × level × region × category × sex | 2006-2024 | 710K |
| `mois_nationality.csv` | year × level × region × group × country × sex | 2009-2024 | 4.1M |
| `mois_children_age.csv` | year × level × region × age × sex | 2011-2024 | 200K |
| `mois_children_parent.csv` | year × level × region × parent_type × country × sex | 2009-2024 | 1.0M |
| `mois_multicultural.csv` | year × eupmyeondong × multicultural-household role | 2016-2024 | 298K |
| `mois_immigration_dynamics.csv` | year × sigungu × dimension × dim_value × sex | 2016-2024 | 47K |
| `mois_eupmyeondong_indices.csv` | year × eupmyeondong diversity indices | 2014-2015 | 7K |
| `mois_eupmyeondong_enclaves.csv` | enclave (LQ≥2, share≥30%, n≥30) tuples | 2014-2015 | 1.5K |
| `mois_region_keys.csv` | unique region keys with first/last year seen | — | 5.5K |
| `mois_moj_validation.csv` | per-district MOJ vs MOIS comparison | 2008-2024 | 4.5K |
| `mois_coverage.csv` | per-year/level/category coverage matrix | — | 49 |

## Long-format schema

All files share the same conventions:
- `year` (int): reference year
- `level` (str): `sido` / `sigungu` / `eupmyeondong`
- `sido` (str): province (canonicalized; 강원특별자치도 → 강원도, 전북특별자치도 → 전라북도,
  제주도 → 제주특별자치도, 세종시 → 세종특별자치시)
- `sigungu` (str): municipality (blank for sido-level rows; 100만-도시 sub-구s are
  rendered as `수원시 장안구` etc. with a space)
- `eupmyeondong` (str): sub-district (blank for higher levels)
- `category` / `country` / `age` / `dim_value` / `parent_type` (varies by file): the
  pivot dimension
- `sex` (str): `total` / `M` / `F`
- `n` (int): count (suppressed `*` values become missing rows, not zeros)

## Six dimensions captured by MOIS that MOJ does not

1. **한국국적취득자 (naturalized Koreans)** at sigungu level, 2006-2024 — MOJ stops
   tracking foreign nationals at naturalization.
2. **외국인주민 자녀 (children of foreign residents)**, by age 0-18, 2011-2024 —
   2nd-generation immigrant population.
3. **Parent type (외국인부모 / 외-한국인부모 / 한국인부모)** — composition of mixed-status
   households.
4. **Sub-district (읍면동) granularity, 2014-2015** — district-below-sigungu detail
   not available in MOJ data.
5. **다문화가구 (multicultural-household members)** by role (한국인배우자, 결혼이민자,
   귀화자, 자녀 등) at the eupmyeondong level, 2016-2024.
6. **귀화자 이전국적 (previous nationality of naturalized Koreans)** at sigungu, 2016-2024.

## Known limitations

- 2016 methodology change: MOIS shifted to a 인구주택총조사 (Population & Housing
  Census) basis, capturing ~30-45% more 한국국적미취득자 than MOJ counts. See
  `mois_moj_validation.csv` for per-district divergence.
- 2008 sigungu-level MOIS data is unavailable in our parse window (sigungu series
  starts 2009).
- 5,226 unique eupmyeondong names; no official BCNT 5-digit administrative codes
  are attached (KIRD geometry joins require external lookup).
- "기타" continent residuals are not disambiguated in `mois_nationality.csv` —
  multiple "기타" sub-categories from different continents lump together.

## Reproducing this dataset

Build from raw Excel yearbooks in `01_raw_data/행정안전부 외국인주민통계/`:

```bash
python scripts_mois/run_all.py        # raw → 03_cleaned_data/mois_*.csv
python scripts/build_mois_04_dataset_release.py   # copy → 04_dataset_release/mois/
```

The full pipeline is described in `scripts_mois/README.md`.

## Citation

```
Yoo, N. (2026). KIRD-MOIS: Korean Foreign Resident Statistics Tidy Dataset, 2006-2024
[Data set]. Zenodo. https://doi.org/[TBD]
```

## License

CC BY 4.0 (matching KIRD core). Underlying data is published by the Korean
Ministry of the Interior and Safety as open public data.
"""


        CITATION_CFF = """cff-version: 1.2.0
title: "KIRD-MOIS: Korean Foreign Resident Statistics Tidy Dataset, 2006-2024"
message: "If you use this dataset, please cite it as below."
type: dataset
authors:
  - family-names: Yoo
    given-names: Nari
    orcid: "https://orcid.org/0000-0002-9020-8061"
    affiliation: "University of Michigan School of Social Work"
date-released: 2026
repository-code: "https://github.com/nariyoo/kird-korea-immigration"
keywords:
  - immigration
  - foreign residents
  - Korea
  - 외국인주민
  - diversity
  - residential segregation
  - sub-district
  - eupmyeondong
license: CC-BY-4.0
"""


        def write_metadata():
            (OUT / "README.md").write_text(README_MD, encoding="utf-8")
            (OUT / "CITATION.cff").write_text(CITATION_CFF, encoding="utf-8")
            # Copy LICENSE from KIRD core
            src_lic = root / "04_dataset_release" / "LICENSE"
            if src_lic.exists():
                shutil.copy2(src_lic, OUT / "LICENSE")
            print(f"  wrote README.md, CITATION.cff, LICENSE")


        def write_data_dictionary():
            """Long-format data dictionary."""
            import csv
            rows = [
                ("file", "variable", "type", "description"),
                ("(all files)", "year", "integer", "Reference year (2006-2024)"),
                ("(all files)", "level", "string", "Administrative level: sido / sigungu / eupmyeondong"),
                ("(all files)", "sido", "string", "Province name (canonicalized — 강원특별자치도→강원도, 전북특별자치도→전라북도, 제주도→제주특별자치도, 세종시→세종특별자치시)"),
                ("(all files)", "sigungu", "string", "Municipality (blank when level=sido). 100만-도시 sub-구s rendered as '수원시 장안구' etc."),
                ("(all files)", "eupmyeondong", "string", "Sub-district (blank when level≠eupmyeondong)"),
                ("(all files)", "sex", "string", "total / M / F. For rows without sex breakdown, total only."),
                ("(all files)", "n", "integer", "Count. Suppressed source values (*) are excluded as missing rows."),
                # population
                ("mois_population.csv", "category", "string", "합계 (total 외국인주민) / 한국국적미취득_소계 / 외국인근로자 / 결혼이민자 / 유학생 / 외국국적동포 / 기타외국인 / 한국국적취득자 / 혼인귀화자 / 기타귀화자 / 외국인주민자녀 / 자녀_외국인부모 / 자녀_외한국인부모 / 자녀_한국인부모 / 세대수"),
                # nationality
                ("mois_nationality.csv", "group", "string", "Subpopulation: all_foreign / workers / marriage / students / overseas_koreans / other_foreign / naturalized / children / naturalized_prev"),
                ("mois_nationality.csv", "country", "string", "Nationality (Korean label). '기타' may collapse different continent residuals."),
                # children
                ("mois_children_age.csv", "age", "integer", "Age 0-18 (years)"),
                ("mois_children_parent.csv", "parent_type", "string", "외국인부모 / 외-한국인부모 / 한국인부모 (2014-2015 읍면동); 귀화·인지및외국국적 / 국내출생 (2016+ 시군구)"),
                ("mois_children_parent.csv", "country", "string", "Country (only for 2014-2015 읍면동; blank for 2016+ 시군구)"),
                # multicultural
                ("mois_multicultural.csv", "category", "string", "Multicultural household role: 한국인배우자 / 결혼이민자 / 귀화자등 / 자녀_귀화인지외국국적 / 자녀_국내출생 / 기타동거인_내국인 / 기타동거인_외국인 / etc."),
                # immigration_dynamics
                ("mois_immigration_dynamics.csv", "dimension", "string", "residence_period (체류기간) or naturalization_period (국적취득경과기간)"),
                ("mois_immigration_dynamics.csv", "dim_value", "string", "Period label, e.g., '5년이상~10년미만', '10년이상'"),
                # indices
                ("mois_eupmyeondong_indices.csv", "shannon_h", "float", "Shannon entropy over country distribution within the eupmyeondong"),
                ("mois_eupmyeondong_indices.csv", "hhi", "float", "Herfindahl-Hirschman index on nationality shares"),
                ("mois_eupmyeondong_indices.csv", "pielou_evenness", "float", "Pielou's evenness = H / ln(k), k = number of nonzero countries"),
                ("mois_eupmyeondong_indices.csv", "top_country_share", "float", "Share of the largest country in the eupmyeondong"),
                # enclaves
                ("mois_eupmyeondong_enclaves.csv", "lq", "float", "Location quotient: (district country share) / (national country share)"),
                ("mois_eupmyeondong_enclaves.csv", "local_share", "float", "Country's share within the eupmyeondong's foreign population (≥0.30 by criterion)"),
                # region_keys
                ("mois_region_keys.csv", "region_key", "string", "Stable join key: '{sido}|{sigungu}|{eupmyeondong}'"),
                ("mois_region_keys.csv", "first_year/last_year/n_years_seen", "integer", "Temporal coverage of the region across the MOIS series"),
                # validation
                ("mois_moj_validation.csv", "moj_n", "integer", "MOJ 등록외국인 count for the sigungu (from KIRD region.json sum)"),
                ("mois_moj_validation.csv", "mois_n", "integer", "MOIS 한국국적미취득_소계 count (from mois_population.csv)"),
                ("mois_moj_validation.csv", "diff/pct_diff", "float", "mois_n minus moj_n (raw and percentage)"),
            ]
            with (OUT / "data_dictionary.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerows(rows)
            print("  wrote data_dictionary.csv")


        def main():
            print(f"Packaging MOIS layer → {OUT}\n")
            OUT.mkdir(parents=True, exist_ok=True)
            copy_data()
            write_metadata()
            write_data_dictionary()
            print(f"\nDone. {OUT}")

        main()



    def write_parquet():
        """Convert large MOIS CSVs to Parquet for the 04_dataset_release/.

        CSV files stay in 03_cleaned_data/ for analyst friendliness (pandas-load-anywhere),
        but Parquet versions go to 04_dataset_release/mois/data/ for size reduction (~10x)
        and for users wanting faster columnar reads.
        """
        root = Path(ROOT)
        DATA = root / "03_cleaned_data"
        OUT_DATA = root / "04_dataset_release" / "mois" / "data"
        OUT_DATA.mkdir(parents=True, exist_ok=True)

        # All tidy thematic files — convert each
        FILES = [
            "mois_population.csv",
            "mois_nationality.csv",
            "mois_children_age.csv",
            "mois_children_parent.csv",
            "mois_multicultural.csv",
            "mois_immigration_dynamics.csv",
            "mois_eupmyeondong_indices.csv",
            "mois_eupmyeondong_enclaves.csv",
            "mois_moj_validation.csv",
            "mois_region_keys.csv",
            "mois_coverage.csv",
        ]


        def main():
            for fn in FILES:
                src = DATA / fn
                if not src.exists():
                    print(f"  MISSING: {fn}")
                    continue
                df = pd.read_csv(src, low_memory=False)
                # Cast known integer cols where possible to int32 for compression
                for col in ("year", "n"):
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")
                if "age" in df.columns:
                    df["age"] = pd.to_numeric(df["age"], errors="coerce").astype("Int8")
                out = OUT_DATA / (fn.replace(".csv", ".parquet"))
                df.to_parquet(out, engine="pyarrow", compression="zstd", index=False)
                csv_kb = src.stat().st_size / 1024
                pq_kb = out.stat().st_size / 1024
                ratio = csv_kb / pq_kb if pq_kb > 0 else 0
                print(f"  {fn:<42s}  csv {csv_kb:>9.1f} KB  →  parquet {pq_kb:>9.1f} KB  ({ratio:.1f}x)")

        main()

    package_release()
    write_parquet()


if __name__ == "__main__":
    canonicalize_eupmyeondong_names()
    region_keys_and_validation()
    build_layer()
    sejong_patches()
    package_for_release()
