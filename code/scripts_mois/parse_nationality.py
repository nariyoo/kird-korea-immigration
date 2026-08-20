"""Parse nationality (국적별) sheets across all year files.

Outputs:
- mois_nationality_sigungu.csv     : year, sido, sigungu, country, sex, n  (2009-2024)
- mois_nationality_eupmyeondong.csv: year, sido, sigungu, eupmyeondong, country, sex, n (2014-2015)
- mois_nationality_by_visa_sigungu.csv : year, sido, sigungu, visa_type, country, sex, n
- mois_nationality_naturalized_sigungu.csv : 한국국적취득자 × 국적 (2014-2015)
- mois_nationality_children_sigungu.csv    : 외국인주민 자녀 × 국적 (2014-2015 sheet 4-1; 2016+ sheet 10)

Strategy: auto-detect the country header by finding the row containing '중국'/'일본',
then read every column flagged with '계' in the following row as country columns.
Continent sub-totals (소계) are skipped.
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

CONTINENT_TOTALS = {"소계", "동북아", "동북아시아", "동남아", "동남아시아",
                    "남부아시아", "서남아시아", "중앙아시아", "아시아",
                    "아시아(기타)", "북미", "유럽", "오세아니아", "중남미",
                    "아프리카"}
SUM_COL_LABELS = {"합계", "총계", "계", "Grand Total"}


def _find_country_header_row(df: pd.DataFrame, max_scan: int = 12) -> int:
    """Locate the row above the (계/남/여) sex header — works for any matrix sheet
    where data columns come in triplets (or singles)."""
    # First find the sex header row: the one with multiple '계' cells at distinct cols
    sex_row = None
    for ri in range(min(max_scan, len(df))):
        count_total = 0
        for v in df.iloc[ri].values:
            if isinstance(v, str) and v.split("\n")[0].strip() == "계":
                count_total += 1
        if count_total >= 2:
            sex_row = ri
            break
    if sex_row is None:
        # Sheets that don't break by sex (e.g. 세대수, simple counts) — header is the row
        # whose next row contains data. Find first row where col 0 is non-empty as data marker.
        # Fall back: assume header is row containing many text labels right before '전국'/합계
        for ri in range(min(max_scan, len(df))):
            v0 = df.iat[ri, 0]
            if isinstance(v0, str) and clean_region_name(v0) in ("전국", "합계", "합 계"):
                return ri - 1
        raise ValueError("Could not locate any header row")
    # The category header is one row above the sex row (sometimes two rows above)
    return sex_row - 1


def _build_country_col_map(df: pd.DataFrame, country_row: int, sex_row: int) -> dict[int, str]:
    """Map data col → country name. Skip 합계/소계 cols."""
    mapping = {}
    # Walk the sex row finding 계 (계 column position is start of a (계,남,여) triplet)
    for c in range(df.shape[1]):
        sex_v = df.iat[sex_row, c]
        if not isinstance(sex_v, str):
            continue
        if sex_v.split("\n")[0].strip() != "계":
            continue
        # Look at country label at country_row, col c. If empty, scan left for nearest non-null.
        country = None
        for cc in range(c, -1, -1):
            v = df.iat[country_row, cc]
            if pd.notna(v):
                country = str(v).split("\n")[0].strip()
                break
        if country is None:
            continue
        # Skip continent sub-totals and 합계
        if country in CONTINENT_TOTALS or country in SUM_COL_LABELS:
            continue
        # Sanitize: drop trailing punctuation
        country = country.replace(" ", "")
        mapping[c] = country
    return mapping


def _find_data_start(df: pd.DataFrame, name_col: int = 0) -> int:
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s in ("합계", "전국", "합 계", "계"):
                return i
    raise ValueError("Data start row not found")


def _parse_matrix_sheet(path: Path, year: int, sheet: str, *,
                        level: str, name_col: int = 0,
                        extra_label: str | None = None) -> list[dict]:
    """Generic matrix parser. extra_label is e.g. visa_type for 5-1-2 sheets.

    For 시군구 sheets: iterate rows, track current_sido, emit at sigungu level only.
    For 읍면동 sheets: iterate rows, track current_sido + current_sigungu, emit at eupmyeondong level.
    For 시도 sheets: emit when current row matches a 시도 name.
    """
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    country_row = _find_country_header_row(df)
    sex_row = country_row + 1
    col_map = _build_country_col_map(df, country_row, sex_row)
    if not col_map:
        return []
    start = _find_data_start(df, name_col=name_col)

    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "전국", "합 계", "계"):
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            if level == "sido":
                _emit_country_row(rows, df, i, year=year, sido=current_sido,
                                  sigungu=None, eupmyeondong=None, col_map=col_map,
                                  extra_label=extra_label)
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            if level == "sigungu":
                if current_sido is None:
                    continue
                _emit_country_row(rows, df, i, year=year, sido=current_sido,
                                  sigungu=current_sigungu, eupmyeondong=None,
                                  col_map=col_map, extra_label=extra_label)
            continue
        if kind == "eupmyeondong":
            if level == "eupmyeondong":
                if current_sido is None or current_sigungu is None:
                    continue
                _emit_country_row(rows, df, i, year=year, sido=current_sido,
                                  sigungu=current_sigungu,
                                  eupmyeondong=strip_gu_prefix(name, current_sigungu),
                                  col_map=col_map, extra_label=extra_label)
    return rows


def _emit_country_row(rows, df, i, *, year, sido, sigungu, eupmyeondong, col_map, extra_label):
    for c, country in col_map.items():
        total = parse_value(df.iat[i, c])
        male = parse_value(df.iat[i, c + 1]) if c + 1 < df.shape[1] else None
        female = parse_value(df.iat[i, c + 2]) if c + 2 < df.shape[1] else None
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "country": country, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            if eupmyeondong is not None:
                row["eupmyeondong"] = eupmyeondong
            if extra_label is not None:
                row["visa_type"] = extra_label
            rows.append(row)


# === Per-year sheet routing ===

NATIONALITY_SIGUNGU_SHEETS = {
    # year: (filename, sheet_name)
    2009: ("2009_외국인주민통계.xls", "2.국적미보유"),
    2010: ("2010_외국인주민통계.xls", "2.국적미취득 "),
    2011: ("2011_외국인주민통계.xlsx", "2.국적미취득(시군구)"),
    2012: ("2012_외국인주민통계.xls", "2.국적미취득(시군구)"),
    2013: ("2013_외국인주민통계.xlsx", "2.국적미취득(시군구)"),
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "2-1.국적별(시군구)"),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "2-1.한국국적을 가지지 않은 자, 국적별(시군구)"),
    2016: ("2016_외국인주민통계.xlsx", "4-2. 국적별(시⋅군⋅구)"),
    2017: ("2017_외국인주민통계.xlsx", "4-2. 국적별(시⋅군⋅구)"),
    2018: ("2018_외국인주민통계.xlsx", "4-2. 국적별(시⋅군⋅구) ("),
    2019: ("2019_외국인주민통계.xlsx", "4-2. 국적별(시·군·구)"),
    2020: ("2020_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2021: ("2021_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2022: ("2022_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2023: ("2023_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2024: ("2024_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
}

NATIONALITY_EUPMYEONDONG_SHEETS = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "2.한국국적을 가지지 않은 자-1. 국적별(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "2-1.한국국적을 가지지 않은 자, 국적별(읍면동)"),
}

# By visa type (외국인근로자/결혼이민자/유학생/외국국적동포/기타) × country × 시군구
NATIONALITY_BY_VISA_SHEETS = {
    # year: list of (visa_type, filename, sheet_name)
    2009: [
        ("외국인근로자", "2009_외국인주민통계.xls", "2-가.외국인근로자"),
        ("결혼이민자", "2009_외국인주민통계.xls", "2-나.결혼이민자"),
        ("유학생", "2009_외국인주민통계.xls", "2-다.유학생"),
        ("외국국적동포", "2009_외국인주민통계.xls", "2-라.재외동포"),
        ("기타외국인", "2009_외국인주민통계.xls", "2-마.기타"),
    ],
    2010: [
        ("외국인근로자", "2010_외국인주민통계.xls", "2-가.외국인근로자"),
        ("결혼이민자", "2010_외국인주민통계.xls", "2-나.결혼이민자"),
        ("유학생", "2010_외국인주민통계.xls", "2-다.유학생"),
        ("외국국적동포", "2010_외국인주민통계.xls", "2-라.재외동포"),
        ("기타외국인", "2010_외국인주민통계.xls", "2-마.기타"),
    ],
    2011: [
        ("외국인근로자", "2011_외국인주민통계.xlsx", "2-가.외국인근로자"),
        ("결혼이민자", "2011_외국인주민통계.xlsx", "2-나.결혼이민자"),
        ("유학생", "2011_외국인주민통계.xlsx", "2-다.유학생"),
        ("외국국적동포", "2011_외국인주민통계.xlsx", "2-라.재외동포"),
        ("기타외국인", "2011_외국인주민통계.xlsx", "2-마.기타"),
    ],
    2012: [
        ("외국인근로자", "2012_외국인주민통계.xls", "2-가.외국인근로자"),
        ("결혼이민자", "2012_외국인주민통계.xls", "2-나.결혼이민자"),
        ("유학생", "2012_외국인주민통계.xls", "2-다.유학생"),
        ("외국국적동포", "2012_외국인주민통계.xls", "2-라.외국국적동포"),
        ("기타외국인", "2012_외국인주민통계.xls", "2-마.기타"),
    ],
    2013: [
        ("외국인근로자", "2013_외국인주민통계.xlsx", "2-가.외국인근로자"),
        ("결혼이민자", "2013_외국인주민통계.xlsx", "2-나.결혼이민자"),
        ("유학생", "2013_외국인주민통계.xlsx", "2-다.유학생"),
        ("외국국적동포", "2013_외국인주민통계.xlsx", "2-라.외국국적동포"),
        ("기타외국인", "2013_외국인주민통계.xlsx", "2-마.기타"),
    ],
    2014: [
        ("외국인근로자", "2014_외국인주민통계_시도시군구.xlsx", "2-2-가.외국인근로자(시군구)"),
        ("결혼이민자", "2014_외국인주민통계_시도시군구.xlsx", "2-2-나.결혼이민자(시군구)"),
        ("유학생", "2014_외국인주민통계_시도시군구.xlsx", "2-2-다.유학생(시군구)"),
        ("외국국적동포", "2014_외국인주민통계_시도시군구.xlsx", "2-2-라.외국국적동포(시군구)"),
        ("기타외국인", "2014_외국인주민통계_시도시군구.xlsx", "2-2-마.기타(시군구)"),
    ],
    2015: [
        ("외국인근로자", "2015_외국인주민통계_시도시군구.xlsx", "2-2-가.외국인근로자(시군구)"),
        ("결혼이민자", "2015_외국인주민통계_시도시군구.xlsx", "2-2-나.결혼이민자(시군구)"),
        ("유학생", "2015_외국인주민통계_시도시군구.xlsx", "2-2-다.유학생(시군구)"),
        ("외국국적동포", "2015_외국인주민통계_시도시군구.xlsx", "2-2-라.외국국적동포(시군구)"),
        ("기타외국인", "2015_외국인주민통계_시도시군구.xlsx", "2-2-마.기타(시군구)"),
    ],
    2016: [
        ("외국인근로자", "2016_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시⋅군⋅구)"),
        ("결혼이민자", "2016_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구)"),
        ("유학생", "2016_외국인주민통계.xlsx", "5-3-2. 유학생(시⋅군⋅구)"),
        ("외국국적동포", "2016_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시⋅군⋅구)"),
        ("기타외국인", "2016_외국인주민통계.xlsx", "5-5-2. 기타(시⋅군⋅구)"),
    ],
    2017: [
        ("외국인근로자", "2017_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시⋅군⋅구)"),
        ("결혼이민자", "2017_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구)"),
        ("유학생", "2017_외국인주민통계.xlsx", "5-3-2. 유학생(시⋅군⋅구)"),
        ("외국국적동포", "2017_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시⋅군⋅구)"),
        ("기타외국인", "2017_외국인주민통계.xlsx", "5-5-2. 기타(시⋅군⋅구)"),
    ],
    2018: [
        ("외국인근로자", "2018_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시⋅군⋅구) "),
        ("결혼이민자", "2018_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구) "),
        ("유학생", "2018_외국인주민통계.xlsx", "5-3-2. 유학생(시⋅군⋅구) "),
        ("외국국적동포", "2018_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시⋅군⋅구) "),
        ("기타외국인", "2018_외국인주민통계.xlsx", "5-5-2. 기타(시⋅군⋅구) "),
    ],
    2019: [
        ("외국인근로자", "2019_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시·군·구)"),
        ("결혼이민자", "2019_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구) "),
        ("유학생", "2019_외국인주민통계.xlsx", "5-3-2.유학생(시·군·구)"),
        ("외국국적동포", "2019_외국인주민통계.xlsx", "5-4-2.외국국적동포(시·군·구)"),
        ("기타외국인", "2019_외국인주민통계.xlsx", "5-5-2.기타(시·군·구)"),
    ],
    2020: [
        ("외국인근로자", "2020_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2020_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2020_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2020_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2020_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2021: [
        ("외국인근로자", "2021_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2021_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2021_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2021_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2021_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2022: [
        ("외국인근로자", "2022_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2022_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2022_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2022_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2022_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2023: [
        ("외국인근로자", "2023_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2023_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2023_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2023_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2023_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2024: [
        ("외국인근로자", "2024_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2024_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2024_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2024_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2024_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
}

# Naturalized × nationality × 시군구 (2014-2015 sheet 3-1) and 자녀 × 국적 × 시군구 (sheet 4-1)
NATIONALITY_NATURALIZED_SHEETS = {
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "3-1.국적별(시군구)"),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "3-1.한국국적취득자, 국적별(시군구)"),
}
NATIONALITY_CHILDREN_SHEETS = {
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "4-1.국적별(시군구)"),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "4-1.국적별(시군구)"),
}


def _safe_parse(year, fname, sheet, *, level, name_col=0, extra_label=None):
    path = RAW_DIR / fname
    try:
        return _parse_matrix_sheet(path, year, sheet, level=level, name_col=name_col,
                                    extra_label=extra_label)
    except Exception as e:
        print(f"  WARN {year} {sheet}: {e}")
        return []


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Total foreigners × nationality × 시군구
    sigungu_rows = []
    for year, (fname, sheet) in NATIONALITY_SIGUNGU_SHEETS.items():
        rows = _safe_parse(year, fname, sheet, level="sigungu")
        sigungu_rows.extend(rows)
        print(f"  {year} 국적별 시군구: {len(rows)} rows")

    # Total foreigners × nationality × 읍면동
    emd_rows = []
    for year, (fname, sheet) in NATIONALITY_EUPMYEONDONG_SHEETS.items():
        # 2014 읍면동 has name at col 0 (Korean), English at col 1, so name_col=0 works
        rows = _safe_parse(year, fname, sheet, level="eupmyeondong", name_col=0)
        emd_rows.extend(rows)
        print(f"  {year} 국적별 읍면동: {len(rows)} rows")

    # By visa-type × nationality × 시군구
    by_visa_rows = []
    for year, items in NATIONALITY_BY_VISA_SHEETS.items():
        for visa_type, fname, sheet in items:
            rows = _safe_parse(year, fname, sheet, level="sigungu", extra_label=visa_type)
            by_visa_rows.extend(rows)
            print(f"  {year} {visa_type} 시군구: {len(rows)} rows")

    # Naturalized × nationality × 시군구
    natur_rows = []
    for year, (fname, sheet) in NATIONALITY_NATURALIZED_SHEETS.items():
        rows = _safe_parse(year, fname, sheet, level="sigungu")
        natur_rows.extend(rows)
        print(f"  {year} 한국국적취득자 국적별 시군구: {len(rows)} rows")

    # Children × nationality × 시군구
    child_rows = []
    for year, (fname, sheet) in NATIONALITY_CHILDREN_SHEETS.items():
        rows = _safe_parse(year, fname, sheet, level="sigungu")
        child_rows.extend(rows)
        print(f"  {year} 자녀 국적별 시군구: {len(rows)} rows")

    pd.DataFrame(sigungu_rows).to_csv(OUT_DIR / "mois_nationality_sigungu.csv",
                                      index=False, encoding="utf-8-sig")
    pd.DataFrame(emd_rows).to_csv(OUT_DIR / "mois_nationality_eupmyeondong.csv",
                                   index=False, encoding="utf-8-sig")
    pd.DataFrame(by_visa_rows).to_csv(OUT_DIR / "mois_nationality_by_visa_sigungu.csv",
                                      index=False, encoding="utf-8-sig")
    pd.DataFrame(natur_rows).to_csv(OUT_DIR / "mois_nationality_naturalized_sigungu.csv",
                                    index=False, encoding="utf-8-sig")
    pd.DataFrame(child_rows).to_csv(OUT_DIR / "mois_nationality_children_sigungu.csv",
                                    index=False, encoding="utf-8-sig")

    print(f"\nTotals:")
    print(f"  국적별 시군구: {len(sigungu_rows):,}")
    print(f"  국적별 읍면동: {len(emd_rows):,}")
    print(f"  비자유형별 시군구: {len(by_visa_rows):,}")
    print(f"  귀화자 국적별 시군구: {len(natur_rows):,}")
    print(f"  자녀 국적별 시군구: {len(child_rows):,}")


if __name__ == "__main__":
    main()
