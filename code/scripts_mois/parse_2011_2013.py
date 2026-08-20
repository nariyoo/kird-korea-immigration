"""Parser for 2011-2013 외국인주민통계 (no 읍면동 layer).

Column layout is identical to 2014/2015 시도시군구. Only the sheet names differ.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mois_common import RAW_DIR, OUT_DIR
from parse_2014_2015 import _parse_sigungu_or_sido_sheet

YEAR_FILES = {
    2011: ("2011_외국인주민통계.xlsx", "1.총괄표(시도) ", "1.총괄표(시군구)"),
    2012: ("2012_외국인주민통계.xls", "1.조사총괄표(시도)", "1.조사총괄표(시군구)"),
    2013: ("2013_외국인주민통계.xlsx", "1.조사총괄표(시도)", "1.조사총괄표(시군구)"),
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu = [], []
    for year, (fname, sname_sido, sname_sigungu) in YEAR_FILES.items():
        path = RAW_DIR / fname
        sido = _parse_sigungu_or_sido_sheet(path, year, sname_sido, level="sido")
        sigungu = _parse_sigungu_or_sido_sheet(path, year, sname_sigungu, level="sigungu")
        print(f"{year}: sido={len(sido)}  sigungu={len(sigungu)}")
        all_sido.extend(sido)
        all_sigungu.extend(sigungu)
    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2011_2013.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2011_2013.csv", index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}")


if __name__ == "__main__":
    main()
