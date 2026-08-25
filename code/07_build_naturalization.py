"""Nationality processing (국적처리), from every yearbook edition to three panels.

Chapter 4 of each yearbook carries only that edition's own by-country and by-age
tables, so the panel step reads all seventeen editions; the annual series comes
from the trend table inside the newest one, which prints every year at once. The
export then writes the three released files.

  naturalization_annual.csv      year x processing type
  naturalization_by_country.csv  year x former nationality x processing type
  naturalization_by_age.csv      year x ten-year age band x processing type
"""
import csv
import glob
import json
import os
import re

import pandas as pd

from kird import COUNTRY_CANONICAL
from kird import COUNTRY_REGION
from kird import CLEAN
from kird import CODE
from kird import LAST_YEAR
from kird import RAW
from kird import RELEASE_DATA
from kird import SITE_DATA


def build_panel():
    """Nationality-processing (국적처리) panel from every yearbook edition.

    Chapter 4 of each yearbook carries that edition's own by-country and by-age
    tables, so reading only the newest edition yields one year. Reading all of them
    yields a panel. The layout changes four times across 2009-2025 (this build stops at 2024):

      2009-2013  title rows above the header; label column 국가 / 국적명; one 귀화
                 column with no general/simplified/special split.
      2014-2018  header on the first row; 국적명 / 합계 / 귀화소계 then the split.
      2019, 2021-2024  the label columns carry no header at all; the header row
                 starts at 총합계.
      2020, 2025  two label columns (대륙, 국적), both filled on every row in 2025.

    Age bands are labelled four different ways (0~10세 / 0~10 / a bare 10 / 0세~9세)
    but every edition publishes the same eleven ten-year bins in the same order, so
    they are harmonized by position and the canonical label is written out.

    Output (long, one row per year x unit x processing type):
      03_cleaned_data/naturalization_by_country_long.csv
      03_cleaned_data/naturalization_by_age_long.csv

    Each year is checked against that year's 연도별 추이 table, which publishes the
    same totals independently.
    """
    YB = os.path.join(RAW, "출입국통계연보")
    YEARS = range(2009, LAST_YEAR + 1)

    # canonical ten-year bins, in publication order
    AGE_BANDS = ["0-9", "10-19", "20-29", "30-39", "40-49", "50-59",
                 "60-69", "70-79", "80-89", "90+"]

    TOTAL_LABELS = {"총계", "총합계", "합계", "계", "소계", "총  계", "연  령", "연령", "Age",
                    "국가", "국적명", "국적", "대륙", "국적･지역", "국적(지역)", "구분", "nan", ""}
    CONTINENT_TOKENS = ("아시아주", "북아메리카주", "남아메리카주", "유럽주", "아프리카주",
                        "오세아니아주", "아시아", "북아메리카", "남아메리카", "유럽",
                        "아프리카", "오세아니아")


    def is_total(label):
        """A row total, however the edition dresses it up: 총계, 총계(Total), 합계 …"""
        return bool(re.match(r"^(총합계|총계|합계|계)(\(|\[|$)", label))


    def is_aggregate(label):
        """A subtotal row: 아시아주, 아시아주소계, 유럽주 소계, 기타계 …"""
        if label.endswith(("소계", "총계", "합계", "기타계")):
            return True
        if label.startswith("기타소계"):
            return True
        return any(label.startswith(t) for t in CONTINENT_TOKENS)


    # published type columns, in the order they should appear in the output
    TYPES = ["총계", "총합계", "합계", "계",
             "귀화소계", "일반귀화", "간이귀화", "특별귀화", "수반취득", "귀화",
             "국적회복", "국적판정", "국적상실", "국적이탈", "국적취득(인지)",
             "국적취득(재취득)", "국적취득", "국적선택", "국적보유"]

    CANON, REGION = COUNTRY_CANONICAL, COUNTRY_REGION


    def norm(x):
        return re.sub(r"\s+", "", str(x)) if pd.notna(x) else ""


    def num(x):
        s = str(x).replace(",", "").split("\n")[0].strip()
        if s in ("", "nan", "-", "‐"):
            return None
        try:
            return int(float(s))
        except ValueError:
            return None


    def find_file(year, kind):
        """The chapter-4 by-country or by-age workbook for one edition."""
        want, avoid = ("연령", "국적") if kind == "age" else ("국적", "연령")
        hits = []
        for f in sorted(glob.glob(os.path.join(YB, f"{year}_출입국통계연보", "*"))):
            b = os.path.basename(f)
            if not b.endswith((".xls", ".xlsx")) or "4장" not in b:
                continue
            stem = b.replace("국적처리", "").replace("국적 처리", "")
            if kind == "country" and "국가" in b and "연령" not in b:
                hits.append(f)
            elif want in stem and avoid not in stem:
                hits.append(f)
        return hits[0] if hits else None


    def header_row(df):
        """Row index whose cells name the processing types."""
        for r in range(min(8, len(df))):
            cells = {norm(v) for v in df.iloc[r].tolist()}
            if sum(1 for c in cells if c in TYPES and c not in ("총계", "총합계", "합계", "계")) >= 2:
                return r
        return None


    def parse(path, kind):
        df = pd.read_excel(path, header=None)
        hr = header_row(df)
        if hr is None:
            return []
        head = [norm(v) for v in df.iloc[hr].tolist()]
        type_cols = {c: head[c] for c in range(len(head)) if head[c] in TYPES}
        if not type_cols:
            return []
        first_type = min(type_cols)
        rows, band = [], 0
        for r in range(hr + 1, df.shape[0]):
            labels = [norm(df.iat[r, c]) for c in range(first_type)]
            vals = {t: num(df.iat[r, c]) for c, t in type_cols.items()}
            if not any(v is not None for v in vals.values()):
                continue
            if kind == "age":
                # bands come in publication order; the source labels them four
                # different ways, so position is the only stable key
                if any(is_total(l) for l in labels):
                    continue
                if band >= len(AGE_BANDS):
                    continue
                unit = AGE_BANDS[band]
                band += 1
            else:
                # 2009-2013 print the English name in a second label column, so the
                # unit is the Korean one: everything in this project keys on it
                name = next((l for l in labels
                             if l and re.search(r"[가-힣]", l)
                             and l not in TOTAL_LABELS and not is_total(l)
                             and not is_aggregate(l)), None)
                if not name:
                    continue
                # a bracketed label is a memo row for a group already counted in the
                # line above it (2017 prints (타이완) and (홍콩) inside 중국), so adding
                # it would double count
                if name.startswith("("):
                    continue
                name = re.sub(r"\d\)$", "", name)          # footnote markers: 중국1)
                unit = CANON.get(name, name)
            for t, v in vals.items():
                if v is not None:
                    rows.append((unit, t, v))
        return rows


    def main():
        out_c, out_a, report = [], [], []
        for y in YEARS:
            for kind, sink in (("country", out_c), ("age", out_a)):
                f = find_file(y, kind)
                if not f:
                    report.append((y, kind, "FILE NOT FOUND", 0, 0))
                    continue
                rows = parse(f, kind)
                agg = {}
                for unit, t, v in rows:
                    agg[(unit, t)] = agg.get((unit, t), 0) + v
                # 귀화소계 = 일반 + 간이 + 특별 + 수반취득, the definition the annual
                # table uses for 귀화; derive it where the edition splits the routes
                units = {u for u, _ in agg}
                for u in units:
                    parts = [agg.get((u, t)) for t in ("일반귀화", "간이귀화", "특별귀화", "수반취득")]
                    if any(p is not None for p in parts):
                        agg[(u, "귀화소계")] = sum(p or 0 for p in parts)
                for (unit, t), v in sorted(agg.items()):
                    sink.append({"year": y, ("country" if kind == "country" else "age"): unit,
                                 "type": t, "n": v})
                natz = (sum(v for (u, t), v in agg.items() if t == "귀화소계")
                        or sum(v for (u, t), v in agg.items() if t == "귀화"))
                report.append((y, kind, os.path.basename(f)[:36], len(units), natz))

        for name, rows, key in (("naturalization_by_country_long.csv", out_c, "country"),
                                ("naturalization_by_age_long.csv", out_a, "age")):
            df = pd.DataFrame(rows).sort_values(["year", key, "type"])
            p = os.path.join(CLEAN, name)
            df.to_csv(p, index=False, encoding="utf-8-sig")
            print(f"{name}: {len(df):,} rows, {df.year.min()}-{df.year.max()}, "
                  f"{df[key].nunique()} {key} values")

        print("\nper-edition parse:")
        for y, kind, f, n_units, natz in report:
            print(f"  {y} {kind:<8} {n_units:>4} units  naturalizations {natz:>8,}  [{f}]")

        # control: the 연도별 추이 table publishes the same yearly totals independently
        ann = json.load(open(os.path.join(SITE_DATA, "data.json"), encoding="utf-8")) \
            ["naturalization_data"]["annual"]
        cdf, adf = pd.DataFrame(out_c), pd.DataFrame(out_a)

        def natz_of(df, y):
            sub = df[df.year == y]
            return int(sub[sub.type == "귀화소계"].n.sum() or sub[sub.type == "귀화"].n.sum())

        print("\nagainst the 연도별 추이 control (귀화 = 일반+간이+특별+수반취득):")
        print(f"  {'year':<6}{'control':>9}{'by country':>12}{'diff':>7}{'by age':>10}{'diff':>7}")
        off = []
        for y in YEARS:
            ref = (ann.get(str(y)) or {}).get("귀화")
            c, a_ = natz_of(cdf, y), natz_of(adf, y)
            dc = c - ref if ref else None
            da = a_ - ref if ref else None
            print(f"  {y:<6}{(ref if ref else '-'):>9}{c:>12,}"
                  f"{(dc if dc is not None else '-'):>7}{a_:>10,}{(da if da is not None else '-'):>7}")
            if ref and abs(dc) > 10:
                off.append((y, dc))
        if off:
            print(f"\n  NOTE {off}: that edition's own country rows do not sum to its printed\n"
                  f"  continent subtotals. Published as issued.")

    main()



