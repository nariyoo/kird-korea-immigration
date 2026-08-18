"""
Build 2006-2025 foreign resident dashboard from KIS yearbook excel files.

Outputs:
- 03_cleaned_data/stay_long.csv  (체류외국인 long format)
- 03_cleaned_data/reg_long.csv   (등록외국인 long format)
- dashboard.html                (single-file Plotly dashboard)
"""

import os
import re
import json
import warnings
import pandas as pd

from kird import morans_i as _morans_i
from kird import (COUNTRY_CANONICAL, COUNTRY_LANGUAGE, COUNTRY_REGION,
                          SIDO_EN_SHORT as SIDO_EN)
from kird import ROOT

warnings.filterwarnings("ignore")

BASE = ROOT
RAW = os.path.join(BASE, "01_raw_data")  # source yearbook + population folders live here
OUT_DATA = os.path.join(BASE, "03_cleaned_data")
OUT_SITE = os.path.join(BASE, "05_dashboard")
OUT_SITE_DATA = os.path.join(OUT_SITE, "data")
os.makedirs(OUT_DATA, exist_ok=True)
os.makedirs(OUT_SITE_DATA, exist_ok=True)

# --- File paths -------------------------------------------------------------

STAY_FILES = {
    # 2007-2010: 체류외국인 = 등록 + 단기 (no combined file); handled by 'stay_combined' loader
    2011: f"{RAW}/출입국통계연보/2011_출입국통계연보/11_2장_Ⅱ_1.국적및체류자격별 체류외국인현황.xls",
    2012: f"{RAW}/출입국통계연보/2012_출입국통계연보/12_2장_Ⅱ_1.국적및체류자격별_체류외국인형황.xlsx",
    2013: f"{RAW}/출입국통계연보/2013_출입국통계연보/13_2장_Ⅱ_1.국적및체류자격별 체류외국인현황.xlsx",
    2014: f"{RAW}/출입국통계연보/2014_출입국통계연보/14_2장_Ⅰ_1.국적_지역 및 체류자격별 체류외국인 현황.xlsx",
    2015: f"{RAW}/출입국통계연보/2015_출입국통계연보/15_2장_Ⅰ_1.국적_지역 및 체류자격별 체류외국인 현황.xlsx",
    2016: f"{RAW}/출입국통계연보/2016_출입국통계연보/16_2장_Ⅰ_1.국적_지역 및 체류자격별 체류외국인 현황.xls",
    2017: f"{RAW}/출입국통계연보/2017_출입국통계연보/17_2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xls",
    2018: f"{RAW}/출입국통계연보/2018_출입국통계연보/18_2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2019: f"{RAW}/출입국통계연보/2019_출입국통계연보/15.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2020: f"{RAW}/출입국통계연보/2020_출입국통계연보/2020_2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2021: f"{RAW}/출입국통계연보/2021_출입국통계연보/2021_2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2022: f"{RAW}/출입국통계연보/2022_출입국통계연보/2022_2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2023: f"{RAW}/출입국통계연보/2023_출입국통계연보/2023 2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2024: f"{RAW}/출입국통계연보/2024_출입국통계연보/2024 2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
    2025: f"{RAW}/출입국통계연보/2025_출입국통계연보/2025 2장_Ⅰ_1.국적(지역) 및 체류자격별 체류외국인 현황.xlsx",
}

REG_FILES = {
    2006: f"{RAW}/출입국통계연보/2006_출입국통계연보/2장/3-가[1].국적및체류자격별.xls",
    2007: f"{RAW}/출입국통계연보/2007_출입국통계연보/2-Ⅲ-1.국적및체류자격별.xls",
    2008: f"{RAW}/출입국통계연보/2008_출입국통계연보/2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xls",
    2009: f"{RAW}/출입국통계연보/2009_출입국통계연보/2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xls",
    2010: f"{RAW}/출입국통계연보/2010_출입국통계연보/2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xls",
    2011: f"{RAW}/출입국통계연보/2011_출입국통계연보/11_2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xls",
    2012: f"{RAW}/출입국통계연보/2012_출입국통계연보/12_2장_Ⅲ_1.국적및체류자격별_등록외국인현황.xlsx",
    2013: f"{RAW}/출입국통계연보/2013_출입국통계연보/13_2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xlsx",
    2014: f"{RAW}/출입국통계연보/2014_출입국통계연보/14_2장_Ⅱ_1.국적_지역 및 체류자격별 등록외국인 현황.xlsx",
    2015: f"{RAW}/출입국통계연보/2015_출입국통계연보/15_2장_Ⅱ_1.국적_지역 및 체류자격별 등록외국인 현황.xlsx",
    2016: f"{RAW}/출입국통계연보/2016_출입국통계연보/16_2장_Ⅱ_1.국적_지역 및 체류자격별 등록외국인 현황.xls",
    2017: f"{RAW}/출입국통계연보/2017_출입국통계연보/17_2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xls",
    2018: f"{RAW}/출입국통계연보/2018_출입국통계연보/18_2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2019: f"{RAW}/출입국통계연보/2019_출입국통계연보/17.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2020: f"{RAW}/출입국통계연보/2020_출입국통계연보/2020_2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2021: f"{RAW}/출입국통계연보/2021_출입국통계연보/2021_2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2022: f"{RAW}/출입국통계연보/2022_출입국통계연보/2022_2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2023: f"{RAW}/출입국통계연보/2023_출입국통계연보/2023 2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2024: f"{RAW}/출입국통계연보/2024_출입국통계연보/2024 2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
    2025: f"{RAW}/출입국통계연보/2025_출입국통계연보/2025 2장_Ⅱ_1.국적(지역) 및 체류자격별 등록외국인 현황.xlsx",
}

# 시군구별 × 국적별 등록외국인 (2014+ modern format only)
REGION_COUNTRY_FILES = {
    2014: f"{RAW}/출입국통계연보/2014_출입국통계연보/14_2장_Ⅱ_3.지역 및 국적_지역별 등록외국인 현황.xlsx",
    2015: f"{RAW}/출입국통계연보/2015_출입국통계연보/15_2장_Ⅱ_3.지역 및 국적_지역별 등록외국인 현황.xlsx",
    2016: f"{RAW}/출입국통계연보/2016_출입국통계연보/16_2장_Ⅱ_3.지역 및 국적_지역별 등록외국인 현황.xls",
    2017: f"{RAW}/출입국통계연보/2017_출입국통계연보/17_2장_Ⅱ_3.시군구 및 국적(지역)별 등록외국인 현황.xls",
    2018: f"{RAW}/출입국통계연보/2018_출입국통계연보/18_2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2019: f"{RAW}/출입국통계연보/2019_출입국통계연보/19.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2020: f"{RAW}/출입국통계연보/2020_출입국통계연보/2020_2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2021: f"{RAW}/출입국통계연보/2021_출입국통계연보/2021_2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2022: f"{RAW}/출입국통계연보/2022_출입국통계연보/2022_2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2023: f"{RAW}/출입국통계연보/2023_출입국통계연보/2023 2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2024: f"{RAW}/출입국통계연보/2024_출입국통계연보/2024 2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
    2025: f"{RAW}/출입국통계연보/2025_출입국통계연보/2025 2장_Ⅱ_3.시군구별 및 국적(지역)별 등록외국인 현황.xlsx",
}

# 국적별 × 연령별 체류외국인 (2014+ modern format only)
AGE_FILES = {
    2014: f"{RAW}/출입국통계연보/2014_출입국통계연보/14_2장_Ⅰ_2.국적_지역 및 연령별 체류외국인 현황.xlsx",
    2015: f"{RAW}/출입국통계연보/2015_출입국통계연보/15_2장_Ⅰ_2.국적_지역 및 연령별 체류외국인 현황.xlsx",
    2016: f"{RAW}/출입국통계연보/2016_출입국통계연보/16_2장_Ⅰ_2.국적_지역 및 연령별 체류외국인 현황.xls",
    2017: f"{RAW}/출입국통계연보/2017_출입국통계연보/17_2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xls",
    2018: f"{RAW}/출입국통계연보/2018_출입국통계연보/18_2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xlsx",
    2019: f"{RAW}/출입국통계연보/2019_출입국통계연보/16.국적(지역) 및 연령별 체류외국인 현황.xlsx",
    2020: f"{RAW}/출입국통계연보/2020_출입국통계연보/2020_2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xlsx",
    2021: f"{RAW}/출입국통계연보/2021_출입국통계연보/2021_2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xlsx",
    2022: f"{RAW}/출입국통계연보/2022_출입국통계연보/2022_2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xlsx",
    2023: f"{RAW}/출입국통계연보/2023_출입국통계연보/2023 2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xlsx",
    2024: f"{RAW}/출입국통계연보/2024_출입국통계연보/2024 2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황(60).xlsx",
    2025: f"{RAW}/출입국통계연보/2025_출입국통계연보/2025 2장_Ⅰ_2.국적(지역) 및 연령별 체류외국인 현황.xlsx",
}

# MOIS 주민등록인구: denominator for residential segregation indices
# Files cover overlapping ranges; we use 2014+ to match foreign data.
# The 2015-2025 export uses the site's current layout (name+code in one column,
# 5 columns per year incl. 세대당 인구); parse_population_file reads both layouts.
# Its 2015-2024 values were verified identical to 201512_202412.xlsx, and it is
# listed last so it supplies 2025 (later files win on duplicate keys).
POPULATION_FILES = [
    f"{RAW}/주민등록인구 현황/200812_201512.xlsx",
    f"{RAW}/주민등록인구 현황/201512_202412.xlsx",
    f"{RAW}/주민등록인구 현황/201512_202512.xls",
]

# 국적처리 (귀화 등): 연도별 추이 + 국가별 + 연령별 (2025 latest file)
NATURALIZATION_FILES = {
    "annual": f"{RAW}/출입국통계연보/2025_출입국통계연보/2025_4장_Ⅰ_1.연도별 국적 처리 현황.xlsx",
    "country": f"{RAW}/출입국통계연보/2025_출입국통계연보/2025 4장_Ⅰ_2.국적(지역) 및 유형별 국적 처리 현황.xlsx",
    "age": f"{RAW}/출입국통계연보/2025_출입국통계연보/2025 4장_Ⅰ_3.연령 및 유형별 국적 처리 현황.xlsx",
}

# 단기체류외국인: used to compose 체류외국인 for 2006-2010 where no combined file exists
SHORT_FILES = {
    2006: f"{RAW}/출입국통계연보/2006_출입국통계연보/2장/4-가[1].국적및체류자격별.xls",
    2007: f"{RAW}/출입국통계연보/2007_출입국통계연보/2-Ⅳ-1.국적및체류자격별.xls",
    2008: f"{RAW}/출입국통계연보/2008_출입국통계연보/2장_Ⅳ_1.국적및체류자격별 단기체류외국인현황.xls",
    2009: f"{RAW}/출입국통계연보/2009_출입국통계연보/2장_Ⅳ_1.국적및체류자격별 단기체류외국인현황.xls",
    2010: f"{RAW}/출입국통계연보/2010_출입국통계연보/2장_Ⅳ_1.국적및체류자격별 단기체류외국인현황.xls",
}

# 외국적동포 거소신고 (overseas-Korean residence reports) — the third
# component of 체류외국인 alongside 등록 + 단기. For 2006-2010 (where stay is
# composed) these holders are otherwise omitted, undercounting 체류 by ~2-7%.
SOJOURN_FILES = {
    2006: f"{RAW}/출입국통계연보/2006_출입국통계연보/4장/가. 외국국적동포 거소신고 현황.xls",
    2007: f"{RAW}/출입국통계연보/2007_출입국통계연보/5-Ⅲ-1.외국적동포거소신고현황.xls",
    2008: f"{RAW}/출입국통계연보/2008_출입국통계연보/5장_Ⅲ_1.외국적동포거소신고현황.xls",
    2009: f"{RAW}/출입국통계연보/2009_출입국통계연보/5장_Ⅲ_1.외국적동포거소신고현황.xls",
    2010: f"{RAW}/출입국통계연보/2010_출입국통계연보/5장_Ⅲ_1.외국적동포거소신고현황.xls",
}

# Continent aggregate / total row names to drop from country axis
DROP_NAMES = {
    "계", "총계", "총합계", "소계", "기타", "기타국",
    "Grand-Total", "GrandTotal",
    "아시아주계", "아시아주", "북아메리카주계", "북아메리카주", "북아메리카",
    "남아메리카주계", "남아메리카주", "남아메리카",
    "유럽주계", "유럽주", "유럽",
    "오세아니아주계", "오세아니아주", "오세아니아",
    "아프리카주계", "아프리카주", "아프리카",
    "무국적계", "무국적", "기타국가", "기타지역",
    "북아메리카계", "남아메리카계",
    "북미주계", "북미주", "남미주계", "남미주",
    "구소련계", "구소련",
    # Footnote / header leakage from legacy files
    "체류자격국적", "체류자격",
    "미상", "미등록국가",
}


# Substring patterns to drop (footnotes etc. that aren't real countries)
DROP_CONTAINS = (
    "*표시", "표시되지", "예외적으로", "산업연수", "Exceptionally",
    "단위", "단위:", "Status", "Sojourn", "Nationality",
)


# Sub-codes that should NOT be collapsed (real 2-digit codes, not 1-digit + sub-letter)
NO_COLLAPSE = {"D10", "E10", "ETC"}


def collapse_visa_code(code):
    """Collapse sub-codes (D2A, E61, F5A, H2B, ...) to parent (D2, E6, F5, H2).

    Pre-2010 yearbooks list sub-types as separate columns. To compare across
    years we roll them up to the 2010+ standard parent codes.
    """
    if not isinstance(code, str) or code in NO_COLLAPSE:
        return code
    m = re.match(r"^([A-Z])(\d)([A-Z0-9]+)?$", code)
    if m and m.group(3):
        return f"{m.group(1)}{m.group(2)}"
    return code


# --- Helpers ---------------------------------------------------------------

VISA_HDR_RE = re.compile(r"^\s*([A-Z]-?\d{1,2}|[A-Z]\d{1,2}|T-?\d?|T\d?)\s*\(([^)]+)\)\s*$")
VISA_HDR_RE_REV = re.compile(r"^\s*([^()]+)\(([A-Z]-?\d{1,2})\)\s*$")  # 2018: 외교(A-1)


STRUCT_COLS = {"대륙", "국적", "국적명", "성별", "총합계", "총계", "소계", "세로축구분"}


def parse_visa_header(s):
    """Return (code_norm, label) e.g. ('A1','외교') or (None, None).

    Also accepts the lone '기타' column (no visa code), mapped to code 'ETC',
    label '기타'.
    """
    if not isinstance(s, str):
        return None, None
    s = s.strip()
    if not s or s in STRUCT_COLS:
        return None, None
    m = VISA_HDR_RE.match(s)
    if m:
        code = m.group(1).replace("-", "").upper()
        label = m.group(2).strip()
        return code, label
    m = VISA_HDR_RE_REV.match(s)
    if m:
        label = m.group(1).strip()
        code = m.group(2).replace("-", "").upper()
        return code, label
    # Lone '기타' column (no code), present in 2024 stay file
    if s == "기타":
        return "ETC", "기타"
    # 2018 has '기타(other)' which doesn't match the visa-code regex
    if s.startswith("기타") and "(" in s:
        return "ETC", "기타"
    # Bare visa code without parenthesized label, e.g. 'E8' in 2024 stay file
    m = re.match(r"^([A-Z])-?(\d{1,2})$", s)
    if m:
        code = f"{m.group(1)}{m.group(2)}"
        return code, code  # label = code itself (unknown Korean name)
    return None, None


def is_total_gender(g):
    if not isinstance(g, str):
        return False
    g = g.strip()
    return g in {"총계", "총합계", "(T)", "T", "계"}



# Country names to drop entirely (data noise, not real foreign-resident entries)
COUNTRY_DROP = {
    "한국",  # Korea shouldn't appear in foreign-resident stats (data entry slip)
}


def clean_country(name):
    if not isinstance(name, str):
        return None
    # Collapse multiple spaces (e.g. "중      국" -> "중국")
    cleaned = re.sub(r"\s+", "", name).strip()
    if not cleaned:
        return None
    # Drop footnote / non-country rows
    for pat in DROP_CONTAINS:
        if pat in cleaned:
            return None
    # Strip enclosing parens (e.g. "(마카오)" → "마카오")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1]
    # Canonicalize alternate spellings
    cleaned = COUNTRY_CANONICAL.get(cleaned, cleaned)
    # Drop noise entries
    if cleaned in COUNTRY_DROP:
        return None
    return cleaned or None


def _sum_newline_cell(val):
    """Parse a cell like '44,791\\n31,688\\n13,103' → sum of all parts.

    Used by the legacy parser for 2006-2013 where data cells stack M/F (or T/M/F)
    values via newline. For country rows the parts are M and F → summing yields
    the country total for that visa. For total/continent rows we drop them via
    DROP_NAMES so triple-counting (T+M+F) is fine to ignore.
    """
    if pd.isna(val):
        return 0
    s = str(val).strip()
    if not s:
        return 0
    total = 0
    for part in re.split(r"[\n\r]+", s):
        p = part.replace(",", "").strip()
        if not p or p == "-":
            continue
        try:
            total += int(float(p))
        except ValueError:
            pass
    return total


def _detect_legacy_header(df, max_scan=15):
    """Scan top rows for visa code patterns and return (header_row, visa_cols).

    Returns dict {col_idx: (code, label)}. Handles:
      - 2007-2013: visa code on its own row (e.g. 'A-1', 'D2A') with Korean label
        on the row above.
      - 2006: visa code embedded in cell like '문화\\n예술\\n(D-1)' (Korean +
        parenthesized code in the same cell).
    """
    code_in_parens_re = re.compile(r"\(([A-Z])-?(\d{1,2})(?:-(\d+))?\)")
    bare_code_re = re.compile(r"^\s*([A-Z])-?(\d{1,2})([A-Z]?)\s*$")

    best_row = None
    best_cols = {}
    for i in range(min(max_scan, len(df))):
        cols_in_row = {}
        for j, v in enumerate(df.iloc[i].tolist()):
            if not isinstance(v, str):
                continue
            # Try embedded paren first (2006 format)
            m = code_in_parens_re.search(v)
            if m:
                if m.group(3):
                    code = f"{m.group(1)}{m.group(2)}{m.group(3)}"  # D-3-1 → D31
                else:
                    code = f"{m.group(1)}{m.group(2)}"
                label = re.sub(r"\(.+?\)", "", v).replace("\n", "").replace(" ", "").strip() or code
                cols_in_row[j] = (code, label)
                continue
            # Try bare code (2007-2013 format)
            m2 = bare_code_re.match(v.strip())
            if m2:
                code = f"{m2.group(1)}{m2.group(2)}{m2.group(3)}"
                cols_in_row[j] = (code, code)
                continue
            # 'Others' / 'Etc' / '기타' column in 2013, etc.
            if v.strip() in {"Others", "Etc", "기타", "其他"}:
                cols_in_row[j] = ("ETC", "기타")
        if len(cols_in_row) > len(best_cols):
            best_cols = cols_in_row
            best_row = i

    return best_row, best_cols


