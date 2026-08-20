"""Parser for 서울특별시 등록외국인 현황 (국적별 동별) — Seoul Open Data CSV.

Source: https://www.data.go.kr/data/15146338/fileData.do
The file must be downloaded manually (data.go.kr download requires browser/login).
Drop the CSV into 01_raw_data/서울_등록외국인_동별/.

This parser auto-detects column layout and writes a long-format CSV:
  03_cleaned_data/mois_seoul_dong_nationality.csv
  schema: ref_date, sigungu, eupmyeondong, country, n

If multiple CSV files are present in the folder, all are merged (different
reference dates / quarters).
"""
from __future__ import annotations
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from kird import ROOT as _ROOT  # noqa: E402
from pathlib import Path
import re
import pandas as pd

ROOT = Path(_ROOT)
RAW = ROOT / "01_raw_data" / "서울_등록외국인_동별"
OUT = ROOT / "03_cleaned_data" / "mois_seoul_dong_nationality.csv"


def _detect_ref_date(fname: str) -> str:
    """Extract YYYYMMDD or YYYY-MM-DD reference date from filename."""
    m = re.search(r"(\d{8})", fname)
    if m:
        s = m.group(1)
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    m = re.search(r"(\d{4}[-_]\d{1,2}[-_]\d{1,2})", fname)
    if m:
        return m.group(1).replace("_", "-")
    return ""


def _parse_one(path: Path) -> pd.DataFrame:
    """Parse a single Seoul registered-foreigner CSV.

    Expected wide format (likely):
      자치구, 행정동, 합계, 중국, 미국, 베트남, ... (one column per country)
    Or long format already. Auto-detect.
    """
    # Try common encodings
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(path, encoding=enc, low_memory=False)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        raise RuntimeError(f"Could not read {path} with common encodings")

    # Normalize column names
    df.columns = [str(c).strip().replace("\n", "") for c in df.columns]

    # Detect format: if there's a 'country' or '국적' column → already long
    long_cols = [c for c in df.columns if c in ("country", "국적", "국적별")]
    if long_cols:
        # Already long; standardize column names
        rename = {}
        for c in df.columns:
            cl = c.lower()
            if c in ("자치구", "구"): rename[c] = "sigungu"
            elif c in ("행정동", "동", "동명"): rename[c] = "eupmyeondong"
            elif c in long_cols: rename[c] = "country"
            elif c in ("계", "합계", "인원", "총계"): rename[c] = "n"
        df = df.rename(columns=rename)
        keep = [c for c in ["sigungu", "eupmyeondong", "country", "n"] if c in df.columns]
        df = df[keep].copy()
    else:
        # Wide format — region cols + many country cols. Melt.
        # Identify region columns by name
        region_cols = []
        for cand in ("자치구", "행정동", "동", "구", "동명"):
            if cand in df.columns:
                region_cols.append(cand)
        if not region_cols:
            # Heuristic: first 2 columns are region
            region_cols = list(df.columns[:2])
        # Optional 합계 column to drop
        drop_cols = [c for c in ("합계", "계", "총계") if c in df.columns]
        value_cols = [c for c in df.columns if c not in region_cols and c not in drop_cols]
        df = df.melt(id_vars=region_cols, value_vars=value_cols,
                     var_name="country", value_name="n")
        # Normalize region col names
        ren = {}
        for c in region_cols:
            if c in ("자치구", "구"): ren[c] = "sigungu"
            elif c in ("행정동", "동", "동명"): ren[c] = "eupmyeondong"
        df = df.rename(columns=ren)

    # Coerce n to numeric
    df["n"] = pd.to_numeric(df["n"], errors="coerce")
    df = df.dropna(subset=["n"])
    df["n"] = df["n"].astype(int)
    # Add ref_date
    df["ref_date"] = _detect_ref_date(path.name)
    # Final column order
    final_cols = ["ref_date", "sigungu", "eupmyeondong", "country", "n"]
    for c in final_cols:
        if c not in df.columns:
            df[c] = ""
    df = df[final_cols]
    return df


def main():
    if not RAW.exists():
        RAW.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(list(RAW.glob("*.csv")) + list(RAW.glob("*.CSV")))
    if not csv_files:
        print(f"[NOTE] No CSV files in {RAW}.")
        print("Download CSV from https://www.data.go.kr/data/15146338/fileData.do")
        print("and place into the above folder, then re-run.")
        return
    parts = []
    for f in csv_files:
        print(f"  parsing {f.name}")
        try:
            df = _parse_one(f)
            print(f"    → {len(df):,} rows")
            parts.append(df)
        except Exception as e:
            print(f"    ERROR: {e}")
    if not parts:
        return
    out = pd.concat(parts, ignore_index=True)
    out = out.sort_values(["ref_date", "sigungu", "eupmyeondong", "country"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\nWrote {OUT}  ({len(out):,} rows; {out['ref_date'].nunique()} reference dates)")


if __name__ == "__main__":
    main()
