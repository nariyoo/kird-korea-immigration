# -*- coding: utf-8 -*-
"""Check the release's national totals against the totals printed in the yearbook.

This backs the manuscript's sentence "agrees with the published figures within
0.x%". It is not a check inside the pipeline. It reads **only the one printed
total cell** from each yearbook file and compares it with that year's total in the
release `visa_national.csv`. Because it compares against values that never went
through harmonization, it shows plainly what harmonization lost or added.

    python 02_code/check_published_totals.py

Staying foreigners are read for every year from the nationality x visa status
table in chapter 2 of the yearbook. For the 2006-2010 editions that table
(chapter 2 II, '체류외국인 현황') was treated as "missing" until 2026-09-26
(round 1 fix), and was built by adding registered + short-term + residence
reports. The totals matched but the nationalities were wrong (China, Russia and
the '기타' column of the residence report table). Now that table is read
directly, and stay_country_gate checks those five years nationality by
nationality against the table's per-nationality totals.

Output: 03_cleaned_data/published_total_check.csv
"""
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from kird import CLEAN, RAW, RELEASE_DATA, RELEASE_LAST_YEAR   # noqa: E402

# '체류외국인 현황' (staying foreigners) at the start of chapter 2 in the 2006-2010
# editions. It is a nationality x visa status table, and 01 reads that year's
# staying foreigners from it (round 1 fix, 2026-09-26; before that, three tables
# were added). 2026-09-26: this path looked for 01_raw_data in the parent of code/
# (04_dataset_release) and always gave "no raw data". Use kird.RAW.
RAWYB = os.path.join(RAW, "출입국통계연보")
HEADLINE_STAY = {
    2006: os.path.join(RAWYB, "2006_출입국통계연보", "2장", "2-체류외국인현황.xls"),
    2007: os.path.join(RAWYB, "2007_출입국통계연보", "2-Ⅱ.체류외국인현황.xls"),
    2008: os.path.join(RAWYB, "2008_출입국통계연보", "2장_Ⅱ_체류외국인현황.xls"),
    2009: os.path.join(RAWYB, "2009_출입국통계연보", "2장_Ⅱ_체류외국인현황.xls"),
    2010: os.path.join(RAWYB, "2010_출입국통계연보", "2장_Ⅱ_체류외국인현황.xls"),
}

TOTAL_LABELS = ("총계", "총 계", "합계", "합 계", "grand-total", "grandtotal", "total")


def norm(v):
    return str(v).replace(" ", "").replace("\n", "").strip().lower()


def cell_number(v):
    """The yearbook sometimes puts several numbers in one cell, split by line
    breaks. Use only the first."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).split("\n")[0].replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def printed_total(path):
    """The total printed in that file.

    Table headers differ by edition, so finding the "total column" by name keeps
    missing (from 2019 the column is named '총합계', and in the 2014 edition it is
    just '계'). Instead, find the total **row** and take the largest number in it.
    The total column is the sum of the other columns, so it is always the largest
    in that row.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    for i in range(min(12, len(df))):
        row = df.iloc[i].tolist()
        head = norm(" ".join(str(x) for x in row[:2] if isinstance(x, str)))
        if not head:
            continue
        if not any(t in head for t in ("총계", "총합계", "합계", "grand-total")):
            continue
        # The 2006-2007 editions put earlier years' total rows on top for
        # comparison. A row like '2004년 총계' must not be read as that year's total.
        if re.search(r"(19|20)[0-9]{2}년", head):
            continue
        nums = [cell_number(v) for v in row]
        nums = [n for n in nums if n and n > 0]
        if nums:
            return max(nums), ""
    # Editions, like 2006-2007, whose first cell is the single character '계'
    for i in range(min(12, len(df))):
        row = df.iloc[i].tolist()
        if isinstance(row[0], str) and norm(row[0]) in ("계", "총계", "총합계"):
            nums = [cell_number(v) for v in row]
            nums = [n for n in nums if n and n > 0]
            if nums:
                return max(nums), ""
    return None, "총계 행을 못 찾았다"


def released_totals():
    df = pd.read_csv(os.path.join(RELEASE_DATA, "visa_national.csv"),
                     encoding="utf-8-sig")
    out = {}
    for pop, g in df.groupby("population"):
        out[pop] = g.groupby("year")["n"].sum().to_dict()
    return out


def main():
    # --data <folder>: hold another copy of the release to the raw tables (the gates
    # were tried on the release before the decisions of 2026-09-27 this way).
    global RELEASE_DATA
    if "--data" in sys.argv:
        RELEASE_DATA = os.path.abspath(sys.argv[sys.argv.index("--data") + 1])
        print("release data read from", RELEASE_DATA)
    # Use the same file list as 01, but restate it without running that script.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_p1", os.path.join(HERE, "01_parse_yearbooks.py"))
    src = open(spec.origin, encoding="utf-8").read()
    ns = {"__name__": "_p1_defs"}
    head = src[:src.index("# Continent aggregate")]
    exec(compile(head, spec.origin, "exec"), ns)      # only get the dicts

    rel = released_totals()
    rows = []
    stay_files = dict(ns["STAY_FILES"])
    stay_files.update(HEADLINE_STAY)          # 2006-2010 use the headline total table
    for series, files, popkey in (("registered", ns["REG_FILES"], "registered"),
                                  ("staying", stay_files, "stay")):
        for year in sorted(files):
            path = files[year]
            if not os.path.exists(path):
                rows.append({"series": series, "year": year, "printed": None,
                             "released": rel.get(popkey, {}).get(year),
                             "note": "원자료 없음"})
                continue
            pt, note = printed_total(path)
            rows.append({"series": series, "year": year, "printed": pt,
                         "released": rel.get(popkey, {}).get(year), "note": note})

    df = pd.DataFrame(rows)
    df["diff_pct"] = (df["released"] - df["printed"]) / df["printed"] * 100
    out = os.path.join(CLEAN, "published_total_check.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print("Yearbook printed totals vs release national totals")
    print()
    for series in ("registered", "staying"):
        sub = df[df["series"] == series].dropna(subset=["diff_pct"])
        print("== %s (%d years)" % (series, len(sub)))
        for _, r in sub.iterrows():
            print("   %d  printed %11s  released %11s  %+.3f%%"
                  % (r["year"], format(int(r["printed"]), ","),
                     format(int(r["released"]), ","), r["diff_pct"]))
        if len(sub):
            w = sub.loc[sub["diff_pct"].abs().idxmax()]
            print("   largest gap %.3f%% (%d)" % (abs(w["diff_pct"]), w["year"]))
        miss = df[(df["series"] == series) & (df["diff_pct"].isna())]
        if len(miss):
            print("   years not compared: %s" %
                  ", ".join("%d(%s)" % (r["year"], r["note"] or "인쇄 총계 없음")
                            for _, r in miss.iterrows()))
        print()
    print("wrote", out)

    # 2026-09-26 gate. The release sum must **equal** the printed total. While the
    # '무국적' and '기타' lines were dropped, it fell short by 106-337 people each
    # year, and that was described only as "within 0.05%". 2006-2010 staying (the
    # sum of three tables) was left out here on the assumption of "overlap", but
    # the real gap ran the other way (composite < published) and equalled, every
    # year, the dropped '기타' column of the residence report table (3rd
    # comparison). Now those five years must match as well.
    direct = df[(df["year"] <= RELEASE_LAST_YEAR) & df["printed"].notna()]
    missing = df[(df["year"] <= RELEASE_LAST_YEAR) & df["printed"].isna()]
    if len(missing):
        print("FAIL: no printed total read for:",
              ", ".join("%s %d" % (r["series"], r["year"]) for _, r in missing.iterrows()))
        return 1
    off = direct[direct["released"] != direct["printed"]]
    if len(off):
        print("FAIL: released national total differs from the printed grand total:")
        print(off[["series", "year", "printed", "released"]].to_string(index=False))
        return 1
    print("GATE OK: every year, 2006-2010 staying included, equals the "
          "printed grand total (%d series-years)" % len(direct))
    rc = district_gate(ns["REGION_COUNTRY_FILES"])
    rc2 = visa_district_gate()        # run all, so one failure does not hide another
    rc3 = district_level_gate(ns["REGION_COUNTRY_FILES"])
    rc4 = stay_country_gate()
    rc5 = early_province_gate()
    rc6 = crosswalk_labels_gate(ns)
    rc7 = mois_mask_gates()
    rc8 = status_label_gate(ns)
    rc9 = district_label_gate(ns)
    rc10 = status_variant_gate(ns)
    rc11 = crew_gate(ns)
    return rc or rc2 or rc3 or rc4 or rc5 or rc6 or rc7 or rc8 or rc9 or rc10 or rc11


def _canon(name):
    """A nationality label as the release spells it: spaces collapsed, enclosing
    parentheses dropped, retired spellings mapped (kird.COUNTRY_CANONICAL)."""
    from kird import COUNTRY_CANONICAL
    c = re.sub(r"\s+", "", str(name).split("\n")[0])
    if c.startswith("(") and c.endswith(")"):
        c = c[1:-1]
    return COUNTRY_CANONICAL.get(c, c)


def stay_country_gate():
    """2006-2010 staying foreigners, nationality by nationality, against the table.

    Round 1 fix (2026-09-26). These five editions print a nationality x status table
    of staying foreigners (chapter 2 II, '체류외국인 현황') that the build did not use: it
    composed the years as registered + short-term + overseas-Korean residence reports,
    which gives the right total but books the residence reports under the generic
    nationality their own table prints ('중국' 2010: 231,304 against the table's 199,802;
    '한국계중국인' 377,577 against 409,079) and turned that table's catch-all column into
    a nationality called '기타' (386-941 a year). Each nationality of
    nationality_national (population stay) must now equal the row total the table
    prints for it, the lines that name no nationality included.
    """
    nn = pd.read_csv(os.path.join(RELEASE_DATA, "nationality_national.csv"),
                     encoding="utf-8-sig")
    nn = nn[nn["population"] == "stay"]
    off, n_cells = [], 0
    for year, path in sorted(HEADLINE_STAY.items()):
        df = pd.read_excel(path, sheet_name=0, header=None)
        tc = None
        for i in range(min(8, len(df))):
            for j, v in enumerate(df.iloc[i].tolist()):
                if isinstance(v, str) and re.sub(r"\s", "", v) == "총계":
                    tc = j
                    break
            if tc is not None:
                break
        if tc is None:
            off.append((year, "no 총계 column"))
            continue
        # the name column: the one left of the totals with the most Korean labels
        def korean(j):
            return int(df.iloc[:, j].astype(str).str.contains(r"[가-힣]").sum())
        nc = max(range(tc), key=korean)
        want = {}
        for _, r in df.iterrows():
            name, v = r.iloc[nc], cell_number(r.iloc[tc])
            if not isinstance(name, str) or v is None or not re.search(r"[가-힣]", name):
                continue
            c = _canon(name)
            if c.endswith("계") or c in ("총계", "합계"):
                continue           # the grand total and the continent subtotals
            want[c] = want.get(c, 0) + int(v)
        got = nn[nn["year"] == year].groupby("country")["n"].sum().to_dict()
        for c in sorted(set(want) | set(got)):
            n_cells += 1
            if int(want.get(c, 0)) != int(got.get(c, 0)):
                off.append((year, c, int(want.get(c, 0)), int(got.get(c, 0))))
    print()
    print("Staying foreigners 2006-2010: per-nationality totals of the yearbook "
          "chapter 2 II table vs nationality_national")
    print("   %d nationality-years, %d mismatched" % (n_cells, len(off)))
    for o in off[:12]:
        print("   ", o)
    if off or not n_cells:
        print("FAIL: the 2006-2010 staying foreigners differ from the table, nationality "
              "by nationality")
        return 1
    print("GATE OK: 2006-2010 staying foreigners equal the table nationality by nationality")
    return 0


EARLY_PROVINCE = {
    2006: os.path.join(RAWYB, "2006_출입국통계연보", "2장", "3-나[1].국적및지역별.xls"),
    2007: os.path.join(RAWYB, "2007_출입국통계연보", "2-Ⅲ-2.국적및지역별.xls"),
}
SHORT_SIDO = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
              "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "경기": "경기도",
              "강원": "강원도", "충북": "충청북도", "충남": "충청남도", "전북": "전라북도",
              "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도"}