def load_legacy(year, path):
    """Parser for 2006-2013 KIS yearbook files.

    Format:
      - Header rows around 2-5: Korean labels and English codes (possibly on
        separate rows, possibly embedded in same cell for 2006).
      - Data starts after header. Each country = one row with comma-formatted
        newline-stacked values like "44,791\\n31,688\\n13,103" (T\\nM\\nF or M\\nF).
      - Country name is in col 0 or col 1 (varies). English name in next col.
      - Total column has the country grand-total as a plain int.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)

    header_row, visa_cols = _detect_legacy_header(df)
    if header_row is None or not visa_cols:
        raise ValueError(f"No visa columns found in {path}")

    # If the row above the code row has Korean text, use it for labels
    bare_code_re = re.compile(r"^\s*[A-Z]-?\d{1,2}[A-Z]?\s*$")
    if header_row > 0:
        label_hdr = df.iloc[header_row - 1].tolist()
        for j in list(visa_cols.keys()):
            code, label = visa_cols[j]
            if label == code and isinstance(label_hdr[j], str):
                cand = label_hdr[j].strip().replace("\n", "").replace(" ", "")
                if cand and not bare_code_re.match(cand):
                    visa_cols[j] = (code, cand)

    # Identify country name column: prefer col 1 (Korean name) over col 0.
    # In 2006 data sometimes col 0 has the name and col 1 is NaN.
    body = df.iloc[header_row + 1:].copy().reset_index(drop=True)

    # Pick the column that has more non-null Korean strings in early rows
    def kr_count(col_idx):
        if col_idx >= body.shape[1]:
            return 0
        sample = body[col_idx].dropna().astype(str).head(40)
        return sample.apply(lambda s: bool(re.search(r"[가-힣]", s))).sum()

    name_col = 1 if kr_count(1) >= kr_count(0) else 0

    # Skip prior-year reference rows (2005 has "2003년 총계" etc.)
    body = body[~body[name_col].astype(str).str.contains(r"\d{4}\s*년|연도\s*별|annual|year", na=False, regex=True)]

    # Clean country names
    body["_country"] = body[name_col].apply(clean_country)
    body = body[body["_country"].notna()]
    body = body[~body["_country"].isin(DROP_NAMES)]
    # Also drop rows where the cleaned name contains '계' as last char (continent totals like 아시아주계)
    body = body[~body["_country"].str.endswith("계")]
    # Drop the global 총계 / Grand-Total row (sometimes ends with English name)
    body = body[~body["_country"].astype(str).str.contains("Grand-Total|소계", na=False, regex=True)]

    # Drop pure-duplicate sub-codes: some legacy yearbooks (2007-2008) list a
    # category total column (e.g. D-3 산업연수) AND its complete sub-breakdown
    # (D31...) summing to the EXACT same value, so keeping both double-counts.
    # This is GATED by the file's own 총계/Grand-Total row: dedup only when the
    # all-column national sum overshoots the authoritative grand total. This
    # avoids mis-dropping years (e.g. 2006) where parent==sub is coincidental
    # and both are genuinely additive.
    # Locate the grand-total column from the header (총계/Grand-Total/합계/Total)
    total_col = None
    for hr_scan in (header_row, header_row - 1):
        if hr_scan < 0:
            continue
        for j, v in enumerate(df.iloc[hr_scan].tolist()):
            if isinstance(v, str) and v.strip() in ("총계", "Grand-Total", "합계", "Total"):
                total_col = j
                break
        if total_col is not None:
            break

    grand_total = None
    for _, r in df.iloc[header_row + 1:].iterrows():
        c0 = r[0] if 0 < len(r) else None
        c1 = r[1] if 1 < len(r) else None
        nm = " ".join(str(x) for x in (c0, c1) if isinstance(x, str))
        if "총계" in nm or "grand-total" in nm.lower():
            if total_col is not None and total_col < len(r):
                grand_total = _sum_newline_cell(r[total_col])
            break

    parent_sum, sub_sum, all_sum = {}, {}, 0
    col_total = {}
    for col_idx, (code, label) in visa_cols.items():
        s = sum(_sum_newline_cell(row[col_idx]) for _, row in body.iterrows())
        col_total[col_idx] = s
        all_sum += s
        parent = collapse_visa_code(code)
        (parent_sum if parent == code else sub_sum)[parent] = \
            (parent_sum if parent == code else sub_sum).get(parent, 0) + s
    if grand_total and all_sum > grand_total * 1.005:
        dup_parents = {p for p, sv in sub_sum.items()
                       if sv > 0 and parent_sum.get(p, 0) == sv}
        if dup_parents:
            visa_cols = {j: (c, l) for j, (c, l) in visa_cols.items()
                         if not (collapse_visa_code(c) != c and collapse_visa_code(c) in dup_parents)}

    # Some legacy editions repeat the EXACT SAME visa code in two adjacent
    # columns (e.g. 2012 staying lists "D-9" twice), so summing both
    # double-counts. When the all-column sum overshoots the authoritative grand
    # total, keep only the largest-valued column for each *exact* code and drop
    # the duplicates. NB: group by the exact detected code, NOT the collapsed
    # parent, so genuine distinct sub-codes (D31, D32 → parent D3) are still
    # summed rather than mistaken for duplicates.
    if grand_total and all_sum > grand_total * 1.001:
        by_code = {}
        for j, (c, l) in visa_cols.items():
            by_code.setdefault(c, []).append(j)
        if any(len(js) > 1 for js in by_code.values()):
            keep = {}
            for code, js in by_code.items():
                best = max(js, key=lambda j: col_total.get(j, 0))
                keep[best] = visa_cols[best]
            visa_cols = keep

    records = []
    for _, row in body.iterrows():
        country = row["_country"]
        if not country:
            continue
        # Skip if country looks like English-only or garbage
        if not re.search(r"[가-힣]", country):
            continue
        for col_idx, (code, label) in visa_cols.items():
            n = _sum_newline_cell(row[col_idx])
            records.append((year, country, code, label, n))

    out = pd.DataFrame(records, columns=["year", "country", "visa_code", "visa_label", "n"])
    out = (
        out.groupby(["year", "country", "visa_code", "visa_label"], as_index=False)["n"].sum()
    )
    return out


def load_modern(year, path):
    """Return long DataFrame: year, country, visa_code, visa_label, n.

    For 2014-2018 the per-country rows only have (M) and (F), no (T), so sum them.
    For 2020+ the per-country rows include a 총계 row directly.
    2019 is a special case (no per-country 총계, M+F only).
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    header_row = df.iloc[0].tolist()

    # Map column index -> (visa_code, visa_label)
    visa_cols = {}
    for i, h in enumerate(header_row):
        code, label = parse_visa_header(h)
        if code:
            visa_cols[i] = (code, label)

    if 2014 <= year <= 2018:
        # 2014-2018: col0=국적명, col1=총계(value), col2=성별(M/F), col3=소계
        # Per-country rows only have (M)/(F); no per-country 총계.
        country_col = 0
        gender_col = 2
        keep_gender = {"(M)", "(F)"}
    elif year == 2019:
        # 2019: col0=대륙, col1=국적, col2=성별, col3=총합계.
        # Per-country rows only have 남성/여성 (no 총계).
        # Continent totals: col0='아시아주', col1='총계', col2='총계'.
        country_col = 1
        gender_col = 2
        keep_gender = {"남성", "여성"}
    else:
        # 2020+: col0=대륙, col1=국적, col2=성별, col3=총합계.
        # Per-country rows have a 총계 row; continent totals have col1=NaN.
        country_col = 1
        gender_col = 2
        keep_gender = None  # use is_total_gender

    body = df.iloc[1:].copy().reset_index(drop=True)

    # Drop continent-aggregate rows BEFORE ffill, otherwise their gender rows
    # (with col1=NaN) inherit the prior country name via ffill and the continent
    # totals get added to that country.
    if year == 2019:
        # Continent totals: col0 non-NaN, col1='총계'.
        # Also drop the gender rows that follow them (col0=NaN, col1=NaN, col2 in {남성,여성})
        # by removing rows where col1 in DROP_NAMES (e.g. '총계') BEFORE ffill,
        # then also blank col1 for rows where col0 marks a new continent block.
        agg_mask = body[country_col].astype(str).str.strip().isin({"총계", "총합계", "소계"})
        # When col0 is a continent name, also blank out col1 for that and next 2 rows
        cont_idx = body.index[body[0].notna() & body[0].astype(str).str.strip().isin(
            {"아시아주", "북아메리카주", "남아메리카주", "유럽주", "오세아니아주", "아프리카주",
             "총합계", "기타", "무국적"}
        )].tolist()
        # The continent row itself is at idx; gender breakout is at idx+1, idx+2.
        # We'll drop continent row + 2 following rows.
        drop_idx = set()
        for ci in cont_idx:
            for off in range(0, 3):
                if ci + off < len(body):
                    drop_idx.add(ci + off)
        body = body.drop(index=list(drop_idx)).reset_index(drop=True)
        # Also drop the agg rows (col1='총계') if any remain
        body = body[~body[country_col].astype(str).str.strip().isin({"총계", "총합계", "소계"})]
        body = body.reset_index(drop=True)
    elif year >= 2020:
        # 2020+: Continent totals look like: col0='아시아주' (non-NaN), col1=NaN.
        agg_mask = body[country_col].isna() & body[0].notna()
        body = body[~agg_mask].reset_index(drop=True)
    # 2014-2018: country name is in col 0 directly; continent rows have col0
    # set to e.g. '아시아주계' which is dropped later via DROP_NAMES.

    # Forward-fill country name (it spans gender rows)
    body[country_col] = body[country_col].ffill()

    if keep_gender is not None:
        mask = body[gender_col].astype(str).str.strip().isin(keep_gender)
    else:
        mask = body[gender_col].apply(is_total_gender)
    body = body[mask].copy()

    # Clean country names & drop continent/total rows
    body["_country"] = body[country_col].apply(clean_country)
    body = body[body["_country"].notna()]
    body = body[~body["_country"].isin(DROP_NAMES)]

    # Build long rows (sum across genders for 2018; otherwise one row per country)
    records = []
    for _, row in body.iterrows():
        country = row["_country"]
        for col_idx, (code, label) in visa_cols.items():
            val = row[col_idx]
            if pd.isna(val):
                val = 0
            try:
                n = int(float(val))
            except (TypeError, ValueError):
                n = 0
            records.append((year, country, code, label, n))

    out = pd.DataFrame(records, columns=["year", "country", "visa_code", "visa_label", "n"])
    # Collapse duplicates (2018: M+F → total; 2019+: defensive in case of duplicate country rows)
    out = (
        out.groupby(["year", "country", "visa_code", "visa_label"], as_index=False)["n"].sum()
    )
    return out


def load_one(year, path):
    """Dispatcher: pick the right parser for the given year."""
    if year <= 2013:
        return load_legacy(year, path)
    return load_modern(year, path)


