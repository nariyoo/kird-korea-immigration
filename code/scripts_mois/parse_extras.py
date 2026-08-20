"""Extract remaining dimensions:

1. 자녀 × 부모유형 × 읍면동 (2014-2015) — from 읍면동 file sheets 4-2-가/나/다
2. 자녀 × 부모유형 × 시군구 (2016-2024) — from main file sheet 8-2
3. 체류기간별 × 시군구 (2016-2024) — sheet 3-2
4. 이전국적별 × 시군구 (2016-2024) — sheet 7-2 (귀화자 origin)
5. 국적취득 경과기간별 × 시군구 (2016-2024) — sheet 6-2
6. 외국인주민 세대수 × 읍면동 (2014-2015) — separate sheet "6.외국인주민세대수(읍면동)"
7. 결혼이민자 및 국적취득자 연령별 × 시군구/읍면동 (2014-2015)

For each, we save a long-format CSV with year, sido, sigungu, [eupmyeondong,] category, sex, n.
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
from parse_nationality import (
    _find_country_header_row, _build_country_col_map, _find_data_start,
    _emit_country_row, _parse_matrix_sheet,
)


# ---- 2014-2015 읍면동 parent-type sheets ----
CHILD_PARENT_EUPMYEONDONG = {
    2014: [
        ("외국인부모", "2014_외국인주민통계_읍면동.xlsx", "4-2. 유형별-가.외국인부모(읍면동)"),
        ("외-한국인부모", "2014_외국인주민통계_읍면동.xlsx", "4-2-나.외-한국인부모(읍면동)"),
        ("한국인부모", "2014_외국인주민통계_읍면동.xlsx", "4-2-다.한국인부모(읍면동)"),
    ],
    2015: [
        ("외국인부모", "2015_외국인주민통계_읍면동.xlsx", "4-2-가.유형별,외국인부모(읍면동)"),
        ("외-한국인부모", "2015_외국인주민통계_읍면동.xlsx", "4-2-나.외-한국인부모(읍면동)"),
        ("한국인부모", "2015_외국인주민통계_읍면동.xlsx", "4-2-다.한국인부모(읍면동)"),
    ],
}

# ---- 2016+ 부모유형별 시군구 (sheet 8-2) ----
CHILD_PARENT_TYPE_SHEETS_2016PLUS = {
    2016: "8-2. 유형별(시⋅군⋅구)",
    2017: "8-2. 유형별(시⋅군⋅구)",
    2018: "8-2. 유형별(시⋅군⋅구) ",
    2019: "8-2. 유형별(시⋅군⋅구) ",
    2020: "8-2. 유형별(시⋅군⋅구) ",
    2021: "8-2. 유형별(시⋅군⋅구) ",
    2022: "8-2. 유형별(시⋅군⋅구) ",
    2023: "8-2. 유형별(시⋅군⋅구) ",
    2024: "8-2. 유형별(시⋅군⋅구) ",
}

# ---- 2016+ 체류기간별 시군구 (sheet 3-2) ----
RESIDENCE_PERIOD_SHEETS = {
    2016: "3-2. 체류기간별(시⋅군⋅구)",
    2017: "3-2. 체류기간별(시⋅군⋅구)",
    2018: "3-2. 체류기간별(시⋅군⋅구) ",
    2019: "3-2. 체류기간별(시·군·구)",
    2020: "3-2. 체류기간별(시.군.구)",
    2021: "3-2. 체류기간별(시.군.구)",
    2022: "3-2. 체류기간별(시.군.구)",
    2023: "3-2. 체류기간별(시.군.구)",
    2024: "3-2. 체류기간별(시.군.구)",
}

# ---- 2016+ 이전국적별 시군구 (sheet 7-2) — 귀화자 origin ----
PREV_NATIONALITY_SHEETS = {
    2016: "7-2. 이전국적별(시⋅군⋅구)",
    2017: "7-2. 이전국적별(시⋅군⋅구)",
    2018: "7-2. 이전국적별(시⋅군⋅구) ",
    2019: "7-2. 이전국적별(시⋅군⋅구) ",
    2020: "7-2. 이전국적별(시⋅군⋅구) ",
    2021: "7-2. 이전국적별(시⋅군⋅구) ",
    2022: "7-2. 이전국적별(시⋅군⋅구) ",
    2023: "7-2. 이전국적별(시⋅군⋅구) ",
    2024: "7-2. 이전국적별(시⋅군⋅구) ",
}

# ---- 2016+ 국적취득 경과기간별 (sheet 6-2) ----
NATURALIZATION_PERIOD_SHEETS = {
    2016: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2017: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2018: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2019: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2020: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2021: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2022: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2023: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2024: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
}

# ---- 2014-2015 세대수 읍면동 ----
HOUSEHOLD_EUPMYEONDONG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "6.외국인주민세대수(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "6.외국인주민세대수(읍면동)"),
}

# ---- 2014-2015 비자유형 × 국적별 × 읍면동 ----
VISA_NATIONALITY_EUPMYEONDONG = {
    2014: [
        ("외국인근로자", "2014_외국인주민통계_읍면동.xlsx", "2-2. 유형별-가.외국인근로자(읍면동)"),
        ("결혼이민자", "2014_외국인주민통계_읍면동.xlsx", "2-2-나.결혼이민자(읍면동)"),
        ("유학생", "2014_외국인주민통계_읍면동.xlsx", "2-2-다.유학생(읍면동)"),
        ("외국국적동포", "2014_외국인주민통계_읍면동.xlsx", "2-2-라.외국국적동포(읍면동)"),
        ("기타외국인", "2014_외국인주민통계_읍면동.xlsx", "2-2-마.기타(읍면동)"),
    ],
    2015: [
        ("외국인근로자", "2015_외국인주민통계_읍면동.xlsx", "2-2-가. 유형별, 외국인근로자(읍면동)"),
        ("결혼이민자", "2015_외국인주민통계_읍면동.xlsx", "2-2-나.결혼이민자(읍면동)"),
        ("유학생", "2015_외국인주민통계_읍면동.xlsx", "2-2-다.유학생(읍면동)"),
        ("외국국적동포", "2015_외국인주민통계_읍면동.xlsx", "2-2-라.외국국적동포(읍면동)"),
        ("기타외국인", "2015_외국인주민통계_읍면동.xlsx", "2-2-마.기타(읍면동)"),
    ],
}

# ---- 2014-2015 귀화자 × 국적별 × 읍면동 ----
NATURALIZED_NATIONALITY_EUPMYEONDONG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "3.한국국적취득자-1. 국적별(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "3-1.한국국적취득자, 국적별(읍면동)"),
}

# ---- 2014-2015 자녀 × 국적별 × 읍면동 ----
CHILDREN_NATIONALITY_EUPMYEONDONG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "4.외국인주민자녀-1. 국적별(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "4-1.외국인주민자녀,국적별(읍면동)"),
}

# ---- 2014-2015 결혼이민자 및 국적취득자 연령별 × 시도/시군구/읍면동 ----
MARRIAGE_AGE_SHEETS = {
    2014: [
        ("sido", "2014_외국인주민통계_읍면동.xlsx", "5.결혼이민자 및 국적취득자  연령별 현황(시도)"),
        ("sigungu", "2014_외국인주민통계_읍면동.xlsx", "5.결혼이민자 및 국적취득자 연령별 현황(시군구)"),
        ("eupmyeondong", "2014_외국인주민통계_읍면동.xlsx", "5.결혼이민자 및 국적취득자 연령별 현황(읍면동)"),
    ],
    2015: [
        ("sido", "2015_외국인주민통계_읍면동.xlsx", "5-1.결혼이민자 및 국적취득자 연령별 현황(시도)"),
        ("sigungu", "2015_외국인주민통계_읍면동.xlsx", "5-2.결혼이민자 및 국적취득자 연령별 현황(시군구)"),
        ("eupmyeondong", "2015_외국인주민통계_읍면동.xlsx", "5-3.결혼이민자 및 국적취득자 연령별 현황(읍면동)"),
    ],
}


def _generic_matrix_sigungu(year: int, fname: str, sheet: str) -> list[dict]:
    """Use the generic country/matrix parser for ANY (region × labeled-categories) sheet."""
    try:
        return _parse_matrix_sheet(RAW_DIR / fname, year, sheet, level="sigungu")
    except Exception as e:
        print(f"  WARN {year} {sheet}: {e}")
        return []


def _generic_matrix_eupmyeondong(year: int, fname: str, sheet: str,
                                  extra_label: str | None = None) -> list[dict]:
    try:
        return _parse_matrix_sheet(RAW_DIR / fname, year, sheet,
                                    level="eupmyeondong", extra_label=extra_label)
    except Exception as e:
        print(f"  WARN {year} {sheet}: {e}")
        return []


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 자녀 × 부모유형 × 읍면동 (2014-2015)
    parent_emd_rows = []
    for year, items in CHILD_PARENT_EUPMYEONDONG.items():
        for parent_type, fname, sheet in items:
            r = _generic_matrix_eupmyeondong(year, fname, sheet, extra_label=parent_type)
            # Rename the auto-added 'visa_type' field to 'parent_type'
            for row in r:
                if "visa_type" in row:
                    row["parent_type"] = row.pop("visa_type")
            parent_emd_rows.extend(r)
            print(f"  {year} 부모유형={parent_type} 읍면동: {len(r)} rows")
    pd.DataFrame(parent_emd_rows).to_csv(OUT_DIR / "mois_children_parent_type_eupmyeondong.csv",
                                          index=False, encoding="utf-8-sig")

    # 2. 자녀 × 부모유형 × 시군구 (2016-2024) — sheet 8-2 has parent type as columns
    parent_sigungu_rows = []
    for year, sheet in CHILD_PARENT_TYPE_SHEETS_2016PLUS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        r = _generic_matrix_sigungu(year, fname, sheet)
        parent_sigungu_rows.extend(r)
        print(f"  {year} 자녀 유형별 시군구: {len(r)} rows")
    pd.DataFrame(parent_sigungu_rows).to_csv(OUT_DIR / "mois_children_parent_type_sigungu.csv",
                                              index=False, encoding="utf-8-sig")

    # 3. 체류기간별 × 시군구 (2016-2024)
    residence_rows = []
    for year, sheet in RESIDENCE_PERIOD_SHEETS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        r = _generic_matrix_sigungu(year, fname, sheet)
        residence_rows.extend(r)
        print(f"  {year} 체류기간별 시군구: {len(r)} rows")
    pd.DataFrame(residence_rows).to_csv(OUT_DIR / "mois_residence_period_sigungu.csv",
                                         index=False, encoding="utf-8-sig")

    # 4. 이전국적별 × 시군구 (2016-2024)
    prev_nat_rows = []
    for year, sheet in PREV_NATIONALITY_SHEETS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        r = _generic_matrix_sigungu(year, fname, sheet)
        prev_nat_rows.extend(r)
        print(f"  {year} 이전국적별 시군구: {len(r)} rows")
    pd.DataFrame(prev_nat_rows).to_csv(OUT_DIR / "mois_naturalized_prev_nationality_sigungu.csv",
                                        index=False, encoding="utf-8-sig")

    # 5. 국적취득 경과기간별 × 시군구 (2016-2024) — single-value matrix (no sex)
    natur_period_rows = []
    for year, sheet in NATURALIZATION_PERIOD_SHEETS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        try:
            r = _parse_single_value_matrix_sigungu(RAW_DIR / fname, year, sheet)
        except Exception as e:
            print(f"  WARN {year} {sheet}: {e}")
            r = []
        natur_period_rows.extend(r)
        print(f"  {year} 국적취득경과기간별 시군구: {len(r)} rows")
    pd.DataFrame(natur_period_rows).to_csv(OUT_DIR / "mois_naturalization_period_sigungu.csv",
                                            index=False, encoding="utf-8-sig")

    # 6. 외국인주민 세대수 × 읍면동 (2014-2015) — handle simpler 1-col layout
    hh_rows = []
    for year, (fname, sheet) in HOUSEHOLD_EUPMYEONDONG.items():
        try:
            r = _parse_household_emd(RAW_DIR / fname, year, sheet)
            hh_rows.extend(r)
            print(f"  {year} 세대수 읍면동: {len(r)} rows")
        except Exception as e:
            print(f"  WARN {year} 세대수 읍면동: {e}")
    pd.DataFrame(hh_rows).to_csv(OUT_DIR / "mois_household_eupmyeondong.csv",
                                  index=False, encoding="utf-8-sig")

    # 7. 비자유형 × 국적별 × 읍면동 (2014-2015)
    visa_nat_emd_rows = []
    for year, items in VISA_NATIONALITY_EUPMYEONDONG.items():
        for visa_type, fname, sheet in items:
            r = _generic_matrix_eupmyeondong(year, fname, sheet, extra_label=visa_type)
            visa_nat_emd_rows.extend(r)
            print(f"  {year} {visa_type}×국적 읍면동: {len(r)} rows")
    pd.DataFrame(visa_nat_emd_rows).to_csv(OUT_DIR / "mois_nationality_by_visa_eupmyeondong.csv",
                                            index=False, encoding="utf-8-sig")

    # 8. 귀화자 × 국적별 × 읍면동 (2014-2015)
    natur_emd_rows = []
    for year, (fname, sheet) in NATURALIZED_NATIONALITY_EUPMYEONDONG.items():
        r = _generic_matrix_eupmyeondong(year, fname, sheet)
        natur_emd_rows.extend(r)
        print(f"  {year} 귀화자 국적별 읍면동: {len(r)} rows")
    pd.DataFrame(natur_emd_rows).to_csv(OUT_DIR / "mois_nationality_naturalized_eupmyeondong.csv",
                                         index=False, encoding="utf-8-sig")

    # 9. 자녀 × 국적별 × 읍면동 (2014-2015)
    child_emd_rows = []
    for year, (fname, sheet) in CHILDREN_NATIONALITY_EUPMYEONDONG.items():
        r = _generic_matrix_eupmyeondong(year, fname, sheet)
        child_emd_rows.extend(r)
        print(f"  {year} 자녀 국적별 읍면동: {len(r)} rows")
    pd.DataFrame(child_emd_rows).to_csv(OUT_DIR / "mois_nationality_children_eupmyeondong.csv",
                                         index=False, encoding="utf-8-sig")

    # 10. 결혼이민자 및 국적취득자 연령별 (2014-2015 시도/시군구/읍면동)
    marriage_age_rows = []
    for year, items in MARRIAGE_AGE_SHEETS.items():
        for level, fname, sheet in items:
            try:
                if level == "eupmyeondong":
                    r = _generic_matrix_eupmyeondong(year, fname, sheet)
                elif level == "sigungu":
                    r = _generic_matrix_sigungu(year, fname, sheet)
                else:
                    r = _parse_matrix_sheet(RAW_DIR / fname, year, sheet, level="sido")
                # Add level marker
                for row in r:
                    row["level"] = level
                marriage_age_rows.extend(r)
                print(f"  {year} 결혼이민자/국적취득자 연령별 {level}: {len(r)} rows")
            except Exception as e:
                print(f"  WARN {year} {sheet}: {e}")
    pd.DataFrame(marriage_age_rows).to_csv(OUT_DIR / "mois_marriage_age.csv",
                                            index=False, encoding="utf-8-sig")

    print(f"\nDone. Outputs in {OUT_DIR}")


def _parse_single_value_matrix_sigungu(path: Path, year: int, sheet: str) -> list[dict]:
    """For sheets without sex breakdown: each col is a single value.
    Headers: row containing categories (e.g. '1년미만', '1년이상~2년미만'),
    data starts at the row where col 0 = '전국' or '합계'."""
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    # Find data start
    start = None
    for i in range(min(20, len(df))):
        v = df.iat[i, 0]
        if pd.notna(v):
            s = clean_region_name(v)
            if s in ("전국", "합계"):
                start = i
                break
    if start is None:
        return []
    # Header is row above data (or 2 above if blank in between)
    header_row = start - 1
    while header_row >= 0:
        v_check = df.iat[header_row, 1] if df.shape[1] > 1 else None
        if isinstance(v_check, str) and v_check.strip():
            break
        header_row -= 1
    if header_row < 0:
        return []
    # Build col → category label
    cat_map = {}
    for c in range(1, df.shape[1]):
        v = df.iat[header_row, c]
        if pd.notna(v):
            label = str(v).replace("\n", "").strip()
            if label in SUM_COL_LABELS_LOCAL:
                continue
            cat_map[c] = label
    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("전국", "합계", "합 계"):
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            if current_sido is None:
                continue
            for c, cat in cat_map.items():
                v = parse_value(df.iat[i, c])
                if v is None:
                    continue
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "category": cat, "n": v,
                })
            continue
    return rows


SUM_COL_LABELS_LOCAL = {"합계", "총계", "계", "Grand Total"}


def _parse_household_emd(path: Path, year: int, sheet: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    # Find data start
    start = None
    for i in range(min(20, len(df))):
        v = df.iat[i, 0]
        if pd.notna(v):
            s = clean_region_name(v)
            if s == "합계":
                start = i
                break
    if start is None:
        return []
    rows = []
    current_sido = None
    current_sigungu = None
    # Find which col has the household count — typically last col with numeric data
    # For simplicity: try col 1 first; fall back to col 2 / col 3
    candidate_cols = [c for c in range(1, min(8, df.shape[1]))]
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계", "전국"):
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
        if kind != "eupmyeondong":
            continue
        if current_sido is None or current_sigungu is None:
            continue
        # find first numeric column
        for c in candidate_cols:
            v = parse_value(df.iat[i, c])
            if v is not None:
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "eupmyeondong": strip_gu_prefix(name, current_sigungu), "n": v,
                })
                break
    return rows


if __name__ == "__main__":
    main()