def early_province_gate():
    """2006-2007 nationality_by_sido against the province table, cell by cell.

    Round 1 fix (2026-09-26). The 2006 and 2007 editions print no district table,
    only a province table naming '타이완', '미국', '일본', '필리핀' and '중국' with an
    Other column. It is now carried as the 2006-2007 rows of nationality_by_sido (Other
    as '기타'). The 2006 province rows print each cell as two lines, ('거주') and
    ('기타'), with no '계' line, so a province's count is their sum; the national row
    prints a '계' line first. Every province and column must match.
    """
    ns = pd.read_csv(os.path.join(RELEASE_DATA, "nationality_by_sido.csv"),
                     encoding="utf-8-sig")
    off, n_cells = [], 0
    for year, path in sorted(EARLY_PROVINCE.items()):
        df = pd.read_excel(path, sheet_name=0, header=None)
        hr = next(i for i in range(8) if "타이완" in [re.sub(r"\s", "", str(v)) for v in df.iloc[i]])
        head = [re.sub(r"\s", "", str(v)) for v in df.iloc[hr]]
        cols = {j: ("기타" if h == "기타" else _canon(h)) for j, h in enumerate(head)
                if h in ("타이완", "미국", "일본", "필리핀", "중국", "기타")}
        mk = head.index("구분") if "구분" in head else None
        for _, r in df.iloc[hr + 1:].iterrows():
            sd = next((SHORT_SIDO[v] for v in r.tolist() if isinstance(v, str)
                       and v.strip() in SHORT_SIDO), None)
            if sd is None:
                continue
            stacked = (mk is not None and "\n" in str(r.iloc[mk])
                       and not str(r.iloc[mk]).split("\n")[0].strip().startswith("계"))
            for j, c in cols.items():
                parts = [cell_number(p) or 0 for p in str(r.iloc[j]).split("\n")]
                v = int(sum(parts)) if stacked else int(parts[0])
                got = ns[(ns["year"] == year) & (ns["sido"] == sd) & (ns["country"] == c)]["n"].sum()
                n_cells += 1
                if int(got) != v:
                    off.append((year, sd, c, v, int(got)))
    print()
    print("Sido x nationality 2006-2007: yearbook province table vs nationality_by_sido")
    print("   %d cells, %d mismatched" % (n_cells, len(off)))
    for o in off[:12]:
        print("   ", o)
    if off or n_cells != 2 * 16 * 6:
        print("FAIL: nationality_by_sido 2006-2007 differs from the province table")
        return 1
    print("GATE OK: nationality_by_sido 2006-2007 equals the province table cell by cell")
    return 0


def _pre2014_files(pattern):
    """The 2008-2013 district tables ('지역및국적별' / '지역및체류자격별'), which 01 does not
    list: 03 reads them with its own glob, and so does this."""
    import glob
    out = {}
    for y in range(2008, 2014):
        g = sorted(glob.glob(os.path.join(RAWYB, "%d_출입국통계연보" % y, pattern)))
        if g:
            out[y] = g[0]
    return out


def _visa_files():
    """The district x visa tables, 2008-2024, found as 03's build_visa_sigungu finds
    them (the country x visa table, whose name also holds '체류자격', is excluded)."""
    import glob
    out = _pre2014_files("*지역및체류자격*")
    for y in range(2014, RELEASE_LAST_YEAR + 1):
        d = os.path.join(RAWYB, "%d_출입국통계연보" % y)
        g = [f for pat in ("*시군구*체류자격*등록외국인*", "*지역*체류자격*등록외국인*")
             for f in sorted(glob.glob(os.path.join(d, pat)))
             if "국적" not in os.path.basename(f)]
        if g:
            out[y] = g[0]
    return out