def parse_sojourn(year, path):
    """Parse one 외국적동포 거소신고 file (region rows × nationality columns).

    Returns long DataFrame [year, country, visa_code, visa_label, n] with the
    national per-country totals (from the grand-total row), attributed to F-4
    (재외동포), which is the dominant residence-report status.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    TOTLAB = {"총계", "총 계", "합계", "합 계", "grand-total", "grandtotal", "total"}

    def norm(x):
        return str(x).replace(" ", "").strip().lower() if isinstance(x, str) else ""

    # Header row = the row with the most recognizable country names
    header_row, ncountry = None, 0
    for i in range(min(8, len(df))):
        cnt = 0
        for v in df.iloc[i].tolist():
            if isinstance(v, str):
                c = clean_country(v)
                if c and c not in DROP_NAMES and re.search(r"[가-힣]", c):
                    cnt += 1
        if cnt > ncountry:
            ncountry, header_row = cnt, i
    if header_row is None:
        return pd.DataFrame(columns=["year", "country", "visa_code", "visa_label", "n"])

    # Map columns -> country (skip the 합계/Total column)
    col_country = {}
    for j, v in enumerate(df.iloc[header_row].tolist()):
        if not isinstance(v, str):
            continue
        if norm(v) in TOTLAB:
            continue
        c = clean_country(v)
        if c and c not in DROP_NAMES and re.search(r"[가-힣]", c):
            col_country[j] = c

    # Grand-total row = first row after header whose label cell is a total AND
    # that actually carries numeric data in the country columns (avoids picking
    # an English sub-header row whose cell happens to read 'Total').
    total_row = None
    for i in range(header_row + 1, len(df)):
        rowvals = df.iloc[i].tolist()
        if not any(norm(x) in TOTLAB for x in rowvals[:3]):
            continue
        if any(j < len(rowvals) and _sum_newline_cell(rowvals[j]) > 0 for j in col_country):
            total_row = rowvals
            break
    if total_row is None:
        return pd.DataFrame(columns=["year", "country", "visa_code", "visa_label", "n"])

    records = []
    for j, country in col_country.items():
        if j >= len(total_row):
            continue
        n = _sum_newline_cell(total_row[j])
        if n > 0:
            records.append((year, country, "F4", "재외동포(거소)", n))
    return pd.DataFrame(records, columns=["year", "country", "visa_code", "visa_label", "n"])


def build_sojourn_long(files):
    parts = []
    for yr, p in sorted(files.items()):
        if not os.path.exists(p):
            print(f"  ! missing sojourn file for {yr}: {p}")
            continue
        try:
            parts.append(parse_sojourn(yr, p))
        except Exception as e:
            print(f"  ! failed sojourn {yr}: {e}")
    if not parts:
        return pd.DataFrame(columns=["year", "country", "visa_code", "visa_label", "n"])
    long = pd.concat(parts, ignore_index=True)
    long["country"] = long["country"].apply(lambda c: COUNTRY_CANONICAL.get(c, c))
    return long


def build_long(files):
    parts = []
    for yr, p in sorted(files.items()):
        if not os.path.exists(p):
            print(f"  ! missing file for {yr}: {p}")
            continue
        try:
            parts.append(load_one(yr, p))
        except Exception as e:
            print(f"  ! failed {yr}: {e}")
    if not parts:
        return pd.DataFrame(columns=["year", "country", "visa_code", "visa_label", "n"])
    long = pd.concat(parts, ignore_index=True)

    # Collapse pre-2010 sub-codes (D2A→D2, E61→E6, F5B→F5, H2C→H2, ...)
    # so we can compare across years on the same axis.
    long["visa_code"] = long["visa_code"].apply(collapse_visa_code)
    # Drop empty rows from defective parses
    long = long[long["visa_code"].astype(bool)]
    # Re-aggregate after collapse
    long = (
        long.groupby(["year", "country", "visa_code"], as_index=False)["n"].sum()
    )

    # For each visa_code, derive the best Korean label using the modern (post-2018)
    # canonical labels first, then fall back to whatever appears in older years.
    CANONICAL_LABELS = {
        "A1": "외교", "A2": "공무", "A3": "협정",
        "B1": "사증면제", "B2": "관광통과",
        "C1": "일시취재", "C3": "단기방문", "C4": "단기취업",
        "D1": "문화예술", "D2": "유학", "D3": "기술연수", "D4": "일반연수",
        "D5": "취재", "D6": "종교", "D7": "주재", "D8": "기업투자",
        "D9": "무역경영", "D10": "구직",
        "E1": "교수", "E2": "회화지도", "E3": "연구", "E4": "기술지도",
        "E5": "전문직업", "E6": "예술흥행", "E7": "특정활동", "E8": "계절근로",
        "E9": "비전문취업", "E10": "선원취업",
        "F1": "방문동거", "F2": "거주", "F3": "동반", "F4": "재외동포",
        "F5": "영주", "F6": "결혼이민",
        "G1": "기타비자",
        "H1": "관광취업", "H2": "방문취업",
        "T1": "관광상륙",
        "ETC": "분류외 (SOFA·협정 등)",
        "E0": "협정활동",  # 2007-2009 only
    }
    long["visa_label"] = long["visa_code"].map(
        lambda c: CANONICAL_LABELS.get(c, c)
    )
    return long


# --- Build datasets --------------------------------------------------------

print("Loading 등록외국인...")
reg_long = build_long(REG_FILES)
reg_long.to_csv(os.path.join(OUT_DATA, "reg_long.csv"), index=False, encoding="utf-8-sig")
print(f"  rows={len(reg_long):,}  countries={reg_long['country'].nunique()}  "
      f"visa codes={reg_long['visa_code'].nunique()}")

print("Loading 단기체류외국인 (for 2006-2010 stay composition)...")
short_long = build_long(SHORT_FILES) if SHORT_FILES else pd.DataFrame(
    columns=["year", "country", "visa_code", "visa_label", "n"]
)

print("Loading 외국적동포 거소신고 (2006-2010 체류 합성 third component)...")
sojourn_long = build_sojourn_long(SOJOURN_FILES) if SOJOURN_FILES else pd.DataFrame(
    columns=["year", "country", "visa_code", "visa_label", "n"]
)

print("Loading 체류외국인 (2011+ direct, 2006-2010 = 등록 + 단기 + 거소)...")
stay_direct = build_long(STAY_FILES)
# Compose 2006-2010 stay = registered + short-term + overseas-Korean sojourn
early_years = sorted(set(REG_FILES) & set(SHORT_FILES))
early_years = [y for y in early_years if y not in STAY_FILES]
if early_years:
    reg_early = reg_long[reg_long["year"].isin(early_years)]
    short_early = short_long[short_long["year"].isin(early_years)]
    sojourn_early = sojourn_long[sojourn_long["year"].isin(early_years)]
    stay_early = (
        pd.concat([reg_early, short_early, sojourn_early], ignore_index=True)
        .groupby(["year", "country", "visa_code", "visa_label"], as_index=False)["n"].sum()
    )
    stay_long = pd.concat([stay_early, stay_direct], ignore_index=True)
else:
    stay_long = stay_direct

stay_long.to_csv(os.path.join(OUT_DATA, "stay_long.csv"), index=False, encoding="utf-8-sig")
print(f"  rows={len(stay_long):,}  countries={stay_long['country'].nunique()}  "
      f"visa codes={stay_long['visa_code'].nunique()}")

# Sanity check: total residents in the latest year (2.65M in 2024, 2.78M in 2025)
_latest_stay_year = int(stay_long["year"].max())
chk = stay_long[(stay_long["year"] == _latest_stay_year)].groupby("year")["n"].sum()
if len(chk):
    print(f"\n{_latest_stay_year} stay sum (all visa × all country): {int(chk.iloc[0]):,}")


# --- Export data.json + static dashboard -------------------------------------

# Visa family rollups (grouped by first letter of code)
VISA_FAMILY_LABELS = {
    "A": "A계 · 외교/공무",
    "B": "B계 · 사증면제/관광통과",
    "C": "C계 · 단기체류",
    "D": "D계 · 장기일반 (유학·투자·주재)",
    "E": "E계 · 취업 (전문·비전문)",
    "F": "F계 · 정주/가족 (영주·결혼이민·재외동포)",
    "G": "G계 · 기타비자",
    "H": "H계 · 관광취업/방문취업",
    "T": "T계 · 관광상륙",
    "X": "기타 (분류불가)",
}


def visa_family(code):
    if not isinstance(code, str) or not code:
        return "X"
    if code == "ETC":
        return "X"
    return code[0].upper()


def long_to_pop_dict(long_df):
    """Convert long-format DataFrame → {visa_code: {year: {country: n}}}.

    Includes "ALL" (sum across visas) and "FAM_X" (sum by family) synthetic keys.
    """
    out = {}
    # Per visa-code
    for vcode, g in long_df.groupby("visa_code"):
        out[vcode] = {
            str(int(yr)): dict(zip(yg["country"], yg["n"].astype(int)))
            for yr, yg in g.groupby("year")
        }
    # Family rollups
    fam = long_df.copy()
    fam["family"] = "FAM_" + fam["visa_code"].apply(visa_family)
    fam_agg = fam.groupby(["family", "year", "country"], as_index=False)["n"].sum()
    for fcode, g in fam_agg.groupby("family"):
        out[fcode] = {
            str(int(yr)): dict(zip(yg["country"], yg["n"].astype(int)))
            for yr, yg in g.groupby("year")
        }
    # ALL
    all_agg = long_df.groupby(["year", "country"], as_index=False)["n"].sum()
    out["ALL"] = {
        str(int(yr)): dict(zip(g["country"], g["n"].astype(int)))
        for yr, g in all_agg.groupby("year")
    }
    return out


def extract_country_en_map():
    """Scan legacy yearbook files (which have bilingual Ko/En country columns)
    and merge a Korean→English country-name mapping."""
    mapping = {}
    bilingual_paths = [
        f"{RAW}/출입국통계연보/2013_출입국통계연보/13_2장_Ⅱ_1.국적및체류자격별 체류외국인현황.xlsx",
        f"{RAW}/출입국통계연보/2013_출입국통계연보/13_2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xlsx",
        f"{RAW}/출입국통계연보/2011_출입국통계연보/11_2장_Ⅱ_1.국적및체류자격별 체류외국인현황.xls",
        f"{RAW}/출입국통계연보/2009_출입국통계연보/2장_Ⅲ_1.국적및체류자격별 등록외국인현황.xls",
        f"{RAW}/출입국통계연보/2007_출입국통계연보/2-Ⅲ-1.국적및체류자격별.xls",
    ]
    skip_en = {
        "Grand-Total", "Asia", "Europe", "North America", "South America",
        "Oceania", "Africa", "Others", "Stateless", "Sex", "Total", "Nationality",
    }
    for f in bilingual_paths:
        if not os.path.exists(f):
            continue
        try:
            df = pd.read_excel(f, sheet_name=0, header=None)
        except Exception:
            continue
        for i in range(min(300, len(df))):
            for ko_col, en_col in [(0, 1), (1, 2)]:
                if df.shape[1] <= en_col:
                    continue
                ko = df.iloc[i, ko_col]
                en = df.iloc[i, en_col]
                if not isinstance(ko, str) or not isinstance(en, str):
                    continue
                ko_clean = clean_country(ko)
                en_clean = en.strip().replace("\n", " ")
                en_clean = re.sub(r"\s+", " ", en_clean).strip()
                if not ko_clean or not en_clean:
                    continue
                if en_clean in skip_en:
                    continue
                if re.search(r"[가-힣]", en_clean):
                    continue
                # Skip codes/numbers
                if re.match(r"^[A-Z0-9\-]+$", en_clean):
                    continue
                # Don't overwrite existing (preference: first source wins; 2013 is first)
                if ko_clean not in mapping:
                    mapping[ko_clean] = en_clean
    return mapping


# Manual overrides for country names that need fixing or are missing from
# yearbook English columns. KIS uses some idiosyncratic Romanizations.
COUNTRY_EN_OVERRIDES = {
    "한국": "Korea",  # used in some legacy outputs
    "한국계중국인": "Korean-Chinese",
    "한국계러시아인": "Korean-Russian",
    "중국": "China",
    "타이완": "Taiwan",
    "홍콩": "Hong Kong",
    "마카오": "Macao",
    "타이": "Thailand",
    "태국": "Thailand",
    "베트남": "Vietnam",
    "일본": "Japan",
    "필리핀": "Philippines",
    "인도네시아": "Indonesia",
    "캄보디아": "Cambodia",
    "라오스": "Laos",
    "미얀마": "Myanmar",
    "말레이시아": "Malaysia",
    "싱가포르": "Singapore",
    "브루나이": "Brunei",
    "동티모르": "Timor-Leste",
    "티모르민주공화국": "Timor-Leste",
    "몽골": "Mongolia",
    "네팔": "Nepal",
    "방글라데시": "Bangladesh",
    "스리랑카": "Sri Lanka",
    "파키스탄": "Pakistan",
    "인도": "India",
    "부탄": "Bhutan",
    "몰디브": "Maldives",
    "아프가니스탄": "Afghanistan",
    "이란": "Iran",
    "이라크": "Iraq",
    "시리아": "Syria",
    "레바논": "Lebanon",
    "이스라엘": "Israel",
    "팔레스타인": "Palestine",
    "요르단": "Jordan",
    "사우디아라비아": "Saudi Arabia",
    "예멘": "Yemen",
    "예멘공화국": "Yemen",
    "오만": "Oman",
    "쿠웨이트": "Kuwait",
    "카타르": "Qatar",
    "바레인": "Bahrain",
    "아랍에미리트연합": "United Arab Emirates",
    "튀르키예": "Türkiye",
    "터키": "Türkiye",
    "키프로스": "Cyprus",
    "조지아": "Georgia",
    "그루지야": "Georgia",
    "아르메니아": "Armenia",
    "아제르바이잔": "Azerbaijan",
    "카자흐스탄": "Kazakhstan",
    "우즈베키스탄": "Uzbekistan",
    "키르기스스탄": "Kyrgyzstan",
    "키르기즈": "Kyrgyzstan",
    "타지키스탄": "Tajikistan",
    "투르크메니스탄": "Turkmenistan",
    "러시아(연방)": "Russia",
    "러시아연방": "Russia",
    "벨라루스": "Belarus",
    "벨로루시": "Belarus",
    "우크라이나": "Ukraine",
    "몰도바": "Moldova",
    "미국": "United States",
    "캐나다": "Canada",
    "멕시코": "Mexico",
    "브라질": "Brazil",
    "아르헨티나": "Argentina",
    "칠레": "Chile",
    "콜롬비아": "Colombia",
    "페루": "Peru",
    "베네수엘라": "Venezuela",
    "에콰도르": "Ecuador",
    "볼리비아": "Bolivia",
    "파라과이": "Paraguay",
    "우루과이": "Uruguay",
    "가이아나": "Guyana",
    "수리남": "Suriname",
    "쿠바": "Cuba",
    "도미니카공화국": "Dominican Republic",
    "도미니카연방": "Dominica",
    "아이티": "Haiti",
    "자메이카": "Jamaica",
    "푸에르토리코": "Puerto Rico",
    "트리니다드토바고": "Trinidad and Tobago",
    "파나마": "Panama",
    "코스타리카": "Costa Rica",
    "니카라과": "Nicaragua",
    "온두라스": "Honduras",
    "엘살바도르": "El Salvador",
    "과테말라": "Guatemala",
    "벨리즈": "Belize",
    "바하마": "Bahamas",
    "바베이도스": "Barbados",
    "그레나다": "Grenada",
    "세인트루시아": "Saint Lucia",
    "세인트빈센트그레나딘": "Saint Vincent and the Grenadines",
    "세인트크리스토퍼네비스": "Saint Kitts and Nevis",
    "앤티가바부다": "Antigua and Barbuda",
    "앤티카바부다": "Antigua and Barbuda",
    "버뮤다": "Bermuda",
    "영국": "United Kingdom",
    "아일랜드": "Ireland",
    "프랑스": "France",
    "독일": "Germany",
    "동독": "East Germany",
    "이탈리아": "Italy",
    "스페인": "Spain",
    "포르투갈": "Portugal",
    "네덜란드": "Netherlands",
    "벨기에": "Belgium",
    "룩셈부르크": "Luxembourg",
    "스위스": "Switzerland",
    "오스트리아": "Austria",
    "덴마크": "Denmark",
    "스웨덴": "Sweden",
    "노르웨이": "Norway",
    "핀란드": "Finland",
    "아이슬란드": "Iceland",
    "그리스": "Greece",
    "폴란드": "Poland",
    "체코": "Czech Republic",
    "슬로바키아": "Slovakia",
    "슬로바크": "Slovakia",
    "헝가리": "Hungary",
    "루마니아": "Romania",
    "불가리아": "Bulgaria",
    "세르비아": "Serbia",
    "세르비아몬테네그로": "Serbia and Montenegro",
    "몬테네그로": "Montenegro",
    "크로아티아": "Croatia",
    "슬로베니아": "Slovenia",
    "보스니아-헤르체고비나": "Bosnia and Herzegovina",
    "알바니아": "Albania",
    "마케도니아": "North Macedonia",
    "북마케도니아": "North Macedonia",
    "코소보": "Kosovo",
    "유고슬라비아": "Yugoslavia",
    "에스토니아": "Estonia",
    "라트비아": "Latvia",
    "리투아니아": "Lithuania",
    "몰타": "Malta",
    "안도라": "Andorra",
    "모나코": "Monaco",
    "산마리노": "San Marino",
    "리히텐슈타인": "Liechtenstein",
    "교황청": "Holy See",
    "이집트": "Egypt",
    "리비아": "Libya",
    "튀니지": "Tunisia",
    "알제리": "Algeria",
    "모로코": "Morocco",
    "수단": "Sudan",
    "남수단공화국": "South Sudan",
    "에티오피아": "Ethiopia",
    "에리트레아": "Eritrea",
    "지부티": "Djibouti",
    "소말리아": "Somalia",
    "케냐": "Kenya",
    "우간다": "Uganda",
    "탄자니아": "Tanzania",
    "르완다": "Rwanda",
    "부룬디": "Burundi",
    "나이지리아": "Nigeria",
    "가나": "Ghana",
    "코트디부아르": "Côte d'Ivoire",
    "세네갈": "Senegal",
    "감비아": "Gambia",
    "기니": "Guinea",
    "기니비사우": "Guinea-Bissau",
    "시에라리온": "Sierra Leone",
    "라이베리아": "Liberia",
    "말리": "Mali",
    "부르키나파소": "Burkina Faso",
    "니제르": "Niger",
    "차드": "Chad",
    "카메룬": "Cameroon",
    "중앙아프리카공화국": "Central African Republic",
    "가봉": "Gabon",
    "콩고": "Congo",
    "콩고민주공화국": "DR Congo",
    "자이르": "DR Congo",
    "앙골라": "Angola",
    "잠비아": "Zambia",
    "짐바브웨": "Zimbabwe",
    "말라위": "Malawi",
    "모잠비크": "Mozambique",
    "마다가스카르": "Madagascar",
    "모리셔스": "Mauritius",
    "세이셸": "Seychelles",
    "코모로": "Comoros",
    "남아프리카공화국": "South Africa",
    "나미비아": "Namibia",
    "보츠와나": "Botswana",
    "레소토": "Lesotho",
    "스와질란드": "Eswatini",
    "에스와티니": "Eswatini",
    "베냉": "Benin",
    "토고": "Togo",
    "모리타니": "Mauritania",
    "카보베르데": "Cape Verde",
    "상투메프린시페": "São Tomé and Príncipe",
    "적도기니": "Equatorial Guinea",
    "오스트레일리아": "Australia",
    "뉴질랜드": "New Zealand",
    "피지": "Fiji",
    "파푸아뉴기니": "Papua New Guinea",
    "솔로몬군도": "Solomon Islands",
    "바누아투": "Vanuatu",
    "사모아": "Samoa",
    "통가": "Tonga",
    "투발루": "Tuvalu",
    "키리바시": "Kiribati",
    "팔라우": "Palau",
    "마샬군도": "Marshall Islands",
    "미이크로네시아": "Micronesia",
    "나우루": "Nauru",
    "괌": "Guam",
    "국제연합": "United Nations",
    "홍콩거주난민": "Hong Kong Refugees",
    "영령인도양섬": "British Indian Ocean Territory",
    "미령버진아일랜드": "U.S. Virgin Islands",
    "미령사모아": "American Samoa",
    "미국인근섬": "U.S. Minor Outlying Islands",
    "영국속국민": "British Subject",
    "영국보호민": "British Protected Person",
    "영국외지민": "British Overseas Citizen",
    "영국외지시민": "British Overseas Citizen",
    "영국속령지시민": "British Dependent Territories Citizen",
    "영국해외영토시민": "British Overseas Territories Citizen",
    "지브롤터": "Gibraltar",
    "크리스마스": "Christmas Island",
    "스발바르": "Svalbard",
    "마르티니크": "Martinique",
    "불령가이아나": "French Guiana",
}


# Module-level canonical Korean labels (also used by build_long internally)
CANONICAL_LABELS_KO = {
    "A1": "외교", "A2": "공무", "A3": "협정",
    "B1": "사증면제", "B2": "관광통과",
    "C1": "일시취재", "C3": "단기방문", "C4": "단기취업",
    "D1": "문화예술", "D2": "유학", "D3": "기술연수", "D4": "일반연수",
    "D5": "취재", "D6": "종교", "D7": "주재", "D8": "기업투자",
    "D9": "무역경영", "D10": "구직",
    "E1": "교수", "E2": "회화지도", "E3": "연구", "E4": "기술지도",
    "E5": "전문직업", "E6": "예술흥행", "E7": "특정활동", "E8": "계절근로",
    "E9": "비전문취업", "E10": "선원취업",
    "F1": "방문동거", "F2": "거주", "F3": "동반", "F4": "재외동포",
    "F5": "영주", "F6": "결혼이민",
    "G1": "기타비자",
    "H1": "관광취업", "H2": "방문취업",
    "T1": "관광상륙",
    "ETC": "분류외 (SOFA·협정 등)",
    "E0": "협정활동",
}


# Visa info compiled from MOJ KIS Visa Navigator + HiKorea + supplementary
# legal/admin sources. Each entry: ko/en purpose, eligibility, max stay, sources.
# Sources are limited to authoritative .go.kr / official refs where possible.
VISA_INFO = {
    "A1": {
        "purpose_ko": "외국 정부의 외교사절단·영사기관 구성원, 조약·국제관례에 따른 외교사절 및 그 가족",
        "purpose_en": "Members of foreign diplomatic missions and consular posts in Korea, and their families",
        "eligibility_ko": "외국 정부 또는 국제기구 파견 외교관·영사관 및 그 가족",
        "eligibility_en": "Foreign diplomats/consular officers and their families dispatched by foreign governments or international organizations",
        "max_stay_ko": "재임 기간 (체류기간 갱신 가능)",
        "max_stay_en": "Duration of assignment (renewable)",
    },
    "A2": {
        "purpose_ko": "외국 정부·국제기구 공무 수행을 위한 자 (외교관 외)",
        "purpose_en": "Government/international-organization officials on official duty (non-diplomatic)",
        "eligibility_ko": "공무 수행을 위해 파견된 자 및 그 가족",
        "eligibility_en": "Officials dispatched on official mission and their families",
        "max_stay_ko": "공무 수행 기간",
        "max_stay_en": "Duration of official mission",
    },
    "A3": {
        "purpose_ko": "협정에 의해 대한민국에 체류하는 외국인 (SOFA 인원 포함되기도 함)",
        "purpose_en": "Persons covered by treaty (sometimes includes SOFA personnel)",
        "eligibility_ko": "한미 SOFA, 기타 협정 적용 대상자 및 그 가족",
        "eligibility_en": "Subjects of ROK-US SOFA and other agreements, plus families",
        "max_stay_ko": "협정 정한 기간",
        "max_stay_en": "Per applicable agreement",
    },
    "B1": {
        "purpose_ko": "사증면제 협정에 따라 무비자 단기 입국",
        "purpose_en": "Short-term entry under visa-waiver agreements",
        "eligibility_ko": "사증면제 협정 체결 국가 국민. 관광·친지방문·단기 상용 등 (영리활동 제외)",
        "eligibility_en": "Nationals of visa-waiver countries; tourism, family visits, short business (no profit)",
        "max_stay_ko": "협정별 상이 (보통 30~90일)",
        "max_stay_en": "Varies by treaty (usually 30–90 days)",
    },
    "B2": {
        "purpose_ko": "관광·통과 목적 (사증면제 협정 없는 국가)",
        "purpose_en": "Tourism/transit (countries without visa-waiver agreement)",
        "eligibility_ko": "관광·통과 목적 단기 방문자",
        "eligibility_en": "Short-term tourists/transit travelers",
        "max_stay_ko": "보통 30일 이내",
        "max_stay_en": "Usually under 30 days",
    },
    "C1": {
        "purpose_ko": "일시 취재·보도 활동 (90일 이내)",
        "purpose_en": "Temporary news coverage/reporting (under 90 days)",
        "eligibility_ko": "외국 언론사 단기 취재 인력",
        "eligibility_en": "Short-term reporters from foreign media",
        "max_stay_ko": "최대 90일",
        "max_stay_en": "Up to 90 days",
    },
    "C3": {
        "purpose_ko": "관광·친지방문·행사참가·의료관광·단기 상용 (영리활동 제외, 90일 이내)",
        "purpose_en": "Tourism, family visits, events, medical tourism, short business (no profit, under 90 days)",
        "eligibility_ko": "방문 목적 단기 방문자. 단수(90일) 또는 더블(30일×2)",
        "eligibility_en": "Short-term visitors. Single (90 days) or double (30×2)",
        "max_stay_ko": "최대 90일",
        "max_stay_en": "Up to 90 days",
    },
    "C4": {
        "purpose_ko": "단기간 수익 발생 활동: 공연·광고/패션모델·강연·기술지도 등",
        "purpose_en": "Short-term profit activities: performance, modeling, lectures, technical guidance",
        "eligibility_ko": "초청업체 보유·계약 증빙 필요",
        "eligibility_en": "Korean inviter/contract required",
        "max_stay_ko": "최대 90일",
        "max_stay_en": "Up to 90 days",
    },
    "D1": {
        "purpose_ko": "수익 목적 없는 문화예술 활동: 학문·예술 연구, 도제 등",
        "purpose_en": "Non-profit cultural/arts activities: academic/artistic research, apprenticeship",
        "eligibility_ko": "초청기관·연구계획 증빙",
        "eligibility_en": "Inviting institution + research plan required",
        "max_stay_ko": "최대 2년 (연장 가능)",
        "max_stay_en": "Up to 2 years (renewable)",
    },
    "D2": {
        "purpose_ko": "전문대학·대학·대학원에서 정규과정 수학 또는 특정 연구",
        "purpose_en": "Regular degree programs at colleges/universities/graduate schools or specific research",
        "eligibility_ko": "한국 교육기관 입학허가 + 재정 증빙",
        "eligibility_en": "Admission letter from Korean institution + financial proof",
        "max_stay_ko": "보통 2년 (정규과정 기간 동안 연장)",
        "max_stay_en": "Typically 2 years (extendable for program duration)",
    },
    "D3": {
        "purpose_ko": "산업기술 연수생 (지정 기업·기관)",
        "purpose_en": "Industrial trainees (designated companies/institutions)",
        "eligibility_ko": "법무부장관이 지정한 기관 연수계약",
        "eligibility_en": "Training contract with MOJ-designated institutions",
        "max_stay_ko": "최대 2년",
        "max_stay_en": "Up to 2 years",
    },
    "D4": {
        "purpose_ko": "어학연수(한국어) 또는 D-2 외 교육기관 일반연수",
        "purpose_en": "Korean language study or other non-D-2 training programs",
        "eligibility_ko": "지정 어학원·교육기관 입학허가",
        "eligibility_en": "Admission to designated language/education institution",
        "max_stay_ko": "6개월 단위 발급, 최대 2년",
        "max_stay_en": "Issued in 6-month blocks, up to 2 years",
    },
    "D5": {
        "purpose_ko": "외국 언론사 한국 지사 장기 취재 인력",
        "purpose_en": "Long-term correspondents at Korean branches of foreign media",
        "eligibility_ko": "외국 언론사 정식 파견",
        "eligibility_en": "Official posting from foreign media outlet",
        "max_stay_ko": "최대 2년 (연장 가능)",
        "max_stay_en": "Up to 2 years (renewable)",
    },
    "D6": {
        "purpose_ko": "외국 종교단체에서 파견된 종교인 (선교사 등)",
        "purpose_en": "Religious workers dispatched by foreign religious organizations",
        "eligibility_ko": "외국 종교단체의 파견 증빙 + 국내 종교단체 초청",
        "eligibility_en": "Proof of dispatch + Korean religious org invitation",
        "max_stay_ko": "최대 2년 (연장 가능)",
        "max_stay_en": "Up to 2 years (renewable)",
    },
    "D7": {
        "purpose_ko": "외국 본사·지점에서 한국 지사로 1년 이상 근무 경력 후 파견된 주재원",
        "purpose_en": "Intra-company transferees with 1+ year tenure at overseas HQ/branch",
        "eligibility_ko": "외국 본사 1년 이상 재직 + 한국 지사 발령",
        "eligibility_en": "1+ year at overseas parent/branch + Korea assignment",
        "max_stay_ko": "최대 3년 (연장 가능)",
        "max_stay_en": "Up to 3 years (renewable)",
    },
    "D8": {
        "purpose_ko": "외국인투자기업 경영·관리·생산기술 분야 종사 (1억 원 이상 투자)",
        "purpose_en": "Management/production at foreign-invested companies (≥KRW 100M investment)",
        "eligibility_ko": "1억 원 이상 투자 + 주식 10% 이상 보유 (D-8-1)",
        "eligibility_en": "≥KRW 100M investment + ≥10% equity (D-8-1)",
        "max_stay_ko": "최대 5년 (사업실적 기반 연장)",
        "max_stay_en": "Up to 5 years (renewal based on business performance)",
    },
    "D9": {
        "purpose_ko": "대외무역·산업설비 도입·수출입 거래 등",
        "purpose_en": "International trade, industrial-equipment import, export/import transactions",
        "eligibility_ko": "무역·경영 활동 증빙",
        "eligibility_en": "Evidence of trade/business operations",
        "max_stay_ko": "최대 2년 (연장 가능)",
        "max_stay_en": "Up to 2 years (renewable)",
    },
    "D10": {
        "purpose_ko": "전문·기술인력의 구직 및 인턴십 (D-2 졸업자 등)",
        "purpose_en": "Job-seeking & internships for skilled workers (incl. D-2 graduates)",
        "eligibility_ko": "학력·경력 점수제 + 구직계획서 + 재정 증빙",
        "eligibility_en": "Points-based qualification + job-search plan + financial proof",
        "max_stay_ko": "최대 6개월 (총 2년까지 연장 가능)",
        "max_stay_en": "Up to 6 months (extendable to 2 years total)",
    },
    "E1": {
        "purpose_ko": "전문대학 이상 교육기관 외국인 교수",
        "purpose_en": "Foreign professors at junior college level or above",
        "eligibility_ko": "박사학위 또는 동등 자격 + 대학 임용 계약",
        "eligibility_en": "PhD or equivalent + university appointment contract",
        "max_stay_ko": "최대 5년 (E-1~E-7은 5년 체류 후 영주 신청 가능)",
        "max_stay_en": "Up to 5 years (E-1~E-7 → eligible for permanent residence after 5 years)",
    },
    "E2": {
        "purpose_ko": "외국어회화 지도 (영어강사 등), 학원·교육기관 소속",
        "purpose_en": "Foreign language conversation instruction (e.g., English teachers)",
        "eligibility_ko": "원어민 + 학사 학위 + 무범죄 확인 + 건강 확인",
        "eligibility_en": "Native speaker + bachelor's + criminal background check + health check",
        "max_stay_ko": "최대 2년 (계약 기간, 연장 가능)",
        "max_stay_en": "Up to 2 years (contract-based, renewable)",
    },
    "E3": {
        "purpose_ko": "대한민국 공공·민간 연구기관에서 자연과학·고도산업기술 연구",
        "purpose_en": "Research in natural sciences/advanced industrial technology at Korean institutions",
        "eligibility_ko": "석사 이상 + 연구기관 채용",
        "eligibility_en": "Master's or higher + research institution employment",
        "max_stay_ko": "최대 5년 (연장 가능)",
        "max_stay_en": "Up to 5 years (renewable)",
    },
    "E4": {
        "purpose_ko": "특수 분야 기술 제공 (자연과학·산업)",
        "purpose_en": "Provision of specialized technology (sciences/industry)",
        "eligibility_ko": "기술지도 계약 + 자격 입증",
        "eligibility_en": "Technical guidance contract + credentials",
        "max_stay_ko": "최대 5년 (연장 가능)",
        "max_stay_en": "Up to 5 years (renewable)",
    },
    "E5": {
        "purpose_ko": "법률·회계·의료 등 국가공인 전문 자격을 갖춘 자",
        "purpose_en": "State-licensed professionals (law, accounting, medicine, etc.)",
        "eligibility_ko": "해당 분야 국가공인 자격증 + 한국 내 활동 증빙",
        "eligibility_en": "State professional license + evidence of Korean engagement",
        "max_stay_ko": "최대 5년 (연장 가능)",
        "max_stay_en": "Up to 5 years (renewable)",
    },
    "E6": {
        "purpose_ko": "수익 목적 음악·미술·문학 등 예술 활동, 흥행·연예 활동",
        "purpose_en": "Profit-making activities in music, arts, literature, entertainment",
        "eligibility_ko": "공연·예술 분야 활동 증빙 + 초청 계약",
        "eligibility_en": "Evidence of arts/entertainment activity + invitation contract",
        "max_stay_ko": "최대 2년 (E-6-2 유흥업소는 더 엄격)",
        "max_stay_en": "Up to 2 years (E-6-2 entertainment subject to stricter rules)",
    },
    "E7": {
        "purpose_ko": "법무부장관이 특별히 지정한 전문·관리·기능 분야 활동",
        "purpose_en": "Specially-designated professional/managerial/skilled activities",
        "eligibility_ko": "MOJ 지정 직종 + 학력·경력 점수제 + 사용자 sponsor",
        "eligibility_en": "MOJ-designated occupation + points-based + employer sponsor",
        "max_stay_ko": "최초 1-3년 (최대 5년까지 연장)",
        "max_stay_en": "1–3 years initially (extendable up to 5)",
    },
    "E8": {
        "purpose_ko": "농업·어업 분야 한시적 계절근로",
        "purpose_en": "Seasonal agricultural/fisheries labor",
        "eligibility_ko": "지자체-해외 자치단체 MOU 기반 모집",
        "eligibility_en": "Recruited via MOU between Korean and foreign local governments",
        "max_stay_ko": "최대 5개월 (연장 시 최대 8개월)",
        "max_stay_en": "Up to 5 months (extendable to 8)",
    },
    "E9": {
        "purpose_ko": "비전문 단순노무: 제조·건설·농어업·서비스업 (고용허가제)",
        "purpose_en": "Non-professional labor: manufacturing, construction, agriculture, services (EPS)",
        "eligibility_ko": "고용허가제(EPS) 송출국가 출신 + 한국어 시험(TOPIK 또는 EPS-TOPIK)",
        "eligibility_en": "From EPS sending country + Korean language test (TOPIK or EPS-TOPIK)",
        "max_stay_ko": "기본 3년 (재고용 시 +1년 10개월, 성실근로자는 추가 4년 10개월까지)",
        "max_stay_en": "Base 3 years (+1y10m on rehire; up to ~4y10m more for 'sincere worker' track)",
    },
    "E10": {
        "purpose_ko": "20톤 이상 외항선 등 선원 활동",
        "purpose_en": "Crew on ocean-going vessels (≥20 tons)",
        "eligibility_ko": "선원 자격 + 선사 고용계약",
        "eligibility_en": "Maritime crew qualifications + shipping company contract",
        "max_stay_ko": "고용계약 기간",
        "max_stay_en": "Contract duration",
    },
    "F1": {
        "purpose_ko": "친척·결혼이민자 가족 방문동거, 외국인 가사보조인, 난민인정자 가족 등",
        "purpose_en": "Family cohabitation visits, foreign domestic helpers, refugee family members",
        "eligibility_ko": "초청자(국민·F-2/F-4/F-5/F-6 등) 가족관계 입증",
        "eligibility_en": "Proof of relationship with Korean national or F-2/F-4/F-5/F-6 holder",
        "max_stay_ko": "원칙 2년 이내 (난민인정자 가족은 부모 자격 기간 한도)",
        "max_stay_en": "Generally up to 2 years (capped by refugee parent's term)",
    },
    "F2": {
        "purpose_ko": "장기거주 자격 (점수제, 투자, 결혼이민 5년 등). 영주 전 단계",
        "purpose_en": "Long-term residence (points-system, investor, marriage-immigrant 5y, etc.). Pre-permanent stage",
        "eligibility_ko": "F-2-7 점수제(80점), F-2-2 투자, F-2-4 난민인정자, F-2-99 등",
        "eligibility_en": "F-2-7 points-based (80pts), F-2-2 investor, F-2-4 recognized refugee, F-2-99, etc.",
        "max_stay_ko": "최대 5년 (취업활동 제한 없음, 거주 5년 후 F-5 신청 가능)",
        "max_stay_en": "Up to 5 years (unrestricted employment; eligible for F-5 after 5y residence)",
    },
    "F3": {
        "purpose_ko": "체류자격(D·E·F-1·F-2 등) 보유자의 배우자 및 미성년 자녀",
        "purpose_en": "Spouse and minor children of D, E, F-1, F-2 visa holders",
        "eligibility_ko": "주체류자격자의 가족관계 입증",
        "eligibility_en": "Proof of family relationship with principal visa holder",
        "max_stay_ko": "주체류자격 기간 한도 (취업활동 제한)",
        "max_stay_en": "Capped by principal's term (employment restricted)",
    },
    "F4": {
        "purpose_ko": "재외동포: 한국계 외국 국적자 및 그 배우자·자녀",
        "purpose_en": "Overseas Koreans: foreign nationals of Korean heritage, spouses, children",
        "eligibility_ko": "재외동포법 적용 대상 (구한말 한국적 보유자 후손 + 외국 국적 취득자)",
        "eligibility_en": "Per Overseas Korean Act (descendants of pre-1948 Korean nationals + naturalized abroad)",
        "max_stay_ko": "최대 3년 (무제한 연장; 단순노무·풍속영업·사행업 제외 자유 취업)",
        "max_stay_en": "Up to 3 years (renewable indefinitely; free employment except low-skill labor)",
    },
    "F5": {
        "purpose_ko": "영주: 무기한 체류, 출국 후 재입국 자유, 자유 취업",
        "purpose_en": "Permanent residence: indefinite stay, free re-entry, unrestricted employment",
        "eligibility_ko": "5년 이상 합법체류 + 생계유지능력 + 한국어·한국사회 이해 등 (27개 경로)",
        "eligibility_en": "5+ years legal residence + financial means + Korean language/society knowledge (27 pathways)",
        "max_stay_ko": "10년 단위 영주증 갱신 (체류기간 무제한)",
        "max_stay_en": "Permanent (residence card renewed every 10 years)",
    },
    "F6": {
        "purpose_ko": "결혼이민: 대한민국 국민의 외국인 배우자",
        "purpose_en": "Marriage immigration: foreign spouse of Korean national",
        "eligibility_ko": "혼인 신고 + 소득 요건 + 한국어 능력 (TOPIK 1급 이상 등)",
        "eligibility_en": "Marriage registration + income requirement + Korean language ability",
        "max_stay_ko": "최대 3년 (취업제한 없음, 2년 이상 체류 시 F-5 신청 가능)",
        "max_stay_en": "Up to 3 years (free employment; eligible for F-5 after 2y residence)",
    },
    "G1": {
        "purpose_ko": "다른 자격에 해당하지 않는 자: 난민신청자(G-1-5), 인도적체류허가자(G-1-6), 의료치료, 소송 진행 중 등",
        "purpose_en": "Catch-all for those not fitting other statuses: refugee applicants (G-1-5), humanitarian permits (G-1-6), medical treatment, ongoing litigation",
        "eligibility_ko": "사유별 상이; 난민신청자는 난민법, 인도적체류허가자는 별도 심사",
        "eligibility_en": "Varies by sub-category; refugee applicants under Refugee Act, humanitarian permits via separate review",
        "max_stay_ko": "사유별 상이 (보통 1년 단위 연장)",
        "max_stay_en": "Varies (typically renewed yearly)",
    },
    "H1": {
        "purpose_ko": "관광취업(워킹홀리데이): 양국 협정 기반 18~30세 청년",
        "purpose_en": "Working holiday: youth (18 to 30) under bilateral treaty",
        "eligibility_ko": "협정 체결국 국민 + 자금 증빙 + 무범죄 확인",
        "eligibility_en": "Treaty-country national + financial proof + criminal record check",
        "max_stay_ko": "보통 1년 (협정별 상이)",
        "max_stay_en": "Typically 1 year (varies by treaty)",
    },
    "H2": {
        "purpose_ko": "방문취업: 중국·구소련 한국계 동포(만25세 이상) 단순노무 취업",
        "purpose_en": "Working visit: ethnic Koreans from China/CIS (25+) for low-skill labor",
        "eligibility_ko": "동포 증명 + 한국어시험 + 추첨 등",
        "eligibility_en": "Heritage proof + Korean language test + lottery (in some years)",
        "max_stay_ko": "최대 5년 (E-9와 달리 사전 고용계약 불필요, 자유 취업)",
        "max_stay_en": "Up to 5 years (unlike E-9, no employer sponsorship needed)",
    },
    "T1": {
        "purpose_ko": "관광상륙: 크루즈선 승객의 상륙",
        "purpose_en": "Tourist landing: cruise-ship passenger shore visits",
        "eligibility_ko": "크루즈 승객",
        "eligibility_en": "Cruise passengers",
        "max_stay_ko": "최대 3일",
        "max_stay_en": "Up to 3 days",
    },
    "ETC": {
        "purpose_ko": "분류외 (주한미군 SOFA, 협정 적용 등). 일반 비자 체계에 잡히지 않는 잔여 카테고리",
        "purpose_en": "Unclassified (US Forces Korea SOFA, treaty personnel, etc.). Residual not in regular visa categories",
        "eligibility_ko": "SOFA, 협정 적용 대상자 등 (미국 기준 약 5만 명대 유지)",
        "eligibility_en": "SOFA/treaty subjects (US ~50K consistently)",
        "max_stay_ko": "협정·임무 기간",
        "max_stay_en": "Per agreement/mission",
    },
    "E0": {
        "purpose_ko": "(2007~2009 한정) 협정활동 비자. 이후 E-7 등으로 통합",
        "purpose_en": "(2007 to 2009 only) Treaty activity visa, later absorbed into E-7 etc.",
        "eligibility_ko": "이 시기 협정 기반 활동자",
        "eligibility_en": "Treaty-activity workers during this period",
        "max_stay_ko": "-",
        "max_stay_en": "-",
    },
}

# ─────────────────────────────────────────────────────────────────────
# REGION (시군구) × COUNTRY parser (2014+ modern format)
# ─────────────────────────────────────────────────────────────────────

# 시도-level names to recognize. Other strings in col0 are sub-districts.
SIDO_NAMES = {
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시",
    "경기도", "강원도", "강원특별자치도",
    "충청북도", "충청남도", "전라북도", "전라남도", "전북특별자치도",
    "경상북도", "경상남도", "제주특별자치도",
    "기타", "총합계",
}


# Sido canonicalization: 2023+ official renames split historical series
SIDO_CANONICAL = {
    "강원특별자치도": "강원도",
    "전북특별자치도": "전라북도",
}

def canon_sigungu(name):
    """Normalize a KIS sigungu name to its MOIS-compatible form."""
    if not isinstance(name, str):
        return name
    s = name.strip()
    # Fold sub-office (출장소) rows into their parent city, e.g.
    # '화성시 동부출장소' -> '화성시'.
    s = re.sub(r"\s*(동부|서부|남부|북부|.{0,3})출장소$", "", s).strip()
    return SIGUNGU_CANONICAL.get(s, s)


# Romanized English for compound 일반구 districts (Revised Romanization).
ILBAN_GU_EN = {
    "수원시 장안구": "Suwon-si Jangan-gu", "수원시 권선구": "Suwon-si Gwonseon-gu",
    "수원시 팔달구": "Suwon-si Paldal-gu", "수원시 영통구": "Suwon-si Yeongtong-gu",
    "성남시 수정구": "Seongnam-si Sujeong-gu", "성남시 중원구": "Seongnam-si Jungwon-gu",
    "성남시 분당구": "Seongnam-si Bundang-gu", "안양시 만안구": "Anyang-si Manan-gu",
    "안양시 동안구": "Anyang-si Dongan-gu", "안산시 상록구": "Ansan-si Sangnok-gu",
    "안산시 단원구": "Ansan-si Danwon-gu", "고양시 덕양구": "Goyang-si Deogyang-gu",
    "고양시 일산동구": "Goyang-si Ilsandong-gu", "고양시 일산서구": "Goyang-si Ilsanseo-gu",
    "용인시 처인구": "Yongin-si Cheoin-gu", "용인시 기흥구": "Yongin-si Giheung-gu",
    "용인시 수지구": "Yongin-si Suji-gu", "부천시 원미구": "Bucheon-si Wonmi-gu",
    "부천시 소사구": "Bucheon-si Sosa-gu", "부천시 오정구": "Bucheon-si Ojeong-gu",
    "청주시 상당구": "Cheongju-si Sangdang-gu", "청주시 서원구": "Cheongju-si Seowon-gu",
    "청주시 흥덕구": "Cheongju-si Heungdeok-gu", "청주시 청원구": "Cheongju-si Cheongwon-gu",
    "천안시 동남구": "Cheonan-si Dongnam-gu", "천안시 서북구": "Cheonan-si Seobuk-gu",
    "전주시 완산구": "Jeonju-si Wansan-gu", "전주시 덕진구": "Jeonju-si Deokjin-gu",
    "포항시 남구": "Pohang-si Nam-gu", "포항시 북구": "Pohang-si Buk-gu",
    "창원시 의창구": "Changwon-si Uichang-gu", "창원시 성산구": "Changwon-si Seongsan-gu",
    "창원시 마산합포구": "Changwon-si Masanhappo-gu", "창원시 마산회원구": "Changwon-si Masanhoewon-gu",
    "창원시 진해구": "Changwon-si Jinhae-gu",
}


def build_sigungu_en(region_df):
    """{"sido|sigungu": English} for the dashboard's English mode. Uses the
    geojson romanization for plain districts and ILBAN_GU_EN for compound ones."""
    out = {}
    geo_path = os.path.join(OUT_SITE_DATA, "korea_sigungu.json")
    geo_en = {}
    if os.path.exists(geo_path):
        try:
            g = json.load(open(geo_path, encoding="utf-8"))
            for f in g["features"]:
                geo_en[f["properties"]["match_key"]] = f["properties"].get("name_eng", "")
        except Exception:
            pass
    for sido, sg in region_df[["sido", "sigungu"]].drop_duplicates().itertuples(index=False):
        if sg in ("총계", "총합계"):
            continue
        if sg in ILBAN_GU_EN:
            en = ILBAN_GU_EN[sg]
        else:
            en = geo_en.get(sido + "|" + str(sg).replace(" ", ""), "")
        out[sido + "|" + sg] = en
    return out


def load_region_country(year, path):
    """Parse 시군구별 × 국적별 등록외국인 file (2014+ format).

    Handles two minor variants:
      - 2014-2018: gender = '계'/'남'/'여', sido subtotal = '소계'
      - 2019+    : gender = '총계'/'남성'/'여성', sido subtotal = '총계'
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    header = df.iloc[0].tolist()

    country_cols = {}
    for i, h in enumerate(header):
        if i < 4 or not isinstance(h, str):
            continue
        cleaned = clean_country(h)
        if cleaned and cleaned not in DROP_NAMES:
            country_cols[i] = cleaned

    body = df.iloc[1:].copy().reset_index(drop=True)
    body[0] = body[0].ffill()  # forward-fill 시도
    body[1] = body[1].ffill()  # forward-fill 시군구 (spans gender rows)

    TOTAL_G = {"총계", "총합계", "계"}
    MALE_G = {"남성", "남", "(M)", "M"}
    FEMALE_G = {"여성", "여", "(F)", "F"}

    # Collect both total rows and M/F rows; resolve per (sido, sigungu, country)
    # later: prefer an explicit total, else sum M+F (needed for 2019 where
    # per-sigungu rows only carry 남성/여성).
    totals = {}   # (sido, sigungu, country) -> n  (explicit total)
    mf_sum = {}   # (sido, sigungu, country) -> n  (sum of M+F)

    for _, row in body.iterrows():
        sido = clean_country(row[0])
        if sido:
            sido = SIDO_CANONICAL.get(sido, sido)
        if not sido or sido in {"총합계", "총계", "계"}:
            continue
        sigungu = row[1]
        if pd.isna(sigungu):
            continue
        sigungu = str(sigungu).strip()
        # Skip 출장소 (sub-office) rows: they are subdivisions WITHIN a city whose
        # residents are already counted in that city's "계" total row, so folding
        # them into the parent (via canon_sigungu) and writing to totals would
        # overwrite the real city total (e.g. 화성시 2014: 출장소 1,709 clobbering
        # the 화성시 계 of 29,968). Dropping them keeps the city total intact.
        if "출장소" in sigungu:
            continue
        if sigungu == "소계":
            sigungu = "총계"
        if sigungu not in ("총계", "총합계"):
            sigungu = canon_sigungu(sigungu)
        gender = str(row[2]).strip()
        is_total = gender in TOTAL_G
        is_mf = gender in MALE_G or gender in FEMALE_G
        if not (is_total or is_mf):
            continue
        for col_idx, ctry in country_cols.items():
            val = row[col_idx]
            if pd.isna(val):
                continue
            try:
                n = int(float(val))
            except (TypeError, ValueError):
                continue
            if n <= 0:
                continue
            key = (sido, sigungu, ctry)
            if is_total:
                totals[key] = n
            else:
                mf_sum[key] = mf_sum.get(key, 0) + n

    records = []
    for key in set(totals) | set(mf_sum):
        n = totals.get(key, mf_sum.get(key, 0))
        if n <= 0:
            continue
        sido, sigungu, ctry = key
        records.append((year, sido, sigungu, ctry, n))

    return pd.DataFrame(records, columns=["year", "sido", "sigungu", "country", "n"])


