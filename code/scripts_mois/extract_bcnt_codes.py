"""Extract 행정구역코드 (BCNT-style 7-digit codes) from in-house MOIS files.

Two source files include the codes directly (most other MOIS files do not):

1. 2015_외국인주민통계_유형지역별읍면동.xls
   Long tabular format with columns: 행정구역코드, 시도, 시군구, 행정동, [counts...]
   Provides codes for ~3,495 읍면동 + parent rows.

2. 2015_외국인주민통계_자녀시군구연령별.xlsx
   Long tabular format with: 지역코드, 년도, 시도, 시군구, [age columns...]
   Provides 7-digit codes for 시도 (NN00000), 시군구 (NNNN000), 전국 (0000000).

The 2015 codes are an internal bootstrap — they cover essentially all sigungu
and most eupmyeondong present in MOIS 2014-2024. Codes are administratively
stable (행정안전부 BCNT) for most regions year over year; only boundary changes
(e.g., 부천시 자치구 통합 2016) cause drift.

Output: 03_cleaned_data/mois_bcnt_codes_inhouse.csv with cols
    bcnt_code, level, sido, sigungu, eupmyeondong
"""
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from kird import ROOT as _ROOT  # noqa: E402
import os
from pathlib import Path
import pandas as pd

ROOT = Path(_ROOT)
RAW = ROOT / "01_raw_data" / "행정안전부 외국인주민통계"
OUT = ROOT / "03_cleaned_data" / "mois_bcnt_codes_inhouse.csv"

SIDO_CANON = {
    "강원도": "강원도", "강원특별자치도": "강원도",
    "전라북도": "전라북도", "전북특별자치도": "전라북도",
    "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
    "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
}


def canon(s):
    if s is None:
        return ""
    return SIDO_CANON.get(s, s)


def extract_from_eupmyeondong_file() -> pd.DataFrame:
    """Extract from 2015_외국인주민통계_유형지역별읍면동.xls."""
    f = RAW / "2015_외국인주민통계_유형지역별읍면동.xls"
    df = pd.read_excel(f, sheet_name="외국인주민", header=None)
    # row 0-1 = headers, row 2 = 전국 합계, row 3+ = 읍면동 rows
    rows = []
    for i in range(3, len(df)):
        code = df.iat[i, 0]
        sido = df.iat[i, 1]
        sigungu = df.iat[i, 2]
        eupmyeondong = df.iat[i, 3]
        if pd.isna(code):
            continue
        code = str(code).strip().zfill(7)
        if not code.isdigit() or len(code) != 7:
            continue
        rows.append({
            "bcnt_code": code,
            "level": "eupmyeondong",
            "sido": canon(sido) if pd.notna(sido) else "",
            "sigungu": str(sigungu).strip() if pd.notna(sigungu) else "",
            "eupmyeondong": str(eupmyeondong).strip() if pd.notna(eupmyeondong) else "",
        })
    return pd.DataFrame(rows)


def extract_from_children_file() -> pd.DataFrame:
    """Extract from 2015_외국인주민통계_자녀시군구연령별.xlsx — covers 시도/시군구."""
    f = RAW / "2015_외국인주민통계_자녀시군구연령별.xlsx"
    df = pd.read_excel(f, sheet_name=0, header=None)
    # Data starts at row 5 with 전국 (code 0000000)
    rows = []
    for i in range(5, len(df)):
        code = df.iat[i, 0]
        sido = df.iat[i, 2]
        sigungu = df.iat[i, 3]
        if pd.isna(code):
            continue
        code = str(code).strip().zfill(7)
        if not code.isdigit() or len(code) != 7:
            continue
        if code == "0000000":
            continue  # national row
        # Classify by code pattern
        if code.endswith("00000"):
            level = "sido"
            sido_name = canon(sido) if pd.notna(sido) else ""
            sigungu_name = ""
        elif code.endswith("000"):
            level = "sigungu"
            sido_name = canon(sido) if pd.notna(sido) else ""
            sigungu_name = str(sigungu).strip() if pd.notna(sigungu) else ""
        else:
            continue  # unexpected
        rows.append({
            "bcnt_code": code,
            "level": level,
            "sido": sido_name,
            "sigungu": sigungu_name,
            "eupmyeondong": "",
        })
    return pd.DataFrame(rows)