def grand_row(path):
    """The grand-total row of a district table: (sheet, row index).

    2008-2013 editions put title lines above a two-line header, and the '총계' label
    sits in column 0 or 1 (2012-2013 stack the Korean and English, and the T/M/F
    values, in one cell, so the first line is read). From 2014 the header is one
    line and the '계' / '총계' / '총합계' row follows it.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    for i in range(1, 9):
        for c in (0, 1):
            if norm(str(df.iloc[i, c]).split("\n")[0]) in ("계", "총계", "총합계"):
                return df, i
    return df, None


def district_gate(files):
    """The district-by-nationality table against its own printed grand-total row.

    2026-09-26 (4th comparison): the parser wrote each nationality column of a row straight
    into its result, so where several columns fold onto one country ('영국' +
    '영국외지민' + '영국외지시민' + '영국해외영토시민', '홍콩' + '홍콩거주난민', '미국' +
    '미국인근섬') the last one overwrote the rest; and the residual lines some editions
    still print under abolished districts ('청원군', '당진군', '연기군', '여주군',
    2014-2018) were dropped
    instead of carried on their successor. nationality_by_sigungu fell short of the
    table's printed total every year from 2014 (by 3,068 in 2024, 2,918 of them United
    Kingdom nationals; by 4,287 in 2014), and the national checks above never saw it,
    because they read the status tables.

    The yearbook's printed grand total must equal nationality_by_sigungu summed over
    every district and every column, the columns that name no nationality ('무국적',
    '미등록국가', '기타') included. Until 2026-09-26 (final audit) those columns were left
    out on both sides here, because the district files dropped them, and the gate
    passed over 126-183 missing people a year; the parser carries them now, district
    by district, so the whole printed total is compared. From 2014 that is the
    '계' cell of the grand-total row, which equals the sum of the province '소계' rows: in
    2014 and 2015 the grand row's own nationality cells add up to 9 and 15 fewer than
    its '계' (the province rows, and the district lines under them, add up). KNOWN
    holds the people the table prints on a line that names no district.
    """
    # The one place the raw table does not add up: in 2015 the district rows of
    # '경기도' sum to one less than the '소계' the same sheet prints (369,664 against
    # 369,665), and the grand total follows the '소계', so the printed total holds
    # one person no row has. The district-by-visa table of the same edition prints
    # that person on a '화성시 동부출장소' line (1), which this table does not print
    # (final audit). (The 2014 '마산시' (1) and '창원시' (3) and 2015 '수원시' (2)
    # and '창원시' (1) city lines were exceptions here until 2026-09-26, 5th
    # comparison; they are carried now.)
    KNOWN = {2015: 1}
    nb = pd.read_csv(os.path.join(RELEASE_DATA, "nationality_by_sigungu.csv"),
                     encoding="utf-8-sig", usecols=["year", "country", "n"])
    got = got_all = nb.groupby("year")["n"].sum()
    rows = []
    # 2008-2013 (5th comparison, 2026-09-26). These editions print the top 19 nationalities
    # and a '기타' column that is the residual of all the others ('무국적' included), and
    # the district files carry that column as a country of its own, so the whole
    # printed total is compared, not the named columns. Until this date no gate
    # covered these years, and the district files fell 5-294 people a year short:
    # the city lines printed beside the gu of that city ('용인시' 14/142/33 in
    # 2008-2010, '창원시' 261 in 2010, '성남시', '안양시', '고양시', '천안시',
    # '청주시' 1-15) and '포천군' 2009 (1) were dropped as strays, though each
    # province '소계' and the grand total count them on top of the gu rows. No
    # exception: in all six tables the district lines add up to the province '소계'
    # and the '소계' to the grand total.
    for year, path in sorted(_pre2014_files("*지역및국적*").items()):
        df, i = grand_row(path)
        if i is None:
            rows.append((year, None, got_all.get(year)))
            continue
        tot = df.iloc[i].tolist()
        want = cell_number(tot[3])
        cells = sum(cell_number(v) or 0 for v in tot[4:])
        if cells != want:
            print("   %d: the printed grand-total row does not add up (%s against %s)"
                  % (year, format(int(cells), ","), format(int(want), ",")))
        rows.append((year, want, got_all.get(year)))
    for year in sorted(files):
        if year > RELEASE_LAST_YEAR or not os.path.exists(files[year]):
            continue
        df = pd.read_excel(files[year], sheet_name=0, header=None)
        tot = None
        for i in range(1, 6):
            if norm(df.iloc[i, 0]) in ("계", "총계", "총합계"):
                tot = df.iloc[i].tolist()
                break
        if tot is None:
            rows.append((year, None, got.get(year)))
            continue
        # column 3 is the row total, every column of the table included
        want = cell_number(tot[3]) or 0
        rows.append((year, want - KNOWN.get(year, 0), got.get(year)))
    print()
    print("Sigungu x nationality table: printed total vs nationality_by_sigungu sum (all columns)")
    for y, pt, g in rows:
        print("   %d  printed %11s  released %11s" %(y, format(int(pt or 0), ","),
                                          format(int(g or 0), ",")))
    off = [(y, pt, g) for y, pt, g in rows if pt is None or g != pt]
    if not rows or off:
        print("FAIL: nationality_by_sigungu does not sum to the district table's printed "
              "total row in %s" % ", ".join(str(y) for y, _, _ in off))
        return 1
    print("GATE OK: nationality_by_sigungu sums to the printed total row of the "
          "district-by-nationality table in every year %d-%d" % (rows[0][0], rows[-1][0]))
    return 0


SIDO_FIX = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"}
SUB_LABELS = ("소계", "총계", "총합계", "계")
# Where the release carries a district-table line under another label (README,
# District (sigungu) units): a rename, a district that moved province, and the
# residual lines some editions still print under an abolished district. '연기군' counts
# in '세종' (owner decision), so it moves province as well.
LINE_TO = {("충청남도", "연기군"): ("세종특별자치시", "세종시"),
           ("충청북도", "청원군"): ("충청북도", "청주시청원구"),
           ("충청남도", "당진군"): ("충청남도", "당진시"),
           ("경기도", "여주군"): ("경기도", "여주시"),
           ("경상남도", "마산시"): ("경상남도", "창원시"),
           ("경상남도", "진해시"): ("경상남도", "창원시진해구"),
           ("인천광역시", "남구"): ("인천광역시", "미추홀구"),
           ("경상북도", "군위군"): ("대구광역시", "군위군")}


def district_table_lines(path):
    """A 2014+ district-by-nationality table, line by line.

    Returns ({(sido, line): n}, {sido: '소계'}, grand '계'), where n is the row-total cell
    (column 3), so every column of the table counts, the ones that name no nationality
    included. The value of a line is its '계' row, or '남' + '여' where the edition prints no '계'
    row for it (the district lines of 2019). Names are compared without spaces.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    body = df.iloc[1:].copy()
    body[0] = body[0].ffill()
    body[1] = body[1].ffill()
    tot, mf, grand = {}, {}, None
    for r in body.itertuples(index=False):
        s0, s1, g = norm(r[0]), norm(r[1]), norm(r[2])
        v = cell_number(r[3]) or 0
        if s0 in ("계", "총계", "총합계"):
            if g in ("계", "총계", "총합계") and grand is None:
                grand = v
            continue
        key = (SIDO_FIX.get(s0, s0), s1)
        if g in ("계", "총계", "총합계"):
            tot.setdefault(key, v)
        elif g in ("남", "여", "남성", "여성"):
            mf[key] = mf.get(key, 0) + v
    lines = {k: tot.get(k, mf.get(k, 0)) for k in set(tot) | set(mf)}
    sub = {s: n for (s, l), n in lines.items() if l in SUB_LABELS}
    dist = {k: n for k, n in lines.items() if k[1] not in SUB_LABELS}
    # '세종' prints its province row and no district line (2021 puts its '남'/'여' rows
    # under a '시군구' cell of 0); its one district is the province.
    dist = {k: n for k, n in dist.items() if k[0] != "세종특별자치시"}
    if "세종특별자치시" in sub:
        dist[("세종특별자치시", "세종시")] = sub["세종특별자치시"]
    return dist, sub, grand


def release_key(sido, line):
    """The (sido, sigungu without spaces) the release files a district line under."""
    if "출장소" in line:
        m = re.match(r"^(.+?시)", line)
        line = m.group(1) if m else line
    if sido == "경기도" and line.startswith("부천시"):
        line = "부천시"
    return LINE_TO.get((sido, line), (sido, line))


def district_level_gate(files):
    """Every district and every province against the lines the table prints.

    2026-09-26 (final audit). The national gate above sees only the grand total. The
    district table columns that name no nationality ('무국적', '미등록국가', '기타') were
    dropped at every level below the country until this date, 126-183 people a year
    over up to 70 districts, and a district that loses a person while another gains
    one leaves the national sum untouched. Here each district of
    nationality_by_sigungu, all columns summed, must equal the row-total cell of the
    line or lines the table prints for it (after the relabelling the README
    documents: renames, residual lines of abolished districts, '출장소' lines, the
    '부천' gu, '세종'), and each province of nationality_by_sido, which counts a district
    in the province of that year, must equal the own '소계' of the table, with the
    residual '연기군' line moved to '세종' as the release does. 2014 to the release
    year. The one exception is the 2015 '경기도' '소계', one person above its own
    district lines.
    """
    KNOWN_PROV = {(2015, "경기도"): 1}
    nb = pd.read_csv(os.path.join(RELEASE_DATA, "nationality_by_sigungu.csv"),
                     encoding="utf-8-sig", usecols=["year", "sido", "sigungu", "n"])
    nb["k"] = nb["sigungu"].astype(str).str.replace(" ", "", regex=False)
    got_d = nb.groupby(["year", "sido", "k"])["n"].sum()
    ns = pd.read_csv(os.path.join(RELEASE_DATA, "nationality_by_sido.csv"),
                     encoding="utf-8-sig", usecols=["year", "sido", "n"])
    got_p = ns.groupby(["year", "sido"])["n"].sum()
    off_d, off_p, n_d, n_p = [], [], 0, 0
    for year in sorted(files):
        if year > RELEASE_LAST_YEAR or not os.path.exists(files[year]):
            continue
        dist, sub, _ = district_table_lines(files[year])
        want = {}
        for (sd, line), n in dist.items():
            k = release_key(sd, line)
            want[k] = want.get(k, 0) + n
        have = {(sd, k): int(v) for (y, sd, k), v in got_d.items() if y == year}
        for k in sorted(set(want) | set(have)):
            n_d += 1
            if want.get(k, 0) != have.get(k, 0):
                off_d.append((year, k, want.get(k, 0), have.get(k, 0)))
        # provinces: the own '소계' of the table, with the '연기군' line counted in '세종'
        prov = dict(sub)
        yg = dist.get(("충청남도", "연기군"), 0)
        if yg:
            prov["충청남도"] = prov.get("충청남도", 0) - yg
            prov["세종특별자치시"] = prov.get("세종특별자치시", 0) + yg
        for sd in sorted(set(prov) | {s for (y, s) in got_p.index if y == year}):
            if not prov.get(sd) and not got_p.get((year, sd)):
                continue           # the empty '기타' province row of 2014
            n_p += 1
            w = prov.get(sd, 0) - KNOWN_PROV.get((year, sd), 0)
            if w != int(got_p.get((year, sd), 0)):
                off_p.append((year, sd, w, int(got_p.get((year, sd), 0))))
    print()
    print("Sigungu x nationality table: every district line, every province subtotal (all columns)")
    print("   districts %d place-years, %d mismatched; provinces %d place-years, %d mismatched"
          % (n_d, len(off_d), n_p, len(off_p)))
    for o in (off_d + off_p)[:12]:
        print("   ", o)
    if off_d or off_p or not n_d:
        print("FAIL: the district files differ from the lines the district-by-nationality "
              "table prints")
        return 1
    print("GATE OK: every district and province of nationality_by_sigungu / "
          "nationality_by_sido equals the printed line, 2014-%d" % RELEASE_LAST_YEAR)
    return 0


