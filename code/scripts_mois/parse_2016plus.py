"""Parser for 2016-2024 외국인주민통계 files (homogeneous schema).

Sheets parsed:
- 1-1. 유형 및 지역별(시.도)       → mois_sido_2016_2024.csv
- 1-2. 유형 및 지역별(시.군.구)   → mois_sigungu_2016_2024.csv
- 1-3. 유형 및 지역별(읍면동)     → mois_eupmyeondong_2016_2024.csv
- 11. 다문화가구 현황(읍면동)     → mois_multicultural_eupmyeondong_2016_2024.csv

Category schema (population sheets):
  합계, 한국국적미취득_소계, 외국인근로자, 결혼이민자, 유학생, 외국국적동포, 기타외국인,
  한국국적취득자, 외국인주민자녀
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mois_common import (
    RAW_DIR, OUT_DIR, SIDO_NAMES, canon_sido, clean_region_name,
    fix_known_typos, split_sub_gu, parse_value, classify_row_name,
    SUB_GU_PARENTS,
)

YEARS = list(range(2016, 2025))

# Canonical category order
POP_CATEGORIES_SIDO_SIGUNGU = [
    "합계", "한국국적미취득_소계",
    "외국인근로자", "결혼이민자", "유학생", "외국국적동포", "기타외국인",
    "한국국적취득자", "외국인주민자녀",
]
POP_CATEGORIES_EUPMYEONDONG = POP_CATEGORIES_SIDO_SIGUNGU  # same set


def find_sheet(xls: pd.ExcelFile, *patterns) -> str | None:
    """Find a sheet matching any of the substrings (loosely)."""
    for s in xls.sheet_names:
        norm = s.replace(" ", "").replace("⋅", ".").replace("·", ".")
        for pat in patterns:
            if pat.replace(" ", "").replace("⋅", ".").replace("·", ".") in norm:
                return s
    return None


def _read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=None)


def _find_data_start(df: pd.DataFrame) -> int:
    """Return the row index of the first data row (where col 0 == '전국')."""
    for i in range(min(15, len(df))):
        v = df.iat[i, 0]
        if isinstance(v, str) and v.strip() == "전국":
            return i
    raise ValueError("Could not find '전국' row")


def _parse_sido_sigungu_sheet(path: Path, year: int, sheet: str, *, level: str) -> list[dict]:
    """Parse 1-1 or 1-2 sheet. Each region has 3 columns per category (계/남/여).

    Layout (from 2024 inspection):
      col 0: 구분 (region name)
      col 1: 총인구 (denominator)
      col 2: 비율
      col 3-5: 합계 (계/남/여)
      col 6-8: 한국국적미취득 소계 (계/남/여)
      col 9-11: 외국인근로자 (계/남/여)
      col 12-14: 결혼이민자 (계/남/여)
      col 15-17: 유학생 (계/남/여)
      col 18-20: 외국국적동포 (계/남/여)
      col 21-23: 기타외국인 (계/남/여)
      col 24-26: 한국국적취득자 (계/남/여)
      col 27-29: 외국인주민자녀 (계/남/여)
    """
    df = _read_sheet(path, sheet)
    start = _find_data_start(df)

    cat_cols = {
        "합계": (3, 4, 5),
        "한국국적미취득_소계": (6, 7, 8),
        "외국인근로자": (9, 10, 11),
        "결혼이민자": (12, 13, 14),
        "유학생": (15, 16, 17),
        "외국국적동포": (18, 19, 20),
        "기타외국인": (21, 22, 23),
        "한국국적취득자": (24, 25, 26),
        "외국인주민자녀": (27, 28, 29),
    }

    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)

        if name == "전국":
            # national row, optional, skip for sido/sigungu CSVs
            continue

        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_region_row(rows, df, i, year=year, sido=current_sido,
                                 sigungu=None, eupmyeondong=None, cat_cols=cat_cols,
                                 with_sex=True)
            continue

        # not sido — must be sigungu
        if level == "sigungu":
            if current_sido is None:
                # malformed — try to skip
                continue
            # detect sub-gu split
            sub = split_sub_gu(name)
            if sub:
                parent, gu = sub
                sigungu_name = parent + " " + gu
            else:
                sigungu_name = name
            _emit_region_row(rows, df, i, year=year, sido=current_sido,
                             sigungu=sigungu_name, eupmyeondong=None,
                             cat_cols=cat_cols, with_sex=True)

    return rows


def _emit_region_row(rows, df, i, *, year, sido, sigungu, eupmyeondong, cat_cols, with_sex):
    for cat, cols in cat_cols.items():
        if with_sex:
            total = parse_value(df.iat[i, cols[0]])
            male = parse_value(df.iat[i, cols[1]])
            female = parse_value(df.iat[i, cols[2]])
            for sex, val in (("total", total), ("M", male), ("F", female)):
                if val is None:
                    continue
                row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
                if sigungu is not None:
                    row["sigungu"] = sigungu
                if eupmyeondong is not None:
                    row["eupmyeondong"] = eupmyeondong
                rows.append(row)
        else:
            val = parse_value(df.iat[i, cols[0]])
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            if eupmyeondong is not None:
                row["eupmyeondong"] = eupmyeondong
            rows.append(row)


def _parse_eupmyeondong_sheet(path: Path, year: int, sheet: str) -> list[dict]:
    """Parse sheet 1-3 (읍면동). Single-column-per-category layout.

    Columns (2024):
      0: name
      1: 합계
      2: 한국국적미취득_소계
      3: 외국인근로자
      4: 결혼이민자
      5: 유학생
      6: 외국국적동포
      7: 기타외국인
      8: 한국국적취득자
      9: 외국인주민자녀
    """
    df = _read_sheet(path, sheet)
    start = _find_data_start(df)

    cat_cols = {
        "합계": 1,
        "한국국적미취득_소계": 2,
        "외국인근로자": 3,
        "결혼이민자": 4,
        "유학생": 5,
        "외국국적동포": 6,
        "기타외국인": 7,
        "한국국적취득자": 8,
        "외국인주민자녀": 9,
    }

    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "전국":
            continue
        kind = classify_row_name(name)

        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue

        if kind == "sigungu":
            # detect sub-gu under parent 시
            sub = split_sub_gu(name)
            if sub:
                parent, gu = sub
                current_sigungu = parent + " " + gu
            else:
                current_sigungu = name
            continue

        if kind == "eupmyeondong":
            # 세종특별자치시는 시군구 없이 시도 바로 아래 읍면동 → 시군구를 '세종시'로 보정
            if current_sido == "세종특별자치시" and current_sigungu is None:
                current_sigungu = "세종시"
            if current_sido is None or current_sigungu is None:
                # malformed (e.g. orphan 완산구); skip
                continue
            for cat, c in cat_cols.items():
                v = parse_value(df.iat[i, c])
                if v is None:
                    continue
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "eupmyeondong": name, "category": cat, "n": v,
                })

    return rows


def _parse_multicultural_sheet(path: Path, year: int, sheet: str) -> list[dict]:
    """Parse sheet 11 (다문화가구) 읍면동 portion.

    2024 columns:
      0: name
      1: 합계
      2: 한국인배우자
      3: 결혼이민자및귀화자등_소계
      4: 결혼이민자
      5: 귀화자등
      6: 자녀_소계
      7: 귀화·인지및외국국적
      8: 국내출생
      9: 기타동거인_소계
      10: 내국인
      11: 외국인
    """
    df = _read_sheet(path, sheet)
    start = _find_data_start(df)

    cat_cols = {
        "합계": 1, "한국인배우자": 2,
        "결혼이민자귀화자_소계": 3, "결혼이민자": 4, "귀화자등": 5,
        "자녀_소계": 6, "자녀_귀화인지외국국적": 7, "자녀_국내출생": 8,
        "기타동거인_소계": 9, "기타동거인_내국인": 10, "기타동거인_외국인": 11,
    }

    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "전국":
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
            for cat, c in cat_cols.items():
                if c >= df.shape[1]:
                    continue
                v = parse_value(df.iat[i, c])
                if v is None:
                    continue
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "eupmyeondong": name, "category": cat, "n": v,
                })
    return rows


def parse_year(year: int) -> dict[str, list[dict]]:
    path = RAW_DIR / f"{year}_외국인주민통계.xlsx"
    xls = pd.ExcelFile(path)
    out: dict[str, list[dict]] = {"sido": [], "sigungu": [], "eupmyeondong": [], "multicultural": []}

    sheet_sido = find_sheet(xls, "1-1.유형및지역별(시.도)", "1-1.유형 및 지역별(시⋅도)", "1-1.유형 및 지역별(시.도)")
    sheet_sigungu = find_sheet(xls, "1-2.유형및지역별(시.군.구)", "1-2.유형 및 지역별(시⋅군⋅구)")
    sheet_eupmyeondong = find_sheet(xls, "1-3.유형및지역별(읍면동)", "1-3.유형 및 지역별(읍⋅면⋅동)")
    sheet_multi = find_sheet(xls, "11.다문화가구")

    if sheet_sido:
        out["sido"] = _parse_sido_sigungu_sheet(path, year, sheet_sido, level="sido")
    if sheet_sigungu:
        out["sigungu"] = _parse_sido_sigungu_sheet(path, year, sheet_sigungu, level="sigungu")
    if sheet_eupmyeondong:
        out["eupmyeondong"] = _parse_eupmyeondong_sheet(path, year, sheet_eupmyeondong)
    if sheet_multi:
        out["multicultural"] = _parse_multicultural_sheet(path, year, sheet_multi)
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu, all_eupmyeondong, all_multi = [], [], [], []

    for year in YEARS:
        print(f"=== {year} ===")
        result = parse_year(year)
        for key in result:
            print(f"  {key}: {len(result[key])} rows")
        all_sido.extend(result["sido"])
        all_sigungu.extend(result["sigungu"])
        all_eupmyeondong.extend(result["eupmyeondong"])
        all_multi.extend(result["multicultural"])

    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2016_2024.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2016_2024.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_eupmyeondong).to_csv(OUT_DIR / "mois_eupmyeondong_2016_2024.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_multi).to_csv(OUT_DIR / "mois_multicultural_eupmyeondong_2016_2024.csv", index=False, encoding="utf-8-sig")

    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}  eupmyeondong={len(all_eupmyeondong):,}  multicultural={len(all_multi):,}")


if __name__ == "__main__":
    main()
