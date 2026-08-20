"""Consolidate 39 fragmented MOIS CSVs → ~7 tidy thematic CSVs.

Reduces the user-facing data surface to a small set of analyst-friendly long
tables. Each thematic CSV is the single source of truth for its dimension.

Output files in 03_cleaned_data/:
  mois_population.csv           — all population categories × level × year
                                   (year, level, sido, sigungu, eupmyeondong, category, sex, n)
  mois_nationality.csv          — all country-based breakdowns with `group`
                                   (year, level, sido, sigungu, eupmyeondong, group, country, sex, n)
  mois_children_age.csv         — children by age 0-18
                                   (year, level, sido, sigungu, age, sex, n)
  mois_children_parent.csv      — children by parent type / parent nationality
                                   (year, level, sido, sigungu, eupmyeondong, parent_type, country, sex, n)
  mois_multicultural.csv        — multicultural household members (= old _eupmyeondong file)
  mois_immigration_dynamics.csv — residence period + naturalization period
                                   (year, sido, sigungu, dimension, dim_value, sex, n)

Kept as-is (specialty derived):
  mois_eupmyeondong_indices.csv
  mois_eupmyeondong_enclaves.csv
  mois_moj_validation.csv
  mois_region_keys.csv
  mois_coverage.csv

Per-epoch intermediates (mois_*_2006.csv, ..._2007_2010.csv, ...) are moved to
03_cleaned_data/_mois_archive/ for reproducibility/debugging but out of the way.
"""
from __future__ import annotations
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from kird import ROOT as _ROOT  # noqa: E402
import shutil
from pathlib import Path
import pandas as pd

ROOT = Path(_ROOT)
DATA = ROOT / "03_cleaned_data"
ARCHIVE = DATA / "_mois_archive"


def _safe_read(name: str) -> pd.DataFrame:
    p = DATA / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def build_population():
    """Merge mois_sido + mois_sigungu + mois_eupmyeondong → one long table with `level`."""
    sido = _safe_read("mois_sido.csv").assign(level="sido", sigungu="", eupmyeondong="")
    sigungu = _safe_read("mois_sigungu.csv").assign(level="sigungu", eupmyeondong="")
    emd = _safe_read("mois_eupmyeondong.csv").assign(level="eupmyeondong")
    if "sex" not in emd.columns:
        emd["sex"] = "total"

    # Add 세대수 from eupmyeondong file
    hh = _safe_read("mois_household_eupmyeondong.csv")
    if not hh.empty:
        hh["category"] = "세대수"
        hh["sex"] = "total"
        hh["level"] = "eupmyeondong"
        # ensure expected columns
        hh = hh[["year", "level", "sido", "sigungu", "eupmyeondong", "category", "sex", "n"]]

    cols = ["year", "level", "sido", "sigungu", "eupmyeondong", "category", "sex", "n"]
    parts = []
    for d in (sido, sigungu, emd, hh):
        if d.empty:
            continue
        for c in cols:
            if c not in d.columns:
                d[c] = ""
        parts.append(d[cols])
    out = pd.concat(parts, ignore_index=True)
    out = out.sort_values(["year", "level", "sido", "sigungu", "eupmyeondong", "category", "sex"])
    out.to_csv(DATA / "mois_population.csv", index=False, encoding="utf-8-sig")
    return len(out)