def visa_district_gate():
    """visa_by_sigungu against the district-by-visa table's printed grand total.

    2026-09-26 (5th comparison). Two losses no gate saw. The '기타' column (Others,
    2013 on), the statuses it does not list by code, has no code in its header, and
    03's parser kept only coded columns: visa_by_sigungu fell short by 363 in 2013,
    39,210 in 2020 and 31,626 in 2024, exactly visa_national's ETC. And the city
    lines of 2008-2013 went through the population table's city-total rule. The
    whole printed total must be there; the table adds up in every year (district
    lines to the '소계', the '소계' to the grand total), so there is no exception.

    The two district tables of one edition do not always place a person in the same
    district: the 2015 nationality table prints a bare '창원시' line (1) above
    '창원시 마산합포구' (2,159), and the visa table prints no '창원시' line and
    2,160 for '마산합포구'. Each file follows its own table; validate_release's
    check_district_tables_agree holds the two files to each other district by
    district and lists the places the tables differ (final audit, 2026-09-26).
    """
    vb = pd.read_csv(os.path.join(RELEASE_DATA, "visa_by_sigungu.csv"),
                     encoding="utf-8-sig", usecols=["year", "n"])
    got = vb.groupby("year")["n"].sum()
    rows = []
    for year, path in sorted(_visa_files().items()):
        df, i = grand_row(path)
        want = cell_number(df.iloc[i, 3]) if i is not None else None
        rows.append((year, want, got.get(year)))
    print()
    print("Sigungu x visa table: printed total vs visa_by_sigungu sum")
    for y, pt, g in rows:
        print("   %d  printed %11s  released %11s" %(y, format(int(pt or 0), ","),
                                          format(int(g or 0), ",")))
    years = set(range(2008, RELEASE_LAST_YEAR + 1))
    off = [(y, pt, g) for y, pt, g in rows if pt is None or g != pt]
    lost = sorted(years - {y for y, _, _ in rows})
    if off or lost:
        print("FAIL: visa_by_sigungu does not sum to the district-by-visa table's printed "
              "total in %s%s" % (", ".join(str(y) for y, _, _ in off),
                                 (" (no table found: %s)" % lost) if lost else ""))
        return 1
    print("GATE OK: visa_by_sigungu sums to the printed total of the district-by-visa "
          "table in every year %d-%d" % (rows[0][0], rows[-1][0]))
    return 0


# Lines of the status and district tables that are totals or continent subtotals,
# not a label a crosswalk maps (the same names 01_parse_yearbooks.DROP_NAMES drops
# from the country axis, less the lines that name no nationality, which the release
# carries and the crosswalk lists).
LABEL_SKIP = {"계", "총계", "총합계", "소계", "합계", "grand-total", "grandtotal",
              "아시아주계", "아시아주", "북아메리카주계", "북아메리카주", "북아메리카",
              "남아메리카주계", "남아메리카주", "남아메리카", "유럽주계", "유럽주", "유럽",
              "오세아니아주계", "오세아니아주", "오세아니아", "아프리카주계", "아프리카주",
              "아프리카", "무국적계", "기타국", "기타국가", "기타지역", "북아메리카계",
              "남아메리카계", "북미주계", "북미주", "남미주계", "남미주", "구소련계", "구소련",
              "시도", "시군구", "성별", "구분", "지역", "국적", "국적명", "국적･지역",
              "국적(지역)", "체류자격", "체류자격국적", "남", "여", "남성", "여성",
              "기타계", "제3의성"}
CODE = re.compile(r"[A-H]-?\d")
FOOTNOTE = re.compile(r"^(※|\*|주\)|\(주|\(단위|note|자료)", re.I)
PROVINCE = re.compile(r"(특별시|광역시|특별자치시|특별자치도|도)$")


def crosswalk_labels_gate(ns):
    """Every label the raw tables print maps through a crosswalk row.

    2026-09-27 (round 2 comparison). The crosswalks are there so a reader holding only the
    deposit can follow every merge from the source spelling to the released one, and
    three kinds of printed label had no row: the parenthesized nationalities of the
    2017 edition ('(타이완)', '(홍콩)', '(마카오)', '(영국외지민)', '(영국속국민)'),
    which the parsers read as the name inside; the code-less '기타' / '기타(other)'
    status column, which becomes ETC; and the full province names the 2008-2009 and
    2014+ tables print, which only '강원도', '전라북도' and '제주특별자치도' had. This reads, 2006 to the
    release year, the nationality lines of the national status tables, the
    nationality columns and province lines of the district tables, and the code-less
    status columns of both, and checks each against crosswalk_country.source_label,
    crosswalk_region's province rows and crosswalk_visa.source_code, spaces removed.
    Since 2026-09-27 (round 3 comparison) a nationality printed with a space between words
    must also have its literal row, and every crosswalk_country row that says an
    edition prints a spelling must name one these tables print.
    `ns` holds the file lists main() read from the head of 01_parse_yearbooks.py.
    """
    ws = lambda v: re.sub(r"\s+", "", str(v).split("\n")[0])
    # The label as printed. A run of two or more spaces is padding (the 2009 sheets
    # pad '중      국' to a fixed width), and so is a name spaced one character at a time
    # (2006: '가 이 아 나'); a single space between words is part of the spelling
    # ('한국계 중국인', '국제연합 전문기구') and needs a row of its own (crosswalks.
    # SPACED_LABELS). 2026-09-27 (round 3 comparison): comparing on ws() alone let a spaced
    # label pass on the unspaced row, though the crosswalk promises a row for every
    # label the tables print.
    lit = lambda v: re.sub(r"\s+", " ", re.sub(r"\s{2,}", "", str(v).split("\n")[0])).strip()
    word_spaced = lambda v: " " in lit(v) and any(len(t) > 1 for t in lit(v).split(" "))
    cw = pd.read_csv(os.path.join(RELEASE_DATA, "crosswalk_country.csv"), encoding="utf-8-sig")
    cv = pd.read_csv(os.path.join(RELEASE_DATA, "crosswalk_visa.csv"), encoding="utf-8-sig")
    cr = pd.read_csv(os.path.join(RELEASE_DATA, "crosswalk_region.csv"), encoding="utf-8-sig")
    C = set(cw["source_label"].map(ws))
    C_LIT = set(cw["source_label"].map(lit))
    V = set(cv["source_code"].map(ws))
    S = set(cr.loc[cr["level"] == "sido", "source_sido"].map(ws))
    national = dict(ns["REG_FILES"])
    stay = dict(ns["STAY_FILES"])
    stay.update(HEADLINE_STAY)
    district = dict(_pre2014_files("*지역및국적*"))
    district.update(ns["REGION_COUNTRY_FILES"])
    visa_d = _visa_files()
    miss = {"country": set(), "status": set(), "province": set()}
    n_seen = {"country": set(), "status": set(), "province": set()}
    n_cols = {}

    def korean(v):
        return isinstance(v, str) and re.search(r"[가-힣]", v)

    def note_country(y, raw, where):
        lab = ws(raw)
        if not lab or lab.lower() in LABEL_SKIP or lab in LABEL_SKIP or FOOTNOTE.match(lab):
            return
        n_seen["country"].add(lab)
        if lab not in C:
            miss["country"].add((y, lab, where))
        elif word_spaced(raw) and lit(raw) not in C_LIT:
            miss["country"].add((y, lit(raw), where + ", printed with a space"))

    def note_status(y, df, i, j, where):
        """A header cell headed '기타' with no status code in its column is the
        code-less column of unclassified statuses (2018 on). Before 2014 the Korean
        label '기타' heads a coded column (G-1, and '기타연수' D-4-5, '기타장기' F-2-5),
        which maps by its code."""
        v = df.iat[i, j]
        lab = ws(v)
        if not lab.startswith("기타"):
            return
        head = [df.iat[k, j] for k in range(max(0, i - 2), min(len(df), i + 3))]
        if any(isinstance(h, str) and CODE.search(h) for h in head):
            return
        n_seen["status"].add(lab)
        if lab not in V:
            miss["status"].add((y, lab, where))

    def note_province(y, lab, where):
        lab = ws(lab)
        if lab in LABEL_SKIP:
            return
        if korean(lab) and (PROVINCE.search(lab) and len(lab) <= 8 or lab in SHORT_SIDO):
            n_seen["province"].add(lab)
            if lab not in S:
                miss["province"].add((y, lab, where))

    for files, tag in ((national, "registered"), (stay, "staying")):
        for y, path in sorted(files.items()):
            if y > RELEASE_LAST_YEAR or not os.path.exists(path):
                continue
            df = pd.read_excel(path, sheet_name=0, header=None)
            # The nationality column is the one of the first four with the most
            # distinct labels. Counting Korean cells instead picked the sex column of
            # the 2019-on tables, which name a country once per '남성'/'여성' pair and print
            # '남성' or '여성' on every row, so the scan drew no nationality from those
            # editions (round 3 comparison, 2026-09-27; 2019 staying: 217 cells of '국적'
            # against 434 of '성별').
            def distinct(j):
                return len({ws(v) for v in df.iloc[:, j]
                            if korean(v) and ws(v) not in LABEL_SKIP})
            nc = max(range(min(4, df.shape[1])), key=distinct)
            n_cols[(tag, y)] = nc
            col = df.iloc[:, nc].tolist()
            TOT = ("총계", "합계", "계", "총합계")
            start = next((i for i, v in enumerate(col) if korean(v) and ws(v) in TOT), None)
            if start is None:
                # 2021-2024: the grand-total line is headed in the continent column
                # ('총합계') and the nationality column is blank on it
                start = next((i for i in range(len(df)) for j in range(nc)
                              if korean(df.iat[i, j]) and ws(df.iat[i, j]) in TOT), None)
            if start is None:
                miss["country"].add((y, "(no grand-total line found)", tag))
                continue
            for v in col[start + 1:]:
                if korean(v):
                    note_country(y, v, tag)
            for i in range(start):
                for j in range(df.shape[1]):
                    if korean(df.iat[i, j]):
                        note_status(y, df, i, j, tag)
    for y, path in sorted(district.items()):
        if y > RELEASE_LAST_YEAR or not os.path.exists(path):
            continue
        df = pd.read_excel(path, sheet_name=0, header=None)
        hr = max(range(min(8, len(df))),
                 key=lambda i: sum(1 for v in df.iloc[i] if korean(v)))
        for v in df.iloc[hr].tolist()[3:]:
            if korean(v):
                note_country(y, v, "district")
        for j in (0, 1):
            for v in df.iloc[hr + 1:, j].tolist():
                note_province(y, v, "district")
    for y, path in sorted(visa_d.items()):
        df = pd.read_excel(path, sheet_name=0, header=None)
        for i in range(min(8, len(df))):
            for j in range(df.shape[1]):
                if korean(df.iat[i, j]):
                    note_status(y, df, i, j, "district")
        for j in (0, 1):
            for v in df.iloc[:, j].tolist():
                note_province(y, v, "district")
    # The other direction (round 3 comparison, 2026-09-27): a row that says an edition
    # prints a spelling must name one the tables print. A '대만' -> '타이완' row stood for
    # a merge no edition makes; no workbook 2006-2025 prints '대만'.
    variant = cw[cw["rule"].astype(str).str.startswith("source label variant")]
    for lab in sorted(set(variant["source_label"].map(ws)) - n_seen["country"]):
        miss["country"].add((0, lab, "crosswalk row for a spelling no table prints"))
    print()
    print("Raw spellings vs crosswalk: %d nationalities, %d other-status columns, %d provinces"
          % tuple(len(n_seen[k]) for k in ("country", "status", "province")))
    print("   nationality column: %s" %", ".join("%s %d:%d" % (t[:3], y, c)
                                    for (t, y), c in sorted(n_cols.items())))
    bad = [(k, sorted(v)[:10]) for k, v in miss.items() if v]
    for k, v in bad:
        print("   no crosswalk row (%s): %s" % (k, v))
    if bad or not all(n_seen.values()):
        print("FAIL: a label the raw tables print has no crosswalk row")
        return 1
    print("GATE OK: every nationality, code-less status and province label the raw "
          "tables print has a crosswalk row")
    return 0


