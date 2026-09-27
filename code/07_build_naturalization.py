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


AGE_BANDS = ["0-9", "10-19", "20-29", "30-39", "40-49", "50-59",
             "60-69", "70-79", "80-89", "90+"]

# the 총계 row each parsed table prints, keyed by (file name, kind); filled by parse()
PRINTED_TOTALS = {}

# 2026-09-26: the panels start with the 2011 edition. The 2009 and 2010 editions'
# by-country and by-age tables are cumulative, 1991 to the edition year: their
# 총계 rows (363,131 and 405,170) equal the 총계(Total) line under each edition's
# own 연도별 추이 table, while that table's single-year rows read 49,820 (2009) and
# 42,039 (2010). Until this date the release carried them as if they were annual.
# The gate in build_panel() compares every edition's detail total with the
# single-year row of its own trend table and stops on a cumulative table.
# The earlier editions give no single year either (5라운드 대조, 2026-09-27): the 2006
# and 2007 by-country and by-age tables are cumulative in the same way (총계 242,374
# and 278,713, each equal to its trend table's 총계 line, against the single-year
# 31,069 and 36,339; the 2006 edition keeps them under 3장/ as 3-나 and 3-다, 2007
# as 4-Ⅱ-2 and 4-Ⅱ-3), and 01_raw_data holds no naturalization table of the 2008
# edition, whose folder has chapters 1, 2, 5, 7 and 8 only. So 2011 is the first
# edition that can open the panel, not only the first after 2009-2010.
PANEL_FIRST_YEAR = 2011