def build_nationality():
    """Merge all country-based files into one with a `group` field."""
    groups = []

    # All foreigners
    df = _safe_read("mois_nationality_sigungu.csv")
    if not df.empty:
        df = df.assign(group="all_foreign", level="sigungu", eupmyeondong="")
        groups.append(df)
    df = _safe_read("mois_nationality_eupmyeondong.csv")
    if not df.empty:
        df = df.assign(group="all_foreign", level="eupmyeondong")
        groups.append(df)

    # By visa type (e.g., 외국인근로자, 결혼이민자, 유학생, 외국국적동포, 기타외국인)
    visa_to_group = {
        "외국인근로자": "workers",
        "결혼이민자": "marriage",
        "유학생": "students",
        "외국국적동포": "overseas_koreans",
        "기타외국인": "other_foreign",
    }
    df = _safe_read("mois_nationality_by_visa_sigungu.csv")
    if not df.empty:
        df["group"] = df["visa_type"].map(visa_to_group).fillna(df["visa_type"])
        df = df.assign(level="sigungu", eupmyeondong="")
        df = df.drop(columns=["visa_type"])
        groups.append(df)
    df = _safe_read("mois_nationality_by_visa_eupmyeondong.csv")
    if not df.empty:
        df["group"] = df["visa_type"].map(visa_to_group).fillna(df["visa_type"])
        df = df.assign(level="eupmyeondong")
        df = df.drop(columns=["visa_type"])
        groups.append(df)

    # Naturalized × nationality
    for fname in ("mois_nationality_naturalized_sigungu.csv",
                  "mois_nationality_naturalized_eupmyeondong.csv"):
        df = _safe_read(fname)
        if df.empty:
            continue
        level = "eupmyeondong" if "eupmyeondong" in fname else "sigungu"
        df = df.assign(group="naturalized", level=level)
        if level == "sigungu":
            df["eupmyeondong"] = ""
        groups.append(df)

    # Children × nationality
    for fname in ("mois_nationality_children_sigungu.csv",
                  "mois_nationality_children_eupmyeondong.csv"):
        df = _safe_read(fname)
        if df.empty:
            continue
        level = "eupmyeondong" if "eupmyeondong" in fname else "sigungu"
        df = df.assign(group="children", level=level)
        if level == "sigungu":
            df["eupmyeondong"] = ""
        groups.append(df)

    # Naturalized × previous nationality (origin)
    df = _safe_read("mois_naturalized_prev_nationality_sigungu.csv")
    if not df.empty:
        df = df.assign(group="naturalized_prev", level="sigungu", eupmyeondong="")
        groups.append(df)

    cols = ["year", "level", "sido", "sigungu", "eupmyeondong", "group", "country", "sex", "n"]
    out_parts = []
    for d in groups:
        for c in cols:
            if c not in d.columns:
                d[c] = ""
        out_parts.append(d[cols])
    out = pd.concat(out_parts, ignore_index=True)
    out = out.sort_values(["year", "level", "group", "sido", "sigungu", "eupmyeondong", "country", "sex"])
    out.to_csv(DATA / "mois_nationality.csv", index=False, encoding="utf-8-sig")
    return len(out)


def build_children_age():
    sido = _safe_read("mois_children_age_sido.csv").assign(level="sido", sigungu="")
    sigungu = _safe_read("mois_children_age_sigungu.csv").assign(level="sigungu")
    cols = ["year", "level", "sido", "sigungu", "age", "sex", "n"]
    parts = []
    for d in (sido, sigungu):
        if d.empty:
            continue
        for c in cols:
            if c not in d.columns:
                d[c] = ""
        parts.append(d[cols])
    out = pd.concat(parts, ignore_index=True)
    out = out.sort_values(["year", "level", "sido", "sigungu", "age", "sex"])
    out.to_csv(DATA / "mois_children_age.csv", index=False, encoding="utf-8-sig")
    return len(out)


def build_children_parent():
    """Combine parent_type (외국인부모/외-한국인부모/한국인부모) sheets across levels.

    For 2014-2015 읍면동: each row carries parent_type + country.
    For 2016+ 시군구 (sheet 8-2): rows carry category (귀화·인지/국내출생, 합계). We map
    these to a `parent_type` of '귀화_인지' / '국내출생' / '합계' for unified shape.
    """
    parts = []

    df = _safe_read("mois_children_parent_type_eupmyeondong.csv")
    if not df.empty:
        df = df.rename(columns={"parent_type": "parent_type"})
        df = df.assign(level="eupmyeondong")
        parts.append(df)

    # 2016+ 시군구 sheet had `category` not `parent_type`. Reshape.
    df = _safe_read("mois_children_parent_type_sigungu.csv")
    if not df.empty:
        df = df.rename(columns={"category": "parent_type", "country": "_drop"})
        if "_drop" in df.columns:
            df = df.drop(columns=["_drop"])
        # No country dimension here — fill blank
        df = df.assign(country="", level="sigungu", eupmyeondong="")
        parts.append(df)

    cols = ["year", "level", "sido", "sigungu", "eupmyeondong", "parent_type", "country", "sex", "n"]
    out_parts = []
    for d in parts:
        for c in cols:
            if c not in d.columns:
                d[c] = ""
        out_parts.append(d[cols])
    if not out_parts:
        return 0
    out = pd.concat(out_parts, ignore_index=True)
    out = out.sort_values(["year", "level", "sido", "sigungu", "eupmyeondong",
                             "parent_type", "country", "sex"])
    out.to_csv(DATA / "mois_children_parent.csv", index=False, encoding="utf-8-sig")
    return len(out)