SUBCODE = re.compile(r"^\(?([A-Z])-?(\d)([A-Z])\)?$")
OWNCODE = re.compile(r"^\(?([A-Z])-?(\d{1,2})\)?$")


def status_label_gate(ns):
    """A status no edition prints under its own code takes its label from the
    sub-statuses the editions print, so the released label must name each of them.

    Round 3 comparison (2026-09-27). The 2007-2009 editions print E0A '내항선원', E0B
    '어선원' and (2009) E0C '순항선원' and never an E-0 column; the parser folded the
    three into E0, and its label read '협정활동' (treaty activity), a status no edition
    prints for these columns (they are the crew subdivisions of E-10 '선원취업').
    Here, over the national
    status tables of every edition to the release year, a code with lettered
    sub-codes (E0A) and no column of its own must carry a visa_label in
    visa_national that contains the first two characters of every sub-label printed.
    Since the owner's decision of the same day the crew columns are E10, a code
    with a column of its own, so no released code is left for this gate to hold
    (crew_gate holds the crew rows instead); it stays for any status a future
    edition prints only as sub-codes.
    """
    national = dict(ns["REG_FILES"])
    stay = dict(ns["STAY_FILES"])
    stay.update(HEADLINE_STAY)
    own, subs = set(), {}
    for files in (national, stay):
        for y, path in sorted(files.items()):
            if y > RELEASE_LAST_YEAR or not os.path.exists(path):
                continue
            df = pd.read_excel(path, sheet_name=0, header=None)
            for j in range(df.shape[1]):
                for i in range(1, min(8, len(df))):
                    v = re.sub(r"\s+", "", str(df.iat[i, j]).split("\n")[-1])
                    m, o = SUBCODE.match(v), OWNCODE.match(v)
                    if o:
                        own.add(o.group(1) + o.group(2))
                        break
                    if m:
                        lab = re.sub(r"\s+", "", str(df.iat[i - 1, j]).split("\n")[0])
                        if re.search(r"[가-힣]", lab):
                            subs.setdefault(m.group(1) + m.group(2), set()).add(lab)
                        break
    vn = pd.read_csv(os.path.join(RELEASE_DATA, "visa_national.csv"), encoding="utf-8-sig")
    labels = vn.drop_duplicates("visa_code").set_index("visa_code")["visa_label"].to_dict()
    bad = []
    for code, labs in sorted(subs.items()):
        if code in own or code not in labels:
            continue
        miss = sorted(l for l in labs if l[:2] not in str(labels[code]))
        if miss:
            bad.append((code, labels[code], miss))
    print()
    print("Statuses with no parent code column: %s" %", ".join(
        "%s (%s)" % (c, "/".join(sorted(l))) for c, l in sorted(subs.items())
        if c not in own and c in labels))
    if bad:
        print("FAIL: a released status label does not name the sub-statuses printed: %s"
              % bad)
        return 1
    print("GATE OK: every status printed only as lettered sub-codes carries a label "
          "that names them")
    return 0


DISTRICT_LABEL = re.compile(r"^[가-힣]+(시|군|구|출장소)$")


def district_label_gate(ns):
    """Every district label the MOJ district tables print maps to a released district.

    Round 4 comparison (2026-09-27). crosswalk_region had no rule row for '진해시', which the
    2008 and 2009 district tables print as a district of its own and the 2011 and 2012
    tables as a residual line of one person, all of it carried on '창원시 진해구'; only the
    boundary-lineage pair named it, and crosswalk_labels_gate checked the province
    labels, not the districts. Here every district line of the district-by-nationality
    and district-by-visa tables, 2008 to the release year, must be carried under its own
    name that year (nationality_by_sigungu or visa_by_sigungu, spaces removed, under the
    province the release files it in) or have a sigungu row in crosswalk_region with
    that province and name as printed.
    """
    ws = lambda v: re.sub(r"\s+", "", str(v).split("\n")[0])
    short = dict(SHORT_SIDO, 세종="세종특별자치시")
    full = set(short.values())
    fix = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주도": "제주특별자치도"}

    def sido_of(v):
        s = ws(v)
        s = fix.get(s, s)
        return s if s in full else short.get(s)

    def labels(path):
        df = pd.read_excel(path, sheet_name=0, header=None)
        out, sido = set(), None
        for i in range(len(df)):
            cells = [df.iat[i, j] for j in range(min(3, df.shape[1]))
                     if isinstance(df.iat[i, j], str)]
            sd = next((sido_of(v) for v in cells if sido_of(v)), None)
            sido = sd or sido
            if sido is None:
                continue
            for v in cells:
                lab = ws(v)
                if lab in LABEL_SKIP or sido_of(lab) or not DISTRICT_LABEL.match(lab):
                    continue
                out.add((sido, lab))
        return out

    have = {}
    for name in ("nationality_by_sigungu.csv", "visa_by_sigungu.csv"):
        df = pd.read_csv(os.path.join(RELEASE_DATA, name), encoding="utf-8-sig",
                         usecols=["year", "sido", "sigungu"]).drop_duplicates()
        for y, sd, sg in df.itertuples(index=False):
            have.setdefault(int(y), set()).add((sd, ws(sg)))
    cr = pd.read_csv(os.path.join(RELEASE_DATA, "crosswalk_region.csv"), encoding="utf-8-sig")
    rows = {(ws(a), ws(b)) for a, b in cr.loc[cr["level"] == "sigungu",
                                               ["source_sido", "source_name"]]
            .itertuples(index=False)}
    nat = dict(_pre2014_files("*지역및국적*"))
    nat.update(ns["REGION_COUNTRY_FILES"])
    tables = [(y, p, "nationality") for y, p in nat.items()] + \
             [(y, p, "visa") for y, p in _visa_files().items()]
    tables = [t for t in tables if t[0] <= RELEASE_LAST_YEAR and os.path.exists(t[1])]
    years = set(range(2008, RELEASE_LAST_YEAR + 1))
    lost = sorted("%s %d" % (k, y) for k in ("nationality", "visa")
                  for y in years - {t[0] for t in tables if t[2] == k})
    miss, n, via = {}, 0, set()
    for y, path, kind in sorted(tables):
        for sd, lab in sorted(labels(path)):
            n += 1
            if (sd, lab) in have.get(y, set()):
                continue
            if (sd, lab) in rows:
                via.add((sd, lab))
                continue
            miss.setdefault((sd, lab), []).append("%d %s" % (y, kind))
    print()
    print("District table names vs release and crosswalk_region: %d line-years, "
          "%d names moved by a crosswalk row" % (n, len(via)))
    for k, v in sorted(miss.items()):
        print("   no row: %s %s (%s)" % (k[0], k[1], ", ".join(v)))
    if miss or lost or not n:
        print("FAIL: a district label the district tables print is neither carried under "
              "its own name nor listed in crosswalk_region%s"
              % ((" (no table: %s)" % lost) if lost else ""))
        return 1
    print("GATE OK: every district label the district tables print, 2008-%d, is carried "
          "under its own name or has a crosswalk_region row" % RELEASE_LAST_YEAR)
    return 0


STATUS_OWN = re.compile(r"^\(?([A-Z])-?(\d{1,2})\)?$")
STATUS_REV = re.compile(r"^([^()]+)\(([A-Z])-?(\d{1,2})\)$")      # e.g. '외교(A-1)'
STATUS_FWD = re.compile(r"^([A-Z])-?(\d{1,2})\(([^()]+)\)$")      # e.g. 'A-1(외교)'