def age_band_from_label(label):
    """The ten-year band a chapter-4 age row belongs to, read from its own label.

    The editions print the same ten bands five ways:
      0~10세Years, 11~20, 21~30 ... 91세이상   (2009-2011, 2017, 2020 as 0-10세, 11~20 ...)
      0~10Years, 10~20, 20~30 ... 80~90, 91세이상   (2012-2013)
      10, 20, 30 ... 90, 99   (2014-2016, 2018-2019, 2023-2024): the upper bound
      0세~9세, 10세~19세 ... 90세이상   (2021-2022, 2025)
    Returns one of AGE_BANDS, or raises ValueError on a label it cannot place.
    """
    s = re.sub(r"\s+", "", str(label))
    s = re.sub(r"(Years?&?over|Years?|&over)$", "", s, flags=re.I)

    def band(lo):
        if lo >= 90:
            return "90+"
        if lo % 10 or not 0 <= lo <= 80:
            raise ValueError(f"age label {label!r}: lower bound {lo}")
        return f"{lo}-{lo + 9}"

    m = re.fullmatch(r"(\d+)세?이상", s)
    if m and int(m.group(1)) in (90, 91):
        return "90+"
    m = re.fullmatch(r"(\d+)세~(\d+)세", s)                 # 0세~9세: both bounds exact
    if m and int(m.group(2)) - int(m.group(1)) == 9:
        return band(int(m.group(1)))
    m = re.fullmatch(r"(\d+)(?:세)?[~-](\d+)(?:세)?", s)     # 0~10세, 11~20, 10~20, 0-10세
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo % 10 == 1 and hi - lo == 9:                  # 11~20 -> 10-19
            return band(lo - 1)
        if lo % 10 == 0 and hi - lo == 10:                 # 0~10, 10~20 -> 0-9, 10-19
            return band(lo)
    m = re.fullmatch(r"(\d+)", s)                         # bare upper bound: 10 -> 0-9
    if m:
        n = int(m.group(1))
        if n == 99:
            return "90+"
        if n % 10 == 0 and 10 <= n <= 90:
            return band(n - 10)
    raise ValueError(f"age label {label!r} matches no known convention")


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

    Age bands are labelled five different ways (0~10세 / 0~10 / 0-10세 / a bare 10 /
    0세~9세), but every edition publishes the same ten bins, youngest first. Each
    row's band is read from its own printed label by `age_band_from_label`, and the
    build stops if that band is not the one the row's position implies or if an
    edition does not print exactly ten bands. A bare numeral is the band's upper
    bound (10 = 0-9, ..., 90 = 80-89, 99 = 90 and over): the 2021, 2022 and 2025
    editions print the same table with explicit 0세~9세 labels, and 수반취득
    (acquisition by a parent's naturalization, i.e. minors) sits in the bare-10
    row of 2014-2019 and 2023-2024 exactly as it sits in the 0세~9세 row of those
    editions.

    Output (long, one row per year x unit x processing type):
      03_cleaned_data/naturalization_by_country_long.csv
      03_cleaned_data/naturalization_by_age_long.csv

    Each year is checked against that year's 연도별 추이 table, which publishes the
    same totals independently.
    """
    YB = os.path.join(RAW, "출입국통계연보")
    YEARS = range(PANEL_FIRST_YEAR, LAST_YEAR + 1)


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
    # 2014-2018 print the two acquisition routes under short headers; without the
    # alias those columns were silently dropped from both panels
    TYPE_ALIAS = {"취득인지": "국적취득(인지)", "재취득": "국적취득(재취득)"}
    # a parent row footnoted "한국계 포함" (2017) already contains this subgroup row
    KOREAN_SUB = {"중국": "한국계중국인", "러시아(연방)": "한국계러시아인"}

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


    def trend_total(year):
        """The single-year 총계 the edition's own 연도별 추이 table prints for `year`."""
        for f in sorted(glob.glob(os.path.join(YB, f"{year}_출입국통계연보", "*"))):
            b = os.path.basename(f)
            if (not b.endswith((".xls", ".xlsx")) or "4장" not in b or "불허" in b
                    or not ("추이" in b or "연도별" in b)):
                continue
            df = pd.read_excel(f, header=None)
            for r in range(df.shape[0]):
                cells = [str(v).strip() for v in df.iloc[r].tolist()]
                for c in range(min(3, len(cells))):
                    if cells[c] in (str(year), f"{year}.0", f"{year}년"):
                        nums = [num(v) for v in cells[c + 1:]]
                        nums = [n for n in nums if n is not None]
                        if nums:
                            return nums[0]
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


    TOTAL_TYPES = ("총계", "총합계", "합계", "계")

    def fill_blanks(vals, where):
        """A printed row's empty cells, read as the zeros they are.

        The 2019, 2020 and 2024 by-country tables and the 2019, 2020, 2023 and 2024
        by-age tables leave a cell empty where every other edition prints 0 (2024
        mixes the two within a row). Until 2026-09-26 (final audit) an empty cell
        wrote no row, so in those years a missing row meant zero while in the others
        a zero was a row: 2019 by country had 409 rows over 103 countries where the
        same grid is 1,339 rows in 2018. A blank is read as 0 only when the row's own
        printed total equals the sum of its printed cells, so the zeros are the
        table's arithmetic and not a guess; otherwise the build stops.
        """
        blanks = [t for t, v in vals.items() if v is None and t not in TOTAL_TYPES]
        if not blanks:
            return vals
        tot = next((vals[t] for t in TOTAL_TYPES if vals.get(t) is not None), None)
        if tot is None:
            raise SystemExit(f"{where}: empty cells {blanks} and no row total to "
                             f"check them against")
        # 귀화소계 is the sum of the four routes where the edition prints them
        # (2014-2018), and a cell of its own where it does not (the 2014 age table)
        split = any(t in vals for t in ("일반귀화", "간이귀화", "특별귀화", "수반취득"))
        leaves = [t for t in vals if t not in TOTAL_TYPES
                  and not (t == "귀화소계" and split)]
        got = sum(vals[t] or 0 for t in leaves)
        if got != tot:
            raise SystemExit(f"{where}: the row total {tot} is not the sum of its printed "
                             f"cells ({got}), so the empty cells {blanks} cannot be read "
                             f"as zeros")
        return {t: (0 if v is None and t not in TOTAL_TYPES else v) for t, v in vals.items()}

    def header_row(df):
        """Row index whose cells name the processing types."""
        for r in range(min(8, len(df))):
            cells = {TYPE_ALIAS.get(norm(v), norm(v)) for v in df.iloc[r].tolist()}
            if sum(1 for c in cells if c in TYPES and c not in ("총계", "총합계", "합계", "계")) >= 2:
                return r
        return None


    def parse(path, kind):
        df = pd.read_excel(path, header=None)
        hr = header_row(df)
        if hr is None:
            return []
        head = [TYPE_ALIAS.get(norm(v), norm(v)) for v in df.iloc[hr].tolist()]
        type_cols = {c: head[c] for c in range(len(head)) if head[c] in TYPES}
        if not type_cols:
            return []
        first_type = min(type_cols)
        # footnotes such as "1) 한국계 포함, 2) 한국계러시아인 포함" (2017)
        notes = {m for r in range(df.shape[0]) for c in range(min(3, df.shape[1]))
                 for m, _ in re.findall(r"(\d)\)([^,\d]*포함)", norm(df.iat[r, c]))}
        recs = []
        for r in range(hr + 1, df.shape[0]):
            labels = [norm(df.iat[r, c]) for c in range(first_type)]
            vals = {t: num(df.iat[r, c]) for c, t in type_cols.items()}
            if any(v is not None for v in vals.values()):
                recs.append((labels, vals))
        rows, band, folded = [], 0, set()
        for i, (labels, vals) in enumerate(recs):
            if kind == "age":
                if any(is_total(l) for l in labels):
                    continue
                # 2026-09-26: the band is read from the row's own label, and the
                # position is only a cross-check. An audit read the bare numerals
                # (10, 20, ... 99) as lower bounds and took the panel for shifted;
                # this makes the reading explicit and stops the build if a future
                # edition drops or adds a band.
                label = next((l for l in labels if l), "")
                if not label and not any(vals.values()):
                    continue        # 2024: an unlabelled trailing row holding a lone 0
                try:
                    unit = age_band_from_label(label)
                except ValueError as e:
                    raise SystemExit(f"{os.path.basename(path)}: {e} (row values {vals})")
                if band >= len(AGE_BANDS) or unit != AGE_BANDS[band]:
                    raise SystemExit(f"{os.path.basename(path)}: age row {band + 1} is "
                                     f"labelled {label!r} -> {unit}, expected "
                                     f"{AGE_BANDS[band] if band < len(AGE_BANDS) else 'no more rows'}")
                band += 1
            else:
                # the rightmost filled label is the row's own: 2019 and 2024 repeat
                # the continent (and 기타) in the first column on every row
                last = next((l for l in reversed(labels) if l), "")
                if is_total(last) or is_aggregate(last) or last in TOTAL_LABELS:
                    # a 기타 subtotal with no rows under it (2014, 2017, 2018, 2020,
                    # 2021) is itself the residual unit
                    nxt = recs[i + 1][0] if i + 1 < len(recs) else None
                    nlast = next((l for l in reversed(nxt) if l), "") if nxt else ""
                    if any(l.startswith("기타") for l in labels) and (
                            nxt is None or is_total(nlast) or is_aggregate(nlast)):
                        unit = "기타"
                    else:
                        continue
                else:
                    # 2009-2013 print the English name in a second label column, so
                    # the unit is the Korean one: everything in this project keys on it
                    name = next((l for l in reversed(labels)
                                 if l and re.search(r"[가-힣]", l)
                                 and l not in TOTAL_LABELS and not is_total(l)
                                 and not is_aggregate(l)), None)
                    if not name:
                        continue
                    m = re.search(r"(\d)\)$", name)            # footnote markers: 중국1)
                    name = re.sub(r"\d\)$", "", name)
                    # 2017 brackets (타이완) and (홍콩); they are separate units and the
                    # 아시아주 소계 (9,942) only closes with them added
                    if name.startswith("(") and name.endswith(")"):
                        name = name[1:-1]
                    unit = CANON.get(name, name)
                    if m and m.group(1) in notes:
                        folded.add(unit)
            vals = fill_blanks(vals, f"{os.path.basename(path)} {kind} row {unit!r}")
            for t, v in vals.items():
                if v is not None:
                    rows.append((unit, t, v))
        # take the 한국계 subgroup back out of a parent printed "한국계 포함", so 중국
        # means China excluding Korean-Chinese in every edition
        if kind == "age" and band != len(AGE_BANDS):
            raise SystemExit(f"{os.path.basename(path)}: {band} age bands, expected "
                             f"{len(AGE_BANDS)}")
        # the edition's own 총계 row, per type: the units must add up to it
        tot = next((vals for labels, vals in recs if any(is_total(l) for l in labels)), {})
        for parent in folded:
            child = KOREAN_SUB.get(parent)
            sub = {t: v for u, t, v in rows if u == child}
            if sub:
                rows = [(u, t, v - sub.get(t, 0)) if u == parent else (u, t, v)
                        for u, t, v in rows]
        PRINTED_TOTALS[(os.path.basename(path), kind)] = {
            t: v for t, v in tot.items() if v is not None}
        return rows


    # 판 안의 어긋남: 연령표 칸들의 합이 그 표가 찍은 총계와 다른 곳. 원자료 그대로다.
    # (year, kind, type, panel - printed)
    # Both read in the raw files: 2014's country rows for 일반귀화 add to 299 against a
    # printed 계 of 298 (the 아시아주 소계 prints 291 over rows that sum to 292), and
    # 2017's continent subtotals for 간이귀화 add to 6,745 against a printed 총계 of
    # 6,742.
    EDITION_RESIDUAL = {(2014, "country", "일반귀화", 1), (2017, "country", "간이귀화", 3)}
    edition_off = []

    def main():
        out_c, out_a, report = [], [], []
        for y in YEARS:
            for kind, sink in (("country", out_c), ("age", out_a)):
                f = find_file(y, kind)
                if not f:
                    report.append((y, kind, "FILE NOT FOUND", 0, 0))
                    continue
                rows = parse(f, kind)
                # 관문: 이 표가 한 해 치인가. 2006·2007·2009·2010년판 상세표는
                # 1991년부터의 누계다(위 PANEL_FIRST_YEAR). 같은 판 추이표의 그 해 행과 댄다.
                printed_all = next((v for t, v in PRINTED_TOTALS.get(
                    (os.path.basename(f), kind), {}).items()
                    if t in ("총계", "총합계", "합계", "계")), None)
                single = trend_total(y)
                if printed_all is None or single is None:
                    raise SystemExit(f"{y} {kind}: no 총계 row ({printed_all}) or no "
                                     f"single-year trend row ({single}) to check against")
                if printed_all > 1.5 * single:
                    raise SystemExit(f"{y} {kind}: the table's 총계 {printed_all:,} is "
                                     f"{printed_all / single:.1f}x the edition's own "
                                     f"{y} trend row {single:,}; a cumulative table, "
                                     f"not one year")
                agg = {}
                for unit, t, v in rows:
                    agg[(unit, t)] = agg.get((unit, t), 0) + v
                # an edition with no 한국계 row (2018) folds it into the parent with no
                # split printed; key it apart so no series mixes the two definitions
                if kind == "country":
                    present = {u for u, _ in agg}
                    for parent, child in KOREAN_SUB.items():
                        if parent in present and child not in present:
                            combo = f"{parent}+{child}"
                            agg = {((combo if u == parent else u), t): v
                                   for (u, t), v in agg.items()}
                # 귀화소계 = 일반 + 간이 + 특별 + 수반취득, the definition the annual
                # table uses for 귀화; derive it where the edition splits the routes
                units = {u for u, _ in agg}
                for u in units:
                    if (u, "귀화소계") in agg:
                        continue        # printed 2014-2018; derive only where absent
                    parts = [agg.get((u, t)) for t in ("일반귀화", "간이귀화", "특별귀화", "수반취득")]
                    if any(p is not None for p in parts):
                        agg[(u, "귀화소계")] = sum(p or 0 for p in parts)
                for (unit, t), v in sorted(agg.items()):
                    sink.append({"year": y, ("country" if kind == "country" else "age"): unit,
                                 "type": t, "n": v})
                # 2026-09-26 관문: 단위들의 합이 그 판이 스스로 찍은 총계 행과 같아야
                # 한다(유형마다). 파서가 행을 빠뜨리거나 두 번 세면 여기서 멈춘다.
                printed = PRINTED_TOTALS.get((os.path.basename(f), kind), {})
                for t, v in printed.items():
                    if t in ("총계", "총합계", "합계", "계"):
                        continue
                    got = sum(n for (u, tt), n in agg.items() if tt == t)
                    if got != v and (y, kind, t, got - v) not in EDITION_RESIDUAL:
                        edition_off.append((y, kind, t, got, v))
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

        if edition_off:
            raise SystemExit(f"a parsed table does not add up to the 총계 row its own "
                             f"edition prints (year, kind, type, parsed, printed): "
                             f"{edition_off}")

        # 원자료 자체의 어긋남. 2012년판 연령표의 칸 합이 제 총계보다 1 적다.
        AGE_RAW_RESIDUAL = {(2012, -1)}

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
            # 2026-09-25: 관문. 전에는 10 명을 넘을 때만 「NOTE」를 찍고 넘어갔다.
            # 그래서 2017년 +1,357(중국 행이 「한국계 포함」인데 한국계중국인을 또
            # 더했다)이 「원자료가 그렇다」는 설명과 함께 실렸다. 원자료의 총계는
            # 연도별 추이 표와 해마다 같다. 차이는 파서의 몫이므로 0 이어야 한다.
            if ref and dc != 0:
                off.append((y, "country", dc))
            if ref and da != 0 and (y, da) not in AGE_RAW_RESIDUAL:
                off.append((y, "age", da))
        if off:
            raise SystemExit(f"naturalization panels do not reconcile to the annual "
                             f"귀화 series: {off}")

        # 2026-09-26: every other processing type too. The annual series is the
        # newest edition's 연도별 추이 table, which MOJ revises; the panels are each
        # edition's own detail tables. The cells below differ for that reason, each
        # one read in the raw files: the 2018 edition's detail tables print
        # 국적보유 86 / 국적상실 26,608 / 국적선택 1,714 / 인지 504, the 2025 trend
        # table 89 / 26,607 / 1,719 / 506 (and the 2018 edition's own trend table a
        # third set, 0 / 26,608 / 1,702 / 506); the 2012 age table prints 국적상실
        # 17,642 in its own 총계 row against 17,641 everywhere else; and the 2013
        # detail tables' 국적취득 column holds re-acquisition only (419), leaving
        # out the 343 acquisitions by recognition the trend table prints.
        # Anything not listed here stops the build. (year, kind, annual type, diff)
        TYPE_TO_ANNUAL = {"국적회복": "회복", "국적판정": "국적판정", "국적상실": "국적상실",
                          "국적이탈": "국적이탈", "국적취득(인지)": "국적취득 (인지)",
                          "국적취득(재취득)": "국적취득 (재취득)", "국적선택": "국적선택",
                          "국적보유": "국적보유", "국적취득": "국적취득"}
        KNOWN_REVISIONS = {
            (2012, "age", "국적상실", 1),
            (2013, "country", "국적취득", -343), (2013, "age", "국적취득", -343),
        } | {(2018, k, t, d) for k in ("country", "age") for t, d in
             (("국적보유", -3), ("국적상실", 1), ("국적선택", -5), ("국적취득 (인지)", -2))}
        type_off = []
        for y in YEARS:
            yd = ann.get(str(y)) or {}
            if not yd:
                continue
            ref = dict(yd)
            ref["국적취득"] = (yd.get("국적취득 (인지)") or 0) + (yd.get("국적취득 (재취득)") or 0)
            for kind, df in (("country", cdf), ("age", adf)):
                sub = df[df.year == y]
                for t, at in TYPE_TO_ANNUAL.items():
                    got = sub[sub.type == t].n
                    if got.empty or at not in ref:
                        continue
                    d = int(got.sum()) - int(ref[at])
                    if d and (y, kind, at, d) not in KNOWN_REVISIONS:
                        type_off.append((y, kind, at, d))
        if type_off:
            raise SystemExit(f"naturalization panels differ from the annual series in "
                             f"cells not traced to the raw files: {type_off}")
        print("  every other processing type equals the annual series except the "
              f"{len(KNOWN_REVISIONS)} cells traced to the raw editions")

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
    COUNTRY_EN.setdefault("중국+한국계중국인", "China incl. Korean-Chinese (2018 edition prints no split)")
    COUNTRY_EN.setdefault("러시아(연방)+한국계러시아인", "Russia incl. Korean-Russian (2018 edition prints no split)")


    def w(fn, head, rows):
        with open(os.path.join(RELEASE_DATA, fn), "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(head)
            wr.writerows(rows)
        years = {r[0] for r in rows}
        print(f"  {fn}: {len(rows):,} rows, {min(years)}-{max(years)}")


    # ---- annual (the trend table prints every year) ----
    # The annual file names a type as the two panels do, so the three join on
    # `type`: the trend table's own headers 회복, 국적취득 (인지) and 국적취득 (재취득)
    # are the panels' 국적회복, 국적취득(인지) and 국적취득(재취득), the spelling the
    # chapter's detail tables print (1라운드 수정, 2026-09-26). 귀화 stays: it is the
    # annual table's name for the sum the panels call 귀화소계 (귀화 before 2014).
    ANNUAL_TYPE = {"회복": "국적회복", "국적취득 (인지)": "국적취득(인지)",
                   "국적취득 (재취득)": "국적취득(재취득)"}
    rows = []
    for y, yd in sorted(D["naturalization_data"]["annual"].items(), key=lambda kv: int(kv[0])):
        for typ, n in yd.items():
            typ = ANNUAL_TYPE.get(typ, typ)
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