def build_region_long(files):
    parts = []
    for yr, p in sorted(files.items()):
        if not os.path.exists(p):
            print(f"  ! missing region {yr}: {p}")
            continue
        try:
            parts.append(load_region_country(yr, p))
        except Exception as e:
            print(f"  ! failed region {yr}: {e}")
    if not parts:
        return pd.DataFrame(columns=["year", "sido", "sigungu", "country", "n"])
    long = pd.concat(parts, ignore_index=True)
    # Sort before anything downstream sees it. The per-year parser emits rows in
    # dictionary order, which differs between processes, and a district's top-20
    # language list breaks ties on that order, so without this a rebuild produces
    # a different language_demand.csv from the same inputs.
    return long.sort_values(["year", "sido", "sigungu", "country"],
                            kind="mergesort").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────
# AGE × COUNTRY parser (2014+ modern format)
# ─────────────────────────────────────────────────────────────────────

# Age column header patterns:
#   "0세~4세" (2019+), "0-4세" (2014-2018), "60세이상" (both)
AGE_HDR_RE = re.compile(
    r"^\s*(\d+)\s*(?:세)?\s*(?:[~∼\-]\s*(\d+)\s*세|세\s*이상|이상)\s*$"
)


def parse_age_header(s):
    if not isinstance(s, str):
        return None
    m = AGE_HDR_RE.match(s.strip())
    if not m:
        return None
    a = int(m.group(1))
    if m.group(2):
        return f"{a}-{int(m.group(2))}"
    return f"{a}+"