def status_variant_gate(ns):
    """Every label a status table prints for a code is the released label, or a
    crosswalk_visa row names it for that edition.

    Round 4 comparison (2026-09-27). The 2006-2012 editions print D-3 as '산업연수' and
    the 2013 edition on as '기술연수', and crosswalk_visa said nothing of it: its only
    row for a label an edition prints differently was the E-8 split. Nine more codes
    are printed under another label in some edition (C-3 '단기종합', D-7 '상사주재',
    E-7 '특정직업', E-9 '비취업', E-2 '회화' and '회화강사', E-10 '내항선원' in 2006,
    G-1 '기타', and '연수취업' over the seasonal-worker E-8 of the 2022 and 2024
    registered tables). Here, over the national registered and staying tables and the
    district status tables, 2006 to the release year, each code printed with a Korean
    label (in one cell, '외교(A-1)' or 'A-1(외교)', or
    the label above the code) is compared with visa_national's label for the code (the
    part before any parenthesis; E-8 through E8_TRAINEE_LAST_YEAR is E8T). A label that
    differs needs a crosswalk_visa row of that code whose rule reads 'same code, label
    printed as <label>' and whose source_code lists the edition; and each such row must
    list exactly the editions that print its label. Sub-codes (D31, E0A) are not
    compared: their rows map them by code.
    """
    ws = lambda v: re.sub(r"\s+", "", str(v))
    src = open(os.path.join(HERE, "01_parse_yearbooks.py"), encoding="utf-8").read()
    e8t_last = int(re.search(r"^E8_TRAINEE_LAST_YEAR\s*=\s*(\d{4})", src, re.M).group(1))
    vn = pd.read_csv(os.path.join(RELEASE_DATA, "visa_national.csv"), encoding="utf-8-sig")
    label = vn.drop_duplicates("visa_code").set_index("visa_code")["visa_label"].to_dict()
    core = {c: ws(str(l).split(" (")[0]) for c, l in label.items()}
    cv = pd.read_csv(os.path.join(RELEASE_DATA, "crosswalk_visa.csv"), encoding="utf-8-sig")
    rule_head = "same code, label printed as "
    listed = {}
    for sc, code, rule in cv[["source_code", "visa_code", "rule"]].itertuples(index=False):
        if not str(rule).startswith(rule_head):
            continue
        lab = re.match(r"[^\s;,(]+", str(rule)[len(rule_head):]).group(0)
        m = re.search(r"\((.+?) editions?\)$", str(sc))
        eds = set()
        for part in (m.group(1).split(",") if m else []):
            a, _, b = part.strip().partition("-")
            eds |= set(range(int(a), int(b or a) + 1))
        listed[(code, lab)] = eds

    def printed(path):
        df = pd.read_excel(path, sheet_name=0, header=None)
        out = set()
        for j in range(df.shape[1]):
            for i in range(min(9, len(df))):
                v = df.iat[i, j]
                if not isinstance(v, str):
                    continue
                v = ws(v)
                m = STATUS_REV.match(v)
                if m and re.search(r"[가-힣]", m.group(1)):
                    out.add((m.group(2) + m.group(3), m.group(1)))
                    break
                m = STATUS_FWD.match(v)
                if m and re.search(r"[가-힣]", m.group(3)):
                    out.add((m.group(1) + m.group(2), m.group(3)))
                    break
                m = STATUS_OWN.match(v)
                if m and i > 0:
                    up = df.iat[i - 1, j]
                    if isinstance(up, str) and re.search(r"[가-힣]", up):
                        out.add((m.group(1) + m.group(2), ws(up)))
                    break
        return out

    stay = dict(ns["STAY_FILES"])
    stay.update(HEADLINE_STAY)
    tables = [(y, p, "registered") for y, p in ns["REG_FILES"].items()] + \
             [(y, p, "staying") for y, p in stay.items()] + \
             [(y, p, "district") for y, p in _visa_files().items()]
    tables = [t for t in tables if t[0] <= RELEASE_LAST_YEAR and os.path.exists(t[1])]
    seen, bad, thin, n = {}, [], [], 0
    for y, path, kind in sorted(tables):
        codes = 0
        for code, lab in sorted(printed(path)):
            rc = "E8T" if code == "E8" and y <= e8t_last else code
            if rc not in core:
                continue                      # a sub-code such as D31, mapped by its row
            codes += 1
            n += 1
            if lab == core[rc]:
                continue
            seen.setdefault((rc, lab), set()).add(y)
            if y not in listed.get((rc, lab), set()):
                bad.append("%d %s %s printed as %s" % (y, kind, rc, lab))
        if codes < 10:
            thin.append("%d %s (%d codes)" % (y, kind, codes))
    for key, eds in sorted(listed.items()):
        if eds != seen.get(key, set()):
            bad.append("crosswalk row %s %s lists %s; the tables print it in %s"
                       % (key[0], key[1], sorted(eds), sorted(seen.get(key, set()))))
    print()
    print("Status table labels vs visa_national and crosswalk_visa: %d code-tables, "
          "%d labels printed differently"
          % (n, len(seen)))
    for (c, l), eds in sorted(seen.items()):
        print("   %s %s: %s" % (c, l, ", ".join(str(e) for e in sorted(eds))))
    for b in bad[:15]:
        print("   ", b)
    if bad or thin:
        print("FAIL: a status label the tables print is neither the released label nor "
              "named for that edition in crosswalk_visa%s"
              % ((" (tables read thin: %s)" % thin) if thin else ""))
        return 1
    print("GATE OK: every status label the status tables print, 2006-%d, is the released "
          "label or a crosswalk_visa row names it for that edition" % RELEASE_LAST_YEAR)
    return 0


# The general-district cities of the MOIS age sheets (05_mois_layer.GU_BY_CITY).
GU_CITY = {
    "고양시": ("덕양구", "일산동구", "일산서구"), "부천시": ("소사구", "오정구", "원미구"),
    "성남시": ("분당구", "수정구", "중원구"), "수원시": ("권선구", "영통구", "장안구", "팔달구"),
    "안산시": ("단원구", "상록구"), "안양시": ("동안구", "만안구"),
    "용인시": ("기흥구", "수지구", "처인구"), "전주시": ("덕진구", "완산구"),
    "창원시": ("마산합포구", "마산회원구", "성산구", "의창구", "진해구"),
    "천안시": ("동남구", "서북구"), "청주시": ("상당구", "서원구", "청원구", "흥덕구"),
    "포항시": ("남구", "북구")}
MOIS_RAW = os.path.join(RAW, "행정안전부 외국인주민통계")
AGE_LABEL = re.compile(r"^만?(\d{1,2})세$")


# ---------------------------------------------------------------- masked MOIS cells
# The owner's decision of 2026-09-27: every cell MOIS masks ('*', '***': a count
# under 5) that the printed cells fix exactly is carried, through the identities
# the sheet itself publishes. Within a row a total is the sum of its parts; across
# rows a row with rows printed under it is their sum, column by column (the nation
# over its provinces, a province over its districts, a city over its general
# districts, a district over its sub-districts); every identity left with one masked
# cell settles it, repeated until none does. The gates below re-read the four MOIS
# sheets the released files come from (1-2 districts, 1-3 sub-districts, 11
# households, 9-2 children by age), settle them here with code of their own
# (05_mois_layer.MaskTree is not imported), and hold every released cell of 2016 to
# the release year to the result, cell by cell: a printed or settled cell must be
# carried with that value, and a cell left masked must not be carried. They also
# stop if a fully printed identity fails, or a settled value falls outside 0-4.

MOIS_SIDO = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
             "울산광역시", "세종특별자치시", "세종시", "경기도", "강원도", "강원특별자치도",
             "충청북도", "충청남도", "전라북도", "전북특별자치도", "전라남도", "경상북도",
             "경상남도", "제주도", "제주특별자치도"}
MOIS_SIDO_RELEASE = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도", "제주도": "제주특별자치도",
                     "세종시": "세종특별자치시"}
MOIS_DONG = ("동", "읍", "면", "리", "출장소", "지소")
MOIS_MASK = "*"
POP_CATS = ["합계", "한국국적미취득_소계", "외국인근로자", "결혼이민자", "유학생", "외국국적동포",
            "기타외국인", "한국국적취득자", "외국인주민자녀"]
POP_IDS = [("합계", ("한국국적미취득_소계", "한국국적취득자", "외국인주민자녀")),
           ("한국국적미취득_소계", ("외국인근로자", "결혼이민자", "유학생", "외국국적동포", "기타외국인"))]
MC_CATS = ["합계", "한국인배우자", "결혼이민자귀화자_소계", "결혼이민자", "귀화자등", "자녀_소계",
           "자녀_귀화인지외국국적", "자녀_국내출생", "기타동거인_소계", "기타동거인_내국인",
           "기타동거인_외국인"]
MC_IDS = [("합계", ("한국인배우자", "결혼이민자귀화자_소계", "자녀_소계", "기타동거인_소계")),
          ("결혼이민자귀화자_소계", ("결혼이민자", "귀화자등")),
          ("자녀_소계", ("자녀_귀화인지외국국적", "자녀_국내출생")),
          ("기타동거인_소계", ("기타동거인_내국인", "기타동거인_외국인"))]
AGES = [str(a) for a in range(19)]
MOIS_SHEETS = {
    # sheet prefix: (the '계' column of each category, the row identities)
    "1-2.": (dict(zip(POP_CATS, (3, 6, 9, 12, 15, 18, 21, 24, 27))), POP_IDS),
    "1-3.": (dict(zip(POP_CATS, range(1, 10))), POP_IDS),
    "11.": (dict(zip(MC_CATS, range(1, 12))), MC_IDS),
    "9-2.": ({"합계": 1}, [("합계", tuple(AGES))]),
}
# The district names the release carries in place of the one a 2016+ edition prints.
MOIS_DISTRICT_RELEASE = {("인천광역시", "남구"): ("인천광역시", "미추홀구"),
                         ("경상북도", "군위군"): ("대구광역시", "군위군")}


