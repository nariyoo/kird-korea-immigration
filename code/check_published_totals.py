# -*- coding: utf-8 -*-
"""배포본의 전국 합계를 연감이 인쇄한 총계와 맞춰 본다.

원고가 대는 「공표치와 0.x% 안에서 일치한다」는 문장의 근거다. 파이프라인 안의
검사가 아니라, 연감 파일에서 **인쇄된 총계 한 칸만** 따로 읽어 배포본
`visa_national.csv` 의 그 해 합계와 비교한다. 조화 과정을 거치지 않은 값과 맞대는
것이라, 조화가 무엇을 흘렸는지 아니면 더했는지 그대로 드러난다.

    python 02_code/check_published_totals.py

체류외국인은 모든 해에 연감 2장의 국적×체류자격 표에서 읽는다. 2006-2010년판의
그 표(2장 Ⅱ 「체류외국인 현황」)는 2026-09-26(1라운드 수정)까지 「없는 표」로 여겨져
등록 + 단기 + 거소신고를 합쳐 만들었는데, 합계는 맞아도 국적은 틀렸다(거소신고 표의
중국·러시아와 기타 칸). 이제 그 표를 바로 읽고, stay_country_gate 가 그 다섯 해를
국적마다 표의 국적별 총계와 맞댄다.

출력: 03_cleaned_data/published_total_check.csv
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

# 2006-2010년판 2장 첫머리의 「체류외국인 현황」. 국적×체류자격 표이고 01 이 그 해의
# 체류외국인을 이 표에서 읽는다(1라운드 수정, 2026-09-26; 그 전에는 세 표를 합쳤다).
# 2026-09-26: 이 경로가 code/ 의 부모(04_dataset_release)에서 01_raw_data 를 찾아
# 늘 「원자료 없음」이었다. kird.RAW 를 쓴다.
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
    """연감은 한 칸에 줄바꿈으로 여러 수를 넣기도 한다. 첫 수만 쓴다."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).split("\n")[0].replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def printed_total(path):
    """그 파일이 인쇄한 총계.

    판마다 표 머리가 달라서 「총계 열」을 이름으로 찾으면 자꾸 빗나간다(2019년
    이후는 열 이름이 총합계이고, 2014년판은 열 이름이 그냥 계다). 대신 총계
    **행**을 찾은 뒤 그 행에서 가장 큰 수를 쓴다. 총계 열은 나머지 열의 합이므로
    그 행에서 언제나 가장 크다.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    for i in range(min(12, len(df))):
        row = df.iloc[i].tolist()
        head = norm(" ".join(str(x) for x in row[:2] if isinstance(x, str)))
        if not head:
            continue
        if not any(t in head for t in ("총계", "총합계", "합계", "grand-total")):
            continue
        # 2006-2007년판은 비교용으로 앞선 해의 총계 행을 위에 얹어 둔다.
        # 「2004년 총계」 같은 행을 그 해의 총계로 읽으면 안 된다.
        if re.search(r"(19|20)[0-9]{2}년", head):
            continue
        nums = [cell_number(v) for v in row]
        nums = [n for n in nums if n and n > 0]
        if nums:
            return max(nums), ""
    # 2006-2007년판처럼 첫 칸이 「계」 한 글자인 판
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
    # 파일 목록은 01 과 같은 것을 쓰되, 그 스크립트를 실행하지 않고 다시 적는다.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_p1", os.path.join(HERE, "01_parse_yearbooks.py"))
    src = open(spec.origin, encoding="utf-8").read()
    ns = {"__name__": "_p1_defs"}
    head = src[:src.index("# Continent aggregate")]
    exec(compile(head, spec.origin, "exec"), ns)      # 사전만 얻는다

    rel = released_totals()
    rows = []
    stay_files = dict(ns["STAY_FILES"])
    stay_files.update(HEADLINE_STAY)          # 2006-2010 은 머리 총계 표로 본다
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

    print("연감이 인쇄한 총계 대 배포본 전국 합계")
    print()
    for series in ("registered", "staying"):
        sub = df[df["series"] == series].dropna(subset=["diff_pct"])
        print("== %s (%d개 연도)" % (series, len(sub)))
        for _, r in sub.iterrows():
            print("   %d  인쇄 %11s  배포 %11s  %+.3f%%"
                  % (r["year"], format(int(r["printed"]), ","),
                     format(int(r["released"]), ","), r["diff_pct"]))
        if len(sub):
            w = sub.loc[sub["diff_pct"].abs().idxmax()]
            print("   최대 어긋남 %.3f%% (%d년)" % (abs(w["diff_pct"]), w["year"]))
        miss = df[(df["series"] == series) & (df["diff_pct"].isna())]
        if len(miss):
            print("   대조 못 한 해: %s" %
                  ", ".join("%d(%s)" % (r["year"], r["note"] or "인쇄 총계 없음")
                            for _, r in miss.iterrows()))
        print()
    print("wrote", out)

    # 2026-09-26 관문. 배포본 합이 인쇄 총계와 **같아야** 한다. 무국적·기타 줄을
    # 버리던 동안은 해마다 106-337명 모자랐고, 그것을 「0.05% 안」이라고만 적었다.
    # 2006-2010 체류(세 표를 합친 값)는 「겹침」이라는 가정으로 여기서 빠져 있었는데,
    # 실제 차이는 반대 방향(합성치 < 공표치)이었고 거소신고 표의 기타 열을 버린
    # 값과 해마다 같았다(3차 대조). 이제 그 다섯 해도 같아야 한다.
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
    return rc or rc2 or rc3 or rc4 or rc5


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

    1라운드 수정 (2026-09-26). These five editions print a nationality x status table
    of staying foreigners (2장 Ⅱ 「체류외국인 현황」) that the build did not use: it
    composed the years as registered + short-term + overseas-Korean residence reports,
    which gives the right total but books the residence reports under the generic
    nationality their own table prints (중국 2010: 231,304 against the table's 199,802;
    한국계중국인 377,577 against 409,079) and turned that table's catch-all column into
    a nationality called 기타 (386-941 a year). Each nationality of
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
    print("체류외국인 2006-2010: 국적마다 연보 2장 Ⅱ 표의 총계 대 nationality_national")
    print("   %d 국적-연도, 어긋남 %d" % (n_cells, len(off)))
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

    1라운드 수정 (2026-09-26). The 2006 and 2007 editions print no district table,
    only a province table naming 타이완, 미국, 일본, 필리핀 and 중국 with an Other
    column. It is now carried as the 2006-2007 rows of nationality_by_sido (Other as
    기타). The 2006 province rows print each cell as two lines, (거주) and (기타),
    with no 계 line, so a province's count is their sum; the national row prints a 계
    line first. Every province and column must match.
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
    print("시도x국적 2006-2007: 연보 시도 표 대 nationality_by_sido")
    print("   %d 칸, 어긋남 %d" % (n_cells, len(off)))
    for o in off[:12]:
        print("   ", o)
    if off or n_cells != 2 * 16 * 6:
        print("FAIL: nationality_by_sido 2006-2007 differs from the province table")
        return 1
    print("GATE OK: nationality_by_sido 2006-2007 equals the province table cell by cell")
    return 0


def _pre2014_files(pattern):
    """The 2008-2013 district tables (지역및국적별 / 지역및체류자격별), which 01 does not
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
    them (the country x visa table, whose name also holds 체류자격, is excluded)."""
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

    2008-2013 editions put title lines above a two-line header, and the 총계 label
    sits in column 0 or 1 (2012-2013 stack the Korean and English, and the T/M/F
    values, in one cell, so the first line is read). From 2014 the header is one
    line and the 계 / 총계 / 총합계 row follows it.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    for i in range(1, 9):
        for c in (0, 1):
            if norm(str(df.iloc[i, c]).split("\n")[0]) in ("계", "총계", "총합계"):
                return df, i
    return df, None


def district_gate(files):
    """The district-by-nationality table against its own printed grand-total row.

    2026-09-26 (4차 대조): the parser wrote each nationality column of a row straight
    into its result, so where several columns fold onto one country (영국 +
    영국외지민 + 영국외지시민 + 영국해외영토시민, 홍콩 + 홍콩거주난민, 미국 + 미국인근섬)
    the last one overwrote the rest; and the residual lines some editions still print
    under abolished districts (청원군, 당진군, 연기군, 여주군, 2014-2018) were dropped
    instead of carried on their successor. nationality_by_sigungu fell short of the
    table's printed total every year from 2014 (by 3,068 in 2024, 2,918 of them United
    Kingdom nationals; by 4,287 in 2014), and the national checks above never saw it,
    because they read the status tables.

    The yearbook's printed grand total must equal nationality_by_sigungu summed over
    every district and every column, the columns that name no nationality (무국적,
    미등록국가, 기타) included. Until 2026-09-26 (final audit) those columns were left
    out on both sides here, because the district files dropped them, and the gate
    passed over 126-183 missing people a year; the parser carries them now, district
    by district, so the whole printed total is compared. From 2014 that is the
    grand-total row's 계 cell, which equals the sum of the province 소계 rows: in
    2014 and 2015 the grand row's own nationality cells add up to 9 and 15 fewer than
    its 계 (the province rows, and the district lines under them, add up). KNOWN
    holds the people the table prints on a line that names no district.
    """
    # The one place the raw table does not add up: in 2015 경기도's district rows sum
    # to one less than the 소계 the same sheet prints (369,664 against 369,665), and
    # the grand total follows the 소계, so the printed total holds one person no row
    # has. The district-by-visa table of the same edition prints that person on a
    # 화성시 동부출장소 line (1), which this table does not print (final audit).
    # (The 2014 마산시 (1) and 창원시 (3) and 2015 수원시 (2) and 창원시 (1) city
    # lines were exceptions here until 2026-09-26, 5차 대조; they are carried now.)
    KNOWN = {2015: 1}
    nb = pd.read_csv(os.path.join(RELEASE_DATA, "nationality_by_sigungu.csv"),
                     encoding="utf-8-sig", usecols=["year", "country", "n"])
    got = got_all = nb.groupby("year")["n"].sum()
    rows = []
    # 2008-2013 (5차 대조, 2026-09-26). These editions print the top 19 nationalities
    # and a 기타 column that is the residual of all the others (무국적 included), and
    # the district files carry that column as a country of its own, so the whole
    # printed total is compared, not the named columns. Until this date no gate
    # covered these years, and the district files fell 5-294 people a year short:
    # the city lines printed beside that city's own gu (용인시 14/142/33 in
    # 2008-2010, 창원시 261 in 2010, 성남시, 안양시, 고양시, 천안시, 청주시 1-15)
    # and 포천군 2009 (1) were dropped as strays, though each province's 소계 and the
    # grand total count them on top of the gu rows. No exception: in all six tables
    # the district lines add up to the province 소계 and the 소계 to the grand total.
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
    print("시군구x국적 표: 인쇄 총계 대 nationality_by_sigungu 합 (모든 칸)")
    for y, pt, g in rows:
        print("   %d  인쇄 %11s  배포 %11s" % (y, format(int(pt or 0), ","),
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
# residual lines some editions still print under an abolished district. 연기군 counts
# in 세종 (owner decision), so it moves province as well.
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

    Returns ({(sido, line): n}, {sido: 소계}, grand 계), where n is the row-total cell
    (column 3), so every column of the table counts, the ones that name no nationality
    included. A line's value is its 계 row, or 남 + 여 where the edition prints no 계
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
    # 세종 prints its province row and no district line (2021 puts its 남/여 rows
    # under a 시군구 cell of 0); its one district is the province.
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
    district table's columns that name no nationality (무국적, 미등록국가, 기타) were
    dropped at every level below the country until this date, 126-183 people a year
    over up to 70 districts, and a district that loses a person while another gains
    one leaves the national sum untouched. Here each district of
    nationality_by_sigungu, all columns summed, must equal the row-total cell of the
    line or lines the table prints for it (after the relabelling the README
    documents: renames, residual lines of abolished districts, 출장소 lines, the
    부천 gu, 세종), and each province of nationality_by_sido, which counts a district
    in the province of that year, must equal the table's own 소계, with the residual
    연기군 line moved to 세종 as the release does. 2014 to the release year. The one
    exception is the 2015 경기도 소계, one person above its own district lines.
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
        # provinces: the table's own 소계, with the 연기군 line counted in 세종
        prov = dict(sub)
        yg = dist.get(("충청남도", "연기군"), 0)
        if yg:
            prov["충청남도"] = prov.get("충청남도", 0) - yg
            prov["세종특별자치시"] = prov.get("세종특별자치시", 0) + yg
        for sd in sorted(set(prov) | {s for (y, s) in got_p.index if y == year}):
            if not prov.get(sd) and not got_p.get((year, sd)):
                continue           # 2014's empty 기타 province row
            n_p += 1
            w = prov.get(sd, 0) - KNOWN_PROV.get((year, sd), 0)
            if w != int(got_p.get((year, sd), 0)):
                off_p.append((year, sd, w, int(got_p.get((year, sd), 0))))
    print()
    print("시군구x국적 표: 시군구 줄마다, 시도 소계마다 (모든 칸)")
    print("   시군구 %d곳-연도, 어긋남 %d; 시도 %d곳-연도, 어긋남 %d"
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

    2026-09-26 (5차 대조). Two losses no gate saw. The table's 기타 column (Others,
    2013 on), the statuses it does not list by code, has no code in its header, and
    03's parser kept only coded columns: visa_by_sigungu fell short by 363 in 2013,
    39,210 in 2020 and 31,626 in 2024, exactly visa_national's ETC. And the city
    lines of 2008-2013 went through the population table's city-total rule. The
    whole printed total must be there; the table adds up in every year (district
    lines to the 소계, the 소계 to the grand total), so there is no exception.

    The two district tables of one edition do not always place a person in the same
    district: the 2015 nationality table prints a bare 창원시 line (1) above 창원시
    마산합포구 (2,159), and the visa table prints no 창원시 line and 2,160 for
    마산합포구. Each file follows its own table; validate_release's
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
    print("시군구x체류자격 표: 인쇄 총계 대 visa_by_sigungu 합")
    for y, pt, g in rows:
        print("   %d  인쇄 %11s  배포 %11s" % (y, format(int(pt or 0), ","),
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


if __name__ == "__main__":
    sys.exit(main())