def build_multicultural():
    df = _safe_read("mois_multicultural_eupmyeondong.csv")
    if df.empty:
        return 0
    df = df.assign(level="eupmyeondong")
    cols = ["year", "level", "sido", "sigungu", "eupmyeondong", "category", "n"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    out = df[cols].sort_values(["year", "sido", "sigungu", "eupmyeondong", "category"])
    out.to_csv(DATA / "mois_multicultural.csv", index=False, encoding="utf-8-sig")
    return len(out)


def build_immigration_dynamics():
    """체류기간 + 국적취득경과기간 → single immigration_dynamics table."""
    parts = []

    df = _safe_read("mois_residence_period_sigungu.csv")
    if not df.empty:
        df = df.rename(columns={"country": "dim_value"})
        df["dimension"] = "residence_period"
        parts.append(df)

    df = _safe_read("mois_naturalization_period_sigungu.csv")
    if not df.empty:
        df = df.rename(columns={"category": "dim_value"})
        df["dimension"] = "naturalization_period"
        if "sex" not in df.columns:
            df["sex"] = "total"
        parts.append(df)

    cols = ["year", "sido", "sigungu", "dimension", "dim_value", "sex", "n"]
    out_parts = []
    for d in parts:
        for c in cols:
            if c not in d.columns:
                d[c] = "total" if c == "sex" else ""
        out_parts.append(d[cols])
    if not out_parts:
        return 0
    out = pd.concat(out_parts, ignore_index=True)
    out = out.sort_values(["year", "sido", "sigungu", "dimension", "dim_value", "sex"])
    out.to_csv(DATA / "mois_immigration_dynamics.csv", index=False, encoding="utf-8-sig")
    return len(out)


def archive_intermediates():
    """Move per-epoch CSVs and now-redundant files to _mois_archive/."""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    patterns = [
        # Per-epoch (already merged into mois_sido/sigungu/eupmyeondong.csv)
        "mois_sido_2006.csv", "mois_sido_2007_2010.csv", "mois_sido_2011_2013.csv",
        "mois_sido_2014_2015.csv", "mois_sido_2016_2024.csv",
        "mois_sigungu_2006.csv", "mois_sigungu_2007_2010.csv",
        "mois_sigungu_2011_2013.csv", "mois_sigungu_2014_2015.csv",
        "mois_sigungu_2016_2024.csv",
        "mois_eupmyeondong_2014_2015.csv", "mois_eupmyeondong_2016_2024.csv",
        "mois_multicultural_eupmyeondong_2016_2024.csv",
        # Now merged into thematic tidy CSVs above
        "mois_sido.csv", "mois_sigungu.csv", "mois_eupmyeondong.csv",
        "mois_multicultural_eupmyeondong.csv",
        "mois_nationality_sigungu.csv", "mois_nationality_eupmyeondong.csv",
        "mois_nationality_by_visa_sigungu.csv", "mois_nationality_by_visa_eupmyeondong.csv",
        "mois_nationality_naturalized_sigungu.csv", "mois_nationality_naturalized_eupmyeondong.csv",
        "mois_nationality_children_sigungu.csv", "mois_nationality_children_eupmyeondong.csv",
        "mois_naturalized_prev_nationality_sigungu.csv",
        "mois_children_age_sido.csv", "mois_children_age_sigungu.csv",
        "mois_children_parent_type_eupmyeondong.csv", "mois_children_parent_type_sigungu.csv",
        "mois_residence_period_sigungu.csv", "mois_naturalization_period_sigungu.csv",
        "mois_household_eupmyeondong.csv",
        "mois_region_keys_dedup.csv",
    ]
    moved = []
    for name in patterns:
        p = DATA / name
        if p.exists():
            shutil.move(str(p), str(ARCHIVE / name))
            moved.append(name)
    print(f"Archived {len(moved)} intermediate files → {ARCHIVE.name}/")
    return moved


def main():
    print("Building tidy thematic MOIS CSVs...\n")
    counts = {
        "mois_population.csv": build_population(),
        "mois_nationality.csv": build_nationality(),
        "mois_children_age.csv": build_children_age(),
        "mois_children_parent.csv": build_children_parent(),
        "mois_multicultural.csv": build_multicultural(),
        "mois_immigration_dynamics.csv": build_immigration_dynamics(),
    }
    for name, n in counts.items():
        print(f"  {name}: {n:,} rows")
    print()
    archive_intermediates()


if __name__ == "__main__":
    main()
