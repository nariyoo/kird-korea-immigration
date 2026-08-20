"""Parser for 2014-2015 외국인주민통계.

Files used:
- 2014_외국인주민통계_시도시군구.xlsx (sheets 1-1 시도, 1-1 시군구)
- 2014_외국인주민통계_읍면동.xlsx     (sheet 1-1 읍면동)
- 2015_외국인주민통계_시도시군구.xlsx
- 2015_외국인주민통계_읍면동.xlsx

These files use a richer category schema than 2016+ (한국국적취득자 split into
혼인귀화/기타사유, 외국인주민자녀 split by parent origin). We emit the same
canonical categories as 2016+ PLUS the extra subcategories.

The 2015_외국인주민통계_인구주택총조사기준.xlsx is NOT used by default — it
is an alternative methodology and would create double counting. We process it
into a separate CSV for documentation.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mois_common import (
    RAW_DIR, OUT_DIR, SIDO_NAMES, canon_sido, clean_region_name,
    fix_known_typos, split_sub_gu, strip_gu_prefix, parse_value, classify_row_name,
)

# Category column maps: each maps category → starting col (계/남/여 are col, col+1, col+2)
# Sheet 1-1 (시도, 시군구) column layout — data starts at row 6 (2014) or row 7 (2015).
CAT_COLS_SIDO_2014_2015 = {
    "합계": 3,
    "한국국적미취득_소계": 6,
    "외국인근로자": 9,
    "결혼이민자": 12,
    "유학생": 15,
    "외국국적동포": 18,
    "기타외국인": 21,
    "한국국적취득자": 24,           # = 한국국적취득_소계
    "혼인귀화자": 27,
    "기타귀화자": 30,
    "외국인주민자녀": 33,           # = 자녀_소계
    "자녀_외국인부모": 36,
    "자녀_외한국인부모": 39,
    "자녀_한국인부모": 42,
}
HOUSEHOLD_COL_SIDO_2014_2015 = 45  # 세대수 (single col, 계만)

# 2014 읍면동 file: shift right by 2 (col 0 = level marker, col 1 = name, col 2 = English)
CAT_COLS_EMD_2014 = {k: v + 2 for k, v in CAT_COLS_SIDO_2014_2015.items()}
HOUSEHOLD_COL_EMD_2014 = HOUSEHOLD_COL_SIDO_2014_2015 + 2

# 2015 읍면동 file: shift right by 1 (col 0 = name, col 1 = English)
CAT_COLS_EMD_2015 = {k: v + 1 for k, v in CAT_COLS_SIDO_2014_2015.items()}
HOUSEHOLD_COL_EMD_2015 = HOUSEHOLD_COL_SIDO_2014_2015 + 1


def _find_data_start_named(df: pd.DataFrame, name_col: int) -> int:
    """Find first data row by looking for '합계' (Grand Total)."""
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v)
            if s == "합계":
                return i
    raise ValueError("Could not find '합계' row")


def _parse_sigungu_or_sido_sheet(path: Path, year: int, sheet: str, *, level: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_named(df, name_col=0)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "합계":
            continue  # national total
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_region_categories(rows, df, i, year=year, sido=current_sido,
                                        sigungu=None, eupmyeondong=None,
                                        cat_cols=CAT_COLS_SIDO_2014_2015,
                                        household_col=HOUSEHOLD_COL_SIDO_2014_2015)
            continue
        if level == "sigungu":
            if current_sido is None:
                continue
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            _emit_region_categories(rows, df, i, year=year, sido=current_sido,
                                    sigungu=sigungu_name, eupmyeondong=None,
                                    cat_cols=CAT_COLS_SIDO_2014_2015,
                                    household_col=HOUSEHOLD_COL_SIDO_2014_2015)
    return rows


def _parse_eupmyeondong_sheet(path: Path, year: int, sheet: str,
                              name_col: int, cat_cols: dict, household_col: int) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_named(df, name_col=name_col)
    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "합계":
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            continue
        if kind == "eupmyeondong":
            if current_sido == "세종특별자치시" and current_sigungu is None:
                current_sigungu = "세종시"
            if current_sido is None or current_sigungu is None:
                continue
            _emit_region_categories(rows, df, i, year=year, sido=current_sido,
                                    sigungu=current_sigungu,
                                    eupmyeondong=strip_gu_prefix(name, current_sigungu),
                                    cat_cols=cat_cols, household_col=household_col)
    return rows


def _emit_region_categories(rows, df, i, *, year, sido, sigungu, eupmyeondong,
                            cat_cols, household_col):
    for cat, c in cat_cols.items():
        total = parse_value(df.iat[i, c])
        male = parse_value(df.iat[i, c + 1])
        female = parse_value(df.iat[i, c + 2])
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            if eupmyeondong is not None:
                row["eupmyeondong"] = eupmyeondong
            rows.append(row)
    # household count (single col, total only)
    hh = parse_value(df.iat[i, household_col])
    if hh is not None:
        row = {"year": year, "sido": sido, "category": "세대수", "sex": "total", "n": hh}
        if sigungu is not None:
            row["sigungu"] = sigungu
        if eupmyeondong is not None:
            row["eupmyeondong"] = eupmyeondong
        rows.append(row)


def parse_2014() -> dict[str, list[dict]]:
    p_main = RAW_DIR / "2014_외국인주민통계_시도시군구.xlsx"
    p_emd = RAW_DIR / "2014_외국인주민통계_읍면동.xlsx"
    return {
        "sido": _parse_sigungu_or_sido_sheet(p_main, 2014, "1-1. 총괄현황, 유형 및 지역별(시도)", level="sido"),
        "sigungu": _parse_sigungu_or_sido_sheet(p_main, 2014, "1-1.유형 및 지역별(시군구)", level="sigungu"),
        "eupmyeondong": _parse_eupmyeondong_sheet(
            p_emd, 2014, "1-1. 유형 및 지역별(읍면동)",
            name_col=1, cat_cols=CAT_COLS_EMD_2014, household_col=HOUSEHOLD_COL_EMD_2014,
        ),
    }


def parse_2015() -> dict[str, list[dict]]:
    p_main = RAW_DIR / "2015_외국인주민통계_시도시군구.xlsx"
    p_emd = RAW_DIR / "2015_외국인주민통계_읍면동.xlsx"
    return {
        "sido": _parse_sigungu_or_sido_sheet(p_main, 2015, "1-1. 총괄현황, 유형 및 지역별(시도)", level="sido"),
        "sigungu": _parse_sigungu_or_sido_sheet(p_main, 2015, "1-1.유형 및 지역별(시군구)", level="sigungu"),
        "eupmyeondong": _parse_eupmyeondong_sheet(
            p_emd, 2015, "1-1. 유형 및 지역별 현황(읍면동)",
            name_col=0, cat_cols=CAT_COLS_EMD_2015, household_col=HOUSEHOLD_COL_EMD_2015,
        ),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu, all_emd = [], [], []
    for fn in (parse_2014, parse_2015):
        result = fn()
        for k, v in result.items():
            print(f"  {fn.__name__}/{k}: {len(v)} rows")
        all_sido.extend(result["sido"])
        all_sigungu.extend(result["sigungu"])
        all_emd.extend(result["eupmyeondong"])
    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2014_2015.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2014_2015.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_emd).to_csv(OUT_DIR / "mois_eupmyeondong_2014_2015.csv", index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}  emd={len(all_emd):,}")


if __name__ == "__main__":
    main()