def _mois_cell(v):
    if isinstance(v, str) and v.strip() in ("*", "***"):
        return MOIS_MASK
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except ValueError:
        return None


def mois_tree(y, prefix):
    """The MOIS sheet of edition y whose name starts with `prefix`, as the rows print
    it: a list of nodes {level, sido, district, dong, parent, cells}. level is
    nation, province, city (a city with general districts printed under it), district
    or dong; district is the release spelling of the district ('수원시 장안구',
    '세종시'); for sheet 9-2 the cells of a node are its '합계' and its single ages."""
    cols, _ = MOIS_SHEETS[prefix]
    path = os.path.join(MOIS_RAW, "%d_외국인주민통계.xlsx" % y)
    xl = pd.ExcelFile(path)
    sheet = next(s for s in xl.sheet_names if re.sub(r"\s+", "", s).startswith(prefix))
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    # the misprints the pipeline corrects (05_mois_layer.fix_known_typos, and
    # 09_finish_release.TYPO_FIX, the 2024 '청순군' among them)
    typo = {"천찬시동남구": "천안시동남구", "천찬시서북구": "천안시서북구", "청순군": "청송군",
            "충청북도충주시": "충주시"}
    ws = lambda v: (lambda t: typo.get(t, t))(re.sub(r"\s+", "", str(v).split("\n")[0]))
    nodes, started = [], False
    nation = province = city = district = None
    sido = city_name = None
    for i in range(len(df)):
        if not isinstance(df.iat[i, 0], str):
            continue
        name = ws(df.iat[i, 0])
        if not name:
            continue
        started = started or name == "전국"
        if not started:
            continue
        age = AGE_LABEL.match(name) if prefix == "9-2." else None
        if age:
            nodes[-1]["cells"][str(int(age.group(1)))] = _mois_cell(df.iat[i, 1])
            continue
        cells = {k: (_mois_cell(df.iat[i, c]) if c < df.shape[1] else None)
                 for k, c in cols.items()}

        def add(level, parent, dist=None, dong=None):
            nodes.append({"level": level, "sido": sido, "district": dist, "dong": dong,
                          "parent": parent, "cells": cells})
            return len(nodes) - 1
        if name == "전국":
            nation = add("nation", None)
        elif name in MOIS_SIDO:
            if name == "세종시" and sido == "세종특별자치시":
                district = add("district", province, "세종시")
            else:
                sido = MOIS_SIDO_RELEASE.get(name, name)
                province = add("province", nation, "세종시" if sido == "세종특별자치시" else None)
                district = province if sido == "세종특별자치시" else None
                city = city_name = None
        elif name.endswith(MOIS_DONG) and prefix in ("1-3.", "11."):
            if district is None:
                raise SystemExit("%d %s: sub-district %s printed under no district"
                                 % (y, prefix, name))
            add("dong", district, nodes[district]["district"], name)
        elif name.endswith(("시", "군", "구")):
            gu = None
            if city_name and name.startswith(city_name) and name[len(city_name):] in GU_CITY[city_name]:
                gu = name[len(city_name):]
            elif city_name and name in GU_CITY[city_name]:
                gu = name
            if gu:
                district = add("district", city, city_name + " " + gu)
                nodes[city]["level"] = "city"
            else:
                district = add("district", province, name)
                city, city_name = (district, name) if name in GU_CITY else (None, None)
        else:
            raise SystemExit("%d %s: a row the gate cannot place: %s" % (y, prefix, name))
    return nodes


def mois_settle(nodes, row_ids):
    """Settle the masked cells of a mois_tree in place; return {(node, cell): value}.
    Stops on a fully printed identity that fails or a settled value outside 0-4."""
    kids = {}
    for i, n in enumerate(nodes):
        if n["parent"] is not None:
            kids.setdefault(n["parent"], []).append(i)
    eqs = []
    for i, n in enumerate(nodes):
        for tot, parts in row_ids:
            if tot in n["cells"] and all(p in n["cells"] for p in parts):
                eqs.append(((i, tot), [(i, p) for p in parts]))
    for i, ch in kids.items():
        for c in nodes[i]["cells"]:
            if all(c in nodes[j]["cells"] for j in ch):
                eqs.append(((i, c), [(j, c) for j in ch]))
    get = lambda cell: nodes[cell[0]]["cells"][cell[1]]
    bad = [(nodes[l[0]]["sido"], nodes[l[0]]["district"], nodes[l[0]]["dong"], l[1])
           for l, r in eqs if all(isinstance(get(c), int) for c in [l] + r)
           and get(l) != sum(get(c) for c in r)]
    if bad:
        raise SystemExit("MOIS identities that do not hold on printed cells: %s" % bad[:5])
    settled, moved = {}, True
    while moved:
        moved = False
        for l, r in eqs:
            cells = [l] + r
            vals = [get(c) for c in cells]
            if any(v is None for v in vals):
                continue
            open_ = [c for c, v in zip(cells, vals) if v == MOIS_MASK]
            if len(open_) != 1:
                continue
            x = open_[0]
            v = sum(get(c) for c in r) if x == l else get(l) - sum(get(c) for c in r if c != x)
            if not 0 <= v <= 4:
                raise SystemExit("MOIS masked cell settles outside 0-4: %s %s %s = %d"
                                 % (nodes[x[0]]["district"], nodes[x[0]]["dong"], x[1], v))
            nodes[x[0]]["cells"][x[1]] = v
            settled[x] = v
            moved = True
    return settled


def _mois_key(n):
    sd, dist = n["sido"], n["district"]
    if dist is None:
        return None
    sd, dist = MOIS_DISTRICT_RELEASE.get((sd, dist), (sd, dist))
    if dist.startswith("부천시 "):
        dist = "부천시"         # one district in every year of the release (2024's gu summed)
    return sd, re.sub(r"\s+", "", dist)


def _dong_key(s):
    t = re.sub(r"[\s·.,・ㆍᆞ‧･]", "", str(s))
    while True:
        u = re.sub(r"제([0-9])", r"\1", t)
        if u == t:
            return t
        t = u