def export_panels():
    """Released nationality-processing tables, one panel per breakdown.

    Source: yearbook chapter 4 (국적처리). The annual series comes from the trend
    table inside the newest edition, which prints every year at once; the by-country
    and by-age panels come from `07_build_naturalization.py`, which reads every
    edition, because each one publishes only its own year.

      naturalization_annual.csv      year x processing type
      naturalization_by_country.csv  year x former nationality x processing type
      naturalization_by_age.csv      year x ten-year age band x processing type

    All three are long. The processing types differ by era: editions before 2014
    publish a single 귀화 column, later ones split it into 일반 / 간이 / 특별 plus
    수반취득, and 귀화소계 is derived as their sum wherever the split exists, which is
    the definition the annual table uses. A rate against the registered population is
    left to the user, who can join visa_by_nationality on year and country.
    """
    TYPE_EN = {"귀화소계": "Naturalization, all routes",
               "일반귀화": "General naturalization", "간이귀화": "Simplified naturalization",
               "특별귀화": "Special naturalization", "수반취득": "Acquired by family",
               "국적회복": "Restoration of nationality", "국적상실": "Loss of nationality",
               "국적이탈": "Renunciation", "국적취득(인지)": "Acquisition (recognition)",
               "국적취득(재취득)": "Re-acquisition", "국적취득 (인지)": "Acquisition (recognition)",
               "국적취득 (재취득)": "Re-acquisition", "국적판정": "Nationality determination",
               "국적선택": "Nationality choice", "국적보유": "Nationality retention",
               "국적취득": "Acquisition of nationality",
               "귀화": "Naturalization", "회복": "Restoration",
               "총계": "Total", "총합계": "Total", "합계": "Total", "계": "Total"}

    D = json.load(open(os.path.join(SITE_DATA, "data.json"), encoding="utf-8"))
    COUNTRY_EN = dict(D.get("country_en", {}))
    # origins that appear only in the nationality-processing tables, so the
    # dashboard's country map has no entry for them
    COUNTRY_EN.setdefault("기타", "Other")
    COUNTRY_EN.setdefault("무국적", "Stateless")
    COUNTRY_EN.setdefault("북한", "North Korea")
    COUNTRY_EN.setdefault("한국", "Republic of Korea")
    COUNTRY_EN.setdefault("케이맨제도", "Cayman Islands")


    def w(fn, head, rows):
        with open(os.path.join(RELEASE_DATA, fn), "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(head)
            wr.writerows(rows)
        years = {r[0] for r in rows}
        print(f"  {fn}: {len(rows):,} rows, {min(years)}-{max(years)}")


    # ---- annual (the trend table prints every year) ----
    rows = []
    for y, yd in sorted(D["naturalization_data"]["annual"].items(), key=lambda kv: int(kv[0])):
        for typ, n in yd.items():
            rows.append([int(y), typ, TYPE_EN.get(typ, ""), n])
    w("naturalization_annual.csv", ["year", "type", "type_en", "n"], rows)

    # ---- by country and by age, panels across every edition ----
    c = pd.read_csv(os.path.join(CLEAN, "naturalization_by_country_long.csv"))
    c = c[~c["type"].isin(("총계", "총합계", "합계", "계"))]
    w("naturalization_by_country.csv", ["year", "country", "country_en", "type", "type_en", "n"],
      [[int(r.year), r.country, COUNTRY_EN.get(r.country, ""), r.type, TYPE_EN.get(r.type, ""), int(r.n)]
       for r in c.sort_values(["year", "country", "type"]).itertuples()])

    a = pd.read_csv(os.path.join(CLEAN, "naturalization_by_age_long.csv"))
    a = a[~a["type"].isin(("총계", "총합계", "합계", "계"))]
    w("naturalization_by_age.csv", ["year", "age", "type", "type_en", "n"],
      [[int(r.year), r.age, r.type, TYPE_EN.get(r.type, ""), int(r.n)]
       for r in a.sort_values(["year", "age", "type"]).itertuples()])

    print("done. Types differ by era; 귀화소계 = 일반+간이+특별+수반취득 where the split exists.")


if __name__ == "__main__":
    build_panel()
    export_panels()
