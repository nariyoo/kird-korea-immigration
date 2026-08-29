# -*- coding: utf-8 -*-
"""Parse the overseas-Korean residence-report tables into a released file.

**Why this file exists.** The district and province visa tables are built from
the yearbook's 시군구별/시도별 체류자격별 **등록외국인** sheets, and holders of
the F-4 overseas-Korean status do not appear in them: under the Overseas Koreans
Act they file a place-of-residence report (거소신고) instead of a foreign-resident
registration. So `visa_by_sigungu` records zero F-4 in every district in every
year, and a user asking where overseas Koreans live gets nothing.

The yearbook does publish them, in a separate chapter, at province level by
nationality, every year from 2008 to 2024. Until now the deposit did not carry
that table at all, which is the gap this file closes. It was found on 2026-08-28
by checking the raw source against the released files rather than trusting the
explanation of why F-4 was absent.

**What this is not.** It is province level, not district, because the source is.
And it counts residence reports, not the F-4 population on the staying basis;
the two differ (553,664 against 555,951 in 2024) because they are different
registers closed on different dates.

    python code/06_diaspora_residence.py
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# **뿌리는 제 위치에서 세지 않는다.** 이 파일은 처음에 04_dataset_release/code
# 안에 있었고, 거기 기준으로 두 칸 위가 뿌리였다. 02_code 로 옮기자 뿌리가 한
# 칸 어긋나 연보를 「한 해도 못 읽었다」고 답했다 — 산출을 안 쓰고 끝나므로
# 조용한 고장이다 (2026-08-29). 다른 단계들처럼 kird 가 찾은 뿌리를 쓴다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kird import ROOT                                        # noqa: E402

SRC = os.path.join(ROOT, "01_raw_data", "출입국통계연보")
OUT = os.path.join(ROOT, "04_dataset_release", "data",
                   "diaspora_residence_by_sido.csv")

# Every year publishes two residence-report tables side by side: 외국적동포
# (ethnic Koreans holding a foreign nationality) and 재외국민 (Korean citizens
# living abroad who report a domestic address). They are different populations
# and only the first belongs here. A glob on 거소신고 alone picks whichever the
# filesystem returns first, and for 2015 it returned the wrong one, which would
# have put Korean citizens into a file about foreign residents.
WANT = re.compile(r"(외국적|외국국적)동포")
SKIP = re.compile(r"재외국민")

# Column labels that hold a row or column total rather than a nationality. 2014
# labels its total column 계, which the first version counted as a nationality
# and so doubled every province in that year.
RESIDUAL = re.compile(r"기타|others?|etc\.?", re.I)

TOTALS = {"총합계", "총계", "계", "소계", "합계", "total", "grand-total", "grandtotal"}

SIDO = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
        "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원도",
        "강원특별자치도", "충청북도", "충청남도", "전라북도", "전북특별자치도",
        "전라남도", "경상북도", "경상남도", "제주특별자치도", "제주도"]
# The panel keeps the pre-2023 province names, as every other released file does.
# 2008 to 2010 abbreviate the province, so the short forms map in here too;
# without them those three years matched no row and were dropped in silence.
ALIAS = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도",
         "제주도": "제주특별자치도",
         "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
         "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
         "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
         "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
         "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
         "경남": "경상남도", "제주": "제주특별자치도"}

EN = {"서울특별시": "Seoul", "부산광역시": "Busan", "대구광역시": "Daegu",
      "인천광역시": "Incheon", "광주광역시": "Gwangju", "대전광역시": "Daejeon",
      "울산광역시": "Ulsan", "세종특별자치시": "Sejong", "경기도": "Gyeonggi-do",
      "강원도": "Gangwon-do", "충청북도": "Chungcheongbuk-do",
      "충청남도": "Chungcheongnam-do", "전라북도": "Jeollabuk-do",
      "전라남도": "Jeollanam-do", "경상북도": "Gyeongsangbuk-do",
      "경상남도": "Gyeongsangnam-do", "제주특별자치도": "Jeju-do"}


def norm(s):
    return re.sub(r"\s+", "", str(s)).strip()


def find_header(df):
    """The header row, and how many leading columns are labels rather than data.

    2008 to 2010 print a bilingual table: column 0 is the Korean province name,
    column 1 its English name, and the numbers start at column 2. Later years
    drop the English column. Reading column 1 as the total in a bilingual year
    parses an English string as a number and loses the year.
    """
    def english(cell):
        c = norm(cell)
        return bool(c) and bool(re.fullmatch(r"[A-Za-z][A-Za-z\-/. ]*", c))

    for i in range(min(14, len(df))):
        row = [norm(c) for c in df.iloc[i].tolist()]
        has_total = any(c.lower() in TOTALS for c in row)
        labelled = any(c in ("시도", "구분", "시·도") or c.startswith("국적")
                       for c in row)
        if has_total and labelled:
            lead = 2 if english(df.iloc[i].tolist()[1]) else 1
            return i, lead
    # Bilingual years label the columns over two rows; the Korean row carries the
    # nationality names and the row under it the English ones.
    for i in range(min(14, len(df))):
        row = [norm(c) for c in df.iloc[i].tolist()]
        if row and row[0].lower() in TOTALS and len(row) > 3:
            hdr = max(0, i - 2)
            lead = 2 if english(df.iloc[i].tolist()[1]) else 1
            return hdr, lead
    return None, 1


def label_col(body):
    """Which column holds the province name.

    2008 and 2009 carry a blank leading column, so the name sits in column 1
    while every later year has it in column 0. Assuming column 0 read "nan" for
    every row and dropped both years without failing.
    """
    best, hits = 0, -1
    for j in range(min(4, body.shape[1])):
        n = sum(1 for v in body.iloc[:, j]
                if norm(v) in SIDO or norm(v) in ALIAS)
        if n > hits:
            best, hits = j, n
    return best


def parse(path, year):
    """One year's table into (year, sido, country, n) rows.

    The residual column is recomputed rather than read. In 2011 the source's
    기타 cell holds 73,992 where the province rows imply 1,122, and reading it
    put the year 54% above its own stated total. Every year is checked against
    the sheet's grand total afterwards, so a source error of that kind fails
    loudly instead of being released.
    """
    raw = pd.read_excel(path, sheet_name=0, header=None)
    h, lead = find_header(raw)
    if h is None:
        return None, "머리 줄을 못 찾음"
    head = [norm(c) for c in raw.iloc[h].tolist()]
    body = raw.iloc[h + 1:].reset_index(drop=True)

    lab = label_col(body)
    lead = max(lead, lab + 1)
    total_col, cols = None, {}
    for j, name in enumerate(head):
        if j < lead or not name or name == "nan":
            continue
        low = name.lower()
        if low in TOTALS:
            if total_col is None:
                total_col = j
            continue
        if name.startswith("국적") or name in ("시도", "구분", "시·도"):
            continue
        if RESIDUAL.fullmatch(name):
            continue
        cols[j] = name

    out, grand = [], None
    for _, r in body.iterrows():
        label = norm(r.iloc[lab])
        if label.lower() in TOTALS:
            if total_col is not None:
                grand = pd.to_numeric(r.iloc[total_col], errors="coerce")
            continue
        if label not in SIDO and label not in ALIAS:
            continue
        sido = ALIAS.get(label, label)
        named = 0
        for j, country in cols.items():
            v = pd.to_numeric(r.iloc[j], errors="coerce")
            if pd.isna(v) or v <= 0:
                continue
            named += v
            out.append({"year": year, "sido": sido, "sido_en": EN.get(sido, ""),
                        "country": country, "n": int(v)})
        if total_col is not None:
            t = pd.to_numeric(r.iloc[total_col], errors="coerce")
            if pd.notna(t) and t > named:
                out.append({"year": year, "sido": sido,
                            "sido_en": EN.get(sido, ""), "country": "기타",
                            "n": int(t - named)})
    if not out:
        return None, "행을 못 읽음"
    df = pd.DataFrame(out)
    if grand and grand > 0:
        gap = abs(df["n"].sum() - grand) / grand * 100
        if gap > 2:
            return None, ("합계가 %.1f%% 어긋난다: 시도합 %s 대 표의 총계 %s"
                          % (gap, format(int(df["n"].sum()), ","),
                             format(int(grand), ",")))
    return df, None


def main():
    frames, notes = [], []
    for year in range(2008, 2025):
        cand = [f for f in glob.glob(os.path.join(SRC, "%d_출입국통계연보" % year,
                                                  "*거소신고*"))
                if WANT.search(os.path.basename(f))
                and not SKIP.search(os.path.basename(f))]
        if not cand:
            notes.append("%d 원본 없음" % year)
            continue
        df, why = parse(cand[0], year)
        if df is None:
            notes.append("%d %s" % (year, why))
            continue
        if why:
            notes.append("%d %s" % (year, why))
        frames.append(df)
        print("  %d  시도 %2d, 국적 %2d, 합계 %s"
              % (year, df["sido"].nunique(), df["country"].nunique(),
                 format(int(df["n"].sum()), ",")))
    if not frames:
        raise SystemExit("한 해도 못 읽었다")
    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df.sort_values(["year", "sido", "country"])
    all_df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("\n-> %s  (%d행, %d개 연도)"
          % (os.path.relpath(OUT, ROOT), len(all_df), all_df["year"].nunique()))
    if notes:
        print("주의:")
        for n in notes:
            print("   " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
