"""Parser for 2006 외국인주민통계.

Schema (시.도별 and 전국 sheets):
  col 0: name
  col 1: 주민등록인구
  col 2: 합계 계
  col 3: 비율 (skip)
  col 4: 합계 남
  col 5: 합계 여
  col 6: 주민등록인구대비 (skip)
  col 7-9:  외국인근로자 (계/남/여)
  col 10-12: 한국국적취득자 (계/남/여)
  col 13-15: 국제결혼이주자 (= 결혼이민자) (계/남/여)
  col 16:    국제결혼가정자녀 (계 only)

Sheet '시.도별' has only 시도 rows. Sheet '전국' has 시도 + 시군구 mixed (same as
2007-2010 sigungu sheet style — 시도 followed by sub-시군구).
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

CAT_COLS_2006 = {
    "합계": None,  # special: 계 at col 2, 남 at col 4, 여 at col 5
    "외국인근로자": 7,
    "한국국적취득자": 10,
    "결혼이민자": 13,
}
CHILDREN_COL_2006 = 16  # 자녀 (계만)


def _find_data_start(df: pd.DataFrame, name_col: int = 0) -> int:
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s == "계":
                return i
    raise ValueError("Could not find national '계' row")


def _emit_2006(rows, df, i, *, year, sido, sigungu):
    # 합계 special
    total = parse_value(df.iat[i, 2])
    male = parse_value(df.iat[i, 4])
    female = parse_value(df.iat[i, 5])
    for sex, val in (("total", total), ("M", male), ("F", female)):
        if val is None:
            continue
        row = {"year": year, "sido": sido, "category": "합계", "sex": sex, "n": val}
        if sigungu is not None:
            row["sigungu"] = sigungu
        rows.append(row)
    # other categories (sex-broken)
    for cat, c in CAT_COLS_2006.items():
        if c is None:
            continue
        t = parse_value(df.iat[i, c])
        m = parse_value(df.iat[i, c + 1])
        f = parse_value(df.iat[i, c + 2])
        for sex, val in (("total", t), ("M", m), ("F", f)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)
    # 자녀 (total only)
    c = parse_value(df.iat[i, CHILDREN_COL_2006])
    if c is not None:
        row = {"year": year, "sido": sido, "category": "외국인주민자녀", "sex": "total", "n": c}
        if sigungu is not None:
            row["sigungu"] = sigungu
        rows.append(row)


def _parse_sheet(path: Path, sheet: str, *, level: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start(df, name_col=0)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("계", "합계", "합 계"):
            continue
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_2006(rows, df, i, year=2006, sido=current_sido, sigungu=None)
            continue
        if level == "sigungu":
            if current_sido is None:
                continue
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            _emit_2006(rows, df, i, year=2006, sido=current_sido, sigungu=sigungu_name)
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = RAW_DIR / "2006_외국인주민통계.xls"
    sido = _parse_sheet(p, "시.도별", level="sido")
    sigungu = _parse_sheet(p, "전국", level="sigungu")
    print(f"2006: sido={len(sido)}  sigungu={len(sigungu)}")
    pd.DataFrame(sido).to_csv(OUT_DIR / "mois_sido_2006.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(sigungu).to_csv(OUT_DIR / "mois_sigungu_2006.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
