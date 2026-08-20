"""Consolidate per-epoch MOIS CSVs into unified long-format outputs.

Inputs (in 03_cleaned_data/):
  mois_sido_2006.csv          (2006 only)
  mois_sigungu_2006.csv
  mois_sido_2007_2010.csv
  mois_sigungu_2007_2010.csv
  mois_sido_2011_2013.csv
  mois_sigungu_2011_2013.csv
  mois_sido_2014_2015.csv
  mois_sigungu_2014_2015.csv
  mois_eupmyeondong_2014_2015.csv
  mois_sido_2016_2024.csv
  mois_sigungu_2016_2024.csv
  mois_eupmyeondong_2016_2024.csv
  mois_multicultural_eupmyeondong_2016_2024.csv

Outputs (overwrites in same folder):
  mois_sido.csv             (2006-2024)
  mois_sigungu.csv          (2006-2024)
  mois_eupmyeondong.csv     (2014-2024)
  mois_multicultural_eupmyeondong.csv   (2016-2024)

Plus a coverage matrix for documentation:
  mois_coverage.csv
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from mois_common import OUT_DIR


SIDO_FILES = [
    "mois_sido_2006.csv",
    "mois_sido_2007_2010.csv",
    "mois_sido_2011_2013.csv",
    "mois_sido_2014_2015.csv",
    "mois_sido_2016_2024.csv",
]
SIGUNGU_FILES = [
    "mois_sigungu_2006.csv",
    "mois_sigungu_2007_2010.csv",
    "mois_sigungu_2011_2013.csv",
    "mois_sigungu_2014_2015.csv",
    "mois_sigungu_2016_2024.csv",
]
EUPMYEONDONG_FILES = [
    "mois_eupmyeondong_2014_2015.csv",
    "mois_eupmyeondong_2016_2024.csv",
]
MULTICULTURAL_FILES = [
    "mois_multicultural_eupmyeondong_2016_2024.csv",
]


def _concat(files: list[str]) -> pd.DataFrame:
    dfs = []
    for fn in files:
        p = OUT_DIR / fn
        if not p.exists():
            print(f"  WARNING: missing {fn}")
            continue
        df = pd.read_csv(p)
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    out = pd.concat(dfs, ignore_index=True)
    return out


def _coverage_summary(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Return per-year coverage: # unique regions × # unique categories."""
    if df.empty:
        return pd.DataFrame()
    if level == "sido":
        group_cols = ["sido"]
    elif level == "sigungu":
        group_cols = ["sido", "sigungu"]
    elif level == "eupmyeondong":
        group_cols = ["sido", "sigungu", "eupmyeondong"]
    else:
        raise ValueError(level)

    rows = []
    for year, sub in df.groupby("year"):
        rows.append({
            "year": year,
            "level": level,
            "n_regions": sub.drop_duplicates(group_cols).shape[0],
            "n_categories": sub["category"].nunique(),
            "n_rows": len(sub),
            "categories": ", ".join(sorted(sub["category"].unique())),
        })
    return pd.DataFrame(rows)


def main():
    print("Consolidating MOIS outputs...")

    sido = _concat(SIDO_FILES)
    sigungu = _concat(SIGUNGU_FILES)
    emd = _concat(EUPMYEONDONG_FILES)
    multi = _concat(MULTICULTURAL_FILES)

    print(f"\nRow counts:")
    print(f"  sido: {len(sido):,}")
    print(f"  sigungu: {len(sigungu):,}")
    print(f"  eupmyeondong: {len(emd):,}")
    print(f"  multicultural: {len(multi):,}")

    # Reorder columns for consistency
    sido_cols = ["year", "sido", "category", "sex", "n"]
    sigungu_cols = ["year", "sido", "sigungu", "category", "sex", "n"]
    emd_cols = ["year", "sido", "sigungu", "eupmyeondong", "category", "sex", "n"]
    multi_cols = ["year", "sido", "sigungu", "eupmyeondong", "category", "n"]

    # eupmyeondong may have 'sex' col present only for 2014/2015 (with M/F/total) — keep but
    # 2016+ rows will lack 'sex' as a column entirely. Standardize: fill missing sex with 'total'.
    if "sex" not in emd.columns:
        emd["sex"] = "total"
    else:
        emd["sex"] = emd["sex"].fillna("total")

    sido = sido[[c for c in sido_cols if c in sido.columns]]
    sigungu = sigungu[[c for c in sigungu_cols if c in sigungu.columns]]
    emd = emd[[c for c in emd_cols if c in emd.columns]]
    if not multi.empty:
        multi = multi[[c for c in multi_cols if c in multi.columns]]

    # Write
    sido.to_csv(OUT_DIR / "mois_sido.csv", index=False, encoding="utf-8-sig")
    sigungu.to_csv(OUT_DIR / "mois_sigungu.csv", index=False, encoding="utf-8-sig")
    emd.to_csv(OUT_DIR / "mois_eupmyeondong.csv", index=False, encoding="utf-8-sig")
    if not multi.empty:
        multi.to_csv(OUT_DIR / "mois_multicultural_eupmyeondong.csv", index=False, encoding="utf-8-sig")

    # Coverage summary
    coverage_parts = []
    coverage_parts.append(_coverage_summary(sido, "sido"))
    coverage_parts.append(_coverage_summary(sigungu, "sigungu"))
    coverage_parts.append(_coverage_summary(emd, "eupmyeondong"))
    coverage = pd.concat(coverage_parts, ignore_index=True)
    coverage.to_csv(OUT_DIR / "mois_coverage.csv", index=False, encoding="utf-8-sig")

    print("\n=== Coverage summary ===")
    print(coverage[["year", "level", "n_regions", "n_categories", "n_rows"]].to_string(index=False))

    print(f"\nOutputs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
