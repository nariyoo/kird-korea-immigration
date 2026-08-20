"""Extract 주민등록인구 (total resident-registration population) at sido/sigungu/eupmyeondong level.

Source: the main MOIS sheet for each year typically has 주민등록인구 as col 1
(directly to the right of region name). This script extracts it as a parallel
denominator column so the dashboard can compute 외국인비율 = 외국인주민 / 주민등록인구.

Coverage:
- 시도 / 시군구: 2006-2024 (all years; col layout fixed)
- 읍면동: 2014-2015 only (2016+ 1-3 시트에 주민등록인구 컬럼 없음)

Output: 03_cleaned_data/mois_total_pop.csv
  Columns: year, level, sido, sigungu, eupmyeondong, total_pop
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

# Per-year file + sheet config: (filename, sheet_sido, sheet_sigungu, name_col, pop_col_sido, pop_col_sigungu, start_marker_after)
# pop_col = column index of 주민등록인구 in that sheet
YEAR_CONFIG = {
    2006: ("2006_외국인주민통계.xls", "시.도별", "전국", 0, 1, 1),
    2007: ("2007_외국인주민통계.xls", "1.조사총괄(시도)", "1.조사총괄(시군구)", 0, 1, 1),
    2008: ("2008_외국인주민통계.xls", "총괄(시도)", "총괄 (시군구)", 0, 1, 1),
    2009: ("2009_외국인주민통계.xls", "1.총괄표(시도)", "1.총괄표", 0, 1, 1),
    2010: ("2010_외국인주민통계.xls", "1.총괄표 (시도) ", "1.총괄표(시군구)", 0, 1, 1),
    2011: ("2011_외국인주민통계.xlsx", "1.총괄표(시도) ", "1.총괄표(시군구)", 0, 1, 1),
    2012: ("2012_외국인주민통계.xls", "1.조사총괄표(시도)", "1.조사총괄표(시군구)", 0, 1, 1),
    2013: ("2013_외국인주민통계.xlsx", "1.조사총괄표(시도)", "1.조사총괄표(시군구)", 0, 1, 1),
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "1-1. 총괄현황, 유형 및 지역별(시도)",
            "1-1.유형 및 지역별(시군구)", 0, 1, 1),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "1-1. 총괄현황, 유형 및 지역별(시도)",
            "1-1.유형 및 지역별(시군구)", 0, 1, 1),
    2016: ("2016_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시⋅도)",
            "1-2. 유형 및 지역별(시⋅군⋅구)", 0, 1, 1),
    2017: ("2017_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시⋅도)",
            "1-2. 유형 및 지역별(시⋅군⋅구)", 0, 1, 1),
    2018: ("2018_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시⋅도) ",
            "1-2. 유형 및 지역별(시⋅군⋅구) ", 0, 1, 1),
    2019: ("2019_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2020: ("2020_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2021: ("2021_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2022: ("2022_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2023: ("2023_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2024: ("2024_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
}

# 읍면동 only 2014-2015 (separate files). col layouts:
# 2014 읍면동 file 1-1: name at col 1 (English at col 2), 주민등록인구 at col 3
# 2015 읍면동 file 1-1: name at col 0 (English at col 1), 주민등록인구 at col 2
EUPMYEONDONG_CONFIG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "1-1. 유형 및 지역별(읍면동)", 1, 3),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "1-1. 유형 및 지역별 현황(읍면동)", 0, 2),
}


def _find_data_start(df: pd.DataFrame, name_col: int = 0) -> int:
    markers = {"합계", "합 계", "전국", "계"}
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s in markers:
                return i
    raise ValueError("data start not found")


def _parse_sheet_sigungu_or_sido(path: Path, sheet: str, *, level: str,
                                  name_col: int, pop_col: int) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start(df, name_col=name_col)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계", "전국", "계"):
            continue
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                tp = parse_value(df.iat[i, pop_col])
                if tp is not None:
                    rows.append({"level": "sido", "sido": current_sido,
                                  "sigungu": "", "eupmyeondong": "",
                                  "total_pop": tp})
            continue
        if level == "sigungu" and current_sido is not None:
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            tp = parse_value(df.iat[i, pop_col])
            if tp is not None:
                rows.append({"level": "sigungu", "sido": current_sido,
                              "sigungu": sigungu_name, "eupmyeondong": "",
                              "total_pop": tp})
    return rows


def _parse_sheet_eupmyeondong(path: Path, sheet: str, name_col: int, pop_col: int) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start(df, name_col=name_col)
    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계", "전국", "계"):
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
            if current_sido is None or current_sigungu is None:
                continue
            tp = parse_value(df.iat[i, pop_col])
            if tp is not None:
                rows.append({"level": "eupmyeondong", "sido": current_sido,
                              "sigungu": current_sigungu,
                              "eupmyeondong": strip_gu_prefix(name, current_sigungu),
                              "total_pop": tp})
    return rows


def main():
    all_rows = []
    for year, (fname, s_sido, s_sigungu, name_col, pop_sido, pop_sg) in YEAR_CONFIG.items():
        path = RAW_DIR / fname
        try:
            rs = _parse_sheet_sigungu_or_sido(path, s_sido, level="sido",
                                                name_col=name_col, pop_col=pop_sido)
            for r in rs: r["year"] = year
            all_rows.extend(rs)
            print(f"  {year} 시도: {len(rs)} rows")
        except Exception as e:
            print(f"  WARN {year} 시도: {e}")
        try:
            rg = _parse_sheet_sigungu_or_sido(path, s_sigungu, level="sigungu",
                                                name_col=name_col, pop_col=pop_sg)
            for r in rg: r["year"] = year
            all_rows.extend(rg)
            print(f"  {year} 시군구: {len(rg)} rows")
        except Exception as e:
            print(f"  WARN {year} 시군구: {e}")
    # 읍면동 (2014-2015)
    for year, (fname, sheet, name_col, pop_col) in EUPMYEONDONG_CONFIG.items():
        path = RAW_DIR / fname
        try:
            re_ = _parse_sheet_eupmyeondong(path, sheet, name_col, pop_col)
            for r in re_: r["year"] = year
            all_rows.extend(re_)
            print(f"  {year} 읍면동: {len(re_)} rows")
        except Exception as e:
            print(f"  WARN {year} 읍면동: {e}")

    df = pd.DataFrame(all_rows)
    df = df[["year", "level", "sido", "sigungu", "eupmyeondong", "total_pop"]]
    df = df.sort_values(["year", "level", "sido", "sigungu", "eupmyeondong"])
    out = OUT_DIR / "mois_total_pop.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nWrote {out}  ({len(df):,} rows)")


if __name__ == "__main__":
    main()
