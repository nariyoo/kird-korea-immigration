"""Parse 자녀 × 연령별 sheets.

Layout: rows alternate between region-total rows (e.g. '전국', '서울특별시', '종로구')
and per-age rows ('0세' / '만0세' / '만19세이상') belonging to the preceding region.

We emit per-age counts at the region level, using 합계 columns (cols 1-3 = 계/남/여).
Country and type breakdowns within the same sheets are not extracted here (kept simple).

Outputs:
- mois_children_age_sido.csv      : year, sido, age, sex, n   (2014-2024 시도)
- mois_children_age_sigungu.csv   : year, sido, sigungu, age, sex, n   (2014-2024 시군구)
"""
from __future__ import annotations
import sys
import re
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mois_common import (
    RAW_DIR, OUT_DIR, SIDO_NAMES, canon_sido, clean_region_name,
    fix_known_typos, split_sub_gu, parse_value, classify_row_name,
)

# Regex to detect age labels: 0세 / 만0세 / 만19세이상 / 18세이상
AGE_RE = re.compile(r"^만?\d+세(이상)?$")


def _normalize_age(label: str) -> str | None:
    """Convert '만0세'/'0세' → '0', '만19세이상' → '19+', etc. Return None if not an age."""
    s = label.replace(" ", "")
    m = AGE_RE.match(s)
    if not m:
        return None
    s = s.replace("만", "")
    if "이상" in s:
        base = s.replace("세이상", "")
        return f"{base}+"
    return s.replace("세", "")


def _parse_age_sheet(path: Path, year: int, sheet: str, *, name_col: int = 0,
                     value_cols: tuple[int, int, int] = (1, 2, 3),
                     emit_levels: tuple[str, ...] = ("sigungu",)) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    rows = []
    current_sido = None
    current_sigungu = None

    # Some sheets (2012-2013) keep region in col 0 and age in col 1.
    # Detect: if col 1 contains '만0세'-style labels in early data rows, age is in col 1.
    age_col = name_col
    region_col = name_col
    value_shift = 0
    for probe in range(min(40, len(df))):
        v1 = df.iat[probe, name_col + 1] if name_col + 1 < df.shape[1] else None
        if isinstance(v1, str) and _normalize_age(clean_region_name(v1)) is not None:
            # age is in col name_col+1; region stays in name_col
            age_col = name_col + 1
            region_col = name_col
            value_shift = 1  # values start at col 2 not col 1
            break

    for i in range(len(df)):
        # Look at region column first
        raw_r = df.iat[i, region_col] if pd.notna(df.iat[i, region_col]) else None
        if raw_r is not None:
            r_name = clean_region_name(raw_r)
            r_name = fix_known_typos(r_name)
            if r_name in ("구분", "Section"):
                continue
            kind = classify_row_name(r_name)
            if kind == "sido":
                current_sido = canon_sido(r_name)
                current_sigungu = None
                # When age is in a separate col, region row may also have age='합계' → keep checking
                if age_col == region_col:
                    continue
            elif kind == "sigungu":
                sub = split_sub_gu(r_name)
                current_sigungu = (sub[0] + " " + sub[1]) if sub else r_name
                if age_col == region_col:
                    continue
            elif r_name in ("전국", "합계", "합 계", ""):
                if age_col == region_col:
                    continue
            elif age_col == region_col:
                # region_col may also hold the age label
                pass

        # Look at age column
        if age_col >= df.shape[1]:
            continue
        raw_a = df.iat[i, age_col]
        if pd.isna(raw_a):
            continue
        a_name = clean_region_name(raw_a)
        if not a_name:
            continue
        age = _normalize_age(a_name)
        if age is None:
            continue
        # 세종특별자치시는 시군구 없이 시도 바로 아래 → 시군구를 '세종시'로 보정
        if current_sido == "세종특별자치시" and current_sigungu is None and "sigungu" in emit_levels:
            current_sigungu = "세종시"
        # Emit at the current finest level we know
        if current_sigungu is not None and "sigungu" in emit_levels:
            level_label, sido, sigungu = "sigungu", current_sido, current_sigungu
        elif current_sido is not None and "sido" in emit_levels:
            level_label, sido, sigungu = "sido", current_sido, None
        else:
            continue
        c_total, c_m, c_f = (c + value_shift for c in value_cols)
        total = parse_value(df.iat[i, c_total]) if c_total < df.shape[1] else None
        male = parse_value(df.iat[i, c_m]) if c_m < df.shape[1] else None
        female = parse_value(df.iat[i, c_f]) if c_f < df.shape[1] else None
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "age": age, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)
    return rows


# Per-year (file, sido_sheet, sigungu_sheet)
AGE_SHEETS = {
    2011: ("2011_외국인주민통계.xlsx", None, "4.자녀(연령)"),
    2012: ("2012_외국인주민통계.xls", None, "4.자녀연령"),
    2013: ("2013_외국인주민통계.xlsx", None, "4.자녀연령"),
    # 2014/2015: sido sheet in 시도시군구 file, sigungu sheet in 읍면동 file (oddly placed)
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "4-3.연령별(시도)",
           ("2014_외국인주민통계_읍면동.xlsx", "4-3.연령별(시군구)")),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "4-3.연령별(시도)",
           ("2015_외국인주민통계_읍면동.xlsx", "4-3.연령별(시군구)")),
    # 2016+ in main file, sheets 9-1 / 9-2
    2016: ("2016_외국인주민통계.xlsx", "9-1. 연령별(시⋅도)", "9-2. 연령별(시⋅군⋅구)"),
    2017: ("2017_외국인주민통계.xlsx", "9-1. 연령별(시⋅도)", "9-2. 연령별(시⋅군⋅구)"),
    2018: ("2018_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2019: ("2019_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2020: ("2020_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2021: ("2021_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2022: ("2022_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2023: ("2023_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2024: ("2024_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sido_rows, sigungu_rows = [], []
    for year, info in AGE_SHEETS.items():
        fname, sido_sheet, sigungu_sheet = info
        path = RAW_DIR / fname
        if sido_sheet:
            try:
                r = _parse_age_sheet(path, year, sido_sheet, emit_levels=("sido",))
                sido_rows.extend(r)
                print(f"  {year} 자녀연령 시도: {len(r)} rows")
            except Exception as e:
                print(f"  WARN {year} 시도 {sido_sheet}: {e}")
        # sigungu_sheet might be tuple (different file, sheet)
        if isinstance(sigungu_sheet, tuple):
            sg_path = RAW_DIR / sigungu_sheet[0]; sg_sheet = sigungu_sheet[1]
        else:
            sg_path, sg_sheet = path, sigungu_sheet
        if sg_sheet:
            try:
                r = _parse_age_sheet(sg_path, year, sg_sheet, emit_levels=("sigungu",))
                sigungu_rows.extend(r)
                print(f"  {year} 자녀연령 시군구: {len(r)} rows")
            except Exception as e:
                print(f"  WARN {year} 시군구 {sg_sheet}: {e}")

    pd.DataFrame(sido_rows).to_csv(OUT_DIR / "mois_children_age_sido.csv",
                                    index=False, encoding="utf-8-sig")
    pd.DataFrame(sigungu_rows).to_csv(OUT_DIR / "mois_children_age_sigungu.csv",
                                       index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(sido_rows):,}  sigungu={len(sigungu_rows):,}")


if __name__ == "__main__":
    main()