def load_age(year, path):
    """Parse 국적 × 연령별 체류외국인 file. Handles two layouts:
      - 2014-2018: col0=국가, col1=총계, col2=성별, col3=성별합계, col4+=ages
                   gender = '(T)'/'(M)'/'(F)'; age headers "0-4세"
      - 2019+    : col0=대륙, col1=국적, col2=성별, col3=총합계, col4+=ages
                   gender = '총계'/'남성'/'여성'; age headers "0세~4세"
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    header = df.iloc[0].tolist()

    age_cols = {}
    for i, h in enumerate(header):
        if i < 4:
            continue
        ag = parse_age_header(h)
        if ag:
            age_cols[i] = ag

    if not age_cols:
        return pd.DataFrame(columns=["year", "country", "gender", "age_group", "n"])

    # Detect layout: 2014-2018 have country in col0 (header label varies:
    # '국적･지역', '국  가', '국적명', '국적', ...). 2019+ uses '대륙' in col0.
    h0 = str(header[0]).replace(" ", "").strip()
    is_legacy = (h0 != "대륙")

    if is_legacy:
        country_col, gender_col = 0, 2
        gender_total_set = {"(T)", "T", "계", "총계", "총합계"}
        gender_male_set = {"(M)", "M", "남", "남성"}
        gender_female_set = {"(F)", "F", "여", "여성"}
    else:
        country_col, gender_col = 1, 2
        gender_total_set = {"총계", "총합계"}
        gender_male_set = {"남성"}
        gender_female_set = {"여성"}

    body = df.iloc[1:].copy().reset_index(drop=True)

    if not is_legacy:
        # Drop continent / 기타계 aggregate blocks before the ffill below. The
        # block's first row is recognisable (continent cell set, country cell
        # empty), but its 남성 / 여성 continuation rows leave BOTH cells empty, so
        # dropping only the head let the ffill hand those rows the previous
        # country's name: the 2020 sheet ends with a 기타계 block and its 282
        # residual persons landed on 카보베르데, the last country above it.
        starts = body[country_col].isna() & body[0].notna()
        state = pd.Series(pd.NA, index=body.index, dtype="object")
        state[starts] = True
        state[body[country_col].notna()] = False
        in_agg = state.ffill().fillna(False).astype(bool)
        body = body[~in_agg].reset_index(drop=True)

    body[country_col] = body[country_col].ffill()
    if not is_legacy:
        body[0] = body[0].ffill()

    all_gender_keys = gender_total_set | gender_male_set | gender_female_set
    body = body[body[gender_col].astype(str).str.strip().isin(all_gender_keys)]

    body["_country"] = body[country_col].apply(clean_country)
    body = body[body["_country"].notna()]
    body = body[~body["_country"].isin(DROP_NAMES)]

    records = []
    for _, row in body.iterrows():
        country = row["_country"]
        gender_raw = str(row[gender_col]).strip()
        if gender_raw in gender_total_set: gender = "T"
        elif gender_raw in gender_male_set: gender = "M"
        elif gender_raw in gender_female_set: gender = "F"
        else: continue
        for col_idx, age_group in age_cols.items():
            val = row[col_idx]
            if pd.isna(val):
                continue
            try:
                n = int(float(val))
            except (TypeError, ValueError):
                continue
            records.append((year, country, gender, age_group, n))

    return pd.DataFrame(records, columns=["year", "country", "gender", "age_group", "n"])


def build_age_long(files):
    parts = []
    for yr, p in sorted(files.items()):
        if not os.path.exists(p):
            print(f"  ! missing age {yr}: {p}")
            continue
        try:
            parts.append(load_age(yr, p))
        except Exception as e:
            print(f"  ! failed age {yr}: {e}")
    if not parts:
        return pd.DataFrame(columns=["year", "country", "gender", "age_group", "n"])
    long = pd.concat(parts, ignore_index=True)
    # For years that only ship per-country M+F (2014-2019 country rows have
    # no 총계 row), derive T = M + F so the JS UI always has a total value.
    # 2020+ already has T from the source file; we only fill missing T rows.
    # drop_duplicates is load-bearing: the source lists several nationality
    # classes that canonicalize to one country (영국 + 영국외지민 + 영국외지시민 +
    # 영국해외영토시민, 홍콩 + 홍콩거주난민, 미국 + 미국인근섬), each with its own
    # 총계 row. Without it this left-join fans out — one duplicate key per extra
    # class — and multiplies every row of that country, so 영국 came out at 4x its
    # real total and 홍콩 at 2x in every year.
    have_t = (long[long["gender"] == "T"][["year", "country", "age_group"]]
              .drop_duplicates().assign(_has_t=True))
    long = long.merge(have_t, on=["year", "country", "age_group"], how="left")
    needs_t = long[long["_has_t"].isna() & long["gender"].isin(["M", "F"])]
    derived = (
        needs_t.groupby(["year", "country", "age_group"], as_index=False)["n"].sum()
        .assign(gender="T")
        [["year", "country", "gender", "age_group", "n"]]
    )
    long = pd.concat([long.drop(columns=["_has_t"]), derived], ignore_index=True)
    return long


# ─────────────────────────────────────────────────────────────────────
# 주민등록인구 (MOIS) parser: sigungu × year × total/M/F
# ─────────────────────────────────────────────────────────────────────

# Sigungu name reconciliation for the population join. Early KIS region files
# (esp. 2014) use pre-reorganization names that don't match the MOIS resident
# population table. Clean, unambiguous renames only (merges/splits left as-is).
SIGUNGU_CANONICAL = {
    "여주군": "여주시",   # promoted to 시 in 2013
    "당진군": "당진시",   # promoted to 시 in 2012
}


def parse_population_file(path):
    """Parse one MOIS 주민등록인구 file (wide format: one block of columns per year).

    Returns long DataFrame: year, sido, sigungu, total_pop, male, female.
    Filters to 시군구-level rows (2-word names, sido + sigungu).

    Two export layouts are in circulation and both are read here:
      * older (200812_201512, 201512_202412): col0 행정기관코드, col1 행정기관,
        then 4 columns per year — 총인구수 / 세대수 / 남자 인구수 / 여자 인구수.
      * current jumin.mois.go.kr export (201512_202512): col0 행정구역 holding
        "이름 (코드)", then 5 columns per year — the four above plus 세대당 인구.
    Row 1 carries the year labels and row 2 the per-column labels, so the value
    columns are located by label within each year block instead of by fixed
    offset.
    """
    df = pd.read_excel(path, sheet_name=0, header=None)
    # Row 1 = year labels (first column of each year block), Row 2 = column types
    year_row = df.iloc[1].tolist()
    label_row = df.iloc[2].tolist()
    year_cols = []  # list of (col_start, year_int)
    for i, v in enumerate(year_row):
        if isinstance(v, str) and "년" in v:
            try:
                yr = int(re.sub(r"\D", "", v))
                year_cols.append((i, yr))
            except ValueError:
                pass

    # Within each year block, find the 총인구수 / 남자 / 여자 columns by label.
    ncol = df.shape[1]
    year_offsets = []  # list of (year, col_total, col_male, col_female)
    for k, (start, yr) in enumerate(year_cols):
        end = year_cols[k + 1][0] if k + 1 < len(year_cols) else ncol
        cols = {}
        for c in range(start, end):
            lab = str(label_row[c]).replace(" ", "")
            if lab.startswith("총인구수"):
                cols["total"] = c
            elif lab.startswith("남자"):
                cols["male"] = c
            elif lab.startswith("여자"):
                cols["female"] = c
        if "total" not in cols:  # fall back to the historical fixed offsets
            cols = {"total": start, "male": start + 2, "female": start + 3}
        year_offsets.append((yr, cols["total"], cols.get("male"), cols.get("female")))

    # Name column: the older layout splits code/name across cols 0-1, the current
    # one puts "이름 (코드)" in col 0.
    name_col = 1
    first_body_row = df.iloc[3] if len(df) > 3 else None
    if first_body_row is not None and isinstance(first_body_row[0], str) and \
            any(t in str(first_body_row[0]) for t in ("시", "도")):
        name_col = 0

    body = df.iloc[3:].copy().reset_index(drop=True)

    # Emit BOTH the 2-word city total ("부천시") and the 3-word 일반구 rows
    # ("부천시 원미구"). The city-total vs 구 double-count is resolved per-year
    # later in build_population_long: 구 rows win in years they carry data, but
    # the city total is kept for years after a city abolished its 구 (e.g.
    # 부천 2016+), where only the 2-word row has population.
    records = []
    for _, row in body.iterrows():
        name = row[name_col]
        if not isinstance(name, str):
            continue
        # the current export appends the administrative code: "서울특별시 종로구 (1111000000)"
        name = re.sub(r"\(\d+\)\s*$", "", name).strip()
        parts = name.split()
        if len(parts) == 1:
            # 시도 alone; only keep 세종 (which has no sub-시군구)
            if "세종" in name:
                sido, sigungu = name, "총계"
            else:
                continue
        elif len(parts) == 2:
            sido, sigungu = parts
        elif len(parts) == 3:
            # 일반구: join last two words to match KIS sigungu format
            sido = parts[0]
            sigungu = parts[1] + " " + parts[2]
        else:
            continue

        for yr, c_tot, c_male, c_female in year_offsets:
            tot = row[c_tot] if c_tot < len(row) else None
            male = row[c_male] if c_male is not None and c_male < len(row) else None
            female = row[c_female] if c_female is not None and c_female < len(row) else None
            def to_int(v):
                if pd.isna(v):
                    return None
                if isinstance(v, str):
                    v = v.replace(",", "").strip()
                    if not v:
                        return None
                try:
                    return int(float(v))
                except (TypeError, ValueError):
                    return None
            n = to_int(tot)
            if n is None:
                continue
            records.append((yr, sido, sigungu, n, to_int(male) or 0, to_int(female) or 0))
    return pd.DataFrame(
        records, columns=["year", "sido", "sigungu", "total_pop", "male", "female"]
    )


def build_population_long():
    parts = []
    for f in POPULATION_FILES:
        if not os.path.exists(f):
            print(f"  ! missing population file: {f}")
            continue
        try:
            parts.append(parse_population_file(f))
        except Exception as e:
            print(f"  ! failed population {f}: {e}")
    if not parts:
        return pd.DataFrame(columns=["year", "sido", "sigungu", "total_pop", "male", "female"])
    long = pd.concat(parts, ignore_index=True)
    long = long.drop_duplicates(subset=["year", "sido", "sigungu"], keep="last")
    long["sido"] = long["sido"].map(lambda s: SIDO_CANONICAL.get(s, s))

    # Resolve city-total vs 일반구 double-counting per (year, sido, base city).
    # 구 rows (sigungu contains a space) take precedence in years they carry
    # population; the 2-word city total is kept only where no 구 data exists
    # (post-구-abolition years, e.g. 부천 2016+). This both prevents national
    # double counting AND matches KIS region naming year by year.
    long["_isgu"] = long["sigungu"].str.contains(" ", regex=False)
    long["_base"] = long["sigungu"].str.split().str[0]
    gu_keys = set(
        map(tuple, long[long["_isgu"] & (long["total_pop"] > 0)]
            [["year", "sido", "_base"]].drop_duplicates().values.tolist())
    )
    keep_mask = long["_isgu"] | long.apply(
        lambda r: (r["year"], r["sido"], r["sigungu"]) not in gu_keys, axis=1)
    long = long[keep_mask].drop(columns=["_isgu", "_base"]).reset_index(drop=True)
    return long


# ─────────────────────────────────────────────────────────────────────
# Derived indices: Shannon Diversity, HHI, Location Quotient,
# Index of Dissimilarity. Computed from region (foreign × sigungu)
# and population (total × sigungu) panels.
# ─────────────────────────────────────────────────────────────────────

import math


# Country → single primary language most relevant for Korean public-service
# interpretation. Single assignment (not an equal split) for defensibility:
# for multilingual countries we pick the language Korean agencies most likely
# need (lingua franca / Danuri-supported language).


def compute_language_demand(region_df, year):
    """Per-sigungu language demand: sum foreign population by primary language.

    Each country contributes its full count to its single primary
    interpretation language (no arbitrary split).
    Returns {('sido','sigungu'): {language: count}}.
    """
    r = region_df[(region_df["year"] == year) &
                  (~region_df["sigungu"].isin({"총계", "총합계"}))]
    out = {}
    for (sido, sigungu), grp in r.groupby(["sido", "sigungu"]):
        langs = {}
        for _, row in grp.iterrows():
            lg = COUNTRY_LANGUAGE.get(row["country"])
            if not lg:
                continue
            langs[lg] = langs.get(lg, 0) + int(row["n"])
        if langs:
            out[(sido, sigungu)] = langs
    return out




def classify_region(country):
    return COUNTRY_REGION.get(country, "기타")


def _load_adjacency():
    """Queen-contiguity adjacency {match_key: [neighbors]} for Moran's I.
    Built once by build_adjacency.py; returns {} if absent (Moran's I skipped)."""
    path = os.path.join(OUT_DATA, "adjacency.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return {}
    return {}


_ADJ = _load_adjacency()


def morans_i(value_by_key):
    """Global Moran's I on the cached queen-contiguity weights."""
    return _morans_i(value_by_key, _ADJ)


def compute_indices(region_df, pop_df):
    """Compute standard segregation/diversity indices for each (year, sigungu)
    and (year, nationality). Returns dict ready to ship in JSON.

    References:
      Shannon, C. E. (1948). Mathematical theory of communication.
      Massey, D. S. & Denton, N. A. (1988). Dimensions of residential
        segregation. Social Forces 67(2):281-315.
      Reardon, S. F. & Firebaugh, G. (2002). Measures of multigroup
        segregation. Sociological Methodology 32(1):33-67.
    """
    if region_df.empty or pop_df.empty:
        return {}

    # Sigungu foreign totals per (year, sido, sigungu), exclude continent
    # "총계" rows from the region table.
    region = region_df[~region_df["sigungu"].isin({"총계", "총합계"})].copy()
    sigungu_total = (
        region.groupby(["year", "sido", "sigungu"], as_index=False)["n"].sum()
        .rename(columns={"n": "foreign_total"})
    )

    # Population denominator: outer-join so missing years are NaN (don't blow up)
    merged = pop_df.merge(sigungu_total, on=["year", "sido", "sigungu"], how="left")
    merged["foreign_total"] = merged["foreign_total"].fillna(0).astype(int)
    merged["korean_est"] = (merged["total_pop"] - merged["foreign_total"]).clip(lower=0)
    merged["foreign_share_pct"] = (
        merged["foreign_total"] / merged["total_pop"] * 100
    ).fillna(0)

    out = {
        "years": sorted(int(y) for y in region["year"].unique()),
        "by_sigungu": {},          # {year: [{sido, sigungu, total, foreign, share, H, HHI}, ...]}
        "by_nationality": {},      # {year: [{country, D, top_lq: [...]}, ...]}
        "summary": {},             # {year: {national_foreign_total, national_total_pop, national_share}}
        "enclaves": {},            # {year: [{sido, sigungu, country, count, lq, share_of_foreign}, ...]}
        "by_sido": {},             # {year: [{sido, foreign_total, total_pop, share, H}, ...]}
    }

    for yr in out["years"]:
        yr_region = region[region["year"] == yr]
        yr_pop = merged[merged["year"] == yr]

        # ----- Per sigungu diversity/HHI -----
        sigungu_rows = []
        for (sido, sigungu), sub in yr_region.groupby(["sido", "sigungu"]):
            counts = sub.set_index("country")["n"].to_dict()
            total = sum(counts.values())
            if total <= 0:
                continue
            # Shannon entropy (natural log)
            H = 0.0
            for v in counts.values():
                if v <= 0:
                    continue
                p = v / total
                H -= p * math.log(p)
            # HHI
            HHI = sum((v / total) ** 2 for v in counts.values() if v > 0)
            pop_row = yr_pop[(yr_pop["sido"] == sido) & (yr_pop["sigungu"] == sigungu)]
            total_pop = int(pop_row["total_pop"].iloc[0]) if len(pop_row) else None
            foreign_share = (total / total_pop * 100) if total_pop else None
            # H_inclusive: Shannon diversity INCLUDING Korean residents as
            # one group (so it reflects overall ethnic diversity of the area,
            # not just diversity within the foreign population). Requires
            # total_pop denominator.
            H_inc = None
            if total_pop and total_pop > 0:
                korean = max(total_pop - total, 0)
                pieces = list(counts.values()) + [korean]
                denom = sum(pieces)
                if denom > 0:
                    H_inc = 0.0
                    for v in pieces:
                        if v <= 0:
                            continue
                        p = v / denom
                        H_inc -= p * math.log(p)
                    H_inc = round(H_inc, 3)
            # Continent-level "visible" diversity: collapse nationalities into
            # world regions and add Koreans to East Asia, then Shannon H over
            # continents. Captures how visibly/phenotypically diverse the whole
            # population looks (East Asians read as one group). Also keep the
            # continental composition (%) for the distribution display.
            # continent_H (visible diversity) counts Koreans as East Asian;
            # continent_shares (the distribution display) is FOREIGN-only so the
            # non-East-Asian continents are visible rather than swamped by Koreans.
            continent_H = None
            continent_shares = None
            if total_pop and total_pop > 0:
                cont = {}
                for c, v in counts.items():
                    if v > 0:
                        r = classify_region(c)
                        cont[r] = cont.get(r, 0) + v
                denom_for = sum(cont.values())
                if denom_for > 0:
                    continent_shares = {k: round(v / denom_for * 100, 3)
                                        for k, v in sorted(cont.items(), key=lambda x: -x[1])}
                cont_full = dict(cont)
                cont_full["동아시아"] = cont_full.get("동아시아", 0) + max(total_pop - total, 0)
                denom = sum(cont_full.values())
                if denom > 0:
                    continent_H = 0.0
                    for v in cont_full.values():
                        if v > 0:
                            p = v / denom
                            continent_H -= p * math.log(p)
                    continent_H = round(continent_H, 4)
            sigungu_rows.append({
                "sido": sido,
                "sigungu": sigungu,
                "foreign_total": int(total),
                "total_pop": total_pop,
                "foreign_share_pct": round(foreign_share, 2) if foreign_share is not None else None,
                "shannon_H": round(H, 3),
                "shannon_H_inclusive": H_inc,
                "continent_H": continent_H,
                "continent_shares": continent_shares,
                "HHI": round(HHI, 4),
                "n_nationalities": sum(1 for v in counts.values() if v > 0),
            })
        out["by_sigungu"][str(yr)] = sorted(
            sigungu_rows, key=lambda r: -(r["foreign_share_pct"] or 0)
        )

        # ----- National summary -----
        national_foreign = int(yr_region["n"].sum())
        national_total_pop = int(yr_pop["total_pop"].sum()) if not yr_pop.empty else None
        # National Shannon H over nationalities (within-foreigner diversity)
        nat_counts = yr_region.groupby("country")["n"].sum()
        nat_H = 0.0
        if national_foreign > 0:
            for v in nat_counts:
                if v > 0:
                    p = v / national_foreign
                    nat_H -= p * math.log(p)
        # Mean within-sigungu H (population-relevant diversity, foreign>=1000)
        sig_H_vals = [r["shannon_H"] for r in sigungu_rows if r["foreign_total"] >= 1000]
        mean_sig_H = (sum(sig_H_vals) / len(sig_H_vals)) if sig_H_vals else None
        out["summary"][str(yr)] = {
            "national_foreign_total": national_foreign,
            "national_total_pop": national_total_pop,
            "national_share_pct": (national_foreign / national_total_pop * 100
                                   if national_total_pop else None),
            "national_shannon_H": round(nat_H, 3),
            "mean_sigungu_H": round(mean_sig_H, 3) if mean_sig_H is not None else None,
            "n_nationalities": int((nat_counts > 0).sum()),
        }
        # Spatial clustering (Massey & Denton clustering dimension): Moran's I of
        # the foreign share across districts. >0 = high-share districts adjoin
        # other high-share districts.
        share_by_key = {r["sido"] + "|" + r["sigungu"].replace(" ", ""): r["foreign_share_pct"]
                        for r in sigungu_rows if r.get("foreign_share_pct") is not None}
        mi = morans_i(share_by_key)
        out["summary"][str(yr)]["morans_I_share"] = round(mi, 4) if mi is not None else None

        # ----- Per nationality: D (vs Korean) + top LQ sigungus -----
        # Aggregate to sigungu × country
        sg_ctry = (
            yr_region.groupby(["sido", "sigungu", "country"], as_index=False)["n"].sum()
        )
        nat_rows = []
        # National total foreigners per nationality
        nat_totals = sg_ctry.groupby("country")["n"].sum().to_dict()
        # Pop merged for this year by (sido, sigungu)
        pop_idx = yr_pop.set_index(["sido", "sigungu"])[["total_pop", "korean_est"]]

        # Pre-compute Korean nationwide total
        kor_total = int(pop_idx["korean_est"].sum()) if len(pop_idx) else None

        for country, ct_sub in sg_ctry.groupby("country"):
            X = nat_totals.get(country, 0)
            if X < 100:  # skip very small populations (noise)
                continue
            # D = 0.5 * Σ |x_i/X - y_i/Y| where y is Korean (reference group)
            D = 0.0
            if kor_total and kor_total > 0:
                ct_lookup = ct_sub.set_index(["sido", "sigungu"])["n"].to_dict()
                for (sido, sg), kor_n in pop_idx["korean_est"].items():
                    x_i = ct_lookup.get((sido, sg), 0)
                    D += abs(x_i / X - kor_n / kor_total)
                D *= 0.5
            # Top 10 sigungus by LQ; isolation + Korean-interaction (exposure dim.)
            top_lq = []
            isolation = 0.0       # _gP*g = Σ (x_i/X)(x_i/t_i): own-group exposure
            interaction_kor = 0.0  # _gP*k = Σ (x_i/X)(kor_i/t_i): exposure to Koreans
            for (sido, sg), x_i in ct_sub.set_index(["sido", "sigungu"])["n"].items():
                if (sido, sg) not in pop_idx.index:
                    continue
                tot_pop = pop_idx.loc[(sido, sg), "total_pop"]
                if not tot_pop or x_i == 0:
                    continue
                if X > 0:
                    isolation += (x_i / X) * (x_i / tot_pop)
                    interaction_kor += (x_i / X) * (pop_idx.loc[(sido, sg), "korean_est"] / tot_pop)
                # LQ = (group share in region) / (group share in nation)
                if national_total_pop and X:
                    region_share = x_i / tot_pop
                    nation_share = X / national_total_pop
                    lq = region_share / nation_share if nation_share > 0 else 0
                    if lq >= 1.5:  # only flag overrepresented
                        top_lq.append({
                            "sido": sido, "sigungu": sg,
                            "count": int(x_i),
                            "lq": round(lq, 2),
                            "local_share_pct": round(x_i / tot_pop * 100, 3),
                        })
            top_lq.sort(key=lambda r: -r["lq"])
            nat_rows.append({
                "country": country,
                "national_total": int(X),
                "D": round(D, 3) if kor_total else None,
                "isolation": round(isolation, 4),
                "interaction_korean": round(interaction_kor, 4),
                "top_lq": top_lq[:10],
            })
        nat_rows.sort(key=lambda r: -r["national_total"])
        out["by_nationality"][str(yr)] = nat_rows

        # ----- National multigroup Theil entropy segregation index H -----
        # Reardon & Firebaugh (2002): how much the population's nationality
        # composition (Korean + each foreign nationality) varies across
        # districts. 0 = every district has the national mix; higher = more
        # residentially segregated. Computed over the whole resident population.
        theil_H = None
        if national_total_pop and kor_total is not None and kor_total > 0:
            T = national_total_pop
            group_tot = dict(nat_totals)
            group_tot["__KOR__"] = kor_total
            E = 0.0
            for v in group_tot.values():
                if v > 0:
                    p = v / T
                    E -= p * math.log(p)
            if E > 0:
                sg_nat = {}
                for (sido, sg, c), n in sg_ctry.set_index(["sido", "sigungu", "country"])["n"].items():
                    sg_nat.setdefault((sido, sg), {})[c] = n
                acc = 0.0
                for (sido, sg) in pop_idx.index:
                    t_i = pop_idx.loc[(sido, sg), "total_pop"]
                    if not t_i or t_i <= 0:
                        continue
                    kor_i = pop_idx.loc[(sido, sg), "korean_est"]
                    groups_i = list((sg_nat.get((sido, sg)) or {}).values()) + [kor_i]
                    E_i = 0.0
                    for g in groups_i:
                        if g > 0:
                            pr = g / t_i
                            E_i -= pr * math.log(pr)
                    acc += (t_i / T) * (E - E_i)
                theil_H = round(acc / E, 4)
        out["summary"][str(yr)]["theil_segregation_H"] = theil_H

        # ----- Region-of-origin segregation -----
        # Aggregate foreign nationalities into world regions and compute each
        # region's dissimilarity (vs Koreans) and isolation index.
        reg_block = {}
        sg_ctry2 = sg_ctry.copy()
        sg_ctry2["region"] = sg_ctry2["country"].map(classify_region)
        for reg_name, g in sg_ctry2.groupby("region"):
            Xg = int(g["n"].sum())
            if Xg <= 0:
                continue
            g_by_sg = g.groupby(["sido", "sigungu"])["n"].sum().to_dict()
            D = 0.0
            if kor_total and kor_total > 0:
                for (sido, sg), kor_n in pop_idx["korean_est"].items():
                    D += abs(g_by_sg.get((sido, sg), 0) / Xg - kor_n / kor_total)
                D *= 0.5
            iso = 0.0
            for (sido, sg), x_i in g_by_sg.items():
                if (sido, sg) in pop_idx.index:
                    t_i = pop_idx.loc[(sido, sg), "total_pop"]
                    if t_i and t_i > 0:
                        iso += (x_i / Xg) * (x_i / t_i)
            reg_block[reg_name] = {"total": Xg,
                                 "D": round(D, 3) if kor_total else None,
                                 "isolation": round(iso, 4)}
        out.setdefault("region_seg", {})[str(yr)] = reg_block

        # ----- Ethnic enclaves -----
        # Criterion (Wilson & Portes 1980; Logan, Zhang & Alba 2002):
        #   LQ >= 2 (2x overrepresented vs national, on total-population basis)
        #   AND the nationality is >= 30% of the sigungu's FOREIGN population
        #   (dominance within the immigrant community)
        # Plus a small absolute floor to avoid noise.
        enclave_rows = []
        sigungu_foreign = sg_ctry.groupby(["sido", "sigungu"])["n"].sum().to_dict()
        for _, row in sg_ctry.iterrows():
            sido, sigungu, country, x = row["sido"], row["sigungu"], row["country"], row["n"]
            if x < 200:
                continue
            sg_for = sigungu_foreign.get((sido, sigungu), 0)
            if sg_for <= 0:
                continue
            tot_pop = pop_idx.loc[(sido, sigungu), "total_pop"] if (sido, sigungu) in pop_idx.index else None
            if not tot_pop:
                continue
            X = nat_totals.get(country, 0)
            if X <= 0 or not national_total_pop:
                continue
            lq = (x / tot_pop) / (X / national_total_pop)
            share_foreign = x / sg_for
            if lq >= 2 and share_foreign >= 0.30:
                enclave_rows.append({
                    "sido": sido,
                    "sigungu": sigungu,
                    "country": country,
                    "count": int(x),
                    "lq": round(lq, 1),
                    "share_of_foreign_pct": round(share_foreign * 100, 1),
                    "sigungu_foreign_total": int(sg_for),
                    "foreign_share_of_pop_pct": round(sg_for / tot_pop * 100, 2),
                })
        enclave_rows.sort(key=lambda r: -r["lq"])
        out["enclaves"][str(yr)] = enclave_rows
        out["summary"][str(yr)]["n_enclaves"] = len(enclave_rows)

        # ----- Sido-level rollup (for the map) -----
        # Source foreign totals from each sido's 총계 row (every sido has one,
        # incl. 세종 which has no sub-sigungu). `region` (the function-level
        # filtered frame) drops 총계, so use the unfiltered region_df here.
        total_rows = region_df[(region_df["year"] == yr) &
                               (region_df["sigungu"].isin({"총계", "총합계"}))]
        sido_pop = yr_pop.groupby("sido")["total_pop"].sum().to_dict() if not yr_pop.empty else {}
        sido_ctry = total_rows.groupby(["sido", "country"])["n"].sum()
        lvl0 = set(sido_ctry.index.get_level_values(0))
        sido_foreign = total_rows.groupby("sido")["n"].sum().to_dict()
        sido_rows = []
        for sido in sorted(set(sido_foreign) | set(sido_pop)):
            f = int(sido_foreign.get(sido, 0))
            p = int(sido_pop.get(sido, 0)) or None
            H = 0.0
            n_nat = 0
            if sido in lvl0 and f > 0:
                counts = sido_ctry[sido]
                for v in counts.values:
                    if v > 0:
                        pr = v / f
                        H -= pr * math.log(pr)
                n_nat = int((counts > 0).sum())
            # Continent composition + visible diversity for this sido
            cont_H, cont_shares = None, None
            if p and p > 0 and sido in lvl0:
                cont = {}
                for c, v in sido_ctry[sido].items():
                    if v > 0:
                        r = classify_region(c)
                        cont[r] = cont.get(r, 0) + int(v)
                denom_for = sum(cont.values())
                if denom_for > 0:
                    cont_shares = {k: round(v / denom_for * 100, 3)
                                   for k, v in sorted(cont.items(), key=lambda x: -x[1])}
                cont_full = dict(cont)
                cont_full["동아시아"] = cont_full.get("동아시아", 0) + max(p - f, 0)
                denom = sum(cont_full.values())
                if denom > 0:
                    cont_H = 0.0
                    for v in cont_full.values():
                        if v > 0:
                            pr = v / denom
                            cont_H -= pr * math.log(pr)
                    cont_H = round(cont_H, 4)
            sido_rows.append({
                "sido": sido,
                "foreign_total": f,
                "total_pop": p,
                "foreign_share_pct": round(f / p * 100, 2) if p else None,
                "shannon_H": round(H, 3),
                "continent_H": cont_H,
                "continent_shares": cont_shares,
                "n_nationalities": n_nat,
            })
        out.setdefault("by_sido", {})[str(yr)] = sido_rows

        # National continental composition (incl. Koreans -> East Asia)
        if national_total_pop and national_total_pop > 0:
            cont = {}
            for c, v in nat_counts.items():
                if v > 0:
                    r = classify_region(c)
                    cont[r] = cont.get(r, 0) + int(v)
            denom_for = sum(cont.values())
            if denom_for > 0:
                out["summary"][str(yr)]["continent_shares"] = {
                    k: round(v / denom_for * 100, 3) for k, v in sorted(cont.items(), key=lambda x: -x[1])}
            cont_full = dict(cont)
            cont_full["동아시아"] = cont_full.get("동아시아", 0) + max(national_total_pop - national_foreign, 0)
            denom = sum(cont_full.values())
            if denom > 0:
                cH = 0.0
                for v in cont_full.values():
                    if v > 0:
                        pr = v / denom
                        cH -= pr * math.log(pr)
                out["summary"][str(yr)]["continent_H"] = round(cH, 4)

        # ----- Language demand -----
        lang_by_sg = compute_language_demand(region_df, yr)
        # National language totals
        nat_lang = {}
        for sg, langs in lang_by_sg.items():
            for lg, c in langs.items():
                nat_lang[lg] = nat_lang.get(lg, 0) + c
        # Store: national ranking + per-sigungu top languages
        out.setdefault("language", {})[str(yr)] = {
            "national": sorted(
                [{"language": k, "count": v} for k, v in nat_lang.items()],
                key=lambda d: -d["count"]),
            "by_sigungu": {
                f"{sido}|{sg}": sorted(
                    [{"language": k, "count": v} for k, v in langs.items()],
                    key=lambda d: -d["count"])[:8]
                for (sido, sg), langs in lang_by_sg.items()
            },
        }

    return out


# ─────────────────────────────────────────────────────────────────────
# 국적취득(귀화) parser
# ─────────────────────────────────────────────────────────────────────

def load_naturalization():
    """Parse 4장 국적처리 files (annual, by country, by age).

    Returns dict ready to drop into data.json.
    """
    out = {"annual": {}, "by_country": [], "by_age": [], "types": []}

    # Annual time series (single file covers 2011-2024)
    annual_path = NATURALIZATION_FILES["annual"]
    if os.path.exists(annual_path):
        df = pd.read_excel(annual_path, sheet_name=0, header=None)
        header = df.iloc[0].tolist()
        # header[0] = '연도', header[1..] = type labels
        types = [str(h).strip() for h in header[1:] if isinstance(h, str)]
        annual = {}
        for i in range(1, len(df)):
            row = df.iloc[i].tolist()
            try:
                year = int(row[0])
            except (TypeError, ValueError):
                continue
            yd = {}
            for j, typ in enumerate(types, start=1):
                v = row[j] if j < len(row) else None
                if pd.notna(v):
                    try:
                        yd[typ] = int(float(v))
                    except (TypeError, ValueError):
                        pass
            annual[str(year)] = yd
        out["annual"] = annual
        out["types"] = types

    # Country breakdown (2024)
    country_path = NATURALIZATION_FILES["country"]
    if os.path.exists(country_path):
        df = pd.read_excel(country_path, sheet_name=0, header=None)
        header = df.iloc[0].tolist()
        # col0=continent, col1=country, col2+=types
        types_c = [str(h).strip() for h in header[2:] if isinstance(h, str)]
        for i in range(1, len(df)):
            row = df.iloc[i].tolist()
            country_raw = row[1] if len(row) > 1 else None
            country = clean_country(country_raw) if country_raw else None
            # Skip continent-aggregate / grand-total rows
            if not country or country in DROP_NAMES:
                continue
            if country in {"총계", "총합계"}:
                continue
            rec = {"country": country}
            for j, typ in enumerate(types_c, start=2):
                v = row[j] if j < len(row) else None
                if pd.notna(v):
                    try:
                        rec[typ] = int(float(v))
                    except (TypeError, ValueError):
                        pass
            # the nationality alias map folds several source rows (e.g. 영국 +
            # 영국외지민) onto one canonical country — aggregate, never duplicate
            prev = next((r for r in out["by_country"] if r["country"] == country), None)
            if prev:
                for k, v in rec.items():
                    if k != "country":
                        prev[k] = (prev.get(k) or 0) + v
            else:
                out["by_country"].append(rec)

    # Age breakdown (2024)
    age_path = NATURALIZATION_FILES["age"]
    if os.path.exists(age_path):
        df = pd.read_excel(age_path, sheet_name=0, header=None)
        header = df.iloc[0].tolist()
        # col0=age, col1+=types
        types_a = [str(h).strip() for h in header[1:] if isinstance(h, str)]
        for i in range(1, len(df)):
            row = df.iloc[i].tolist()
            age_raw = row[0] if len(row) else None
            if pd.isna(age_raw):
                continue
            age_label = str(age_raw).strip()
            if age_label in {"총합계", "총계"}:
                continue
            rec = {"age": age_label}
            for j, typ in enumerate(types_a, start=1):
                v = row[j] if j < len(row) else None
                if pd.notna(v):
                    try:
                        rec[typ] = int(float(v))
                    except (TypeError, ValueError):
                        pass
            out["by_age"].append(rec)

    return out


NATURALIZATION_SOURCES = [
    {"label_ko": "법무부 출입국·외국인정책 통계연보 4장 (국적처리)",
     "label_en": "KIS Yearbook Ch. 4 (Nationality Processing)",
     "url": "https://www.moj.go.kr/moj/2412/subview.do"},
]


# ─────────────────────────────────────────────────────────────────────
# REFUGEE & NORTH KOREAN DEFECTOR DATA
# Compiled from public Korean government sources; .go.kr sites block
# automated fetch so values are taken from cited press releases / data
# portal previews / Wikipedia summaries of the underlying gov data.
# ─────────────────────────────────────────────────────────────────────

# Refugee applications & decisions, 1994–2024.
# Source: 법무부 출입국·외국인정책본부 난민정책과,
# "난민 신청 및 심사 통계 (1994년~2024년)" published 2025-02.
# Local copy: refugee statistics/94_24년 난민 신청 및 심사 통계.pdf
REFUGEE_DATA = {
    # Annual new applications (Table 1). 1994-2012 lumped per source.
    "applications": {
        "1994-2012": 5069,
        "2013": 1574, "2014": 2896, "2015": 5711, "2016": 7541, "2017": 9942,
        "2018": 16173, "2019": 15452, "2020": 6684, "2021": 2341, "2022": 11539,
        "2023": 18837, "2024": 18336,
    },
    # Recognized refugees per year (Table 4). 1994-2015 lumped per source.
    "recognized": {
        "1994-2015": 580,
        "2016": 98, "2017": 121, "2018": 144, "2019": 79, "2020": 69,
        "2021": 72, "2022": 175, "2023": 101, "2024": 105,
    },
    # Humanitarian permits per year (Table 4). 1994-2015 lumped.
    "humanitarian": {
        "1994-2015": 908,
        "2016": 252, "2017": 316, "2018": 507, "2019": 229, "2020": 154,
        "2021": 49, "2022": 55, "2023": 125, "2024": 101,
    },
    "cumulative": {
        "applications_total": 122095,
        "recognized_total": 1544,
        "humanitarian_total": 2696,
        "protected_total": 4240,
        "protection_rate_pct": 7.4,      # 보호율 cumulative (인정+인도)/심사완료
        "recognition_rate_pct": 2.7,     # 인정률 cumulative
        "recognition_rate_2024_pct": 1.9,
    },
    "gender": {  # Table 8 cumulative
        "male": 91330, "female": 30765,
        "male_pct": 74.8, "female_pct": 25.2,
    },
    "by_visa_at_application": [  # Table 5
        ["사증면제 (B-1)", "Visa Exemption (B-1)", 44296, 36.3],
        ["단기종합 (C-3)", "Short-term (C-3)", 40773, 33.4],
        ["관광통과 (B-2)", "Tourist Transit (B-2)", 9395, 7.7],
        ["비전문취업 (E-9)", "Non-professional Employment (E-9)", 8622, 7.1],
        ["난민신청자 재신청 (G-1-5)", "Refugee Re-applicant (G-1-5)", 7221, 5.9],
        ["출국기한유예", "Departure Postponed", 3814, 3.1],
        ["유학 (D-2/D-4)", "Student (D-2/D-4)", 2808, 2.3],
        ["기타", "Other", 5166, 4.2],
    ],
    "by_reason_applied": [  # Table 9
        ["협약외 사유", "Outside Convention", 51432, 42.1],
        ["정치적 의견", "Political Opinion", 24513, 20.1],
        ["종교", "Religion", 23480, 19.2],
        ["특정사회 구성원", "Particular Social Group", 10757, 8.8],
        ["인종", "Race", 5541, 4.5],
        ["가족결합", "Family Reunification", 5210, 4.3],
        ["국적", "Nationality", 1162, 1.0],
    ],
    "by_reason_recognized": [  # Table 10
        ["가족결합", "Family Reunification", 605, 39.2],
        ["정치적 의견", "Political Opinion", 451, 29.2],
        ["인종", "Race", 280, 18.1],
        ["종교", "Religion", 140, 9.1],
        ["특정사회 구성원", "Particular Social Group", 64, 4.1],
        ["국적", "Nationality", 4, 0.3],
    ],
    "top_applicant_nationalities": [  # Table 11, top 10
        ["러시아", "Russia", 18257, 15.0],
        ["카자흐스탄", "Kazakhstan", 13078, 10.7],
        ["중국", "China", 11077, 9.1],
        ["파키스탄", "Pakistan", 8213, 6.7],
        ["인도", "India", 7794, 6.4],
        ["말레이시아", "Malaysia", 6041, 4.9],
        ["이집트", "Egypt", 6026, 4.9],
        ["방글라데시", "Bangladesh", 4254, 3.5],
        ["나이지리아", "Nigeria", 3533, 2.9],
        ["튀르키예", "Türkiye", 3262, 2.7],
    ],
    "top_recognized_nationalities": [  # Table 14
        ["미얀마", "Myanmar", 474, 30.7],
        ["에티오피아", "Ethiopia", 164, 10.6],
        ["이집트", "Egypt", 154, 10.0],
        ["방글라데시", "Bangladesh", 124, 8.0],
        ["파키스탄", "Pakistan", 109, 7.1],
        ["콩고민주공화국", "DR Congo", 63, 4.1],
        ["이란", "Iran", 61, 4.0],
        ["예멘공화국", "Yemen", 46, 3.0],
        ["아프가니스탄", "Afghanistan", 45, 2.9],
        ["수단", "Sudan", 41, 2.7],
    ],
    "top_humanitarian_nationalities": [  # Table 15
        ["시리아", "Syria", 1271, 47.1],
        ["예멘공화국", "Yemen", 802, 29.7],
        ["아이티", "Haiti", 117, 4.3],
        ["미얀마", "Myanmar", 55, 2.0],
        ["중국", "China", 37, 1.4],
        ["파키스탄", "Pakistan", 37, 1.4],
        ["아프가니스탄", "Afghanistan", 34, 1.3],
        ["에티오피아", "Ethiopia", 33, 1.2],
        ["코트디부아르", "Côte d'Ivoire", 30, 1.1],
        ["이라크", "Iraq", 29, 1.1],
    ],
    "notes_ko": [
        "1994년 난민협약 가입, 2013년 7월 난민법 시행",
        "누적 신청 122,095건 중 심사완료 65,227건, 심사 진행 27,704건",
        "보호율 7.4% (난민인정 1,544명 + 인도적체류허가 2,696명), 누적 기준",
        "재신청 11,409건 (전체 신청의 9.4%)",
        "재정착난민 250명 포함 (미얀마 236, 이란 5, 시리아 5, 무국적 3, 아프간 1)",
    ],
    "notes_en": [
        "Refugee Convention signed 1994; Refugee Act effective July 2013",
        "Of 122,095 cumulative applications: 65,227 reviewed, 27,704 pending",
        "Protection rate 7.4% (1,544 recognized + 2,696 humanitarian permits), cumulative",
        "11,409 re-applications (9.4% of total)",
        "Includes 250 resettled refugees (Myanmar 236, Iran 5, Syria 5, Stateless 3, Afghan 1)",
    ],
}

# North Korean defector entries to South Korea, 1998–2024.
# Source: 통일부 정착지원과 + Wikipedia (Korean) compiled from 통일부 official figures.
# Cumulative entries through end-2024: ~34,314.
DEFECTOR_DATA = {
    "annual": {
        1998: 71, 1999: 148, 2000: 310, 2001: 586, 2002: 1142,
        2003: 1285, 2004: 1898, 2005: 1384, 2006: 2028, 2007: 2554,
        2008: 2803, 2009: 2914, 2010: 2402, 2011: 2706, 2012: 1502,
        2013: 1514, 2014: 1397, 2015: 1275, 2016: 1418, 2017: 1127,
        2018: 1137, 2019: 1047, 2020: 229, 2021: 63, 2022: 67,
        2023: 196, 2024: 236,
    },
    "cumulative": {
        "total_through_2024": 34314,
        "male_total": 9576,
        "female_total": 24834,
        "female_share_pct": 72.2,
        "peak_year": 2009,
        "peak_count": 2914,
    },
    "notes_ko": [
        "1998년부터 통계 기준 (1998년 이전 947명 별도 누계)",
        "2002년부터 여성 입국자가 남성을 초과; 누적 여성 비율 ~72%",
        "2020년 코로나19로 급감 후 2024년 부분 회복",
        "2009년 최고치 2,914명 → 2012년 김정은 체제 이후 1천 명대로 감소",
    ],
    "notes_en": [
        "Statistics from 1998 onwards (947 entrants before 1998 tracked separately)",
        "Since 2002, female entries exceed male; cumulative female share ~72%",
        "COVID-19 collapse in 2020; partial recovery by 2024",
        "Peak 2,914 in 2009 → dropped to ~1,000s after Kim Jong Un era began (2012)",
    ],
}

REFUGEE_SOURCES = [
    {"label_ko": "법무부 난민통계 (1994~2024)",
     "label_en": "MOJ Refugee Statistics (1994–2024)",
     "url": "https://immigration.go.kr/bbs/immigration/228/477062/download.do"},
    {"label_ko": "법무부 2025.2.3 보도자료 (난민제도 30년)",
     "label_en": "MOJ Press Release 2025-02-03 (30 years of refugee system)",
     "url": "https://www.moj.go.kr/bbs/moj/182/476997/download.do"},
    {"label_ko": "e-나라지표:난민 신청 및 인정 현황",
     "label_en": "e-나라지표:Refugee Applications & Recognitions",
     "url": "https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=2820"},
    {"label_ko": "공공데이터포털:법무부 난민 통계",
     "label_en": "Public Data Portal:MOJ Refugee Data",
     "url": "https://www.data.go.kr/data/15100054/fileData.do"},
]

DEFECTOR_SOURCES = [
    {"label_ko": "통일부: 북한이탈주민 정착지원 현황",
     "label_en": "Ministry of Unification: N. Korean Defector Settlement Statistics",
     "url": "https://www.unikorea.go.kr/web/unikorea/contents/status_entry"},
    {"label_ko": "공공데이터포털:통일부 북한이탈주민 입국 현황",
     "label_en": "Public Data Portal:MOU Defector Entry Data",
     "url": "https://www.data.go.kr/data/15106185/fileData.do"},
    {"label_ko": "e-나라지표:북한이탈주민 입국 현황",
     "label_en": "e-나라지표:N. Korean Defector Entry",
     "url": "https://www.index.go.kr/potal/main/EachDtlPageDetail.do?idx_cd=1694"},
    {"label_ko": "KOSIS: 북한이탈주민 입국 현황",
     "label_en": "KOSIS: N. Korean Defector Entry",
     "url": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1ZGAA42"},
]


# ─────────────────────────────────────────────────────────────────────
# SUPPORT SYSTEMS for migrant / minority populations in Korea
# Curated from .go.kr official sites + lead-agency publications.
# ─────────────────────────────────────────────────────────────────────
SUPPORT_SYSTEMS = [
    {
        "code": "general",
        "label_ko": "외국인 (일반)",
        "label_en": "General Foreigners",
        "definition_ko": "한국 체류 외국인 전반을 대상으로 하는 정책·서비스. 법무부 출입국·외국인청과 고용노동부가 주관.",
        "definition_en": "Programs targeting foreign residents in general, led by MOJ Korea Immigration Service and the Ministry of Employment & Labor.",
        "programs": [
            {
                "name_ko": "외국인종합안내센터 (1345)",
                "name_en": "Foreigner Comprehensive Information Center (1345)",
                "agency_ko": "법무부",
                "agency_en": "Ministry of Justice",
                "target_ko": "한국 체류 외국인 전체",
                "target_en": "All foreign residents",
                "desc_ko": "20개 외국어로 체류·출입국·생활 정보 종합상담. 365일 운영.",
                "desc_en": "365-day multilingual hotline (20 languages) for residence, immigration, and daily-life questions.",
                "url": "https://www.hikorea.go.kr/info/InfoDetail_R_Kr.pt?CAT_SEQ=312&PARENT_ID=311",
            },
            {
                "name_ko": "사회통합프로그램 (KIIP)",
                "name_en": "Korea Immigration & Integration Program (KIIP)",
                "agency_ko": "법무부",
                "agency_en": "Ministry of Justice",
                "target_ko": "결혼이민자·영주·귀화 희망자",
                "target_en": "Marriage migrants, permanent-residence and naturalization applicants",
                "desc_ko": "한국어·한국사회이해 단계별 교육 (0~5단계). 이수 시 영주·귀화 심사 우대 + 한국어 시험 면제.",
                "desc_en": "Tiered Korean language + society courses (levels 0-5). Completion waives Korean test for permanent residence/naturalization.",
                "url": "https://www.socinet.go.kr",
            },
            {
                "name_ko": "외국인 노동자 지원센터",
                "name_en": "Migrant Worker Support Centers",
                "agency_ko": "고용노동부 / 한국산업인력공단",
                "agency_en": "MOEL / HRD Korea",
                "target_ko": "E-9 비전문취업·H-2 방문취업 등 이주노동자",
                "target_en": "E-9, H-2 and other migrant workers",
                "desc_ko": "노무·산재·통역·임금체불 상담, 한국어 교육. 전국 거점센터 + 소지역센터.",
                "desc_en": "Labor, industrial accident, interpretation, and unpaid-wage support, plus Korean classes. Network of regional + local centers.",
                "url": "https://www.eps.go.kr",
            },
            {
                "name_ko": "다문화가족지원포털 다누리",
                "name_en": "Danuri Multicultural Family Portal",
                "agency_ko": "여성가족부",
                "agency_en": "Ministry of Gender Equality & Family",
                "target_ko": "외국인 및 다문화가족",
                "target_en": "Foreigners and multicultural families",
                "desc_ko": "13개 언어 생활정보·정책안내. 지역 다문화가족지원센터 검색.",
                "desc_en": "13-language portal for life info and policy navigation; locator for local Family Centers.",
                "url": "https://www.liveinkorea.kr",
            },
        ],
    },
    {
        "code": "worker",
        "label_ko": "외국인 노동자 (이주노동자)",
        "label_en": "Migrant Workers",
        "definition_ko": "E-9 비전문취업, E-10 선원취업, H-2 방문취업 등 비전문·단순노무 분야 외국인 근로자. 「외국인근로자의 고용 등에 관한 법률」(EPS법, 2003)이 근거.",
        "definition_en": "Foreign workers under E-9 (non-professional employment), E-10 (crew), H-2 (working visit) and related visas. Statutory basis: Employment Permit System (EPS) Act, 2003.",
        "programs": [
            {
                "name_ko": "외국인근로자 종합상담센터 (1577-0071)",
                "name_en": "Migrant Worker Comprehensive Counseling Center (1577-0071)",
                "agency_ko": "고용노동부 / 한국산업인력공단",
                "agency_en": "MOEL / HRD Korea",
                "target_ko": "E-9·E-10·H-2 이주노동자",
                "target_en": "E-9, E-10, H-2 migrant workers",
                "desc_ko": "임금체불·산재·고용허가·체류 상담. 16개 언어 지원 (한국어·영어·중국어·베트남어·태국어·인도네시아어·필리핀어·캄보디아어·미얀마어·네팔어·우즈벡어·스리랑카어·키르기즈어·몽골어·방글라데시어·동티모르어).",
                "desc_en": "Counseling on wage delays, industrial accidents, employment permits, and visa issues. 16 languages supported.",
                "url": "https://www.eps.go.kr",
            },
            {
                "name_ko": "외국인노동자지원센터 (전국 거점)",
                "name_en": "Migrant Worker Support Centers (regional hubs)",
                "agency_ko": "고용노동부 위탁 운영 (민간단체)",
                "agency_en": "MOEL-commissioned (NGOs)",
                "target_ko": "이주노동자 및 가족",
                "target_en": "Migrant workers and families",
                "desc_ko": "전국 거점센터 + 소지역센터. 휴일 상담, 한국어 교육, 컴퓨터 교육, 응급 의료지원, 문화 행사, 쉼터.",
                "desc_en": "Hub + local centers nationwide. Weekend counseling, Korean classes, computer literacy, emergency medical, cultural events, shelter.",
                "url": "https://www.moel.go.kr",
            },
            {
                "name_ko": "EPS (고용허가제) Center",
                "name_en": "EPS (Employment Permit System) Center",
                "agency_ko": "한국산업인력공단",
                "agency_en": "HRD Korea",
                "target_ko": "E-9 비전문취업 입국 예정자·재직자",
                "target_en": "Prospective and incumbent E-9 workers",
                "desc_ko": "16개 송출국가 운영. EPS-TOPIK, 입국 전 교육, 고용주 매칭, 재고용 절차. 일부 EPS Korea Centers 송출국 현지에 설치.",
                "desc_en": "Operates in 16 sending countries. EPS-TOPIK exam, pre-departure training, employer matching, re-employment. EPS Korea Centers in sending-country capitals.",
                "url": "https://www.eps.go.kr",
            },
            {
                "name_ko": "산재 외국인근로자 지원",
                "name_en": "Industrial Accident Support for Migrant Workers",
                "agency_ko": "근로복지공단",
                "agency_en": "Korea Workers' Compensation & Welfare Service",
                "target_ko": "산업재해 피해 이주노동자",
                "target_en": "Migrant workers injured on the job",
                "desc_ko": "산재보험 적용 (국적 무관). 의료비, 휴업급여, 장해급여, 유족급여. 다국어 안내.",
                "desc_en": "Industrial accident insurance regardless of nationality: medical costs, leave allowance, disability/survivor benefits. Multilingual.",
                "url": "https://www.comwel.or.kr",
            },
            {
                "name_ko": "이주노동자노동조합 (MTU)",
                "name_en": "Migrants' Trade Union (MTU)",
                "agency_ko": "민간 노조 (민주노총 가맹)",
                "agency_en": "Independent labor union (KCTU-affiliated)",
                "target_ko": "이주노동자 (체류자격 무관)",
                "target_en": "Migrant workers (regardless of status)",
                "desc_ko": "노동권·인권 옹호, 노조 가입, 단체교섭 지원. 2007년 대법원 판결로 활동 합법성 확보.",
                "desc_en": "Labor rights advocacy, union membership, collective bargaining support. Legal status confirmed by 2007 Supreme Court ruling.",
                "url": "https://migrants.or.kr",
            },
        ],
    },
    {
        "code": "overseas_korean",
        "label_ko": "재외동포 (한국계 외국인)",
        "label_en": "Overseas Koreans (Korean Diaspora)",
        "definition_ko": "F-4 재외동포 비자 보유자 등 한국계 외국 국적자. 「재외동포의 출입국과 법적 지위에 관한 법률」(재외동포법) 적용. 2023년부터 외교부 산하 재외동포청이 주관.",
        "definition_en": "Foreign nationals of Korean heritage (F-4 visa holders). Per Overseas Korean Act. Since 2023, led by Overseas Koreans Agency under MOFA.",
        "programs": [
            {
                "name_ko": "재외동포청 (OKA)",
                "name_en": "Overseas Koreans Agency (OKA)",
                "agency_ko": "외교부 (2023.6 신설)",
                "agency_en": "MOFA (established June 2023)",
                "target_ko": "재외국민 + 재외동포 (F-4 포함)",
                "target_en": "Overseas Korean nationals + ethnic Korean foreign citizens (incl. F-4)",
                "desc_ko": "정책 총괄 부처. 정착·교육·문화·법률 지원 사업 운영. 인천 송도 본부.",
                "desc_en": "Main policy agency. Coordinates settlement, education, cultural, and legal support programs. HQ in Incheon Songdo.",
                "url": "https://www.oka.go.kr",
            },
            {
                "name_ko": "재외동포 종합지원센터",
                "name_en": "Overseas Korean Comprehensive Support Center",
                "agency_ko": "재외동포청",
                "agency_en": "OKA",
                "target_ko": "국내 거주 재외동포 (F-4·F-5 등)",
                "target_en": "Domestic-residing overseas Koreans (F-4, F-5)",
                "desc_ko": "법률·생활·교육 상담, 한국어 교육, 한국 사회 적응 프로그램. 서울·인천·안산·광주 등 거점 운영.",
                "desc_en": "Legal/daily-life/education counseling, Korean classes, settlement programs. Branches in Seoul, Incheon, Ansan, Gwangju, etc.",
                "url": "https://www.oka.go.kr",
            },
            {
                "name_ko": "한국어교육·정체성 교육 (한글학교)",
                "name_en": "Korean Language & Identity Education (Hangeul Schools)",
                "agency_ko": "재외동포청 / 교육부",
                "agency_en": "OKA / Ministry of Education",
                "target_ko": "재외동포 자녀 (해외 한글학교 및 국내 거주)",
                "target_en": "Children of overseas Koreans (overseas Hangeul schools + domestic)",
                "desc_ko": "해외 1,500여 한글학교 + 국내 동포자녀 한국어·문화 교육 지원. 교재·교사·운영비 보조.",
                "desc_en": "1,500+ overseas Hangeul schools + domestic programs. Curriculum, teacher, and operating-cost subsidies.",
                "url": "https://www.oka.go.kr",
            },
            {
                "name_ko": "재외동포 모국방문 사업",
                "name_en": "Heritage Visit Program for Overseas Koreans",
                "agency_ko": "재외동포청",
                "agency_en": "OKA",
                "target_ko": "해외 한국계 청년·학생",
                "target_en": "Overseas Korean youth/students",
                "desc_ko": "한국 단기 방문 + 정체성 교육 + 모국 체험. 매년 약 2,000명 대상.",
                "desc_en": "Short-term Korea visit + identity education + heritage experience. ~2,000 annually.",
                "url": "https://www.oka.go.kr",
            },
            {
                "name_ko": "재외동포 통합지원포털",
                "name_en": "Overseas Korean Integrated Support Portal",
                "agency_ko": "재외동포청",
                "agency_en": "OKA",
                "target_ko": "재외국민·재외동포 전체",
                "target_en": "All overseas Korean nationals and ethnic Koreans abroad",
                "desc_ko": "비자·여권·국적·납세·교육·복지 안내. 다국어 (한국어·영어·러시아어·중국어).",
                "desc_en": "Visa, passport, nationality, tax, education, welfare info. Multilingual (Korean, English, Russian, Chinese).",
                "url": "https://www.oka.go.kr",
            },
        ],
    },
    {
        "code": "marriage",
        "label_ko": "결혼이민자 · 다문화가족",
        "label_en": "Marriage Migrants & Multicultural Families",
        "definition_ko": "F-6 결혼이민자, 그 자녀, 한국인 배우자 등 다문화가족 구성원. 「다문화가족지원법」(2008) 근거.",
        "definition_en": "F-6 marriage immigrants, their children, and Korean spouses. Statutory basis: Multicultural Families Support Act (2008).",
        "programs": [
            {
                "name_ko": "가족센터 (구 다문화가족지원센터)",
                "name_en": "Family Centers (formerly Multicultural Family Support Centers)",
                "agency_ko": "여성가족부",
                "agency_en": "Ministry of Gender Equality & Family",
                "target_ko": "결혼이민자 가족",
                "target_en": "Marriage-migrant families",
                "desc_ko": "전국 228개소. 한국어교육, 통번역, 부부·가족상담, 자녀양육·학습지원, 방문서비스.",
                "desc_en": "228 centers nationwide. Korean language classes, translation/interpretation, couple/family counseling, child-rearing support, home visits.",
                "url": "https://www.familynet.or.kr",
            },
            {
                "name_ko": "다누리콜센터 (1577-1366)",
                "name_en": "Danuri Helpline (1577-1366)",
                "agency_ko": "여성가족부",
                "agency_en": "Ministry of Gender Equality & Family",
                "target_ko": "결혼이민자·이주여성",
                "target_en": "Marriage migrants and migrant women",
                "desc_ko": "13개 언어 365일 상담 (한국어/영어/베트남어/중국어/필리핀어/캄보디아어/몽골어/러시아어/일본어/태국어/우즈벡어/네팔어/라오스어). 가정폭력·성폭력·생활고충.",
                "desc_en": "13-language 24/7 hotline for marriage migrants and migrant women: domestic/sexual violence, life support.",
                "url": "https://www.liveinkorea.kr/center/page/contents.do?menuSeq=180",
            },
            {
                "name_ko": "결혼이민자 통번역서비스",
                "name_en": "Marriage Migrant Translation/Interpretation Service",
                "agency_ko": "여성가족부",
                "agency_en": "MOGEF",
                "target_ko": "결혼이민자 (한국어 미숙자)",
                "target_en": "Marriage migrants with limited Korean",
                "desc_ko": "지역 가족센터 배치 통번역사. 의료기관·관공서·학교 방문 지원.",
                "desc_en": "Translators stationed at local Family Centers supporting hospital, government, school visits.",
                "url": "https://www.familynet.or.kr",
            },
            {
                "name_ko": "다문화가족 자녀 언어발달지원",
                "name_en": "Language Development Support for Multicultural Children",
                "agency_ko": "여성가족부",
                "agency_en": "MOGEF",
                "target_ko": "다문화가족 자녀 (만 12세 이하)",
                "target_en": "Multicultural family children (≤12)",
                "desc_ko": "언어평가, 1:1 언어교육, 부모 코칭. 가족센터에서 운영.",
                "desc_en": "Language assessment, 1:1 instruction, parent coaching at Family Centers.",
                "url": "https://www.familynet.or.kr",
            },
        ],
    },
    {
        "code": "migrant_women",
        "label_ko": "이주여성 (폭력피해 중심)",
        "label_en": "Migrant Women (incl. Violence Survivors)",
        "definition_ko": "결혼이민·근로·유학·난민 등 다양한 경로로 입국한 이주여성. 특히 가정폭력·성폭력 피해자 보호에 초점.",
        "definition_en": "Migrant women across all entry pathways (marriage, work, study, refugee), with emphasis on protecting victims of domestic and sexual violence.",
        "programs": [
            {
                "name_ko": "여성긴급전화 1366",
                "name_en": "Women's Emergency Hotline 1366",
                "agency_ko": "여성가족부",
                "agency_en": "MOGEF",
                "target_ko": "가정폭력·성폭력·성매매 피해 여성 (외국인 포함)",
                "target_en": "Women victims of domestic / sexual violence / trafficking (incl. foreigners)",
                "desc_ko": "24시간 365일. 다국어 연결은 1577-1366으로 자동 라우팅.",
                "desc_en": "24/7. Multilingual cases routed to 1577-1366.",
                "url": "https://www.mogef.go.kr",
            },
            {
                "name_ko": "폭력피해 이주여성 보호시설 (쉼터)",
                "name_en": "Shelters for Migrant Women Victims of Violence",
                "agency_ko": "여성가족부",
                "agency_en": "MOGEF",
                "target_ko": "폭력 피해 이주여성 + 자녀",
                "target_en": "Migrant women survivors and their children",
                "desc_ko": "전국 약 28개소 (쉼터 + 그룹홈 + 자활지원시설). 임시 보호 + 의료·법률·심리상담 + 자립지원.",
                "desc_en": "~28 facilities (shelters, group homes, self-reliance centers). Temporary protection, medical/legal/psychological support, self-sufficiency programs.",
                "url": "https://www.mogef.go.kr",
            },
            {
                "name_ko": "한국이주여성인권센터",
                "name_en": "Korean Center for Migrant Women's Rights",
                "agency_ko": "민간 NGO (여가부 지원)",
                "agency_en": "Civil-society NGO (MOGEF-funded)",
                "target_ko": "이주여성 전반",
                "target_en": "Migrant women",
                "desc_ko": "법률·노동·체류상담, 정책 옹호활동. 지역별 이주여성쉼터·상담소 연결.",
                "desc_en": "Legal/labor/visa counseling and policy advocacy. Network of regional shelters and counseling centers.",
                "url": "http://www.wmigrant.org",
            },
        ],
    },
    {
        "code": "refugee",
        "label_ko": "난민",
        "label_en": "Refugees",
        "definition_ko": "「난민법」(2013년 시행) 상 난민 신청자, 인정자, 인도적체류허가자. 법무부 출입국·외국인청 난민과 주관.",
        "definition_en": "Persons under the Refugee Act (2013): applicants, recognized refugees, humanitarian-permit holders. Led by MOJ KIS Refugee Division.",
        "programs": [
            {
                "name_ko": "출입국·외국인지원센터 (영종도)",
                "name_en": "Immigration Reception Center (Yeongjong)",
                "agency_ko": "법무부",
                "agency_en": "Ministry of Justice",
                "target_ko": "난민신청자 (입국 초기, 자력 정착 곤란자)",
                "target_en": "Refugee applicants with limited resources upon arrival",
                "desc_ko": "전국 1개소, 90명 수용. 의식주, 한국어교육, 의료, 사회적응 지원 (최대 6개월).",
                "desc_en": "Single facility (90 beds). Food/lodging, Korean instruction, healthcare, social orientation for up to 6 months.",
                "url": "https://www.immigration.go.kr",
            },
            {
                "name_ko": "난민인권센터 (NANCEN)",
                "name_en": "Refugee Rights Center (NANCEN)",
                "agency_ko": "민간 NGO",
                "agency_en": "Civil-society NGO",
                "target_ko": "난민신청자·인정자",
                "target_en": "Refugee applicants and recognized refugees",
                "desc_ko": "법률·생활상담, 통역, 정책 옹호. 서울 기반.",
                "desc_en": "Legal aid, daily-life support, interpretation, policy advocacy. Seoul-based.",
                "url": "https://nancen.org",
            },
            {
                "name_ko": "피난처",
                "name_en": "PNAN (Refuge p'Nan)",
                "agency_ko": "민간 NGO",
                "agency_en": "Civil-society NGO",
                "target_ko": "난민신청자, 강제송환 위험자",
                "target_en": "Refugee applicants, those at risk of refoulement",
                "desc_ko": "긴급쉼터, 법률지원, 한국어교실, 자녀 학습지원.",
                "desc_en": "Emergency shelter, legal support, Korean classes, child education support.",
                "url": "https://www.pnan.org",
            },
            {
                "name_ko": "UNHCR 한국대표부",
                "name_en": "UNHCR Korea",
                "agency_ko": "국제기구",
                "agency_en": "International organization",
                "target_ko": "한국 내 난민·무국적자",
                "target_en": "Refugees and stateless persons in Korea",
                "desc_ko": "재정착프로그램 자문, 정책 모니터링, 인식제고 활동.",
                "desc_en": "Resettlement program advisory, policy monitoring, awareness raising.",
                "url": "https://www.unhcr.org/kr",
            },
        ],
    },
    {
        "code": "defector",
        "label_ko": "북한이탈주민 (탈북민)",
        "label_en": "North Korean Defectors",
        "definition_ko": "「북한이탈주민의 보호 및 정착지원에 관한 법률」(1997) 적용 대상. 헌법상 대한민국 국민. 통일부 주관 (법무부 아님).",
        "definition_en": "Persons covered by the Protection & Settlement Support Act (1997). Recognized as ROK citizens under the Constitution. Led by Ministry of Unification (not MOJ).",
        "programs": [
            {
                "name_ko": "하나원 (북한이탈주민정착지원사무소)",
                "name_en": "Hanawon (Settlement Support Center)",
                "agency_ko": "통일부",
                "agency_en": "Ministry of Unification",
                "target_ko": "보호결정 받은 탈북민 전원",
                "target_en": "All protected defectors",
                "desc_ko": "12주 사회적응교육 (남한 사회, 직업훈련, 심리치료). 경기 안성 + 강원 화천 분원.",
                "desc_en": "12-week orientation (South Korean society, vocational training, psychological care). Anseong main + Hwacheon branch.",
                "url": "https://www.unikorea.go.kr",
            },
            {
                "name_ko": "남북하나재단 (북한이탈주민지원재단)",
                "name_en": "Korea Hana Foundation",
                "agency_ko": "통일부 산하 공공기관",
                "agency_en": "MOU-affiliated public institution",
                "target_ko": "정착 이후 탈북민",
                "target_en": "Defectors post-Hanawon",
                "desc_ko": "취업·교육·의료·심리·자녀지원. 전국 25개 하나센터(지역적응센터) 운영.",
                "desc_en": "Employment, education, health, psychological, and child support. Runs 25 regional Hana Centers nationwide.",
                "url": "https://www.koreahana.or.kr",
            },
            {
                "name_ko": "정착기본금 + 가산금",
                "name_en": "Settlement Basic Funds + Bonuses",
                "agency_ko": "통일부",
                "agency_en": "MOU",
                "target_ko": "보호결정 탈북민",
                "target_en": "Protected defectors",
                "desc_ko": "1인 기본금 1,000만원 + 직업훈련/취업/자격증 등 가산금 (최대 약 2,500만원).",
                "desc_en": "KRW 10M base + bonuses for training/employment/certification (up to ~KRW 25M).",
                "url": "https://www.unikorea.go.kr",
            },
            {
                "name_ko": "임대주택 + 주거지원금",
                "name_en": "Public Housing + Housing Allowance",
                "agency_ko": "통일부 / LH",
                "agency_en": "MOU / Korea Land & Housing Corp",
                "target_ko": "보호결정 탈북민",
                "target_en": "Protected defectors",
                "desc_ko": "공공임대주택 우선 배정 + 주거지원금 1,600만원 (1인기준).",
                "desc_en": "Priority public-housing allocation + KRW 16M housing allowance (single).",
                "url": "https://www.unikorea.go.kr",
            },
        ],
    },
    {
        "code": "student",
        "label_ko": "유학생 (외국인 학생)",
        "label_en": "International Students",
        "definition_ko": "D-2 (대학·대학원 유학), D-4 (어학연수) 비자 보유자. 교육부·각 대학 주관.",
        "definition_en": "Holders of D-2 (degree program) and D-4 (language training) visas. Led by Ministry of Education and individual universities.",
        "programs": [
            {
                "name_ko": "정부초청 외국인장학생 (GKS)",
                "name_en": "Global Korea Scholarship (GKS)",
                "agency_ko": "교육부 / NIIED",
                "agency_en": "Ministry of Education / NIIED",
                "target_ko": "외국인 학부·대학원 유학생 (약 150개국 대상)",
                "target_en": "International undergraduate/graduate students (~150 countries)",
                "desc_ko": "등록금·생활비·왕복항공·한국어 1년 어학연수 풀 패키지. 연간 약 1,200명 선발.",
                "desc_en": "Full package: tuition, stipend, round-trip airfare, 1-year Korean training. ~1,200 selected annually.",
                "url": "https://www.studyinkorea.go.kr",
            },
            {
                "name_ko": "Study in Korea 포털",
                "name_en": "Study in Korea Portal",
                "agency_ko": "교육부 / NIIED",
                "agency_en": "Ministry of Education / NIIED",
                "target_ko": "유학 희망 외국인",
                "target_en": "Prospective international students",
                "desc_ko": "대학·전공 검색, 장학금, 비자, 한국 생활 정보. 영어·중국어·베트남어 등 다국어.",
                "desc_en": "University/major search, scholarships, visa info, life-in-Korea info. Multilingual (English, Chinese, Vietnamese, etc.).",
                "url": "https://www.studyinkorea.go.kr",
            },
            {
                "name_ko": "한국어능력시험 (TOPIK)",
                "name_en": "Test of Proficiency in Korean (TOPIK)",
                "agency_ko": "교육부 / NIIED",
                "agency_en": "Ministry of Education / NIIED",
                "target_ko": "한국어 학습자, 대학 입학 지원자, 영주·귀화 신청자",
                "target_en": "Korean learners, university applicants, residence/naturalization candidates",
                "desc_ko": "공식 한국어 능력 평가. 대학 입학·취업·체류자격 변경의 기준.",
                "desc_en": "Official Korean proficiency assessment used for university admission, employment, and visa change.",
                "url": "https://www.topik.go.kr",
            },
            {
                "name_ko": "각 대학 국제처 (OIA)",
                "name_en": "University Offices of International Affairs (OIA)",
                "agency_ko": "각 대학",
                "agency_en": "Individual universities",
                "target_ko": "재학 외국인 학생",
                "target_en": "Enrolled international students",
                "desc_ko": "비자 자문, 한국어 프로그램, 멘토링, 한국문화 행사, 인턴십 연계.",
                "desc_en": "Visa advising, Korean language programs, mentorship, cultural events, internship coordination.",
                "url": "https://www.studyinkorea.go.kr",
            },
        ],
    },
]


VISA_INFO_SOURCES = [
    {"label_ko": "법무부 출입국·외국인정책본부 비자 네비게이터",
     "label_en": "MOJ Visa Navigator (Korea Immigration Service)",
     "url": "https://www.immigration.go.kr/bbs/immigration/229/454083/artclView.do"},
    {"label_ko": "HiKorea 비자 안내",
     "label_en": "HiKorea Visa Guide",
     "url": "https://www.hikorea.go.kr/"},
    {"label_ko": "외교부 비자포털",
     "label_en": "MOFA Visa Portal",
     "url": "https://www.visa.go.kr/"},
    {"label_ko": "찾기쉬운 생활법령정보 (법제처)",
     "label_en": "Easy-to-find Living-Law Info (Korea Legislation Research Institute)",
     "url": "https://easylaw.go.kr/"},
    {"label_ko": "출입국관리법 시행령 별표 1·1의2 (체류자격 일람)",
     "label_en": "Immigration Control Act Enforcement Decree Annex 1 (full visa status list)",
     "url": "https://www.law.go.kr/lsSc.do?menuId=1&subMenuId=15&tabMenuId=81&query=출입국관리법시행령"},
]


def export_json(stay_long, reg_long, out_path):
    years = sorted(set(stay_long["year"]).union(reg_long["year"]))
    # Build ko→en country map from legacy bilingual files + manual overrides
    country_en = extract_country_en_map()
    country_en.update(COUNTRY_EN_OVERRIDES)  # overrides win
    # Limit to countries that actually appear in our data
    all_countries = set(stay_long["country"].unique()) | set(reg_long["country"].unique())
    country_en = {k: v for k, v in country_en.items() if k in all_countries}
    missing = [c for c in all_countries if c not in country_en]
    if missing:
        print(f"  (no EN translation for {len(missing)}: {sorted(missing)[:8]}...)")

    # Visa label EN map (codes → English KIS label)
    VISA_LABEL_EN = {
        "A1": "Diplomatic", "A2": "Official Mission", "A3": "Treaty",
        "B1": "Visa Exemption", "B2": "Tourist Transit",
        "C1": "Temporary Coverage", "C3": "Short-term Visit", "C4": "Short-term Employment",
        "D1": "Culture & Arts", "D2": "Student", "D3": "Industrial Trainee",
        "D4": "General Trainee", "D5": "Journalism", "D6": "Religious Worker",
        "D7": "Intra-company Transferee", "D8": "Corporate Investment",
        "D9": "Trade Management", "D10": "Job Seeker",
        "E1": "Professor", "E2": "Foreign Language Instructor", "E3": "Researcher",
        "E4": "Technical Instructor", "E5": "Specialized Occupation",
        "E6": "Arts & Entertainment", "E7": "Specially Designated Activities",
        "E8": "Seasonal Worker", "E9": "Non-professional Employment",
        "E10": "Crew Employment",
        "F1": "Visiting Cohabitation", "F2": "Residential", "F3": "Dependent Family",
        "F4": "Overseas Korean", "F5": "Permanent Residence", "F6": "Marriage Migration",
        "G1": "Other (Miscellaneous)",
        "H1": "Working Holiday", "H2": "Visiting Employment",
        "T1": "Tourist Landing",
        "ETC": "Unclassified (SOFA · Treaty)",
        "E0": "Treaty Activity",
    }

    VISA_FAMILY_LABELS_EN = {
        "A": "A · Diplomatic & Official",
        "B": "B · Visa Exemption & Transit",
        "C": "C · Short-term Stay",
        "D": "D · Long-term General (Student, Investment, Religion)",
        "E": "E · Employment (Professional & Non-professional)",
        "F": "F · Settlement & Family (Permanent, Marriage, Overseas Korean)",
        "G": "G · Other Visas",
        "H": "H · Working Holiday & Visiting Employment",
        "T": "T · Tourist Landing",
        "X": "Other (Unclassified)",
    }

    def build_visa_options_i18n(long_df):
        label_map = (
            long_df.drop_duplicates("visa_code")
            .set_index("visa_code")["visa_label"]
            .to_dict()
        )
        families_present = sorted(set(long_df["visa_code"].apply(visa_family)))
        individual_codes = sorted(long_df["visa_code"].unique())

        options = [{
            "value": "ALL",
            "label_ko": "전체 (총합계)",
            "label_en": "All (Total)",
            "group_ko": "전체", "group_en": "All",
        }]
        for fam in families_present:
            options.append({
                "value": f"FAM_{fam}",
                "label_ko": VISA_FAMILY_LABELS.get(fam, f"{fam}계"),
                "label_en": VISA_FAMILY_LABELS_EN.get(fam, f"{fam}-series"),
                "group_ko": "그룹", "group_en": "Group",
            })
        for c in individual_codes:
            ko = label_map.get(c, c)
            en = VISA_LABEL_EN.get(c, c)
            options.append({
                "value": c,
                "label_ko": f"{c} · {ko}",
                "label_en": f"{c} · {en}",
                "group_ko": "개별", "group_en": "Individual",
            })
        return options

    data = {
        "years": [int(y) for y in years],
        "populations": {
            "stay": {
                "label_ko": "체류외국인 (전체)",
                "label_en": "Foreign Residents (All)",
                "description_ko": "등록(장기) + 단기체류 합계. 관광·단기방문 포함.",
                "description_en": "Registered (long-term) + short-term stays. Includes tourists & short visits.",
                "visa_options": build_visa_options_i18n(stay_long),
                "data": long_to_pop_dict(stay_long),
            },
            "reg": {
                "label_ko": "등록외국인 (장기)",
                "label_en": "Registered Foreigners (Long-term)",
                "description_ko": "90일 초과 장기체류 등록자 (D·E·F 비자 중심).",
                "description_en": "Long-term residents staying over 90 days (primarily D/E/F visas).",
                "visa_options": build_visa_options_i18n(reg_long),
                "data": long_to_pop_dict(reg_long),
            },
        },
        "country_en": country_en,
        "source_ko": "법무부 출입국·외국인정책 통계연보 (2006–2025)",
        "source_en": "Korea Immigration Service Statistical Yearbook (2006–2025)",
        "visa_info": {
            code: {
                "code": code,
                "code_display": code[0] + "-" + code[1:] if len(code) > 1 and code[1].isdigit() else code,
                "family": visa_family(code),
                "name_ko": CANONICAL_LABELS_KO.get(code, code),
                "name_en": VISA_LABEL_EN.get(code, code),
                **info,
            }
            for code, info in VISA_INFO.items()
        },
        "visa_info_sources": VISA_INFO_SOURCES,
        "refugee_data": REFUGEE_DATA,
        "refugee_sources": REFUGEE_SOURCES,
        "defector_data": DEFECTOR_DATA,
        "defector_sources": DEFECTOR_SOURCES,
        "naturalization_data": load_naturalization(),
        "naturalization_sources": NATURALIZATION_SOURCES,
        "support_systems": SUPPORT_SYSTEMS,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"✅ data.json saved: {out_path} ({size_kb:,.0f} KB)")


print("\nLoading 시군구별 등록외국인 (2014~2025)...")
region_long = build_region_long(REGION_COUNTRY_FILES)
region_long.to_csv(os.path.join(OUT_DATA, "region_long.csv"), index=False, encoding="utf-8-sig")
print(f"  rows={len(region_long):,}  sidos={region_long['sido'].nunique() if len(region_long) else 0}  "
      f"sigungus={region_long['sigungu'].nunique() if len(region_long) else 0}")

print("\nLoading 주민등록인구 (denominator)...")
pop_long = build_population_long()
pop_long.to_csv(os.path.join(OUT_DATA, "population_long.csv"), index=False, encoding="utf-8-sig")
print(f"  rows={len(pop_long):,}  sigungus={pop_long['sigungu'].nunique() if len(pop_long) else 0}  "
      f"years={pop_long['year'].nunique() if len(pop_long) else 0}")

print("\nComputing segregation/diversity indices (Shannon H, HHI, LQ, D)...")
indices_data = compute_indices(region_long, pop_long)
print(f"  years covered: {indices_data.get('years', [])}")

print("\nLoading 연령별 체류외국인 (2014~2025)...")
age_long = build_age_long(AGE_FILES)
age_long.to_csv(os.path.join(OUT_DATA, "age_long.csv"), index=False, encoding="utf-8-sig")
print(f"  rows={len(age_long):,}  countries={age_long['country'].nunique() if len(age_long) else 0}  "
      f"age groups={age_long['age_group'].nunique() if len(age_long) else 0}")


def export_region_age_json(region_df, age_df, out_dir):
    # Region: {year: {sido: {sigungu: {country: n}}}}
    region_out = {}
    if len(region_df):
        for yr, yg in region_df.groupby("year"):
            region_out[str(int(yr))] = {}
            for sido, sg in yg.groupby("sido"):
                region_out[str(int(yr))][sido] = {}
                for sigungu, ig in sg.groupby("sigungu"):
                    region_out[str(int(yr))][sido][sigungu] = dict(
                        zip(ig["country"], ig["n"].astype(int))
                    )
    # Sido-level totals (sum over sigungu) for quick lookup
    region_sido_total = {}
    if len(region_df):
        sido_agg = (
            region_df[region_df["sigungu"].isin({"총계", "총합계"})]
            .groupby(["year", "sido", "country"], as_index=False)["n"].sum()
        )
        for yr, yg in sido_agg.groupby("year"):
            region_sido_total[str(int(yr))] = {}
            for sido, sg in yg.groupby("sido"):
                region_sido_total[str(int(yr))][sido] = dict(
                    zip(sg["country"], sg["n"].astype(int))
                )

    region_path = os.path.join(out_dir, "region.json")
    with open(region_path, "w", encoding="utf-8") as f:
        json.dump({
            "years": sorted(region_df["year"].unique().astype(int).tolist()) if len(region_df) else [],
            "sidos": sorted(region_df["sido"].unique().tolist()) if len(region_df) else [],
            "sido_en": SIDO_EN,
            "sigungu_en": build_sigungu_en(region_df),
            "by_sigungu": region_out,
            "by_sido": region_sido_total,
            "source_ko": "법무부 출입국·외국인정책 통계연보 · 시군구별 등록외국인 (2014~2025)",
            "source_en": "KIS Yearbook · Registered foreigners by sigungu (2014–2025)",
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✅ region.json saved: {region_path} ({os.path.getsize(region_path)/1024:.0f} KB)")

    # Age: {year: {country: {age_group: {gender: n}}}}
    age_out = {}
    if len(age_df):
        for yr, yg in age_df.groupby("year"):
            age_out[str(int(yr))] = {}
            for country, cg in yg.groupby("country"):
                age_out[str(int(yr))][country] = {}
                for age, ag in cg.groupby("age_group"):
                    age_out[str(int(yr))][country][age] = dict(
                        zip(ag["gender"], ag["n"].astype(int))
                    )

    age_path = os.path.join(out_dir, "age.json")
    with open(age_path, "w", encoding="utf-8") as f:
        # Sort age groups by starting age
        def sort_key(a):
            if a.endswith("+"):
                return int(a[:-1])
            return int(a.split("-")[0])
        all_ages = sorted(age_df["age_group"].unique().tolist(), key=sort_key) if len(age_df) else []
        json.dump({
            "years": sorted(age_df["year"].unique().astype(int).tolist()) if len(age_df) else [],
            "age_groups": all_ages,
            "data": age_out,
            "source_ko": "법무부 출입국·외국인정책 통계연보 · 국적 및 연령별 체류외국인 (2014~2025)",
            "source_en": "KIS Yearbook · Foreign residents by nationality and age (2014–2025)",
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✅ age.json saved: {age_path} ({os.path.getsize(age_path)/1024:.0f} KB)")


print("\nExporting data.json for static site...")
export_json(stay_long, reg_long, os.path.join(OUT_SITE_DATA, "data.json"))
print("\nExporting region.json + age.json...")
export_region_age_json(region_long, age_long, OUT_SITE_DATA)

# Indices JSON
indices_path = os.path.join(OUT_SITE_DATA, "indices.json")
with open(indices_path, "w", encoding="utf-8") as f:
    json.dump({
        "data": indices_data,
        "sources": [
            {"label_ko": "법무부 출입국·외국인정책 통계연보 (외국인 분자)",
             "label_en": "MOJ KIS Yearbook (foreign-population numerator)",
             "url": "https://www.moj.go.kr"},
            {"label_ko": "행정안전부 주민등록 인구통계 (총인구 분모)",
             "label_en": "MOIS Resident Registration Statistics (total-population denominator)",
             "url": "https://jumin.mois.go.kr"},
        ],
        "methodology": {
            "ko": [
                "외국인 비율 (%) = 등록외국인 / 주민등록 총인구. 가장 직관적 지표.",
                "Shannon Diversity (H, 외국인만) = -Σ p_i × ln(p_i), where p_i = 외국인 중 국적 i의 점유율. 외국인 내부 국적 다양성.",
                "Shannon Diversity (H, 한국인 포함) = 한국인을 한 그룹, 각 외국 국적을 각각의 그룹으로 두고 계산. 전체 인구 ethnic 다양성 (한국인이 압도적이라 값은 작지만 상대 ranking 의미 있음).",
                "HHI (Herfindahl-Hirschman) = Σ p_i². 1에 가까울수록 단일 국적 집중.",
                "체감 인종다양성 (대륙 단위 H) = 국적을 대륙(동아시아·동남아 등)으로 묶고 한국인을 동아시아에 포함해 계산한 Shannon H. 동아시아끼리는 외형이 비슷하므로 다른 대륙이 섞일수록 높음 (예: 한국계중국인 밀집지는 외국인 많아도 체감 다양성 낮음).",
                "Location Quotient (LQ) = (해당 시군구 점유율) / (전국 점유율). LQ≥1.5 = 과대표집.",
                "Index of Dissimilarity (D, Massey & Denton 1988) = 0.5 × Σ |x_i/X - y_i/Y|. 한국인 대비 분포 차이(균등 차원). 0=균등, 1=완전분리.",
                "고립지수(Isolation) = Σ (x_i/X)(x_i/t_i): 그 국적 평균 구성원이 같은 국적과 만날 확률(노출 차원). 한국인 상호작용지수 = Σ (x_i/X)(한국인_i/t_i).",
                "Theil 다집단 분리지수(H, Reardon & Firebaugh 2002) = Σ t_i(E−E_i)/(T·E): 한국인+각 국적의 시군구별 구성이 전국 구성과 얼마나 다른가. 0=완전균등, 1=완전분리.",
                "Moran's I (공간군집 차원) = 외국인 비율의 시군구 간 공간 자기상관 (queen 인접). >0이면 외국인 많은 시군구끼리 인접해 뭉침.",
                "출신 지역별 분리: 국적을 대륙·지역(동아시아·동남아·남아시아·중앙아시아·서아시아·유럽·북미·중남미·아프리카·오세아니아)으로 묶어 그룹별 D·고립지수 계산.",
                "한국인 인구 = 주민등록 총인구 - 등록외국인. 분모 100명 미만 국적 또는 외국인 1,000명 미만 시군구는 노이즈로 제외.",
                "Ethnic Enclave = LQ ≥ 2 (전국 대비 2배 밀집) AND 그 시군구 외국인의 30% 이상이 단일 국적 (Wilson & Portes 1980; Logan, Zhang & Alba 2002). 절대 200명 미만 제외.",
            ],
            "en": [
                "Foreign share (%) = registered foreigners / MOIS total residents. Most intuitive measure.",
                "Shannon Diversity (H, foreigners only) = -Σ p_i × ln(p_i) where p_i = nationality i's share among foreigners. Within-foreign diversity.",
                "Shannon Diversity (H, incl. Koreans) = treat Koreans as one group and each foreign nationality as a separate group. Overall ethnic diversity of residents (low absolute values since Koreans dominate, but relative ranking is informative).",
                "HHI (Herfindahl-Hirschman) = Σ p_i². Closer to 1 = single-nationality concentration.",
                "Visible (continent-level) diversity = Shannon H over world regions (East/Southeast/South Asia, etc.) with Koreans counted as East Asian. East-Asian groups look similar, so the index rises when other-continent groups are present (a Korean-Chinese cluster can have many foreigners yet low visible diversity).",
                "Location Quotient (LQ) = (sigungu share) / (national share). LQ ≥ 1.5 = overrepresented.",
                "Index of Dissimilarity (D, Massey & Denton 1988) = 0.5 × Σ |x_i/X - y_i/Y|. Compared to Koreans (evenness dimension). 0 = even, 1 = total segregation.",
                "Isolation index = Σ (x_i/X)(x_i/t_i): probability the average member of a nationality shares a district with own group (exposure dimension). Korean interaction = Σ (x_i/X)(korean_i/t_i).",
                "Theil multigroup segregation index (H, Reardon & Firebaugh 2002) = Σ t_i(E−E_i)/(T·E): how much each district's composition (Koreans + each nationality) departs from the national mix. 0 = even, 1 = complete segregation.",
                "Moran's I (clustering dimension) = spatial autocorrelation of the foreign share across districts (queen contiguity). >0 = high-share districts adjoin one another.",
                "Region-of-origin segregation: nationalities grouped into world regions (East/Southeast/South/Central/West Asia, Europe, North America, Latin America, Africa, Oceania); dissimilarity and isolation computed per region.",
                "Korean reference population = MOIS total residents - registered foreigners. Nationalities under 100 or sigungus under 1,000 foreigners excluded as noise.",
                "Ethnic Enclave = LQ ≥ 2 (2x overrepresented vs nation) AND one nationality ≥ 30% of the sigungu's foreign population (Wilson & Portes 1980; Logan, Zhang & Alba 2002). Excludes groups under 200.",
            ],
            "citations": [
                "Massey, D. S., & Denton, N. A. (1988). The dimensions of residential segregation. Social Forces, 67(2), 281-315.",
                "Reardon, S. F., & Firebaugh, G. (2002). Measures of multigroup segregation. Sociological Methodology, 32(1), 33-67.",
                "Shannon, C. E. (1948). A mathematical theory of communication. Bell System Technical Journal, 27(3), 379-423.",
                "Wilson, K. L., & Portes, A. (1980). Immigrant enclaves: An analysis of the labor market experiences of Cubans in Miami. American Journal of Sociology, 86(2), 295-319.",
                "Logan, J. R., Zhang, W., & Alba, R. D. (2002). Immigrant enclaves and ethnic communities in New York and Los Angeles. American Sociological Review, 67(2), 299-322.",
            ],
        },
    }, f, ensure_ascii=False, separators=(",", ":"))
print(f"✅ indices.json saved: {indices_path} ({os.path.getsize(indices_path)/1024:.0f} KB)")
print(f"✅ Source CSVs: {OUT_DATA}/stay_long.csv, reg_long.csv")
print(f"\nNext: copy site/index.html (already in repo) and deploy to Vercel.")