def main():
    emd_df = extract_from_eupmyeondong_file()
    print(f"From 유형지역별읍면동 file: {len(emd_df):,} rows")
    print(f"  unique 읍면동 codes: {emd_df['bcnt_code'].nunique():,}")

    sg_df = extract_from_children_file()
    print(f"From 자녀시군구연령별 file: {len(sg_df):,} rows")
    print(f"  level breakdown: {sg_df['level'].value_counts().to_dict()}")

    # Derive sigungu codes from eupmyeondong codes:
    # - 일반 시군구 (e.g., 종로구): first 4 digits + "000" (e.g., 1101000)
    # - sub-구 of 100만 도시 (e.g., 성남시 분당구): first 5 digits + "00"
    #   (e.g., 3102300 — 5번째 자리가 sub-구 식별자)
    derived_sigungu = []
    for _, r in emd_df.iterrows():
        sigungu = r["sigungu"]
        code = r["bcnt_code"]
        if isinstance(sigungu, str) and " " in sigungu:
            # sub-구 of 100만 도시 — preserve 5-digit prefix
            sg_code = code[:5] + "00"
        else:
            sg_code = code[:4] + "000"
        derived_sigungu.append({
            "bcnt_code": sg_code,
            "level": "sigungu",
            "sido": r["sido"],
            "sigungu": sigungu,
            "eupmyeondong": "",
        })
    derived_sigungu_df = pd.DataFrame(derived_sigungu).drop_duplicates(
        subset=["bcnt_code", "sido", "sigungu"]
    )
    print(f"Derived sigungu codes from eupmyeondong parents: {len(derived_sigungu_df):,}")

    # Additionally, derive PARENT 100만-도시 codes (e.g., 성남시 = 3102000) by
    # taking the first 4 digits + "000" of any sub-구 in that city.
    parent_si = []
    for _, r in emd_df.iterrows():
        sigungu = r["sigungu"]
        if isinstance(sigungu, str) and " " in sigungu:
            parent_name = sigungu.split(" ")[0]
            parent_code = r["bcnt_code"][:4] + "000"
            parent_si.append({
                "bcnt_code": parent_code,
                "level": "sigungu",
                "sido": r["sido"],
                "sigungu": parent_name,
                "eupmyeondong": "",
            })
    parent_si_df = pd.DataFrame(parent_si).drop_duplicates(
        subset=["bcnt_code", "sido", "sigungu"]
    )
    print(f"Derived parent 시 codes (100만 도시 with sub-구s): {len(parent_si_df):,}")
    derived_sigungu_df = pd.concat([derived_sigungu_df, parent_si_df], ignore_index=True)
    derived_sigungu_df = derived_sigungu_df.drop_duplicates(
        subset=["bcnt_code", "sido", "sigungu"])

    # Combine and dedupe (prefer children file for sigungu where overlap exists)
    full = pd.concat([sg_df, derived_sigungu_df, emd_df], ignore_index=True)
    full = full.drop_duplicates(subset=["bcnt_code", "level", "sido", "sigungu", "eupmyeondong"])

    # Build sido-only rows (NN00000)
    sido_codes = sg_df[sg_df["level"] == "sido"].copy()
    if sido_codes.empty:
        # derive from sigungu codes
        sido_pairs = full[full["level"] == "sigungu"][["bcnt_code", "sido"]].copy()
        sido_pairs["sido_code"] = sido_pairs["bcnt_code"].str[:2] + "00000"
        sido_pairs = sido_pairs.drop_duplicates(["sido_code", "sido"])
        sido_rows = pd.DataFrame({
            "bcnt_code": sido_pairs["sido_code"],
            "level": "sido",
            "sido": sido_pairs["sido"],
            "sigungu": "",
            "eupmyeondong": "",
        })
        full = pd.concat([full, sido_rows], ignore_index=True).drop_duplicates(
            subset=["bcnt_code", "level"])

    full = full.sort_values(["level", "sido", "sigungu", "eupmyeondong"])
    full.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\nWrote {OUT}")
    print(f"Total: {len(full):,} rows; levels: {full['level'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