def mois_mask_gates():
    """The released MOIS cells of 2016 to the release year against the sheets they
    come from, every masked cell settled by the sheets' identities (above)."""
    years = range(2016, RELEASE_LAST_YEAR + 1)
    rd = lambda f, **kw: pd.read_csv(os.path.join(RELEASE_DATA, f), encoding="utf-8-sig", **kw)
    rc, report = 0, []

    def compare(label, want, got, settled_keys):
        """want/got: {key: value}; settled_keys: the keys of want that were masked."""
        miss = sorted(k for k in want if k not in got)
        diff = sorted(k for k in want if k in got and got[k] != want[k])
        extra = sorted(k for k in got if k not in want)
        per = {}
        for k in settled_keys:
            if k in got and got[k] == want[k]:
                per[k[0]] = per.get(k[0], 0) + 1
        report.append((label, len(want), sum(per.values()), per, miss, diff, extra))
        return 1 if (miss or diff or extra) else 0

    # children_by_age <- 9-2: the districts, and the 2024 '부천시' as the sum of its gu
    ca = rd("children_by_age.csv", usecols=["year", "sido", "sigungu", "age", "n"])
    ca = ca[ca["year"].isin(years)]
    got = {(int(y), sd, re.sub(r"\s+", "", sg), str(int(a))): int(n)
           for y, sd, sg, a, n in ca.itertuples(index=False)}
    want, masked = {}, set()
    for y in years:
        nodes = mois_tree(y, "9-2.")
        was = {(i, c) for i, n in enumerate(nodes) for c, v in n["cells"].items() if v == MOIS_MASK}
        mois_settle(nodes, MOIS_SHEETS["9-2."][1])
        acc = {}
        for i, n in enumerate(nodes):
            if n["level"] not in ("district",) and not (n["level"] == "province"
                                                          and n["sido"] == "세종특별자치시"):
                continue
            if n["level"] == "province" and any(m["parent"] == i for m in nodes):
                continue                     # '세종' prints its district row too
            k = _mois_key(n)
            for a in AGES:
                v = n["cells"].get(a)
                if not isinstance(v, int):
                    if k[1] == "부천시" and n["district"].startswith("부천시 "):
                        acc.setdefault((y,) + k + (a,), []).append(None)
                    continue
                if k[1] == "부천시" and n["district"].startswith("부천시 "):
                    acc.setdefault((y,) + k + (a,), []).append(v)
                    if (i, a) in was:
                        masked.add((y,) + k + (a,))
                    continue
                want[(y,) + k + (a,)] = v
                if (i, a) in was:
                    masked.add((y,) + k + (a,))
        for key, vs in acc.items():
            if None not in vs:
                want[key] = sum(vs)
    rc |= compare("children_by_age (9-2)", want, got, masked)

    # summary_by_eupmyeondong <- 1-3; multicultural_households <- 11
    em = rd("summary_by_eupmyeondong.csv")
    em = em[em["year"].isin(years)]
    colmap = {"합계": "broad_total", "한국국적미취득_소계": "non_naturalized",
              "외국인근로자": "workers", "결혼이민자": "marriage_migrants", "유학생": "students",
              "외국국적동포": "ethnic_koreans", "기타외국인": "other_foreigners",
              "한국국적취득자": "naturalized", "외국인주민자녀": "children"}
    got = {}
    for r in em.itertuples(index=False):
        for ko, en in colmap.items():
            v = getattr(r, en)
            if pd.notna(v):
                got[(int(r.year), r.sido, re.sub(r"\s+", "", r.sigungu),
                     _dong_key(r.eupmyeondong), ko)] = int(v)
    mc = rd("multicultural_households.csv", usecols=["year", "sido", "sigungu",
                                                     "eupmyeondong", "category", "n"])
    mc = mc[mc["year"].isin(years)]
    got_mc = {(int(y), sd, re.sub(r"\s+", "", sg), _dong_key(d), c): int(n)
              for y, sd, sg, d, c, n in mc.itertuples(index=False)}
    for prefix, label, g in (("1-3.", "summary_by_eupmyeondong (1-3)", got),
                             ("11.", "multicultural_households (11)", got_mc)):
        want, masked = {}, set()
        for y in years:
            nodes = mois_tree(y, prefix)
            was = {(i, c) for i, n in enumerate(nodes) for c, v in n["cells"].items()
                   if v == MOIS_MASK}
            mois_settle(nodes, MOIS_SHEETS[prefix][1])
            for i, n in enumerate(nodes):
                if n["level"] != "dong":
                    continue
                k = (y,) + _mois_key(n) + (_dong_key(n["dong"]),)
                for c, v in n["cells"].items():
                    if isinstance(v, int):
                        want[k + (c,)] = v
                        if (i, c) in was:
                            masked.add(k + (c,))
        rc |= compare(label, want, g, masked)

    # summary_by_sigungu <- 1-2: the districts MOIS prints (the 2024 '부천' gu summed)
    sg = rd("summary_by_sigungu.csv")
    sg = sg[sg["year"].isin(years) & sg["broad_total"].notna()]
    got = {}
    for r in sg.itertuples(index=False):
        for ko, en in colmap.items():
            v = getattr(r, en)
            if pd.notna(v):
                got[(int(r.year), r.sido, re.sub(r"\s+", "", r.sigungu), ko)] = int(v)
    want, masked = {}, set()
    for y in years:
        nodes = mois_tree(y, "1-2.")
        was = {(i, c) for i, n in enumerate(nodes) for c, v in n["cells"].items() if v == MOIS_MASK}
        mois_settle(nodes, MOIS_SHEETS["1-2."][1])
        for i, n in enumerate(nodes):
            gu_of_bucheon = n["level"] == "district" and n["district"].startswith("부천시 ")
            if n["level"] == "city" and n["district"] != "부천시":
                continue
            if n["level"] not in ("district", "city") and not (
                    n["level"] == "province" and n["sido"] == "세종특별자치시"):
                continue
            if gu_of_bucheon:
                continue                     # the release carries the city row
            if n["level"] == "province" and any(m["parent"] == i for m in nodes):
                continue
            k = (y,) + _mois_key(n)
            for c, v in n["cells"].items():
                if isinstance(v, int):
                    want[k + (c,)] = v
                    if (i, c) in was:
                        masked.add(k + (c,))
    rc |= compare("summary_by_sigungu (1-2)", want, got, masked)

    print()
    print("MOIS masked cells, %d-%d: printed cells and identity-fixed cells of the "
          "source sheet vs release" % (years[0], years[-1]))
    for label, n, n_set, per, miss, diff, extra in report:
        print("   %-34s cells %8s, of which masked cells fixed %6s (%s)"
              % (label, format(n, ","), format(n_set, ","),
                 ", ".join("%d %d" % kv for kv in sorted(per.items()))))
        for tag, lst in (("missing", miss), ("differs", diff), ("not determined", extra)):
            if lst:
                print("      %s %d, e.g. %s" % (tag, len(lst), lst[:4]))
    if rc:
        print("FAIL: a released MOIS cell differs from what the sheet prints or its "
              "identities fix, or a cell they fix is missing")
        return 1
    print("GATE OK: every released MOIS cell of %d-%d is printed or fixed by the sheet's "
          "identities, and every cell they fix is carried" % (years[0], years[-1]))
    return 0


CREW_CODE = re.compile(r"^E-?0-?([ABC])$")
CREW_HEAD = "crew column printed as "


def crew_gate(ns):
    """The crew status is E10 in every year, and crosswalk_visa names its 2007-2009
    columns as the raw tables print them.

    Owner decision (2026-09-27). The 2007-2009 editions print the crew status as columns
    of their own, E0A '내항선원', E0B '어선원' and (2009) E0C '순항선원' (E-0-A to E-0-C in
    the 2008-2009 district tables), the three subdivisions of E-10 '선원취업' that the
    2006 edition and the 2010 edition on print as E-10; until that day they were
    carried under a code of their own, E0, so E10 had no values in 2007-2009. Here:
    no released visa file carries E0; visa_national has E10 in every year and
    population, and in 2007-2009 it equals the crew columns of the table's grand-total
    row; and the crosswalk_visa rows whose rule reads 'crew column printed as ...'
    name exactly the codes, labels and editions the national registered and staying
    tables print.
    """
    stay = dict(ns["STAY_FILES"])
    stay.update(HEADLINE_STAY)
    printed, sums = {}, {}
    for pop, files in (("registered", ns["REG_FILES"]), ("stay", stay)):
        for y, path in sorted(files.items()):
            if not 2006 <= y <= 2010 or not os.path.exists(path):
                continue
            df = pd.read_excel(path, sheet_name=0, header=None)
            cols = {}
            for j in range(df.shape[1]):
                for i in range(1, min(9, len(df))):
                    v = re.sub(r"\s+", "", str(df.iat[i, j]).split("\n")[-1])
                    m = CREW_CODE.match(v)
                    if m:
                        lab = re.sub(r"\s+", "", str(df.iat[i - 1, j]).split("\n")[0])
                        cols[j] = ("E0" + m.group(1), lab)
                        printed.setdefault(("E0" + m.group(1), lab), set()).add(y)
                        break
            if not cols:
                continue
            # the grand-total row, as printed_total() finds it
            row = None
            for i in range(min(12, len(df))):
                head = norm(" ".join(str(x) for x in df.iloc[i].tolist()[:2] if isinstance(x, str)))
                if any(t in head for t in ("총계", "총합계", "합계", "grand-total")) and \
                        not re.search(r"(19|20)[0-9]{2}년", head):
                    row = i
                    break
            if row is None:
                sums[(pop, y)] = None
                continue
            sums[(pop, y)] = int(sum(cell_number(df.iat[row, j]) or 0 for j in cols))
    vn = pd.read_csv(os.path.join(RELEASE_DATA, "visa_national.csv"), encoding="utf-8-sig")
    bad = []
    for f in ("visa_national.csv", "visa_by_nationality.csv", "visa_by_sido.csv",
              "visa_by_sigungu.csv", "crosswalk_visa.csv"):
        d = pd.read_csv(os.path.join(RELEASE_DATA, f), encoding="utf-8-sig", usecols=["visa_code"])
        if d["visa_code"].astype(str).str.fullmatch(r"E0[A-C]?").any():
            bad.append("%s carries an E0 code" % f)
    e10 = vn[vn["visa_code"] == "E10"].groupby(["population", "year"])["n"].sum()
    for pop in ("registered", "stay"):
        for y in range(2006, RELEASE_LAST_YEAR + 1):
            if int(e10.get((pop, y), 0)) <= 0:
                bad.append("visa_national has no E10 in %s %d" % (pop, y))
    for (pop, y), s in sorted(sums.items()):
        got = int(e10.get((pop, y), 0))
        if s is None or got != s:
            bad.append("%s %d: E10 %d, the table's crew columns %s" % (pop, y, got, s))
    cv = pd.read_csv(os.path.join(RELEASE_DATA, "crosswalk_visa.csv"), encoding="utf-8-sig")
    listed = {}
    for sc, code, rule in cv[["source_code", "visa_code", "rule"]].itertuples(index=False):
        if not str(rule).startswith(CREW_HEAD):
            continue
        lab = re.match(r"[^\s(]+", str(rule)[len(CREW_HEAD):]).group(0)
        m = re.match(r"^(E0[A-C]) \((.+?) editions?\)$", str(sc))
        eds = set()
        for part in (m.group(2).split(",") if m else []):
            a, _, b = part.strip().partition("-")
            eds |= set(range(int(a), int(b or a) + 1))
        listed[(m.group(1) if m else sc, lab)] = eds
        if code != "E10":
            bad.append("crosswalk_visa maps %s to %s" % (sc, code))
    if listed != printed:
        bad.append("crosswalk_visa crew rows %s; the tables print %s"
                   % (sorted((k, sorted(v)) for k, v in listed.items()),
                      sorted((k, sorted(v)) for k, v in printed.items())))
    print()
    print("Crew status (E0A-E0C = E-10-1..3): %s" %", ".join(
        "%s %s %s" % (c, l, "/".join(str(y) for y in sorted(e))) for (c, l), e in sorted(printed.items())))
    print("   E10 2007-2009 = crew columns of the table: %s" %", ".join(
        "%s %d %s" % (p, y, format(s, ",") if s is not None else "?") for (p, y), s in sorted(sums.items())))
    for b in bad[:12]:
        print("   ", b)
    if bad or not printed:
        print("FAIL: the crew status is not one E10 series, or crosswalk_visa does not name "
              "the crew columns the tables print")
        return 1
    print("GATE OK: no E0 in any released visa file, E10 in every year 2006-%d, the "
          "2007-2009 crew columns carried as E10 and listed in crosswalk_visa as printed"
          % RELEASE_LAST_YEAR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
