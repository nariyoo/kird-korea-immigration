"""Parser for 2007-2010 외국인주민통계.

Schemas evolve year by year:
- 2007: 25 cols, no 유학생, no 외국국적동포, no 한국국적미취득_소계, 자녀 only as a single cell
- 2008: 27 cols, has 유학생, no 외국국적동포
- 2009: 46 cols (same buckets as 2011+). BUT 시도 sheet has 총계 at cols 2-4 (비율 at col 5),
        while 시군구 sheet has 비율 at col 2 and 총계 at cols 3-5 (= standard).
- 2010: 46 cols, same as 2011-2013 throughout.

We re-use the 2014-2015 emit helper.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mois_common import (
    RAW_DIR, OUT_DIR, SIDO_NAMES, canon_sido, clean_region_name,
    fix_known_typos, split_sub_gu, parse_value,
)


# Cat cols for 2010 + 2009 시군구 (= same as 2011-2015 시도시군구)
STANDARD_CAT_COLS = {
    "합계": 3,
    "한국국적미취득_소계": 6,
    "외국인근로자": 9,
    "결혼이민자": 12,
    "유학생": 15,
    "외국국적동포": 18,
    "기타외국인": 21,
    "한국국적취득자": 24,
    "혼인귀화자": 27,
    "기타귀화자": 30,
    "외국인주민자녀": 33,
    "자녀_외국인부모": 36,
    "자녀_외한국인부모": 39,
    "자녀_한국인부모": 42,
}
STANDARD_HOUSEHOLD_COL = 45

# 2009 시도 sheet has 총계 shifted: col 2,3,4 = 총계 계/남/여; col 5 = 비율; col 6+ = standard from there
CAT_COLS_2009_SIDO = {
    "합계": 2,
    "한국국적미취득_소계": 6,
    "외국인근로자": 9,
    "결혼이민자": 12,
    "유학생": 15,
    "외국국적동포": 18,  # actually labeled '재외동포'
    "기타외국인": 21,
    "한국국적취득자": 24,
    "혼인귀화자": 27,
    "기타귀화자": 30,
    "외국인주민자녀": 33,
    "자녀_외국인부모": 36,
    "자녀_외한국인부모": 39,
    "자녀_한국인부모": 42,
}
HOUSEHOLD_COL_2009_SIDO = 45

# 2008 layout (27 cols, no 외국국적동포, no soce)
CAT_COLS_2008 = {
    "합계": 2,
    "외국인근로자": 6,
    "결혼이민자": 9,
    "유학생": 12,
    "기타외국인": 15,
    "혼인귀화자": 18,
    "기타귀화자": 21,
    "외국인주민자녀": 24,
}
HOUSEHOLD_COL_2008 = None  # not present

# 2007 layout (25 cols, simpler)
CAT_COLS_2007 = {
    "합계": 2,           # 계/남/여 at cols 2, 4, 5 — col 3 = 비율 placeholder
    # We'll handle 합계 specially (3 non-consecutive cols)
    "외국인근로자": 7,
    "결혼이민자": 10,
    "기타외국인": 13,
    "혼인귀화자": 16,
    "기타귀화자": 19,
    "외국인주민자녀": 22,
}
# 2007: 합계 spans cols 2 (계), 4 (남), 5 (여), with col 3 = 비율


def _find_data_start_named(df: pd.DataFrame, name_col: int = 0,
                            markers: tuple[str, ...] = ("합계", "합 계")) -> int:
    for i in range(min(25, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s in {m.replace(" ", "") for m in markers}:
                return i
    raise ValueError(f"Could not find {markers} row")


def _emit_categories(rows, df, i, *, year, sido, sigungu, cat_cols, household_col,
                     special_2007=False):
    for cat, c in cat_cols.items():
        if special_2007 and cat == "합계":
            # 2007 합계: 계 at col 2, 남 at col 4, 여 at col 5
            total = parse_value(df.iat[i, 2])
            male = parse_value(df.iat[i, 4])
            female = parse_value(df.iat[i, 5])
        else:
            total = parse_value(df.iat[i, c])
            male = parse_value(df.iat[i, c + 1]) if c + 1 < df.shape[1] else None
            female = parse_value(df.iat[i, c + 2]) if c + 2 < df.shape[1] else None
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)
    if household_col is not None and household_col < df.shape[1]:
        hh = parse_value(df.iat[i, household_col])
        if hh is not None:
            row = {"year": year, "sido": sido, "category": "세대수", "sex": "total", "n": hh}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)


def _parse_sheet(path: Path, year: int, sheet: str, *, level: str,
                 cat_cols: dict, household_col, special_2007: bool = False) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_named(df, name_col=0)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계"):
            continue
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_categories(rows, df, i, year=year, sido=current_sido, sigungu=None,
                                 cat_cols=cat_cols, household_col=household_col,
                                 special_2007=special_2007)
            continue
        if level == "sigungu":
            if current_sido is None:
                continue
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            _emit_categories(rows, df, i, year=year, sido=current_sido, sigungu=sigungu_name,
                             cat_cols=cat_cols, household_col=household_col,
                             special_2007=special_2007)
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu = [], []

    # 2007
    p = RAW_DIR / "2007_외국인주민통계.xls"
    sido = _parse_sheet(p, 2007, "1.조사총괄(시도)", level="sido",
                        cat_cols=CAT_COLS_2007, household_col=None, special_2007=True)
    sigungu = _parse_sheet(p, 2007, "1.조사총괄(시군구)", level="sigungu",
                           cat_cols=CAT_COLS_2007, household_col=None, special_2007=True)
    print(f"2007: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    # 2008
    p = RAW_DIR / "2008_외국인주민통계.xls"
    sido = _parse_sheet(p, 2008, "총괄(시도)", level="sido",
                        cat_cols=CAT_COLS_2008, household_col=None)
    sigungu = _parse_sheet(p, 2008, "총괄 (시군구)", level="sigungu",
                           cat_cols=CAT_COLS_2008, household_col=None)
    print(f"2008: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    # 2009 — different cat_cols for sido vs sigungu!
    p = RAW_DIR / "2009_외국인주민통계.xls"
    sido = _parse_sheet(p, 2009, "1.총괄표(시도)", level="sido",
                        cat_cols=CAT_COLS_2009_SIDO, household_col=HOUSEHOLD_COL_2009_SIDO)
    sigungu = _parse_sheet(p, 2009, "1.총괄표", level="sigungu",
                           cat_cols=STANDARD_CAT_COLS, household_col=STANDARD_HOUSEHOLD_COL)
    print(f"2009: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    # 2010 — standard 46-col
    p = RAW_DIR / "2010_외국인주민통계.xls"
    sido = _parse_sheet(p, 2010, "1.총괄표 (시도) ", level="sido",
                        cat_cols=STANDARD_CAT_COLS, household_col=STANDARD_HOUSEHOLD_COL)
    sigungu = _parse_sheet(p, 2010, "1.총괄표(시군구)", level="sigungu",
                           cat_cols=STANDARD_CAT_COLS, household_col=STANDARD_HOUSEHOLD_COL)
    print(f"2010: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2007_2010.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2007_2010.csv", index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}")


if __name__ == "__main__":
    main()
