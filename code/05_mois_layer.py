"""The MOIS layer, end to end: the raw 행정안전부 files parsed, then the layer built on them.

행정안전부 「지방자치단체 외국인주민 현황」 counts a broader population than MOJ: it
adds naturalized residents and the Korean-born children of foreign residents, and it
reaches one administrative level further down, to 읍면동. This step owns all of it,
from the raw Excel editions in 01_raw_data/행정안전부 외국인주민통계/ to the released
CSV and Parquet in 04_dataset_release/mois/.

Two entry points, and only the second one runs in the pipeline:

    python 02_code/05_mois_layer.py --reparse   # raw Excel -> 03_cleaned_data/mois_*.csv
    python 02_code/05_mois_layer.py             # those CSVs -> the layer, then the release

The re-parse is separate because it reads nineteen editions of a survey that is
published once a year and never revised, so its output changes only when a new
edition arrives. `run_pipeline.py` runs the second form.

## The re-parse, in order (--reparse)

Every stage is idempotent, and the order matters only in that the consolidation
stages read what the parsers wrote:

    2006 -> 2007-2010 -> 2011-2013 -> 2014-2015 -> 2016+ -> 국적별 -> 자녀 연령별
    -> 나머지 차원 -> 에폭 통합 -> 주민등록인구 -> 주제별 통합 -> 행정구역코드

`parse_seoul_dong_files()` sits outside that sequence. It reads a Seoul open-data CSV
that has to be downloaded by hand, and nothing downstream depends on it.

## The layer, in order (default)

    canonicalize_eupmyeondong_names -> region_keys_and_validation -> build_layer
    -> sejong_patches -> package_for_release

## 산출물 (03_cleaned_data/)

The parsers write one CSV per source shape; `build_tidy_tables()` then folds those
into the seven tidy thematic tables the dashboard and the release actually read, and
moves the fragments to `03_cleaned_data/_mois_archive/`.

| 파일 | 차원 | 연도 | 행 수 |
|---|---|---|---|
| `mois_sido.csv` | 시도 × 외국인주민 카테고리 × 성별 | 2006-2024 | 10,004 |
| `mois_sigungu.csv` | 시군구 × 카테고리 × 성별 | 2006-2024 | 143,785 |
| `mois_eupmyeondong.csv` | 읍면동 × 카테고리 | 2014-2024 | 549,355 |
| `mois_multicultural_eupmyeondong.csv` | 다문화가구원 × 읍면동 × 가구원유형 | 2016-2024 | 298,049 |
| `mois_nationality_sigungu.csv` | 시군구 × 국적별 × 성별 | 2009-2024 | 257,709 |
| `mois_nationality_eupmyeondong.csv` | 읍면동 × 국적별 × 성별 | 2014-2015 | 380,322 |
| `mois_nationality_by_visa_sigungu.csv` | 시군구 × 비자유형 × 국적별 × 성별 | 2009-2024 | 825,948 |
| `mois_nationality_by_visa_eupmyeondong.csv` | 읍면동 × 비자유형 × 국적별 | 2014-2015 | 1,779,084 |
| `mois_nationality_naturalized_sigungu.csv` | 시군구 × 귀화자 국적 × 성별 | 2014-2015 | 24,678 |
| `mois_nationality_naturalized_eupmyeondong.csv` | 읍면동 × 귀화자 국적 | 2014-2015 | 379,404 |
| `mois_nationality_children_sigungu.csv` | 시군구 × 자녀 국적 × 성별 | 2014-2015 | 24,678 |
| `mois_nationality_children_eupmyeondong.csv` | 읍면동 × 자녀 국적 | 2014-2015 | 380,052 |
| `mois_children_age_sido.csv` | 시도 × 자녀 연령(0-18세) × 성별 | 2014-2024 | 10,651 |
| `mois_children_age_sigungu.csv` | 시군구 × 자녀 연령 × 성별 | 2011-2024 | 189,664 |
| `mois_children_parent_type_eupmyeondong.csv` | 읍면동 × 부모유형 × 국적 | 2014-2015 | 986,256 |
| `mois_children_parent_type_sigungu.csv` | 시군구 × 자녀유형(귀화·인지/국내출생) | 2016-2024 | 14,306 |
| `mois_residence_period_sigungu.csv` | 시군구 × 체류기간 × 성별 | 2016-2024 | 31,626 |
| `mois_naturalized_prev_nationality_sigungu.csv` | 시군구 × 귀화자 이전국적 × 성별 | 2016-2024 | 44,617 |
| `mois_naturalization_period_sigungu.csv` | 시군구 × 국적취득경과기간 | 2016-2024 | 15,710 |
| `mois_household_eupmyeondong.csv` | 읍면동 × 외국인주민 세대수 | 2014-2015 | 7,048 |
| `mois_coverage.csv` | (메타) 연도/레벨/카테고리 매트릭스 | — | 49 |
| | | 합계 | ~6.4M |

Long format throughout: `year, sido, sigungu, [eupmyeondong,] [category|country|age|
visa_type|parent_type,] sex, n`.

## MOIS 단독 차원

- 읍면동 × 국적별 (2014-2015), 380K 행. 동 단위 다양성/enclave 지표가 여기서 나온다.
- 읍면동 × 비자유형 × 국적별 (2014-2015), 1.78M 행. 근로자/결혼이민자/유학생 동 단위 분포.
- 읍면동 × 부모유형 × 국적별 (2014-2015), 986K 행. 동 단위 2세대 분포.
- 읍면동 × 귀화자·자녀 국적별 (2014-2015), 759K 행. 읍면동 × 세대수, 7K 행.
- 귀화자(한국국적취득자) × 시군구 × 국적/연도. MOJ 에는 없다.
- 외국인주민 자녀 × 시군구 × 연령(0-18세) × 성별, 2011-2024.
- 자녀 부모유형: 2009-2015 메인 시트, 2016+ 귀화·인지/국내출생.
- 체류기간별(2016-2024), 귀화자 이전국적(2016-2024), 다문화가구원(2016-2024).

| 카테고리 | KIRD (MOJ) | MOIS |
|---|---|---|
| 등록외국인 | 2006-2024 | 2006-2024 |
| 한국국적취득자 | 없음 | 2006-2024 |
| 외국인주민 자녀 | 없음 | 2006-2024 |
| 외국인 × 국적 × 시군구 | 2017+ | 2009-2024 |
| 외국인 × 국적 × 읍면동 | 없음 | 2014-2015 |
| 자녀 × 연령 × 시군구 | 없음 | 2011-2024 |
| 다문화가구원 | 없음 | 2016-2024 |

## 한계

1. 2015->2016 스키마 단절. 2016+ 메인 1-1/1-2/1-3 시트는 합계 수준만 주고, 한국국적취득
   sub 와 자녀 부모유형 sub 가 빠진다. 세부는 별도 시트(6, 7, 8, 9, 10)로 흩어져 있고,
   여기 파서들이 그것을 모두 긁는다.
2. 2014-2015 는 읍면동과 시도시군구가 서로 다른 파일로 배포되어, 파서도 두 파일을 읽는다.
3. `2015_외국인주민통계_인구주택총조사기준.xlsx` 는 같은 해 다른 방법론이라 쓰지 않는다.
   이중계상을 막기 위한 것이고, robustness check 에만 따로 쓸 수 있다.
4. 2024 1-3 시트의 오타(`천찬시동남구` -> `천안시동남구`)는 `fix_known_typos()` 가 잡는다.
5. 결혼이민자 및 국적취득자 연령별(2014-2015 시트 5)은 시도 × 연령 × 혼인이민/귀화
   cross-table 이라 구조가 특수하다. `mois_marriage_age.csv` 로만 떨어뜨리고 더 쓰지 않는다.
6. 읍면동에는 공식 행정동 코드가 없다. `extract_bcnt_codes()` 가 2015 년 보조 파일에서
   7자리 BCNT 를 끌어와 이름으로 붙이는 것이 현재의 최선이고, 매칭 실패는 빈 코드로 남는다.
7. 2016 년부터 MOIS 가 인구주택총조사 기준으로 옮겨 가면서 한국국적미취득자를 MOJ 보다
   30-45% 많이 잡는다. 지역별 격차는 `mois_moj_validation.csv` 에 있다.
8. 2008 년은 시군구 단위가 없어, 시군구 계열은 2009 년부터 시작한다.

Sejong needs patching because the parsers key on 시군구 and Sejong has none, and
because MOIS lists it only from 2013, so 2006-2012 comes from the predecessor
연기군.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import json
import os
import re
import shutil

import pandas as pd

from kird import ROOT


# -- 공통 헬퍼: 경로, 시도 이름, 셀 파싱 ----------------------------------------------------
# Shared helpers for parsing MOIS 외국인주민통계 files (2006-2024).
#
# Output convention:
# - Population data → long CSVs by admin level:
#   - mois_sido.csv:         year, sido, category, sex, n
#   - mois_sigungu.csv:      year, sido, sigungu, category, sex, n
#   - mois_eupmyeondong.csv: year, sido, sigungu, eupmyeondong, category, n
# - Children:
#   - mois_children_sigungu.csv (by parent origin / age group / nationality)
# - Multicultural households (2016+):
#   - mois_multicultural_eupmyeondong.csv

RAW_DIR = Path(ROOT) / "01_raw_data" / "행정안전부 외국인주민통계"
OUT_DIR = Path(ROOT) / "03_cleaned_data"

# 17 시도 (with rename variants 2023-2024)
SIDO_NAMES = {
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시",
    "세종특별자치시", "세종시",
    "경기도",
    "강원도", "강원특별자치도",
    "충청북도", "충청남도",
    "전라북도", "전북특별자치도",
    "전라남도", "경상북도", "경상남도",
    "제주도", "제주특별자치도",
}

SIDO_CANONICAL = {
    "세종시": "세종특별자치시",
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "제주도": "제주특별자치도",
}

# 일반구 by parent 시, every district these twelve cities have carried 2006-2024,
# including the ones since abolished (부천시 2019) and the ones added on a merger
# (청주시 2014, 창원시 2010). Two things read this map:
#
#   1. split_sub_gu, which turns a 시군구 row like '수원시장안구' into the released
#      two-token form '수원시 장안구'.
#   2. strip_gu_prefix, below. The 2014 and 2015 읍면동 sheets print the district in
#      front of the 읍면동 name ('덕양구 고양동'), and clean_region_name glues that to
#      '덕양구고양동'. The district belongs in `sigungu`; left inside `eupmyeondong` it
#      forges a second, value-less copy of every 동 in these cities.
GU_BY_CITY = {
    "고양시": ("덕양구", "일산동구", "일산서구"),
    "부천시": ("소사구", "오정구", "원미구"),
    "성남시": ("분당구", "수정구", "중원구"),
    "수원시": ("권선구", "영통구", "장안구", "팔달구"),
    "안산시": ("단원구", "상록구"),
    "안양시": ("동안구", "만안구"),
    "용인시": ("기흥구", "수지구", "처인구"),
    "전주시": ("덕진구", "완산구"),
    "창원시": ("마산합포구", "마산회원구", "성산구", "의창구", "진해구"),
    "천안시": ("동남구", "서북구"),
    "청주시": ("상당구", "서원구", "청원구", "흥덕구"),
    "포항시": ("남구", "북구"),
}

# 시 with sub-구 (100만 도시 + others with 자치구). Used to split rows like '수원시장안구'.
SUB_GU_PARENTS = frozenset(GU_BY_CITY)

EUPMYEONDONG_SUFFIXES = ("동", "읍", "면", "리", "출장소")
SIGUNGU_SUFFIXES = ("시", "군", "구")


def canon_sido(s: str) -> str:
    s = s.strip().replace("⋅", ".").replace("·", ".").replace("･", ".")
    return SIDO_CANONICAL.get(s, s)


def clean_region_name(s) -> str:
    """Strip whitespace, English suffixes, and normalize bullet chars."""
    if s is None:
        return ""
    s = str(s).strip()
    # Strip bilingual English suffix (e.g., '서울특별시\nSeoul' → '서울특별시')
    if "\n" in s:
        s = s.split("\n")[0].strip()
    s = s.replace(" ", "")
    return s


def fix_known_typos(s: str) -> str:
    fixes = {
        "천찬시동남구": "천안시동남구",
        "천찬시서북구": "천안시서북구",
    }
    return fixes.get(s, s)


def split_sub_gu(name: str):
    """If name like '수원시장안구', return ('수원시', '장안구'). Else None."""
    for parent in SUB_GU_PARENTS:
        if name.startswith(parent) and len(name) > len(parent):
            return parent, name[len(parent):]
    return None


def strip_gu_prefix(name: str, sigungu) -> str:
    """Drop a 일반구 the source printed in front of a 읍면동 name.

    ('덕양구고양동', '고양시')      -> '고양동'      (2014 sheets: 시 only in sigungu)
    ('덕양구고양동', '고양시 덕양구') -> '고양동'      (2015 sheets: 구 in both places)
    ('구서1동', '금정구')           -> '구서1동'     (금정구 is a 자치구, not a 일반구)
    ('북구죽장면상옥출장소', '포항시') -> '죽장면상옥출장소'

    Only a district of the row's own 시 is stripped, and only when what is left is
    still a 읍/면/동/출장소, so a 동 whose own name opens with a 구 syllable is safe.
    """
    if not name or not sigungu:
        return name
    city = str(sigungu).split(" ")[0]
    for gu in sorted(GU_BY_CITY.get(city, ()), key=len, reverse=True):
        if name.startswith(gu) and len(name) > len(gu):
            rest = name[len(gu):]
            if rest.endswith(EUPMYEONDONG_SUFFIXES):
                return rest
    return name


def parse_value(v):
    """Convert a cell to int/None. '*', '-', empty become None (suppressed)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if v != v:  # NaN
            return None
        return int(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "*", "-", "nan", "None", "..", ".", "X"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def classify_row_name(name: str) -> str:
    """Classify a region name as 'national', 'sido', 'sigungu', 'eupmyeondong', or 'other'."""
    if name == "전국":
        return "national"
    if name in SIDO_NAMES:
        return "sido"
    if name.endswith(EUPMYEONDONG_SUFFIXES):
        return "eupmyeondong"
    if name.endswith(SIGUNGU_SUFFIXES):
        return "sigungu"
    return "other"


# -- 2006 (시.도별 / 전국 시트) -------------------------------------------------------
# Parser for 2006 외국인주민통계.
#
# Schema (시.도별 and 전국 sheets):
#   col 0: name
#   col 1: 주민등록인구
#   col 2: 합계 계
#   col 3: 비율 (skip)
#   col 4: 합계 남
#   col 5: 합계 여
#   col 6: 주민등록인구대비 (skip)
#   col 7-9:  외국인근로자 (계/남/여)
#   col 10-12: 한국국적취득자 (계/남/여)
#   col 13-15: 국제결혼이주자 (= 결혼이민자) (계/남/여)
#   col 16:    국제결혼가정자녀 (계 only)
#
# Sheet '시.도별' has only 시도 rows. Sheet '전국' has 시도 + 시군구 mixed (same as
# 2007-2010 sigungu sheet style — 시도 followed by sub-시군구).

CAT_COLS_2006 = {
    "합계": None,  # special: 계 at col 2, 남 at col 4, 여 at col 5
    "외국인근로자": 7,
    "한국국적취득자": 10,
    "결혼이민자": 13,
}
CHILDREN_COL_2006 = 16  # 자녀 (계만)


def _find_data_start_2006(df: pd.DataFrame, name_col: int = 0) -> int:
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s == "계":
                return i
    raise ValueError("Could not find national '계' row")


def _emit_2006(rows, df, i, *, year, sido, sigungu):
    # 합계 special
    total = parse_value(df.iat[i, 2])
    male = parse_value(df.iat[i, 4])
    female = parse_value(df.iat[i, 5])
    for sex, val in (("total", total), ("M", male), ("F", female)):
        if val is None:
            continue
        row = {"year": year, "sido": sido, "category": "합계", "sex": sex, "n": val}
        if sigungu is not None:
            row["sigungu"] = sigungu
        rows.append(row)
    # other categories (sex-broken)
    for cat, c in CAT_COLS_2006.items():
        if c is None:
            continue
        t = parse_value(df.iat[i, c])
        m = parse_value(df.iat[i, c + 1])
        f = parse_value(df.iat[i, c + 2])
        for sex, val in (("total", t), ("M", m), ("F", f)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)
    # 자녀 (total only)
    c = parse_value(df.iat[i, CHILDREN_COL_2006])
    if c is not None:
        row = {"year": year, "sido": sido, "category": "외국인주민자녀", "sex": "total", "n": c}
        if sigungu is not None:
            row["sigungu"] = sigungu
        rows.append(row)


def _parse_sheet_2006(path: Path, sheet: str, *, level: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_2006(df, name_col=0)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("계", "합계", "합 계"):
            continue
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_2006(rows, df, i, year=2006, sido=current_sido, sigungu=None)
            continue
        if level == "sigungu":
            if current_sido is None:
                continue
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            _emit_2006(rows, df, i, year=2006, sido=current_sido, sigungu=sigungu_name)
    return rows


def parse_2006_totals():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = RAW_DIR / "2006_외국인주민통계.xls"
    sido = _parse_sheet_2006(p, "시.도별", level="sido")
    sigungu = _parse_sheet_2006(p, "전국", level="sigungu")
    print(f"2006: sido={len(sido)}  sigungu={len(sigungu)}")
    pd.DataFrame(sido).to_csv(OUT_DIR / "mois_sido_2006.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(sigungu).to_csv(OUT_DIR / "mois_sigungu_2006.csv", index=False, encoding="utf-8-sig")


# -- 2007-2010 (연도별 컬럼 배치) -----------------------------------------------------
# Parser for 2007-2010 외국인주민통계.
#
# Schemas evolve year by year:
# - 2007: 25 cols, no 유학생, no 외국국적동포, no 한국국적미취득_소계, 자녀 only as a single cell
# - 2008: 27 cols, has 유학생, no 외국국적동포
# - 2009: 46 cols (same buckets as 2011+). BUT 시도 sheet has 총계 at cols 2-4 (비율 at col 5),
#         while 시군구 sheet has 비율 at col 2 and 총계 at cols 3-5 (= standard).
# - 2010: 46 cols, same as 2011-2013 throughout.
#
# We re-use the 2014-2015 emit helper.

# Cat cols for 2010 + 2009 시군구 (= same as 2011-2015 시도시군구)
STANDARD_CAT_COLS = {
    "합계": 3,
    "한국국적미취득_소계": 6,
    "외국인근로자": 9,
    "결혼이민자": 12,
    "유학생": 15,
    "외국국적동포": 18,
    "기타외국인": 21,
    "한국국적취득자": 24,
    "혼인귀화자": 27,
    "기타귀화자": 30,
    "외국인주민자녀": 33,
    "자녀_외국인부모": 36,
    "자녀_외한국인부모": 39,
    "자녀_한국인부모": 42,
}
STANDARD_HOUSEHOLD_COL = 45

# 2009 시도 sheet has 총계 shifted: col 2,3,4 = 총계 계/남/여; col 5 = 비율; col 6+ = standard from there
CAT_COLS_2009_SIDO = {
    "합계": 2,
    "한국국적미취득_소계": 6,
    "외국인근로자": 9,
    "결혼이민자": 12,
    "유학생": 15,
    "외국국적동포": 18,  # actually labeled '재외동포'
    "기타외국인": 21,
    "한국국적취득자": 24,
    "혼인귀화자": 27,
    "기타귀화자": 30,
    "외국인주민자녀": 33,
    "자녀_외국인부모": 36,
    "자녀_외한국인부모": 39,
    "자녀_한국인부모": 42,
}
HOUSEHOLD_COL_2009_SIDO = 45

# 2008 layout (27 cols, no 외국국적동포, no soce)
CAT_COLS_2008 = {
    "합계": 2,
    "외국인근로자": 6,
    "결혼이민자": 9,
    "유학생": 12,
    "기타외국인": 15,
    "혼인귀화자": 18,
    "기타귀화자": 21,
    "외국인주민자녀": 24,
}
HOUSEHOLD_COL_2008 = None  # not present

# 2007 layout (25 cols, simpler)
CAT_COLS_2007 = {
    "합계": 2,           # 계/남/여 at cols 2, 4, 5 — col 3 = 비율 placeholder
    # We'll handle 합계 specially (3 non-consecutive cols)
    "외국인근로자": 7,
    "결혼이민자": 10,
    "기타외국인": 13,
    "혼인귀화자": 16,
    "기타귀화자": 19,
    "외국인주민자녀": 22,
}
# 2007: 합계 spans cols 2 (계), 4 (남), 5 (여), with col 3 = 비율


def _find_data_start_named_2007_2010(df: pd.DataFrame, name_col: int = 0,
                            markers: tuple[str, ...] = ("합계", "합 계")) -> int:
    for i in range(min(25, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s in {m.replace(" ", "") for m in markers}:
                return i
    raise ValueError(f"Could not find {markers} row")


def _emit_categories(rows, df, i, *, year, sido, sigungu, cat_cols, household_col,
                     special_2007=False):
    for cat, c in cat_cols.items():
        if special_2007 and cat == "합계":
            # 2007 합계: 계 at col 2, 남 at col 4, 여 at col 5
            total = parse_value(df.iat[i, 2])
            male = parse_value(df.iat[i, 4])
            female = parse_value(df.iat[i, 5])
        else:
            total = parse_value(df.iat[i, c])
            male = parse_value(df.iat[i, c + 1]) if c + 1 < df.shape[1] else None
            female = parse_value(df.iat[i, c + 2]) if c + 2 < df.shape[1] else None
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)
    if household_col is not None and household_col < df.shape[1]:
        hh = parse_value(df.iat[i, household_col])
        if hh is not None:
            row = {"year": year, "sido": sido, "category": "세대수", "sex": "total", "n": hh}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)


def _parse_sheet_2007_2010(path: Path, year: int, sheet: str, *, level: str,
                 cat_cols: dict, household_col, special_2007: bool = False) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_named_2007_2010(df, name_col=0)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계"):
            continue
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_categories(rows, df, i, year=year, sido=current_sido, sigungu=None,
                                 cat_cols=cat_cols, household_col=household_col,
                                 special_2007=special_2007)
            continue
        if level == "sigungu":
            if current_sido is None:
                continue
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            _emit_categories(rows, df, i, year=year, sido=current_sido, sigungu=sigungu_name,
                             cat_cols=cat_cols, household_col=household_col,
                             special_2007=special_2007)
    return rows


def parse_2007_2010_totals():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu = [], []

    # 2007
    p = RAW_DIR / "2007_외국인주민통계.xls"
    sido = _parse_sheet_2007_2010(p, 2007, "1.조사총괄(시도)", level="sido",
                        cat_cols=CAT_COLS_2007, household_col=None, special_2007=True)
    sigungu = _parse_sheet_2007_2010(p, 2007, "1.조사총괄(시군구)", level="sigungu",
                           cat_cols=CAT_COLS_2007, household_col=None, special_2007=True)
    print(f"2007: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    # 2008
    p = RAW_DIR / "2008_외국인주민통계.xls"
    sido = _parse_sheet_2007_2010(p, 2008, "총괄(시도)", level="sido",
                        cat_cols=CAT_COLS_2008, household_col=None)
    sigungu = _parse_sheet_2007_2010(p, 2008, "총괄 (시군구)", level="sigungu",
                           cat_cols=CAT_COLS_2008, household_col=None)
    print(f"2008: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    # 2009 — different cat_cols for sido vs sigungu!
    p = RAW_DIR / "2009_외국인주민통계.xls"
    sido = _parse_sheet_2007_2010(p, 2009, "1.총괄표(시도)", level="sido",
                        cat_cols=CAT_COLS_2009_SIDO, household_col=HOUSEHOLD_COL_2009_SIDO)
    sigungu = _parse_sheet_2007_2010(p, 2009, "1.총괄표", level="sigungu",
                           cat_cols=STANDARD_CAT_COLS, household_col=STANDARD_HOUSEHOLD_COL)
    print(f"2009: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    # 2010 — standard 46-col
    p = RAW_DIR / "2010_외국인주민통계.xls"
    sido = _parse_sheet_2007_2010(p, 2010, "1.총괄표 (시도) ", level="sido",
                        cat_cols=STANDARD_CAT_COLS, household_col=STANDARD_HOUSEHOLD_COL)
    sigungu = _parse_sheet_2007_2010(p, 2010, "1.총괄표(시군구)", level="sigungu",
                           cat_cols=STANDARD_CAT_COLS, household_col=STANDARD_HOUSEHOLD_COL)
    print(f"2010: sido={len(sido)}  sigungu={len(sigungu)}")
    all_sido.extend(sido); all_sigungu.extend(sigungu)

    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2007_2010.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2007_2010.csv", index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}")


# -- 2011-2013 (2014-2015 배치, 다른 시트 이름) ----------------------------------------
# Parser for 2011-2013 외국인주민통계 (no 읍면동 layer).
#
# Column layout is identical to 2014/2015 시도시군구. Only the sheet names differ.

YEAR_FILES = {
    2011: ("2011_외국인주민통계.xlsx", "1.총괄표(시도) ", "1.총괄표(시군구)"),
    2012: ("2012_외국인주민통계.xls", "1.조사총괄표(시도)", "1.조사총괄표(시군구)"),
    2013: ("2013_외국인주민통계.xlsx", "1.조사총괄표(시도)", "1.조사총괄표(시군구)"),
}


def parse_2011_2013_totals():
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


# -- 2014-2015 (읍면동 별도 파일) -----------------------------------------------------
# Parser for 2014-2015 외국인주민통계.
#
# Files used:
# - 2014_외국인주민통계_시도시군구.xlsx (sheets 1-1 시도, 1-1 시군구)
# - 2014_외국인주민통계_읍면동.xlsx     (sheet 1-1 읍면동)
# - 2015_외국인주민통계_시도시군구.xlsx
# - 2015_외국인주민통계_읍면동.xlsx
#
# These files use a richer category schema than 2016+ (한국국적취득자 split into
# 혼인귀화/기타사유, 외국인주민자녀 split by parent origin). We emit the same
# canonical categories as 2016+ PLUS the extra subcategories.
#
# The 2015_외국인주민통계_인구주택총조사기준.xlsx is NOT used by default — it
# is an alternative methodology and would create double counting. We process it
# into a separate CSV for documentation.

# Category column maps: each maps category → starting col (계/남/여 are col, col+1, col+2)
# Sheet 1-1 (시도, 시군구) column layout — data starts at row 6 (2014) or row 7 (2015).
CAT_COLS_SIDO_2014_2015 = {
    "합계": 3,
    "한국국적미취득_소계": 6,
    "외국인근로자": 9,
    "결혼이민자": 12,
    "유학생": 15,
    "외국국적동포": 18,
    "기타외국인": 21,
    "한국국적취득자": 24,           # = 한국국적취득_소계
    "혼인귀화자": 27,
    "기타귀화자": 30,
    "외국인주민자녀": 33,           # = 자녀_소계
    "자녀_외국인부모": 36,
    "자녀_외한국인부모": 39,
    "자녀_한국인부모": 42,
}
HOUSEHOLD_COL_SIDO_2014_2015 = 45  # 세대수 (single col, 계만)

# 2014 읍면동 file: shift right by 2 (col 0 = level marker, col 1 = name, col 2 = English)
CAT_COLS_EMD_2014 = {k: v + 2 for k, v in CAT_COLS_SIDO_2014_2015.items()}
HOUSEHOLD_COL_EMD_2014 = HOUSEHOLD_COL_SIDO_2014_2015 + 2

# 2015 읍면동 file: shift right by 1 (col 0 = name, col 1 = English)
CAT_COLS_EMD_2015 = {k: v + 1 for k, v in CAT_COLS_SIDO_2014_2015.items()}
HOUSEHOLD_COL_EMD_2015 = HOUSEHOLD_COL_SIDO_2014_2015 + 1


def _find_data_start_named_2014_2015(df: pd.DataFrame, name_col: int) -> int:
    """Find first data row by looking for '합계' (Grand Total)."""
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v)
            if s == "합계":
                return i
    raise ValueError("Could not find '합계' row")


def _parse_sigungu_or_sido_sheet(path: Path, year: int, sheet: str, *, level: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_named_2014_2015(df, name_col=0)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "합계":
            continue  # national total
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_region_categories(rows, df, i, year=year, sido=current_sido,
                                        sigungu=None, eupmyeondong=None,
                                        cat_cols=CAT_COLS_SIDO_2014_2015,
                                        household_col=HOUSEHOLD_COL_SIDO_2014_2015)
            continue
        if level == "sigungu":
            if current_sido is None:
                continue
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            _emit_region_categories(rows, df, i, year=year, sido=current_sido,
                                    sigungu=sigungu_name, eupmyeondong=None,
                                    cat_cols=CAT_COLS_SIDO_2014_2015,
                                    household_col=HOUSEHOLD_COL_SIDO_2014_2015)
    return rows


def _parse_eupmyeondong_sheet_2014_2015(path: Path, year: int, sheet: str,
                              name_col: int, cat_cols: dict, household_col: int) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_named_2014_2015(df, name_col=name_col)
    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "합계":
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            continue
        if kind == "eupmyeondong":
            if current_sido == "세종특별자치시" and current_sigungu is None:
                current_sigungu = "세종시"
            if current_sido is None or current_sigungu is None:
                continue
            _emit_region_categories(rows, df, i, year=year, sido=current_sido,
                                    sigungu=current_sigungu,
                                    eupmyeondong=strip_gu_prefix(name, current_sigungu),
                                    cat_cols=cat_cols, household_col=household_col)
    return rows


def _emit_region_categories(rows, df, i, *, year, sido, sigungu, eupmyeondong,
                            cat_cols, household_col):
    for cat, c in cat_cols.items():
        total = parse_value(df.iat[i, c])
        male = parse_value(df.iat[i, c + 1])
        female = parse_value(df.iat[i, c + 2])
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            if eupmyeondong is not None:
                row["eupmyeondong"] = eupmyeondong
            rows.append(row)
    # household count (single col, total only)
    hh = parse_value(df.iat[i, household_col])
    if hh is not None:
        row = {"year": year, "sido": sido, "category": "세대수", "sex": "total", "n": hh}
        if sigungu is not None:
            row["sigungu"] = sigungu
        if eupmyeondong is not None:
            row["eupmyeondong"] = eupmyeondong
        rows.append(row)


def parse_2014() -> dict[str, list[dict]]:
    p_main = RAW_DIR / "2014_외국인주민통계_시도시군구.xlsx"
    p_emd = RAW_DIR / "2014_외국인주민통계_읍면동.xlsx"
    return {
        "sido": _parse_sigungu_or_sido_sheet(p_main, 2014, "1-1. 총괄현황, 유형 및 지역별(시도)", level="sido"),
        "sigungu": _parse_sigungu_or_sido_sheet(p_main, 2014, "1-1.유형 및 지역별(시군구)", level="sigungu"),
        "eupmyeondong": _parse_eupmyeondong_sheet_2014_2015(
            p_emd, 2014, "1-1. 유형 및 지역별(읍면동)",
            name_col=1, cat_cols=CAT_COLS_EMD_2014, household_col=HOUSEHOLD_COL_EMD_2014,
        ),
    }


def parse_2015() -> dict[str, list[dict]]:
    p_main = RAW_DIR / "2015_외국인주민통계_시도시군구.xlsx"
    p_emd = RAW_DIR / "2015_외국인주민통계_읍면동.xlsx"
    return {
        "sido": _parse_sigungu_or_sido_sheet(p_main, 2015, "1-1. 총괄현황, 유형 및 지역별(시도)", level="sido"),
        "sigungu": _parse_sigungu_or_sido_sheet(p_main, 2015, "1-1.유형 및 지역별(시군구)", level="sigungu"),
        "eupmyeondong": _parse_eupmyeondong_sheet_2014_2015(
            p_emd, 2015, "1-1. 유형 및 지역별 현황(읍면동)",
            name_col=0, cat_cols=CAT_COLS_EMD_2015, household_col=HOUSEHOLD_COL_EMD_2015,
        ),
    }


def parse_2014_2015_totals():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu, all_emd = [], [], []
    for fn in (parse_2014, parse_2015):
        result = fn()
        for k, v in result.items():
            print(f"  {fn.__name__}/{k}: {len(v)} rows")
        all_sido.extend(result["sido"])
        all_sigungu.extend(result["sigungu"])
        all_emd.extend(result["eupmyeondong"])
    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2014_2015.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2014_2015.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_emd).to_csv(OUT_DIR / "mois_eupmyeondong_2014_2015.csv", index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}  emd={len(all_emd):,}")


# -- 2016-2024 (한 파일에 시도·시군구·읍면동·다문화가구) ----------------------------------------
# Parser for 2016-2024 외국인주민통계 files (homogeneous schema).
#
# Sheets parsed:
# - 1-1. 유형 및 지역별(시.도)       → mois_sido_2016_2024.csv
# - 1-2. 유형 및 지역별(시.군.구)   → mois_sigungu_2016_2024.csv
# - 1-3. 유형 및 지역별(읍면동)     → mois_eupmyeondong_2016_2024.csv
# - 11. 다문화가구 현황(읍면동)     → mois_multicultural_eupmyeondong_2016_2024.csv
#
# Category schema (population sheets):
#   합계, 한국국적미취득_소계, 외국인근로자, 결혼이민자, 유학생, 외국국적동포, 기타외국인,
#   한국국적취득자, 외국인주민자녀

YEARS = list(range(2016, 2025))

# Canonical category order
POP_CATEGORIES_SIDO_SIGUNGU = [
    "합계", "한국국적미취득_소계",
    "외국인근로자", "결혼이민자", "유학생", "외국국적동포", "기타외국인",
    "한국국적취득자", "외국인주민자녀",
]
POP_CATEGORIES_EUPMYEONDONG = POP_CATEGORIES_SIDO_SIGUNGU  # same set


def find_sheet(xls: pd.ExcelFile, *patterns) -> str | None:
    """Find a sheet matching any of the substrings (loosely)."""
    for s in xls.sheet_names:
        norm = s.replace(" ", "").replace("⋅", ".").replace("·", ".")
        for pat in patterns:
            if pat.replace(" ", "").replace("⋅", ".").replace("·", ".") in norm:
                return s
    return None


def _read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet, header=None)


def _find_data_start_2016plus(df: pd.DataFrame) -> int:
    """Return the row index of the first data row (where col 0 == '전국')."""
    for i in range(min(15, len(df))):
        v = df.iat[i, 0]
        if isinstance(v, str) and v.strip() == "전국":
            return i
    raise ValueError("Could not find '전국' row")


def _parse_sido_sigungu_sheet(path: Path, year: int, sheet: str, *, level: str) -> list[dict]:
    """Parse 1-1 or 1-2 sheet. Each region has 3 columns per category (계/남/여).

    Layout (from 2024 inspection):
      col 0: 구분 (region name)
      col 1: 총인구 (denominator)
      col 2: 비율
      col 3-5: 합계 (계/남/여)
      col 6-8: 한국국적미취득 소계 (계/남/여)
      col 9-11: 외국인근로자 (계/남/여)
      col 12-14: 결혼이민자 (계/남/여)
      col 15-17: 유학생 (계/남/여)
      col 18-20: 외국국적동포 (계/남/여)
      col 21-23: 기타외국인 (계/남/여)
      col 24-26: 한국국적취득자 (계/남/여)
      col 27-29: 외국인주민자녀 (계/남/여)
    """
    df = _read_sheet(path, sheet)
    start = _find_data_start_2016plus(df)

    cat_cols = {
        "합계": (3, 4, 5),
        "한국국적미취득_소계": (6, 7, 8),
        "외국인근로자": (9, 10, 11),
        "결혼이민자": (12, 13, 14),
        "유학생": (15, 16, 17),
        "외국국적동포": (18, 19, 20),
        "기타외국인": (21, 22, 23),
        "한국국적취득자": (24, 25, 26),
        "외국인주민자녀": (27, 28, 29),
    }

    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)

        if name == "전국":
            # national row, optional, skip for sido/sigungu CSVs
            continue

        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                _emit_region_row(rows, df, i, year=year, sido=current_sido,
                                 sigungu=None, eupmyeondong=None, cat_cols=cat_cols,
                                 with_sex=True)
            continue

        # not sido — must be sigungu
        if level == "sigungu":
            if current_sido is None:
                # malformed — try to skip
                continue
            # detect sub-gu split
            sub = split_sub_gu(name)
            if sub:
                parent, gu = sub
                sigungu_name = parent + " " + gu
            else:
                sigungu_name = name
            _emit_region_row(rows, df, i, year=year, sido=current_sido,
                             sigungu=sigungu_name, eupmyeondong=None,
                             cat_cols=cat_cols, with_sex=True)

    return rows


def _emit_region_row(rows, df, i, *, year, sido, sigungu, eupmyeondong, cat_cols, with_sex):
    for cat, cols in cat_cols.items():
        if with_sex:
            total = parse_value(df.iat[i, cols[0]])
            male = parse_value(df.iat[i, cols[1]])
            female = parse_value(df.iat[i, cols[2]])
            for sex, val in (("total", total), ("M", male), ("F", female)):
                if val is None:
                    continue
                row = {"year": year, "sido": sido, "category": cat, "sex": sex, "n": val}
                if sigungu is not None:
                    row["sigungu"] = sigungu
                if eupmyeondong is not None:
                    row["eupmyeondong"] = eupmyeondong
                rows.append(row)
        else:
            val = parse_value(df.iat[i, cols[0]])
            if val is None:
                continue
            row = {"year": year, "sido": sido, "category": cat, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            if eupmyeondong is not None:
                row["eupmyeondong"] = eupmyeondong
            rows.append(row)


def _parse_eupmyeondong_sheet_2016plus(path: Path, year: int, sheet: str) -> list[dict]:
    """Parse sheet 1-3 (읍면동). Single-column-per-category layout.

    Columns (2024):
      0: name
      1: 합계
      2: 한국국적미취득_소계
      3: 외국인근로자
      4: 결혼이민자
      5: 유학생
      6: 외국국적동포
      7: 기타외국인
      8: 한국국적취득자
      9: 외국인주민자녀
    """
    df = _read_sheet(path, sheet)
    start = _find_data_start_2016plus(df)

    cat_cols = {
        "합계": 1,
        "한국국적미취득_소계": 2,
        "외국인근로자": 3,
        "결혼이민자": 4,
        "유학생": 5,
        "외국국적동포": 6,
        "기타외국인": 7,
        "한국국적취득자": 8,
        "외국인주민자녀": 9,
    }

    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "전국":
            continue
        kind = classify_row_name(name)

        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue

        if kind == "sigungu":
            # detect sub-gu under parent 시
            sub = split_sub_gu(name)
            if sub:
                parent, gu = sub
                current_sigungu = parent + " " + gu
            else:
                current_sigungu = name
            continue

        if kind == "eupmyeondong":
            # 세종특별자치시는 시군구 없이 시도 바로 아래 읍면동 → 시군구를 '세종시'로 보정
            if current_sido == "세종특별자치시" and current_sigungu is None:
                current_sigungu = "세종시"
            if current_sido is None or current_sigungu is None:
                # malformed (e.g. orphan 완산구); skip
                continue
            for cat, c in cat_cols.items():
                v = parse_value(df.iat[i, c])
                if v is None:
                    continue
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "eupmyeondong": name, "category": cat, "n": v,
                })

    return rows


def _parse_multicultural_sheet(path: Path, year: int, sheet: str) -> list[dict]:
    """Parse sheet 11 (다문화가구) 읍면동 portion.

    2024 columns:
      0: name
      1: 합계
      2: 한국인배우자
      3: 결혼이민자및귀화자등_소계
      4: 결혼이민자
      5: 귀화자등
      6: 자녀_소계
      7: 귀화·인지및외국국적
      8: 국내출생
      9: 기타동거인_소계
      10: 내국인
      11: 외국인
    """
    df = _read_sheet(path, sheet)
    start = _find_data_start_2016plus(df)

    cat_cols = {
        "합계": 1, "한국인배우자": 2,
        "결혼이민자귀화자_소계": 3, "결혼이민자": 4, "귀화자등": 5,
        "자녀_소계": 6, "자녀_귀화인지외국국적": 7, "자녀_국내출생": 8,
        "기타동거인_소계": 9, "기타동거인_내국인": 10, "기타동거인_외국인": 11,
    }

    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name == "전국":
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            continue
        if kind == "eupmyeondong":
            if current_sido == "세종특별자치시" and current_sigungu is None:
                current_sigungu = "세종시"
            if current_sido is None or current_sigungu is None:
                continue
            for cat, c in cat_cols.items():
                if c >= df.shape[1]:
                    continue
                v = parse_value(df.iat[i, c])
                if v is None:
                    continue
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "eupmyeondong": name, "category": cat, "n": v,
                })
    return rows


def parse_year(year: int) -> dict[str, list[dict]]:
    path = RAW_DIR / f"{year}_외국인주민통계.xlsx"
    xls = pd.ExcelFile(path)
    out: dict[str, list[dict]] = {"sido": [], "sigungu": [], "eupmyeondong": [], "multicultural": []}

    sheet_sido = find_sheet(xls, "1-1.유형및지역별(시.도)", "1-1.유형 및 지역별(시⋅도)", "1-1.유형 및 지역별(시.도)")
    sheet_sigungu = find_sheet(xls, "1-2.유형및지역별(시.군.구)", "1-2.유형 및 지역별(시⋅군⋅구)")
    sheet_eupmyeondong = find_sheet(xls, "1-3.유형및지역별(읍면동)", "1-3.유형 및 지역별(읍⋅면⋅동)")
    sheet_multi = find_sheet(xls, "11.다문화가구")

    if sheet_sido:
        out["sido"] = _parse_sido_sigungu_sheet(path, year, sheet_sido, level="sido")
    if sheet_sigungu:
        out["sigungu"] = _parse_sido_sigungu_sheet(path, year, sheet_sigungu, level="sigungu")
    if sheet_eupmyeondong:
        out["eupmyeondong"] = _parse_eupmyeondong_sheet_2016plus(path, year, sheet_eupmyeondong)
    if sheet_multi:
        out["multicultural"] = _parse_multicultural_sheet(path, year, sheet_multi)
    return out


def parse_2016plus_totals():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_sido, all_sigungu, all_eupmyeondong, all_multi = [], [], [], []

    for year in YEARS:
        print(f"=== {year} ===")
        result = parse_year(year)
        for key in result:
            print(f"  {key}: {len(result[key])} rows")
        all_sido.extend(result["sido"])
        all_sigungu.extend(result["sigungu"])
        all_eupmyeondong.extend(result["eupmyeondong"])
        all_multi.extend(result["multicultural"])

    pd.DataFrame(all_sido).to_csv(OUT_DIR / "mois_sido_2016_2024.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_sigungu).to_csv(OUT_DIR / "mois_sigungu_2016_2024.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_eupmyeondong).to_csv(OUT_DIR / "mois_eupmyeondong_2016_2024.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_multi).to_csv(OUT_DIR / "mois_multicultural_eupmyeondong_2016_2024.csv", index=False, encoding="utf-8-sig")

    print(f"\nTotals: sido={len(all_sido):,}  sigungu={len(all_sigungu):,}  eupmyeondong={len(all_eupmyeondong):,}  multicultural={len(all_multi):,}")


# -- 국적별 (2009-2024) -----------------------------------------------------------
# Parse nationality (국적별) sheets across all year files.
#
# Outputs:
# - mois_nationality_sigungu.csv     : year, sido, sigungu, country, sex, n  (2009-2024)
# - mois_nationality_eupmyeondong.csv: year, sido, sigungu, eupmyeondong, country, sex, n (2014-2015)
# - mois_nationality_by_visa_sigungu.csv : year, sido, sigungu, visa_type, country, sex, n
# - mois_nationality_naturalized_sigungu.csv : 한국국적취득자 × 국적 (2014-2015)
# - mois_nationality_children_sigungu.csv    : 외국인주민 자녀 × 국적 (2014-2015 sheet 4-1; 2016+ sheet 10)
#
# Strategy: auto-detect the country header by finding the row containing '중국'/'일본',
# then read every column flagged with '계' in the following row as country columns.
# Continent sub-totals (소계) are skipped.

CONTINENT_TOTALS = {"소계", "동북아", "동북아시아", "동남아", "동남아시아",
                    "남부아시아", "서남아시아", "중앙아시아", "아시아",
                    "아시아(기타)", "북미", "유럽", "오세아니아", "중남미",
                    "아프리카"}
SUM_COL_LABELS = {"합계", "총계", "계", "Grand Total"}


def _find_country_header_row(df: pd.DataFrame, max_scan: int = 12) -> int:
    """Locate the row above the (계/남/여) sex header — works for any matrix sheet
    where data columns come in triplets (or singles)."""
    # First find the sex header row: the one with multiple '계' cells at distinct cols
    sex_row = None
    for ri in range(min(max_scan, len(df))):
        count_total = 0
        for v in df.iloc[ri].values:
            if isinstance(v, str) and v.split("\n")[0].strip() == "계":
                count_total += 1
        if count_total >= 2:
            sex_row = ri
            break
    if sex_row is None:
        # Sheets that don't break by sex (e.g. 세대수, simple counts) — header is the row
        # whose next row contains data. Find first row where col 0 is non-empty as data marker.
        # Fall back: assume header is row containing many text labels right before '전국'/합계
        for ri in range(min(max_scan, len(df))):
            v0 = df.iat[ri, 0]
            if isinstance(v0, str) and clean_region_name(v0) in ("전국", "합계", "합 계"):
                return ri - 1
        raise ValueError("Could not locate any header row")
    # The category header is one row above the sex row (sometimes two rows above)
    return sex_row - 1


def _build_country_col_map(df: pd.DataFrame, country_row: int, sex_row: int) -> dict[int, str]:
    """Map data col → country name. Skip 합계/소계 cols."""
    mapping = {}
    # Walk the sex row finding 계 (계 column position is start of a (계,남,여) triplet)
    for c in range(df.shape[1]):
        sex_v = df.iat[sex_row, c]
        if not isinstance(sex_v, str):
            continue
        if sex_v.split("\n")[0].strip() != "계":
            continue
        # Look at country label at country_row, col c. If empty, scan left for nearest non-null.
        country = None
        for cc in range(c, -1, -1):
            v = df.iat[country_row, cc]
            if pd.notna(v):
                country = str(v).split("\n")[0].strip()
                break
        if country is None:
            continue
        # Skip continent sub-totals and 합계
        if country in CONTINENT_TOTALS or country in SUM_COL_LABELS:
            continue
        # Sanitize: drop trailing punctuation
        country = country.replace(" ", "")
        mapping[c] = country
    return mapping


def _find_data_start_nationality(df: pd.DataFrame, name_col: int = 0) -> int:
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s in ("합계", "전국", "합 계", "계"):
                return i
    raise ValueError("Data start row not found")


def _parse_matrix_sheet(path: Path, year: int, sheet: str, *,
                        level: str, name_col: int = 0,
                        extra_label: str | None = None) -> list[dict]:
    """Generic matrix parser. extra_label is e.g. visa_type for 5-1-2 sheets.

    For 시군구 sheets: iterate rows, track current_sido, emit at sigungu level only.
    For 읍면동 sheets: iterate rows, track current_sido + current_sigungu, emit at eupmyeondong level.
    For 시도 sheets: emit when current row matches a 시도 name.
    """
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    country_row = _find_country_header_row(df)
    sex_row = country_row + 1
    col_map = _build_country_col_map(df, country_row, sex_row)
    if not col_map:
        return []
    start = _find_data_start_nationality(df, name_col=name_col)

    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "전국", "합 계", "계"):
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            if level == "sido":
                _emit_country_row(rows, df, i, year=year, sido=current_sido,
                                  sigungu=None, eupmyeondong=None, col_map=col_map,
                                  extra_label=extra_label)
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            if level == "sigungu":
                if current_sido is None:
                    continue
                _emit_country_row(rows, df, i, year=year, sido=current_sido,
                                  sigungu=current_sigungu, eupmyeondong=None,
                                  col_map=col_map, extra_label=extra_label)
            continue
        if kind == "eupmyeondong":
            if level == "eupmyeondong":
                if current_sido is None or current_sigungu is None:
                    continue
                _emit_country_row(rows, df, i, year=year, sido=current_sido,
                                  sigungu=current_sigungu,
                                  eupmyeondong=strip_gu_prefix(name, current_sigungu),
                                  col_map=col_map, extra_label=extra_label)
    return rows


def _emit_country_row(rows, df, i, *, year, sido, sigungu, eupmyeondong, col_map, extra_label):
    for c, country in col_map.items():
        total = parse_value(df.iat[i, c])
        male = parse_value(df.iat[i, c + 1]) if c + 1 < df.shape[1] else None
        female = parse_value(df.iat[i, c + 2]) if c + 2 < df.shape[1] else None
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "country": country, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            if eupmyeondong is not None:
                row["eupmyeondong"] = eupmyeondong
            if extra_label is not None:
                row["visa_type"] = extra_label
            rows.append(row)


# === Per-year sheet routing ===

NATIONALITY_SIGUNGU_SHEETS = {
    # year: (filename, sheet_name)
    2009: ("2009_외국인주민통계.xls", "2.국적미보유"),
    2010: ("2010_외국인주민통계.xls", "2.국적미취득 "),
    2011: ("2011_외국인주민통계.xlsx", "2.국적미취득(시군구)"),
    2012: ("2012_외국인주민통계.xls", "2.국적미취득(시군구)"),
    2013: ("2013_외국인주민통계.xlsx", "2.국적미취득(시군구)"),
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "2-1.국적별(시군구)"),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "2-1.한국국적을 가지지 않은 자, 국적별(시군구)"),
    2016: ("2016_외국인주민통계.xlsx", "4-2. 국적별(시⋅군⋅구)"),
    2017: ("2017_외국인주민통계.xlsx", "4-2. 국적별(시⋅군⋅구)"),
    2018: ("2018_외국인주민통계.xlsx", "4-2. 국적별(시⋅군⋅구) ("),
    2019: ("2019_외국인주민통계.xlsx", "4-2. 국적별(시·군·구)"),
    2020: ("2020_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2021: ("2021_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2022: ("2022_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2023: ("2023_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
    2024: ("2024_외국인주민통계.xlsx", "4-2. 국적별(시.군.구)"),
}

NATIONALITY_EUPMYEONDONG_SHEETS = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "2.한국국적을 가지지 않은 자-1. 국적별(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "2-1.한국국적을 가지지 않은 자, 국적별(읍면동)"),
}

# By visa type (외국인근로자/결혼이민자/유학생/외국국적동포/기타) × country × 시군구
NATIONALITY_BY_VISA_SHEETS = {
    # year: list of (visa_type, filename, sheet_name)
    2009: [
        ("외국인근로자", "2009_외국인주민통계.xls", "2-가.외국인근로자"),
        ("결혼이민자", "2009_외국인주민통계.xls", "2-나.결혼이민자"),
        ("유학생", "2009_외국인주민통계.xls", "2-다.유학생"),
        ("외국국적동포", "2009_외국인주민통계.xls", "2-라.재외동포"),
        ("기타외국인", "2009_외국인주민통계.xls", "2-마.기타"),
    ],
    2010: [
        ("외국인근로자", "2010_외국인주민통계.xls", "2-가.외국인근로자"),
        ("결혼이민자", "2010_외국인주민통계.xls", "2-나.결혼이민자"),
        ("유학생", "2010_외국인주민통계.xls", "2-다.유학생"),
        ("외국국적동포", "2010_외국인주민통계.xls", "2-라.재외동포"),
        ("기타외국인", "2010_외국인주민통계.xls", "2-마.기타"),
    ],
    2011: [
        ("외국인근로자", "2011_외국인주민통계.xlsx", "2-가.외국인근로자"),
        ("결혼이민자", "2011_외국인주민통계.xlsx", "2-나.결혼이민자"),
        ("유학생", "2011_외국인주민통계.xlsx", "2-다.유학생"),
        ("외국국적동포", "2011_외국인주민통계.xlsx", "2-라.재외동포"),
        ("기타외국인", "2011_외국인주민통계.xlsx", "2-마.기타"),
    ],
    2012: [
        ("외국인근로자", "2012_외국인주민통계.xls", "2-가.외국인근로자"),
        ("결혼이민자", "2012_외국인주민통계.xls", "2-나.결혼이민자"),
        ("유학생", "2012_외국인주민통계.xls", "2-다.유학생"),
        ("외국국적동포", "2012_외국인주민통계.xls", "2-라.외국국적동포"),
        ("기타외국인", "2012_외국인주민통계.xls", "2-마.기타"),
    ],
    2013: [
        ("외국인근로자", "2013_외국인주민통계.xlsx", "2-가.외국인근로자"),
        ("결혼이민자", "2013_외국인주민통계.xlsx", "2-나.결혼이민자"),
        ("유학생", "2013_외국인주민통계.xlsx", "2-다.유학생"),
        ("외국국적동포", "2013_외국인주민통계.xlsx", "2-라.외국국적동포"),
        ("기타외국인", "2013_외국인주민통계.xlsx", "2-마.기타"),
    ],
    2014: [
        ("외국인근로자", "2014_외국인주민통계_시도시군구.xlsx", "2-2-가.외국인근로자(시군구)"),
        ("결혼이민자", "2014_외국인주민통계_시도시군구.xlsx", "2-2-나.결혼이민자(시군구)"),
        ("유학생", "2014_외국인주민통계_시도시군구.xlsx", "2-2-다.유학생(시군구)"),
        ("외국국적동포", "2014_외국인주민통계_시도시군구.xlsx", "2-2-라.외국국적동포(시군구)"),
        ("기타외국인", "2014_외국인주민통계_시도시군구.xlsx", "2-2-마.기타(시군구)"),
    ],
    2015: [
        ("외국인근로자", "2015_외국인주민통계_시도시군구.xlsx", "2-2-가.외국인근로자(시군구)"),
        ("결혼이민자", "2015_외국인주민통계_시도시군구.xlsx", "2-2-나.결혼이민자(시군구)"),
        ("유학생", "2015_외국인주민통계_시도시군구.xlsx", "2-2-다.유학생(시군구)"),
        ("외국국적동포", "2015_외국인주민통계_시도시군구.xlsx", "2-2-라.외국국적동포(시군구)"),
        ("기타외국인", "2015_외국인주민통계_시도시군구.xlsx", "2-2-마.기타(시군구)"),
    ],
    2016: [
        ("외국인근로자", "2016_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시⋅군⋅구)"),
        ("결혼이민자", "2016_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구)"),
        ("유학생", "2016_외국인주민통계.xlsx", "5-3-2. 유학생(시⋅군⋅구)"),
        ("외국국적동포", "2016_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시⋅군⋅구)"),
        ("기타외국인", "2016_외국인주민통계.xlsx", "5-5-2. 기타(시⋅군⋅구)"),
    ],
    2017: [
        ("외국인근로자", "2017_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시⋅군⋅구)"),
        ("결혼이민자", "2017_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구)"),
        ("유학생", "2017_외국인주민통계.xlsx", "5-3-2. 유학생(시⋅군⋅구)"),
        ("외국국적동포", "2017_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시⋅군⋅구)"),
        ("기타외국인", "2017_외국인주민통계.xlsx", "5-5-2. 기타(시⋅군⋅구)"),
    ],
    2018: [
        ("외국인근로자", "2018_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시⋅군⋅구) "),
        ("결혼이민자", "2018_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구) "),
        ("유학생", "2018_외국인주민통계.xlsx", "5-3-2. 유학생(시⋅군⋅구) "),
        ("외국국적동포", "2018_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시⋅군⋅구) "),
        ("기타외국인", "2018_외국인주민통계.xlsx", "5-5-2. 기타(시⋅군⋅구) "),
    ],
    2019: [
        ("외국인근로자", "2019_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시·군·구)"),
        ("결혼이민자", "2019_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시⋅군⋅구) "),
        ("유학생", "2019_외국인주민통계.xlsx", "5-3-2.유학생(시·군·구)"),
        ("외국국적동포", "2019_외국인주민통계.xlsx", "5-4-2.외국국적동포(시·군·구)"),
        ("기타외국인", "2019_외국인주민통계.xlsx", "5-5-2.기타(시·군·구)"),
    ],
    2020: [
        ("외국인근로자", "2020_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2020_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2020_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2020_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2020_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2021: [
        ("외국인근로자", "2021_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2021_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2021_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2021_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2021_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2022: [
        ("외국인근로자", "2022_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2022_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2022_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2022_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2022_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2023: [
        ("외국인근로자", "2023_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2023_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2023_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2023_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2023_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
    2024: [
        ("외국인근로자", "2024_외국인주민통계.xlsx", "5-1-2. 외국인근로자(시.군.구)"),
        ("결혼이민자", "2024_외국인주민통계.xlsx", "5-2-2. 결혼이민자(시.군.구)"),
        ("유학생", "2024_외국인주민통계.xlsx", "5-3-2.유학생(시.군.구)"),
        ("외국국적동포", "2024_외국인주민통계.xlsx", "5-4-2. 외국국적동포(시.군.구)"),
        ("기타외국인", "2024_외국인주민통계.xlsx", "5-5-2. 기타(시.군.구)"),
    ],
}

# Naturalized × nationality × 시군구 (2014-2015 sheet 3-1) and 자녀 × 국적 × 시군구 (sheet 4-1)
NATIONALITY_NATURALIZED_SHEETS = {
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "3-1.국적별(시군구)"),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "3-1.한국국적취득자, 국적별(시군구)"),
}
NATIONALITY_CHILDREN_SHEETS = {
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "4-1.국적별(시군구)"),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "4-1.국적별(시군구)"),
}


def _safe_parse(year, fname, sheet, *, level, name_col=0, extra_label=None):
    path = RAW_DIR / fname
    try:
        return _parse_matrix_sheet(path, year, sheet, level=level, name_col=name_col,
                                    extra_label=extra_label)
    except Exception as e:
        print(f"  WARN {year} {sheet}: {e}")
        return []


def parse_nationality_sheets():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Total foreigners × nationality × 시군구
    sigungu_rows = []
    for year, (fname, sheet) in NATIONALITY_SIGUNGU_SHEETS.items():
        rows = _safe_parse(year, fname, sheet, level="sigungu")
        sigungu_rows.extend(rows)
        print(f"  {year} 국적별 시군구: {len(rows)} rows")

    # Total foreigners × nationality × 읍면동
    emd_rows = []
    for year, (fname, sheet) in NATIONALITY_EUPMYEONDONG_SHEETS.items():
        # 2014 읍면동 has name at col 0 (Korean), English at col 1, so name_col=0 works
        rows = _safe_parse(year, fname, sheet, level="eupmyeondong", name_col=0)
        emd_rows.extend(rows)
        print(f"  {year} 국적별 읍면동: {len(rows)} rows")

    # By visa-type × nationality × 시군구
    by_visa_rows = []
    for year, items in NATIONALITY_BY_VISA_SHEETS.items():
        for visa_type, fname, sheet in items:
            rows = _safe_parse(year, fname, sheet, level="sigungu", extra_label=visa_type)
            by_visa_rows.extend(rows)
            print(f"  {year} {visa_type} 시군구: {len(rows)} rows")

    # Naturalized × nationality × 시군구
    natur_rows = []
    for year, (fname, sheet) in NATIONALITY_NATURALIZED_SHEETS.items():
        rows = _safe_parse(year, fname, sheet, level="sigungu")
        natur_rows.extend(rows)
        print(f"  {year} 한국국적취득자 국적별 시군구: {len(rows)} rows")

    # Children × nationality × 시군구
    child_rows = []
    for year, (fname, sheet) in NATIONALITY_CHILDREN_SHEETS.items():
        rows = _safe_parse(year, fname, sheet, level="sigungu")
        child_rows.extend(rows)
        print(f"  {year} 자녀 국적별 시군구: {len(rows)} rows")

    pd.DataFrame(sigungu_rows).to_csv(OUT_DIR / "mois_nationality_sigungu.csv",
                                      index=False, encoding="utf-8-sig")
    pd.DataFrame(emd_rows).to_csv(OUT_DIR / "mois_nationality_eupmyeondong.csv",
                                   index=False, encoding="utf-8-sig")
    pd.DataFrame(by_visa_rows).to_csv(OUT_DIR / "mois_nationality_by_visa_sigungu.csv",
                                      index=False, encoding="utf-8-sig")
    pd.DataFrame(natur_rows).to_csv(OUT_DIR / "mois_nationality_naturalized_sigungu.csv",
                                    index=False, encoding="utf-8-sig")
    pd.DataFrame(child_rows).to_csv(OUT_DIR / "mois_nationality_children_sigungu.csv",
                                    index=False, encoding="utf-8-sig")

    print(f"\nTotals:")
    print(f"  국적별 시군구: {len(sigungu_rows):,}")
    print(f"  국적별 읍면동: {len(emd_rows):,}")
    print(f"  비자유형별 시군구: {len(by_visa_rows):,}")
    print(f"  귀화자 국적별 시군구: {len(natur_rows):,}")
    print(f"  자녀 국적별 시군구: {len(child_rows):,}")


# -- 자녀 연령별 (2011-2024) --------------------------------------------------------
# Parse 자녀 × 연령별 sheets.
#
# Layout: rows alternate between region-total rows (e.g. '전국', '서울특별시', '종로구')
# and per-age rows ('0세' / '만0세' / '만19세이상') belonging to the preceding region.
#
# We emit per-age counts at the region level, using 합계 columns (cols 1-3 = 계/남/여).
# Country and type breakdowns within the same sheets are not extracted here (kept simple).
#
# Outputs:
# - mois_children_age_sido.csv      : year, sido, age, sex, n   (2014-2024 시도)
# - mois_children_age_sigungu.csv   : year, sido, sigungu, age, sex, n   (2014-2024 시군구)

# Regex to detect age labels: 0세 / 만0세 / 만19세이상 / 18세이상
AGE_RE = re.compile(r"^만?\d+세(이상)?$")


def _normalize_age(label: str) -> str | None:
    """Convert '만0세'/'0세' → '0', '만19세이상' → '19+', etc. Return None if not an age."""
    s = label.replace(" ", "")
    m = AGE_RE.match(s)
    if not m:
        return None
    s = s.replace("만", "")
    if "이상" in s:
        base = s.replace("세이상", "")
        return f"{base}+"
    return s.replace("세", "")


def _parse_age_sheet(path: Path, year: int, sheet: str, *, name_col: int = 0,
                     value_cols: tuple[int, int, int] = (1, 2, 3),
                     emit_levels: tuple[str, ...] = ("sigungu",)) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    rows = []
    current_sido = None
    current_sigungu = None

    # Some sheets (2012-2013) keep region in col 0 and age in col 1.
    # Detect: if col 1 contains '만0세'-style labels in early data rows, age is in col 1.
    age_col = name_col
    region_col = name_col
    value_shift = 0
    for probe in range(min(40, len(df))):
        v1 = df.iat[probe, name_col + 1] if name_col + 1 < df.shape[1] else None
        if isinstance(v1, str) and _normalize_age(clean_region_name(v1)) is not None:
            # age is in col name_col+1; region stays in name_col
            age_col = name_col + 1
            region_col = name_col
            value_shift = 1  # values start at col 2 not col 1
            break

    for i in range(len(df)):
        # Look at region column first
        raw_r = df.iat[i, region_col] if pd.notna(df.iat[i, region_col]) else None
        if raw_r is not None:
            r_name = clean_region_name(raw_r)
            r_name = fix_known_typos(r_name)
            if r_name in ("구분", "Section"):
                continue
            kind = classify_row_name(r_name)
            if kind == "sido":
                current_sido = canon_sido(r_name)
                current_sigungu = None
                # When age is in a separate col, region row may also have age='합계' → keep checking
                if age_col == region_col:
                    continue
            elif kind == "sigungu":
                sub = split_sub_gu(r_name)
                current_sigungu = (sub[0] + " " + sub[1]) if sub else r_name
                if age_col == region_col:
                    continue
            elif r_name in ("전국", "합계", "합 계", ""):
                if age_col == region_col:
                    continue
            elif age_col == region_col:
                # region_col may also hold the age label
                pass

        # Look at age column
        if age_col >= df.shape[1]:
            continue
        raw_a = df.iat[i, age_col]
        if pd.isna(raw_a):
            continue
        a_name = clean_region_name(raw_a)
        if not a_name:
            continue
        age = _normalize_age(a_name)
        if age is None:
            continue
        # 세종특별자치시는 시군구 없이 시도 바로 아래 → 시군구를 '세종시'로 보정
        if current_sido == "세종특별자치시" and current_sigungu is None and "sigungu" in emit_levels:
            current_sigungu = "세종시"
        # Emit at the current finest level we know
        if current_sigungu is not None and "sigungu" in emit_levels:
            level_label, sido, sigungu = "sigungu", current_sido, current_sigungu
        elif current_sido is not None and "sido" in emit_levels:
            level_label, sido, sigungu = "sido", current_sido, None
        else:
            continue
        c_total, c_m, c_f = (c + value_shift for c in value_cols)
        total = parse_value(df.iat[i, c_total]) if c_total < df.shape[1] else None
        male = parse_value(df.iat[i, c_m]) if c_m < df.shape[1] else None
        female = parse_value(df.iat[i, c_f]) if c_f < df.shape[1] else None
        for sex, val in (("total", total), ("M", male), ("F", female)):
            if val is None:
                continue
            row = {"year": year, "sido": sido, "age": age, "sex": sex, "n": val}
            if sigungu is not None:
                row["sigungu"] = sigungu
            rows.append(row)
    return rows


# Per-year (file, sido_sheet, sigungu_sheet)
AGE_SHEETS = {
    2011: ("2011_외국인주민통계.xlsx", None, "4.자녀(연령)"),
    2012: ("2012_외국인주민통계.xls", None, "4.자녀연령"),
    2013: ("2013_외국인주민통계.xlsx", None, "4.자녀연령"),
    # 2014/2015: sido sheet in 시도시군구 file, sigungu sheet in 읍면동 file (oddly placed)
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "4-3.연령별(시도)",
           ("2014_외국인주민통계_읍면동.xlsx", "4-3.연령별(시군구)")),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "4-3.연령별(시도)",
           ("2015_외국인주민통계_읍면동.xlsx", "4-3.연령별(시군구)")),
    # 2016+ in main file, sheets 9-1 / 9-2
    2016: ("2016_외국인주민통계.xlsx", "9-1. 연령별(시⋅도)", "9-2. 연령별(시⋅군⋅구)"),
    2017: ("2017_외국인주민통계.xlsx", "9-1. 연령별(시⋅도)", "9-2. 연령별(시⋅군⋅구)"),
    2018: ("2018_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2019: ("2019_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2020: ("2020_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2021: ("2021_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2022: ("2022_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2023: ("2023_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
    2024: ("2024_외국인주민통계.xlsx", "9-1. 연령별(시⋅도) ", "9-2. 연령별(시⋅군⋅구) "),
}


def parse_children_age_sheets():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sido_rows, sigungu_rows = [], []
    for year, info in AGE_SHEETS.items():
        fname, sido_sheet, sigungu_sheet = info
        path = RAW_DIR / fname
        if sido_sheet:
            try:
                r = _parse_age_sheet(path, year, sido_sheet, emit_levels=("sido",))
                sido_rows.extend(r)
                print(f"  {year} 자녀연령 시도: {len(r)} rows")
            except Exception as e:
                print(f"  WARN {year} 시도 {sido_sheet}: {e}")
        # sigungu_sheet might be tuple (different file, sheet)
        if isinstance(sigungu_sheet, tuple):
            sg_path = RAW_DIR / sigungu_sheet[0]; sg_sheet = sigungu_sheet[1]
        else:
            sg_path, sg_sheet = path, sigungu_sheet
        if sg_sheet:
            try:
                r = _parse_age_sheet(sg_path, year, sg_sheet, emit_levels=("sigungu",))
                sigungu_rows.extend(r)
                print(f"  {year} 자녀연령 시군구: {len(r)} rows")
            except Exception as e:
                print(f"  WARN {year} 시군구 {sg_sheet}: {e}")

    pd.DataFrame(sido_rows).to_csv(OUT_DIR / "mois_children_age_sido.csv",
                                    index=False, encoding="utf-8-sig")
    pd.DataFrame(sigungu_rows).to_csv(OUT_DIR / "mois_children_age_sigungu.csv",
                                       index=False, encoding="utf-8-sig")
    print(f"\nTotals: sido={len(sido_rows):,}  sigungu={len(sigungu_rows):,}")


# -- 나머지 차원: 부모유형, 체류기간, 이전국적, 경과기간, 세대수 ---------------------------------------
# Extract remaining dimensions:
#
# 1. 자녀 × 부모유형 × 읍면동 (2014-2015) — from 읍면동 file sheets 4-2-가/나/다
# 2. 자녀 × 부모유형 × 시군구 (2016-2024) — from main file sheet 8-2
# 3. 체류기간별 × 시군구 (2016-2024) — sheet 3-2
# 4. 이전국적별 × 시군구 (2016-2024) — sheet 7-2 (귀화자 origin)
# 5. 국적취득 경과기간별 × 시군구 (2016-2024) — sheet 6-2
# 6. 외국인주민 세대수 × 읍면동 (2014-2015) — separate sheet "6.외국인주민세대수(읍면동)"
# 7. 결혼이민자 및 국적취득자 연령별 × 시군구/읍면동 (2014-2015)
#
# For each, we save a long-format CSV with year, sido, sigungu, [eupmyeondong,] category, sex, n.

# ---- 2014-2015 읍면동 parent-type sheets ----
CHILD_PARENT_EUPMYEONDONG = {
    2014: [
        ("외국인부모", "2014_외국인주민통계_읍면동.xlsx", "4-2. 유형별-가.외국인부모(읍면동)"),
        ("외-한국인부모", "2014_외국인주민통계_읍면동.xlsx", "4-2-나.외-한국인부모(읍면동)"),
        ("한국인부모", "2014_외국인주민통계_읍면동.xlsx", "4-2-다.한국인부모(읍면동)"),
    ],
    2015: [
        ("외국인부모", "2015_외국인주민통계_읍면동.xlsx", "4-2-가.유형별,외국인부모(읍면동)"),
        ("외-한국인부모", "2015_외국인주민통계_읍면동.xlsx", "4-2-나.외-한국인부모(읍면동)"),
        ("한국인부모", "2015_외국인주민통계_읍면동.xlsx", "4-2-다.한국인부모(읍면동)"),
    ],
}

# ---- 2016+ 부모유형별 시군구 (sheet 8-2) ----
CHILD_PARENT_TYPE_SHEETS_2016PLUS = {
    2016: "8-2. 유형별(시⋅군⋅구)",
    2017: "8-2. 유형별(시⋅군⋅구)",
    2018: "8-2. 유형별(시⋅군⋅구) ",
    2019: "8-2. 유형별(시⋅군⋅구) ",
    2020: "8-2. 유형별(시⋅군⋅구) ",
    2021: "8-2. 유형별(시⋅군⋅구) ",
    2022: "8-2. 유형별(시⋅군⋅구) ",
    2023: "8-2. 유형별(시⋅군⋅구) ",
    2024: "8-2. 유형별(시⋅군⋅구) ",
}

# ---- 2016+ 체류기간별 시군구 (sheet 3-2) ----
RESIDENCE_PERIOD_SHEETS = {
    2016: "3-2. 체류기간별(시⋅군⋅구)",
    2017: "3-2. 체류기간별(시⋅군⋅구)",
    2018: "3-2. 체류기간별(시⋅군⋅구) ",
    2019: "3-2. 체류기간별(시·군·구)",
    2020: "3-2. 체류기간별(시.군.구)",
    2021: "3-2. 체류기간별(시.군.구)",
    2022: "3-2. 체류기간별(시.군.구)",
    2023: "3-2. 체류기간별(시.군.구)",
    2024: "3-2. 체류기간별(시.군.구)",
}

# ---- 2016+ 이전국적별 시군구 (sheet 7-2) — 귀화자 origin ----
PREV_NATIONALITY_SHEETS = {
    2016: "7-2. 이전국적별(시⋅군⋅구)",
    2017: "7-2. 이전국적별(시⋅군⋅구)",
    2018: "7-2. 이전국적별(시⋅군⋅구) ",
    2019: "7-2. 이전국적별(시⋅군⋅구) ",
    2020: "7-2. 이전국적별(시⋅군⋅구) ",
    2021: "7-2. 이전국적별(시⋅군⋅구) ",
    2022: "7-2. 이전국적별(시⋅군⋅구) ",
    2023: "7-2. 이전국적별(시⋅군⋅구) ",
    2024: "7-2. 이전국적별(시⋅군⋅구) ",
}

# ---- 2016+ 국적취득 경과기간별 (sheet 6-2) ----
NATURALIZATION_PERIOD_SHEETS = {
    2016: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2017: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2018: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2019: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2020: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2021: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2022: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2023: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
    2024: "6-2. 국적취득 경과 기간별(시⋅군⋅구)",
}

# ---- 2014-2015 세대수 읍면동 ----
HOUSEHOLD_EUPMYEONDONG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "6.외국인주민세대수(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "6.외국인주민세대수(읍면동)"),
}

# ---- 2014-2015 비자유형 × 국적별 × 읍면동 ----
VISA_NATIONALITY_EUPMYEONDONG = {
    2014: [
        ("외국인근로자", "2014_외국인주민통계_읍면동.xlsx", "2-2. 유형별-가.외국인근로자(읍면동)"),
        ("결혼이민자", "2014_외국인주민통계_읍면동.xlsx", "2-2-나.결혼이민자(읍면동)"),
        ("유학생", "2014_외국인주민통계_읍면동.xlsx", "2-2-다.유학생(읍면동)"),
        ("외국국적동포", "2014_외국인주민통계_읍면동.xlsx", "2-2-라.외국국적동포(읍면동)"),
        ("기타외국인", "2014_외국인주민통계_읍면동.xlsx", "2-2-마.기타(읍면동)"),
    ],
    2015: [
        ("외국인근로자", "2015_외국인주민통계_읍면동.xlsx", "2-2-가. 유형별, 외국인근로자(읍면동)"),
        ("결혼이민자", "2015_외국인주민통계_읍면동.xlsx", "2-2-나.결혼이민자(읍면동)"),
        ("유학생", "2015_외국인주민통계_읍면동.xlsx", "2-2-다.유학생(읍면동)"),
        ("외국국적동포", "2015_외국인주민통계_읍면동.xlsx", "2-2-라.외국국적동포(읍면동)"),
        ("기타외국인", "2015_외국인주민통계_읍면동.xlsx", "2-2-마.기타(읍면동)"),
    ],
}

# ---- 2014-2015 귀화자 × 국적별 × 읍면동 ----
NATURALIZED_NATIONALITY_EUPMYEONDONG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "3.한국국적취득자-1. 국적별(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "3-1.한국국적취득자, 국적별(읍면동)"),
}

# ---- 2014-2015 자녀 × 국적별 × 읍면동 ----
CHILDREN_NATIONALITY_EUPMYEONDONG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "4.외국인주민자녀-1. 국적별(읍면동)"),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "4-1.외국인주민자녀,국적별(읍면동)"),
}

# ---- 2014-2015 결혼이민자 및 국적취득자 연령별 × 시도/시군구/읍면동 ----
MARRIAGE_AGE_SHEETS = {
    2014: [
        ("sido", "2014_외국인주민통계_읍면동.xlsx", "5.결혼이민자 및 국적취득자  연령별 현황(시도)"),
        ("sigungu", "2014_외국인주민통계_읍면동.xlsx", "5.결혼이민자 및 국적취득자 연령별 현황(시군구)"),
        ("eupmyeondong", "2014_외국인주민통계_읍면동.xlsx", "5.결혼이민자 및 국적취득자 연령별 현황(읍면동)"),
    ],
    2015: [
        ("sido", "2015_외국인주민통계_읍면동.xlsx", "5-1.결혼이민자 및 국적취득자 연령별 현황(시도)"),
        ("sigungu", "2015_외국인주민통계_읍면동.xlsx", "5-2.결혼이민자 및 국적취득자 연령별 현황(시군구)"),
        ("eupmyeondong", "2015_외국인주민통계_읍면동.xlsx", "5-3.결혼이민자 및 국적취득자 연령별 현황(읍면동)"),
    ],
}


def _generic_matrix_sigungu(year: int, fname: str, sheet: str) -> list[dict]:
    """Use the generic country/matrix parser for ANY (region × labeled-categories) sheet."""
    try:
        return _parse_matrix_sheet(RAW_DIR / fname, year, sheet, level="sigungu")
    except Exception as e:
        print(f"  WARN {year} {sheet}: {e}")
        return []


def _generic_matrix_eupmyeondong(year: int, fname: str, sheet: str,
                                  extra_label: str | None = None) -> list[dict]:
    try:
        return _parse_matrix_sheet(RAW_DIR / fname, year, sheet,
                                    level="eupmyeondong", extra_label=extra_label)
    except Exception as e:
        print(f"  WARN {year} {sheet}: {e}")
        return []


def parse_extra_dimensions():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 자녀 × 부모유형 × 읍면동 (2014-2015)
    parent_emd_rows = []
    for year, items in CHILD_PARENT_EUPMYEONDONG.items():
        for parent_type, fname, sheet in items:
            r = _generic_matrix_eupmyeondong(year, fname, sheet, extra_label=parent_type)
            # Rename the auto-added 'visa_type' field to 'parent_type'
            for row in r:
                if "visa_type" in row:
                    row["parent_type"] = row.pop("visa_type")
            parent_emd_rows.extend(r)
            print(f"  {year} 부모유형={parent_type} 읍면동: {len(r)} rows")
    pd.DataFrame(parent_emd_rows).to_csv(OUT_DIR / "mois_children_parent_type_eupmyeondong.csv",
                                          index=False, encoding="utf-8-sig")

    # 2. 자녀 × 부모유형 × 시군구 (2016-2024) — sheet 8-2 has parent type as columns
    parent_sigungu_rows = []
    for year, sheet in CHILD_PARENT_TYPE_SHEETS_2016PLUS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        r = _generic_matrix_sigungu(year, fname, sheet)
        parent_sigungu_rows.extend(r)
        print(f"  {year} 자녀 유형별 시군구: {len(r)} rows")
    pd.DataFrame(parent_sigungu_rows).to_csv(OUT_DIR / "mois_children_parent_type_sigungu.csv",
                                              index=False, encoding="utf-8-sig")

    # 3. 체류기간별 × 시군구 (2016-2024)
    residence_rows = []
    for year, sheet in RESIDENCE_PERIOD_SHEETS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        r = _generic_matrix_sigungu(year, fname, sheet)
        residence_rows.extend(r)
        print(f"  {year} 체류기간별 시군구: {len(r)} rows")
    pd.DataFrame(residence_rows).to_csv(OUT_DIR / "mois_residence_period_sigungu.csv",
                                         index=False, encoding="utf-8-sig")

    # 4. 이전국적별 × 시군구 (2016-2024)
    prev_nat_rows = []
    for year, sheet in PREV_NATIONALITY_SHEETS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        r = _generic_matrix_sigungu(year, fname, sheet)
        prev_nat_rows.extend(r)
        print(f"  {year} 이전국적별 시군구: {len(r)} rows")
    pd.DataFrame(prev_nat_rows).to_csv(OUT_DIR / "mois_naturalized_prev_nationality_sigungu.csv",
                                        index=False, encoding="utf-8-sig")

    # 5. 국적취득 경과기간별 × 시군구 (2016-2024) — single-value matrix (no sex)
    natur_period_rows = []
    for year, sheet in NATURALIZATION_PERIOD_SHEETS.items():
        fname = f"{year}_외국인주민통계.xlsx"
        try:
            r = _parse_single_value_matrix_sigungu(RAW_DIR / fname, year, sheet)
        except Exception as e:
            print(f"  WARN {year} {sheet}: {e}")
            r = []
        natur_period_rows.extend(r)
        print(f"  {year} 국적취득경과기간별 시군구: {len(r)} rows")
    pd.DataFrame(natur_period_rows).to_csv(OUT_DIR / "mois_naturalization_period_sigungu.csv",
                                            index=False, encoding="utf-8-sig")

    # 6. 외국인주민 세대수 × 읍면동 (2014-2015) — handle simpler 1-col layout
    hh_rows = []
    for year, (fname, sheet) in HOUSEHOLD_EUPMYEONDONG.items():
        try:
            r = _parse_household_emd(RAW_DIR / fname, year, sheet)
            hh_rows.extend(r)
            print(f"  {year} 세대수 읍면동: {len(r)} rows")
        except Exception as e:
            print(f"  WARN {year} 세대수 읍면동: {e}")
    pd.DataFrame(hh_rows).to_csv(OUT_DIR / "mois_household_eupmyeondong.csv",
                                  index=False, encoding="utf-8-sig")

    # 7. 비자유형 × 국적별 × 읍면동 (2014-2015)
    visa_nat_emd_rows = []
    for year, items in VISA_NATIONALITY_EUPMYEONDONG.items():
        for visa_type, fname, sheet in items:
            r = _generic_matrix_eupmyeondong(year, fname, sheet, extra_label=visa_type)
            visa_nat_emd_rows.extend(r)
            print(f"  {year} {visa_type}×국적 읍면동: {len(r)} rows")
    pd.DataFrame(visa_nat_emd_rows).to_csv(OUT_DIR / "mois_nationality_by_visa_eupmyeondong.csv",
                                            index=False, encoding="utf-8-sig")

    # 8. 귀화자 × 국적별 × 읍면동 (2014-2015)
    natur_emd_rows = []
    for year, (fname, sheet) in NATURALIZED_NATIONALITY_EUPMYEONDONG.items():
        r = _generic_matrix_eupmyeondong(year, fname, sheet)
        natur_emd_rows.extend(r)
        print(f"  {year} 귀화자 국적별 읍면동: {len(r)} rows")
    pd.DataFrame(natur_emd_rows).to_csv(OUT_DIR / "mois_nationality_naturalized_eupmyeondong.csv",
                                         index=False, encoding="utf-8-sig")

    # 9. 자녀 × 국적별 × 읍면동 (2014-2015)
    child_emd_rows = []
    for year, (fname, sheet) in CHILDREN_NATIONALITY_EUPMYEONDONG.items():
        r = _generic_matrix_eupmyeondong(year, fname, sheet)
        child_emd_rows.extend(r)
        print(f"  {year} 자녀 국적별 읍면동: {len(r)} rows")
    pd.DataFrame(child_emd_rows).to_csv(OUT_DIR / "mois_nationality_children_eupmyeondong.csv",
                                         index=False, encoding="utf-8-sig")

    # 10. 결혼이민자 및 국적취득자 연령별 (2014-2015 시도/시군구/읍면동)
    marriage_age_rows = []
    for year, items in MARRIAGE_AGE_SHEETS.items():
        for level, fname, sheet in items:
            try:
                if level == "eupmyeondong":
                    r = _generic_matrix_eupmyeondong(year, fname, sheet)
                elif level == "sigungu":
                    r = _generic_matrix_sigungu(year, fname, sheet)
                else:
                    r = _parse_matrix_sheet(RAW_DIR / fname, year, sheet, level="sido")
                # Add level marker
                for row in r:
                    row["level"] = level
                marriage_age_rows.extend(r)
                print(f"  {year} 결혼이민자/국적취득자 연령별 {level}: {len(r)} rows")
            except Exception as e:
                print(f"  WARN {year} {sheet}: {e}")
    pd.DataFrame(marriage_age_rows).to_csv(OUT_DIR / "mois_marriage_age.csv",
                                            index=False, encoding="utf-8-sig")

    print(f"\nDone. Outputs in {OUT_DIR}")


def _parse_single_value_matrix_sigungu(path: Path, year: int, sheet: str) -> list[dict]:
    """For sheets without sex breakdown: each col is a single value.
    Headers: row containing categories (e.g. '1년미만', '1년이상~2년미만'),
    data starts at the row where col 0 = '전국' or '합계'."""
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    # Find data start
    start = None
    for i in range(min(20, len(df))):
        v = df.iat[i, 0]
        if pd.notna(v):
            s = clean_region_name(v)
            if s in ("전국", "합계"):
                start = i
                break
    if start is None:
        return []
    # Header is row above data (or 2 above if blank in between)
    header_row = start - 1
    while header_row >= 0:
        v_check = df.iat[header_row, 1] if df.shape[1] > 1 else None
        if isinstance(v_check, str) and v_check.strip():
            break
        header_row -= 1
    if header_row < 0:
        return []
    # Build col → category label
    cat_map = {}
    for c in range(1, df.shape[1]):
        v = df.iat[header_row, c]
        if pd.notna(v):
            label = str(v).replace("\n", "").strip()
            if label in SUM_COL_LABELS_LOCAL:
                continue
            cat_map[c] = label
    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("전국", "합계", "합 계"):
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            if current_sido is None:
                continue
            for c, cat in cat_map.items():
                v = parse_value(df.iat[i, c])
                if v is None:
                    continue
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "category": cat, "n": v,
                })
            continue
    return rows


SUM_COL_LABELS_LOCAL = {"합계", "총계", "계", "Grand Total"}


def _parse_household_emd(path: Path, year: int, sheet: str) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    # Find data start
    start = None
    for i in range(min(20, len(df))):
        v = df.iat[i, 0]
        if pd.notna(v):
            s = clean_region_name(v)
            if s == "합계":
                start = i
                break
    if start is None:
        return []
    rows = []
    current_sido = None
    current_sigungu = None
    # Find which col has the household count — typically last col with numeric data
    # For simplicity: try col 1 first; fall back to col 2 / col 3
    candidate_cols = [c for c in range(1, min(8, df.shape[1]))]
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, 0])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계", "전국"):
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            continue
        if kind != "eupmyeondong":
            continue
        if current_sido is None or current_sigungu is None:
            continue
        # find first numeric column
        for c in candidate_cols:
            v = parse_value(df.iat[i, c])
            if v is not None:
                rows.append({
                    "year": year, "sido": current_sido, "sigungu": current_sigungu,
                    "eupmyeondong": strip_gu_prefix(name, current_sigungu), "n": v,
                })
                break
    return rows


# -- 주민등록인구 (외국인 비율의 분모) -------------------------------------------------------
# Extract 주민등록인구 (total resident-registration population) at sido/sigungu/eupmyeondong level.
#
# Source: the main MOIS sheet for each year typically has 주민등록인구 as col 1
# (directly to the right of region name). This script extracts it as a parallel
# denominator column so the dashboard can compute 외국인비율 = 외국인주민 / 주민등록인구.
#
# Coverage:
# - 시도 / 시군구: 2006-2024 (all years; col layout fixed)
# - 읍면동: 2014-2015 only (2016+ 1-3 시트에 주민등록인구 컬럼 없음)
#
# Output: 03_cleaned_data/mois_total_pop.csv
#   Columns: year, level, sido, sigungu, eupmyeondong, total_pop

# Per-year file + sheet config: (filename, sheet_sido, sheet_sigungu, name_col, pop_col_sido, pop_col_sigungu, start_marker_after)
# pop_col = column index of 주민등록인구 in that sheet
YEAR_CONFIG = {
    2006: ("2006_외국인주민통계.xls", "시.도별", "전국", 0, 1, 1),
    2007: ("2007_외국인주민통계.xls", "1.조사총괄(시도)", "1.조사총괄(시군구)", 0, 1, 1),
    2008: ("2008_외국인주민통계.xls", "총괄(시도)", "총괄 (시군구)", 0, 1, 1),
    2009: ("2009_외국인주민통계.xls", "1.총괄표(시도)", "1.총괄표", 0, 1, 1),
    2010: ("2010_외국인주민통계.xls", "1.총괄표 (시도) ", "1.총괄표(시군구)", 0, 1, 1),
    2011: ("2011_외국인주민통계.xlsx", "1.총괄표(시도) ", "1.총괄표(시군구)", 0, 1, 1),
    2012: ("2012_외국인주민통계.xls", "1.조사총괄표(시도)", "1.조사총괄표(시군구)", 0, 1, 1),
    2013: ("2013_외국인주민통계.xlsx", "1.조사총괄표(시도)", "1.조사총괄표(시군구)", 0, 1, 1),
    2014: ("2014_외국인주민통계_시도시군구.xlsx", "1-1. 총괄현황, 유형 및 지역별(시도)",
            "1-1.유형 및 지역별(시군구)", 0, 1, 1),
    2015: ("2015_외국인주민통계_시도시군구.xlsx", "1-1. 총괄현황, 유형 및 지역별(시도)",
            "1-1.유형 및 지역별(시군구)", 0, 1, 1),
    2016: ("2016_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시⋅도)",
            "1-2. 유형 및 지역별(시⋅군⋅구)", 0, 1, 1),
    2017: ("2017_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시⋅도)",
            "1-2. 유형 및 지역별(시⋅군⋅구)", 0, 1, 1),
    2018: ("2018_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시⋅도) ",
            "1-2. 유형 및 지역별(시⋅군⋅구) ", 0, 1, 1),
    2019: ("2019_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2020: ("2020_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2021: ("2021_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2022: ("2022_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2023: ("2023_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
    2024: ("2024_외국인주민통계.xlsx", "1-1. 유형 및 지역별(시.도)",
            "1-2. 유형 및 지역별(시.군.구)", 0, 1, 1),
}

# 읍면동 only 2014-2015 (separate files). col layouts:
# 2014 읍면동 file 1-1: name at col 1 (English at col 2), 주민등록인구 at col 3
# 2015 읍면동 file 1-1: name at col 0 (English at col 1), 주민등록인구 at col 2
EUPMYEONDONG_CONFIG = {
    2014: ("2014_외국인주민통계_읍면동.xlsx", "1-1. 유형 및 지역별(읍면동)", 1, 3),
    2015: ("2015_외국인주민통계_읍면동.xlsx", "1-1. 유형 및 지역별 현황(읍면동)", 0, 2),
}


def _find_data_start_total_pop(df: pd.DataFrame, name_col: int = 0) -> int:
    markers = {"합계", "합 계", "전국", "계"}
    for i in range(min(20, len(df))):
        v = df.iat[i, name_col]
        if pd.notna(v):
            s = clean_region_name(v).replace(" ", "")
            if s in markers:
                return i
    raise ValueError("data start not found")


def _parse_sheet_sigungu_or_sido(path: Path, sheet: str, *, level: str,
                                  name_col: int, pop_col: int) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_total_pop(df, name_col=name_col)
    rows = []
    current_sido = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계", "전국", "계"):
            continue
        if name in SIDO_NAMES:
            current_sido = canon_sido(name)
            if level == "sido":
                tp = parse_value(df.iat[i, pop_col])
                if tp is not None:
                    rows.append({"level": "sido", "sido": current_sido,
                                  "sigungu": "", "eupmyeondong": "",
                                  "total_pop": tp})
            continue
        if level == "sigungu" and current_sido is not None:
            sub = split_sub_gu(name)
            sigungu_name = (sub[0] + " " + sub[1]) if sub else name
            tp = parse_value(df.iat[i, pop_col])
            if tp is not None:
                rows.append({"level": "sigungu", "sido": current_sido,
                              "sigungu": sigungu_name, "eupmyeondong": "",
                              "total_pop": tp})
    return rows


def _parse_sheet_eupmyeondong(path: Path, sheet: str, name_col: int, pop_col: int) -> list[dict]:
    df = pd.read_excel(path, sheet_name=sheet, header=None)
    start = _find_data_start_total_pop(df, name_col=name_col)
    rows = []
    current_sido = None
    current_sigungu = None
    for i in range(start, len(df)):
        name = clean_region_name(df.iat[i, name_col])
        if not name:
            continue
        name = fix_known_typos(name)
        if name in ("합계", "합 계", "전국", "계"):
            continue
        kind = classify_row_name(name)
        if kind == "sido":
            current_sido = canon_sido(name)
            current_sigungu = None
            continue
        if kind == "sigungu":
            sub = split_sub_gu(name)
            current_sigungu = (sub[0] + " " + sub[1]) if sub else name
            continue
        if kind == "eupmyeondong":
            if current_sido is None or current_sigungu is None:
                continue
            tp = parse_value(df.iat[i, pop_col])
            if tp is not None:
                rows.append({"level": "eupmyeondong", "sido": current_sido,
                              "sigungu": current_sigungu,
                              "eupmyeondong": strip_gu_prefix(name, current_sigungu),
                              "total_pop": tp})
    return rows


def extract_total_population():
    all_rows = []
    for year, (fname, s_sido, s_sigungu, name_col, pop_sido, pop_sg) in YEAR_CONFIG.items():
        path = RAW_DIR / fname
        try:
            rs = _parse_sheet_sigungu_or_sido(path, s_sido, level="sido",
                                                name_col=name_col, pop_col=pop_sido)
            for r in rs: r["year"] = year
            all_rows.extend(rs)
            print(f"  {year} 시도: {len(rs)} rows")
        except Exception as e:
            print(f"  WARN {year} 시도: {e}")
        try:
            rg = _parse_sheet_sigungu_or_sido(path, s_sigungu, level="sigungu",
                                                name_col=name_col, pop_col=pop_sg)
            for r in rg: r["year"] = year
            all_rows.extend(rg)
            print(f"  {year} 시군구: {len(rg)} rows")
        except Exception as e:
            print(f"  WARN {year} 시군구: {e}")
    # 읍면동 (2014-2015)
    for year, (fname, sheet, name_col, pop_col) in EUPMYEONDONG_CONFIG.items():
        path = RAW_DIR / fname
        try:
            re_ = _parse_sheet_eupmyeondong(path, sheet, name_col, pop_col)
            for r in re_: r["year"] = year
            all_rows.extend(re_)
            print(f"  {year} 읍면동: {len(re_)} rows")
        except Exception as e:
            print(f"  WARN {year} 읍면동: {e}")

    df = pd.DataFrame(all_rows)
    df = df[["year", "level", "sido", "sigungu", "eupmyeondong", "total_pop"]]
    df = df.sort_values(["year", "level", "sido", "sigungu", "eupmyeondong"])
    out = OUT_DIR / "mois_total_pop.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nWrote {out}  ({len(df):,} rows)")


# -- 행정구역코드 (2015 년 보조 파일의 7자리 BCNT) -------------------------------------------
# Extract 행정구역코드 (BCNT-style 7-digit codes) from in-house MOIS files.
#
# Two source files include the codes directly (most other MOIS files do not):
#
# 1. 2015_외국인주민통계_유형지역별읍면동.xls
#    Long tabular format with columns: 행정구역코드, 시도, 시군구, 행정동, [counts...]
#    Provides codes for ~3,495 읍면동 + parent rows.
#
# 2. 2015_외국인주민통계_자녀시군구연령별.xlsx
#    Long tabular format with: 지역코드, 년도, 시도, 시군구, [age columns...]
#    Provides 7-digit codes for 시도 (NN00000), 시군구 (NNNN000), 전국 (0000000).
#
# The 2015 codes are an internal bootstrap — they cover essentially all sigungu
# and most eupmyeondong present in MOIS 2014-2024. Codes are administratively
# stable (행정안전부 BCNT) for most regions year over year; only boundary changes
# (e.g., 부천시 자치구 통합 2016) cause drift.
#
# Output: 03_cleaned_data/mois_bcnt_codes_inhouse.csv with cols
#     bcnt_code, level, sido, sigungu, eupmyeondong

BCNT_OUT = OUT_DIR / "mois_bcnt_codes_inhouse.csv"

SIDO_CANON = {
    "강원도": "강원도", "강원특별자치도": "강원도",
    "전라북도": "전라북도", "전북특별자치도": "전라북도",
    "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
    "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
}


def canon(s):
    if s is None:
        return ""
    return SIDO_CANON.get(s, s)


def extract_from_eupmyeondong_file() -> pd.DataFrame:
    """Extract from 2015_외국인주민통계_유형지역별읍면동.xls."""
    f = RAW_DIR / "2015_외국인주민통계_유형지역별읍면동.xls"
    df = pd.read_excel(f, sheet_name="외국인주민", header=None)
    # row 0-1 = headers, row 2 = 전국 합계, row 3+ = 읍면동 rows
    rows = []
    for i in range(3, len(df)):
        code = df.iat[i, 0]
        sido = df.iat[i, 1]
        sigungu = df.iat[i, 2]
        eupmyeondong = df.iat[i, 3]
        if pd.isna(code):
            continue
        code = str(code).strip().zfill(7)
        if not code.isdigit() or len(code) != 7:
            continue
        rows.append({
            "bcnt_code": code,
            "level": "eupmyeondong",
            "sido": canon(sido) if pd.notna(sido) else "",
            "sigungu": str(sigungu).strip() if pd.notna(sigungu) else "",
            "eupmyeondong": str(eupmyeondong).strip() if pd.notna(eupmyeondong) else "",
        })
    return pd.DataFrame(rows)


def extract_from_children_file() -> pd.DataFrame:
    """Extract from 2015_외국인주민통계_자녀시군구연령별.xlsx — covers 시도/시군구."""
    f = RAW_DIR / "2015_외국인주민통계_자녀시군구연령별.xlsx"
    df = pd.read_excel(f, sheet_name=0, header=None)
    # Data starts at row 5 with 전국 (code 0000000)
    rows = []
    for i in range(5, len(df)):
        code = df.iat[i, 0]
        sido = df.iat[i, 2]
        sigungu = df.iat[i, 3]
        if pd.isna(code):
            continue
        code = str(code).strip().zfill(7)
        if not code.isdigit() or len(code) != 7:
            continue
        if code == "0000000":
            continue  # national row
        # Classify by code pattern
        if code.endswith("00000"):
            level = "sido"
            sido_name = canon(sido) if pd.notna(sido) else ""
            sigungu_name = ""
        elif code.endswith("000"):
            level = "sigungu"
            sido_name = canon(sido) if pd.notna(sido) else ""
            sigungu_name = str(sigungu).strip() if pd.notna(sigungu) else ""
        else:
            continue  # unexpected
        rows.append({
            "bcnt_code": code,
            "level": level,
            "sido": sido_name,
            "sigungu": sigungu_name,
            "eupmyeondong": "",
        })
    return pd.DataFrame(rows)


def extract_bcnt_codes():
    emd_df = extract_from_eupmyeondong_file()
    print(f"From 유형지역별읍면동 file: {len(emd_df):,} rows")
    print(f"  unique 읍면동 codes: {emd_df['bcnt_code'].nunique():,}")

    sg_df = extract_from_children_file()
    print(f"From 자녀시군구연령별 file: {len(sg_df):,} rows")
    print(f"  level breakdown: {sg_df['level'].value_counts().to_dict()}")

    # Derive sigungu codes from eupmyeondong codes:
    # - 일반 시군구 (e.g., 종로구): first 4 digits + "000" (e.g., 1101000)
    # - sub-구 of 100만 도시 (e.g., 성남시 분당구): first 5 digits + "00"
    #   (e.g., 3102300 — 5번째 자리가 sub-구 식별자)
    derived_sigungu = []
    for _, r in emd_df.iterrows():
        sigungu = r["sigungu"]
        code = r["bcnt_code"]
        if isinstance(sigungu, str) and " " in sigungu:
            # sub-구 of 100만 도시 — preserve 5-digit prefix
            sg_code = code[:5] + "00"
        else:
            sg_code = code[:4] + "000"
        derived_sigungu.append({
            "bcnt_code": sg_code,
            "level": "sigungu",
            "sido": r["sido"],
            "sigungu": sigungu,
            "eupmyeondong": "",
        })
    derived_sigungu_df = pd.DataFrame(derived_sigungu).drop_duplicates(
        subset=["bcnt_code", "sido", "sigungu"]
    )
    print(f"Derived sigungu codes from eupmyeondong parents: {len(derived_sigungu_df):,}")

    # Additionally, derive PARENT 100만-도시 codes (e.g., 성남시 = 3102000) by
    # taking the first 4 digits + "000" of any sub-구 in that city.
    parent_si = []
    for _, r in emd_df.iterrows():
        sigungu = r["sigungu"]
        if isinstance(sigungu, str) and " " in sigungu:
            parent_name = sigungu.split(" ")[0]
            parent_code = r["bcnt_code"][:4] + "000"
            parent_si.append({
                "bcnt_code": parent_code,
                "level": "sigungu",
                "sido": r["sido"],
                "sigungu": parent_name,
                "eupmyeondong": "",
            })
    parent_si_df = pd.DataFrame(parent_si).drop_duplicates(
        subset=["bcnt_code", "sido", "sigungu"]
    )
    print(f"Derived parent 시 codes (100만 도시 with sub-구s): {len(parent_si_df):,}")
    derived_sigungu_df = pd.concat([derived_sigungu_df, parent_si_df], ignore_index=True)
    derived_sigungu_df = derived_sigungu_df.drop_duplicates(
        subset=["bcnt_code", "sido", "sigungu"])

    # Combine and dedupe (prefer children file for sigungu where overlap exists)
    full = pd.concat([sg_df, derived_sigungu_df, emd_df], ignore_index=True)
    full = full.drop_duplicates(subset=["bcnt_code", "level", "sido", "sigungu", "eupmyeondong"])

    # Build sido-only rows (NN00000)
    sido_codes = sg_df[sg_df["level"] == "sido"].copy()
    if sido_codes.empty:
        # derive from sigungu codes
        sido_pairs = full[full["level"] == "sigungu"][["bcnt_code", "sido"]].copy()
        sido_pairs["sido_code"] = sido_pairs["bcnt_code"].str[:2] + "00000"
        sido_pairs = sido_pairs.drop_duplicates(["sido_code", "sido"])
        sido_rows = pd.DataFrame({
            "bcnt_code": sido_pairs["sido_code"],
            "level": "sido",
            "sido": sido_pairs["sido"],
            "sigungu": "",
            "eupmyeondong": "",
        })
        full = pd.concat([full, sido_rows], ignore_index=True).drop_duplicates(
            subset=["bcnt_code", "level"])

    full = full.sort_values(["level", "sido", "sigungu", "eupmyeondong"])
    full.to_csv(BCNT_OUT, index=False, encoding="utf-8-sig")
    print(f"\nWrote {BCNT_OUT}")
    print(f"Total: {len(full):,} rows; levels: {full['level'].value_counts().to_dict()}")


# -- 서울 동별 등록외국인 (수동 다운로드본, 재파싱 순서 밖) ------------------------------------------
# Parser for 서울특별시 등록외국인 현황 (국적별 동별) — Seoul Open Data CSV.
#
# Source: https://www.data.go.kr/data/15146338/fileData.do
# The file must be downloaded manually (data.go.kr download requires browser/login).
# Drop the CSV into 01_raw_data/서울_등록외국인_동별/.
#
# This parser auto-detects column layout and writes a long-format CSV:
#   03_cleaned_data/mois_seoul_dong_nationality.csv
#   schema: ref_date, sigungu, eupmyeondong, country, n
#
# If multiple CSV files are present in the folder, all are merged (different
# reference dates / quarters).

SEOUL_DONG_RAW = Path(ROOT) / "01_raw_data" / "서울_등록외국인_동별"
SEOUL_DONG_OUT = OUT_DIR / "mois_seoul_dong_nationality.csv"


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


def parse_seoul_dong_files():
    if not SEOUL_DONG_RAW.exists():
        SEOUL_DONG_RAW.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(list(SEOUL_DONG_RAW.glob("*.csv")) + list(SEOUL_DONG_RAW.glob("*.CSV")))
    if not csv_files:
        print(f"[NOTE] No CSV files in {SEOUL_DONG_RAW}.")
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
    out.to_csv(SEOUL_DONG_OUT, index=False, encoding="utf-8-sig")
    print(f"\nWrote {SEOUL_DONG_OUT}  ({len(out):,} rows; {out['ref_date'].nunique()} reference dates)")


# -- 에폭별 CSV -> 단일 long CSV ----------------------------------------------------
# Consolidate per-epoch MOIS CSVs into unified long-format outputs.
#
# Inputs (in 03_cleaned_data/):
#   mois_sido_2006.csv          (2006 only)
#   mois_sigungu_2006.csv
#   mois_sido_2007_2010.csv
#   mois_sigungu_2007_2010.csv
#   mois_sido_2011_2013.csv
#   mois_sigungu_2011_2013.csv
#   mois_sido_2014_2015.csv
#   mois_sigungu_2014_2015.csv
#   mois_eupmyeondong_2014_2015.csv
#   mois_sido_2016_2024.csv
#   mois_sigungu_2016_2024.csv
#   mois_eupmyeondong_2016_2024.csv
#   mois_multicultural_eupmyeondong_2016_2024.csv
#
# Outputs (overwrites in same folder):
#   mois_sido.csv             (2006-2024)
#   mois_sigungu.csv          (2006-2024)
#   mois_eupmyeondong.csv     (2014-2024)
#   mois_multicultural_eupmyeondong.csv   (2016-2024)
#
# Plus a coverage matrix for documentation:
#   mois_coverage.csv

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


def consolidate_epochs():
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


# -- 파편 CSV -> 주제별 tidy CSV ----------------------------------------------------
# Consolidate 39 fragmented MOIS CSVs → ~7 tidy thematic CSVs.
#
# Reduces the user-facing data surface to a small set of analyst-friendly long
# tables. Each thematic CSV is the single source of truth for its dimension.
#
# Output files in 03_cleaned_data/:
#   mois_population.csv           — all population categories × level × year
#                                    (year, level, sido, sigungu, eupmyeondong, category, sex, n)
#   mois_nationality.csv          — all country-based breakdowns with `group`
#                                    (year, level, sido, sigungu, eupmyeondong, group, country, sex, n)
#   mois_children_age.csv         — children by age 0-18
#                                    (year, level, sido, sigungu, age, sex, n)
#   mois_children_parent.csv      — children by parent type / parent nationality
#                                    (year, level, sido, sigungu, eupmyeondong, parent_type, country, sex, n)
#   mois_multicultural.csv        — multicultural household members (= old _eupmyeondong file)
#   mois_immigration_dynamics.csv — residence period + naturalization period
#                                    (year, sido, sigungu, dimension, dim_value, sex, n)
#
# Kept as-is (specialty derived):
#   mois_eupmyeondong_indices.csv
#   mois_eupmyeondong_enclaves.csv
#   mois_moj_validation.csv
#   mois_region_keys.csv
#   mois_coverage.csv
#
# Per-epoch intermediates (mois_*_2006.csv, ..._2007_2010.csv, ...) are moved to
# 03_cleaned_data/_mois_archive/ for reproducibility/debugging but out of the way.

# 03_cleaned_data. 위의 OUT_DIR 과 같은 폴더이고, 아래 통합 코드가 쓰던 이름이다.
DATA = OUT_DIR
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


def build_tidy_tables():
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


def reparse_mois_sources():
    """원자료 엑셀을 다시 읽어 03_cleaned_data/mois_*.csv 를 새로 쓴다.

    앞의 파서들이 에폭별 CSV 를 떨어뜨리고, consolidate_epochs() 가 그것을 합치고,
    build_tidy_tables() 가 주제별 tidy CSV 로 접은 다음 파편을 _mois_archive/ 로
    치운다. 그래서 순서를 바꾸면 안 된다.

    파이프라인 기본 실행 경로에는 없다. 새 연도 자료가 들어왔을 때만 --reparse 로 부른다.
    """
    steps = [
        parse_2006_totals,
        parse_2007_2010_totals,
        parse_2011_2013_totals,
        parse_2014_2015_totals,
        parse_2016plus_totals,
        parse_nationality_sheets,
        parse_children_age_sheets,
        parse_extra_dimensions,
        consolidate_epochs,
        extract_total_population,      # 주민등록인구 (외국인 비율 계산용 denominator)
        build_tidy_tables,             # 39 fragmented files -> 7 tidy thematic CSVs
        extract_bcnt_codes,            # in-house BCNT lookup from 2015 helper files
    ]
    for step in steps:
        print(f"\n{'=' * 60}\nRunning {step.__name__}\n{'=' * 60}")
        step()
    print("\nAll steps completed.")


# -- 레이어: 읍면동 이름 정규화, 키와 검증, 조립, 세종 보정, 패키징 ------------------------------------
_EMD_SUFFIXES = ("동", "읍", "면", "리", "출장소")


def _strip_gu_prefix(name, sigungu):
    """Drop a 일반구 that the source printed in front of a 읍면동 name.

    ('덕양구고양동', '고양시')       -> '고양동'   (2014 sheets: 시 only in sigungu)
    ('덕양구고양동', '고양시 덕양구') -> '고양동'   (2015 sheets: 구 in both places)
    ('구서1동', '금정구')            -> '구서1동'  (금정구 is a 자치구, not a 일반구)

    Only a district of the row's own 시 is stripped, and only when what is left is
    still a 읍/면/동/출장소, so a 동 whose own name opens with a 구 syllable is safe.
    """
    if not name or not sigungu:
        return name
    city = str(sigungu).split(" ")[0]
    for gu in sorted(GU_BY_CITY.get(city, ()), key=len, reverse=True):
        if name.startswith(gu) and len(name) > len(gu):
            rest = name[len(gu):]
            if rest.endswith(_EMD_SUFFIXES):
                return rest
    return name


def canonicalize_eupmyeondong_names():
    """Put a 일반구 the 2014-2015 sources printed inside the 읍면동 name back in sigungu.

    The 2014 and 2015 행정안전부 읍면동 sheets write the sub-district of a city with
    general districts as '덕양구 고양동', and the parser's whitespace strip glues that
    into '덕양구고양동'. In 2015 the district is also in `sigungu` ('고양시 덕양구'), so
    the glued copy is a mislabelled but single row; in 2014 `sigungu` is the bare city,
    so the glued name is a *second* key for a 동 that already exists, carrying only the
    세대수 the auxiliary sheet supplies and none of the population the main 유형별 sheet
    does. That is where the 434 value-less 2014 rows in summary_by_eupmyeondong.csv came
    from: 창원 62, 성남 48, 수원 40, 고양 39, 부천 36, 전주 33, and the rest.

    Names are canonicalized here, on the tidy tables, because this step owns the MOIS
    join keys and because the released `04_dataset_release/mois/` CSVs are copies of
    them. The parsers above now emit the canonical form directly, so on a
    build that re-parses the yearbooks this pass finds nothing and rewrites nothing.

    Only the 읍면동 name is touched. 시군구 names are left exactly as the edition
    printed them (인천 남구 until the 2018 rename, a bare 마산합포구 in 2024), because
    the levels are joined on `sigungu_code` from `admin_codes.py`, which resolves each
    edition's own spelling against that year's 법정동코드. An earlier version of this
    pass also rewrote 시군구, and its "attach the parent city to a bare 일반구" rule
    matched across provinces: 광주광역시 남구 and 대구광역시 북구 became 포항시 남구 and
    포항시 북구, which silently emptied the MOIS broad columns for those districts.

    A row that collides with an existing unstripped row once its district is removed is
    dropped: that is the 2014 세대수, which the auxiliary sheet 6 repeats for a 동 the
    main sheet already reported, and the main sheet is the one every other category
    comes from. Rows whose stripped name matches nothing (청주 강서1동, the 출장소
    branch offices) stay, value-less, as they were.
    """
    DATA = Path(ROOT) / "03_cleaned_data"
    # Every tidy MOIS table keyed by 읍면동. mois_region_keys*.csv are rebuilt from
    # mois_population.csv by the next function, so they are not listed here.
    FILES = [
        "mois_population.csv",          # + the collision rule, below
        "mois_total_pop.csv",
        "mois_nationality.csv",
        "mois_children_parent.csv",
        "mois_multicultural.csv",
        "mois_eupmyeondong_indices.csv",
        "mois_eupmyeondong_enclaves.csv",
    ]
    KEY = ["year", "level", "sido", "sigungu", "eupmyeondong", "category", "sex"]

    def renamed(chunk):
        chunk = chunk.copy()
        new = [_strip_gu_prefix(e, s)
               for e, s in zip(chunk["eupmyeondong"].astype(str), chunk["sigungu"].astype(str))]
        n = int((pd.Series(new, index=chunk.index) != chunk["eupmyeondong"]).sum())
        chunk["eupmyeondong"] = new
        return chunk, n

    print("\n===== canonicalize 읍면동 names (일반구 out of eupmyeondong) =====")
    for fn in FILES:
        p = DATA / fn
        if not p.exists():
            print(f"  {fn:<34s} MISSING")
            continue
        read = dict(dtype=str, keep_default_na=False, encoding="utf-8-sig", low_memory=False)
        if fn == "mois_population.csv":
            df = pd.read_csv(p, **read)
            if "eupmyeondong" not in df.columns:
                print(f"  {fn:<34s} no eupmyeondong column"); continue
            keep_keys = set(map(tuple, df.loc[
                [_strip_gu_prefix(e, s) == e for e, s in
                 zip(df["eupmyeondong"], df["sigungu"])], KEY].values))
            out, n_renamed = renamed(df)
            dup = pd.Series([tuple(r) in keep_keys for r in out[KEY].values], index=out.index)
            dup &= pd.Series([a != b for a, b in zip(out["eupmyeondong"], df["eupmyeondong"])],
                             index=out.index)
            n_dropped = int(dup.sum())
            if n_renamed == 0 and n_dropped == 0:
                print(f"  {fn:<34s} already canonical")
                continue
            out[~dup].to_csv(p, index=False, encoding="utf-8-sig")
            print(f"  {fn:<34s} {n_renamed:,} names fixed, "
                  f"{n_dropped:,} duplicate rows dropped ({len(out) - n_dropped:,} rows)")
            continue
        # Everything else: count first on two columns, and only rewrite if a name really
        # changes, so a canonical build does no IO. The rewrite streams, because the
        # nationality table is 318 MB and does not need to be resident.
        head = pd.read_csv(p, nrows=0, encoding="utf-8-sig")
        if "eupmyeondong" not in head.columns:
            print(f"  {fn:<34s} no eupmyeondong column")
            continue
        total = 0
        for chunk in pd.read_csv(p, chunksize=400_000,
                                 usecols=["sigungu", "eupmyeondong"], **read):
            total += renamed(chunk)[1]
        if not total:
            print(f"  {fn:<34s} already canonical")
            continue
        tmp = p.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
            for i, chunk in enumerate(pd.read_csv(p, chunksize=400_000, **read)):
                renamed(chunk)[0].to_csv(fh, index=False, header=(i == 0), lineterminator="\r\n")
        os.replace(tmp, p)
        print(f"  {fn:<34s} {total:,} names fixed")


def region_keys_and_validation():
    """Region keys for the MOIS layer, the codes on them, and the cross-check against MOJ.

    Three passes over the same tables, which only ever run together:

      1. A stable internal join key, `sido|sigungu|eupmyeondong`, on normalized names.
         MOIS publishes no official 행정동 code, so the key is name-based.
      2. The 행정구역코드 (BCNT, 7 digits) from the in-house 2015 lookup, which covers
         most regions in 2014-2024. Names that do not match get a blank code.
      3. MOIS 한국국적미취득자 against MOJ 등록외국인 at district level. The two are
         close but not equal by construction, since MOJ counts immigration registries
         and MOIS counts resident registries.
    """
    def build_region_keys():
        """Build stable region keys for MOIS data.

        Status: name-only normalization (no official 행정동 BCNT 5-digit code).
        True 행정동 코드 매핑은 외부 lookup 필요:
          - 행정안전부 표준 행정동 코드 (BCNT): https://www.code.go.kr/
          - 통계청 KOSTAT 코드: https://kssc.kostat.go.kr/
          - SGIS API (행정동 경계 자료): https://sgis.kostat.go.kr/

        This script generates a stable internal key for downstream joins:
          region_key = f"{canonical_sido}|{sigungu}|{eupmyeondong}"

        Outputs:
        - 03_cleaned_data/mois_region_keys.csv
          Columns: region_key, level (sigungu/eupmyeondong), sido, sigungu, eupmyeondong,
                   first_year, last_year, n_years_seen
        - 03_cleaned_data/mois_region_keys_dedup.csv:  unique (region_key, level) only

        Use this CSV as the join key between MOIS data and any geometry / external coding.
        A follow-up script (TBD) can later attach BCNT 5-digit codes by joining on
        canonical names to a KOSTAT lookup table.
        """
        HERE = os.path.dirname(os.path.abspath(__file__))
        DATA = os.path.join(ROOT, "03_cleaned_data")

        SIDO_CANON = {
            "강원도": "강원도",
            "강원특별자치도": "강원도",
            "전라북도": "전라북도",
            "전북특별자치도": "전라북도",
            "제주도": "제주특별자치도",
            "제주특별자치도": "제주특별자치도",
            "세종시": "세종특별자치시",
            "세종특별자치시": "세종특별자치시",
        }


        def canon(s):
            return SIDO_CANON.get(s, s)


        def main():
            pop = pd.read_csv(os.path.join(DATA, "mois_population.csv"))
            sigungu = pop[pop["level"] == "sigungu"][
                ["year", "sido", "sigungu"]].drop_duplicates()
            emd = pop[pop["level"] == "eupmyeondong"][
                ["year", "sido", "sigungu", "eupmyeondong"]].drop_duplicates()

            sigungu["sido_canon"] = sigungu["sido"].map(canon)
            emd["sido_canon"] = emd["sido"].map(canon)

            sigungu["region_key"] = (sigungu["sido_canon"] + "|" + sigungu["sigungu"]
                                      + "|" )
            emd["region_key"] = (emd["sido_canon"] + "|" + emd["sigungu"] + "|"
                                  + emd["eupmyeondong"])

            sigungu["level"] = "sigungu"; sigungu["eupmyeondong"] = ""
            emd["level"] = "eupmyeondong"

            cols = ["region_key", "level", "sido_canon", "sigungu", "eupmyeondong",
                    "year"]
            full = pd.concat([sigungu[cols], emd[cols]], ignore_index=True)
            full = full.rename(columns={"sido_canon": "sido"})

            # Aggregate
            grouped = full.groupby(["region_key", "level", "sido", "sigungu",
                                      "eupmyeondong"]).agg(
                first_year=("year", "min"),
                last_year=("year", "max"),
                n_years_seen=("year", "nunique"),
            ).reset_index()

            grouped = grouped.sort_values(["level", "sido", "sigungu", "eupmyeondong"])
            grouped.to_csv(os.path.join(DATA, "mois_region_keys.csv"),
                            index=False, encoding="utf-8-sig")
            # Also a unique-only version
            grouped[["region_key", "level", "sido", "sigungu", "eupmyeondong"]].to_csv(
                os.path.join(DATA, "mois_region_keys_dedup.csv"),
                index=False, encoding="utf-8-sig")

            print(f"Total unique region keys: {len(grouped):,}")
            print(grouped.groupby("level").size().rename("n_keys"))
            print()
            print(f"Examples (eupmyeondong, first 10):")
            print(grouped[grouped.level == "eupmyeondong"].head(10).to_string(index=False))

        main()



    def attach_bcnt_codes():
        """Attach 행정구역코드 (BCNT 7-digit) to MOIS region_keys.

        Uses the in-house lookup at 03_cleaned_data/mois_bcnt_codes_inhouse.csv
        (extracted from 2015 행안부 source files by extract_bcnt_codes(), above).

        The 2015 codes cover most regions present in 2014-2024 — code drift mainly
        comes from 2014→2024 boundary changes (Bucheon merger, 청주시 통합 등). For
        unmatched names we just emit blank `bcnt_code` and print a sample to console.

        If you obtain a fresh / authoritative external BCNT table from
        https://www.code.go.kr (행정안전부 표준 행정구역코드), drop it as
        external/bcnt_codes_external.csv with cols (sido, sigungu, eupmyeondong, code)
        — that takes precedence over the in-house lookup.

        Output: 03_cleaned_data/mois_region_keys_with_bcnt.csv
        """
        root = Path(ROOT)
        DATA = root / "03_cleaned_data"
        EXTERNAL = root / "external" / "bcnt_codes_external.csv"

        SIDO_CANON = {
            "강원도": "강원도", "강원특별자치도": "강원도",
            "전라북도": "전라북도", "전북특별자치도": "전라북도",
            "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
            "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
        }


        def canon(s):
            return SIDO_CANON.get(s, s) if isinstance(s, str) else s


        def _norm_name(s):
            return s.replace(" ", "") if isinstance(s, str) else s


        def main():
            keys = pd.read_csv(DATA / "mois_region_keys.csv")
            print(f"MOIS region keys: {len(keys):,} rows")

            # In-house lookup
            inhouse = pd.read_csv(DATA / "mois_bcnt_codes_inhouse.csv", dtype={"bcnt_code": str})
            print(f"In-house BCNT lookup: {len(inhouse):,} rows")

            # Optional external override
            if EXTERNAL.exists():
                ext = pd.read_csv(EXTERNAL, dtype={"code": str})
                ext = ext.rename(columns={"code": "bcnt_code"})
                ext["level"] = ext["eupmyeondong"].fillna("").apply(
                    lambda x: "eupmyeondong" if x else "sigungu"
                )
                for c in ("sido", "sigungu", "eupmyeondong"):
                    if c not in ext.columns:
                        ext[c] = ""
                # Combine: external first (precedence), then in-house
                merged_lookup = pd.concat(
                    [ext[["bcnt_code", "level", "sido", "sigungu", "eupmyeondong"]], inhouse],
                    ignore_index=True,
                ).drop_duplicates(subset=["level", "sido", "sigungu", "eupmyeondong"],
                                  keep="first")
                print(f"  (using external override: +{len(ext):,} external rows)")
            else:
                merged_lookup = inhouse

            # Normalize for join
            for d in (keys, merged_lookup):
                d["sido_canon"] = d["sido"].map(canon)
                d["sigungu_norm"] = d["sigungu"].fillna("").map(_norm_name)
                d["eupmyeondong_norm"] = d.get("eupmyeondong", "").fillna("").map(_norm_name)

            # Merge by level
            out_parts = []
            for level in ("sido", "sigungu", "eupmyeondong"):
                kk = keys[keys["level"] == level].copy()
                ll = merged_lookup[merged_lookup["level"] == level].copy()
                if level == "sido":
                    join_cols = ["sido_canon"]
                elif level == "sigungu":
                    join_cols = ["sido_canon", "sigungu_norm"]
                else:
                    join_cols = ["sido_canon", "sigungu_norm", "eupmyeondong_norm"]
                merged = kk.merge(ll[join_cols + ["bcnt_code"]], on=join_cols, how="left")
                n_match = merged["bcnt_code"].notna().sum()
                print(f"  {level}: {n_match:,}/{len(merged):,} ({n_match/len(merged)*100:.1f}%) matched")
                out_parts.append(merged)

            out = pd.concat(out_parts, ignore_index=True)
            out = out.drop(columns=["sido_canon", "sigungu_norm", "eupmyeondong_norm"])
            out.to_csv(DATA / "mois_region_keys_with_bcnt.csv",
                        index=False, encoding="utf-8-sig")
            print(f"\nWrote {DATA / 'mois_region_keys_with_bcnt.csv'}")

            # Spot-check unmatched
            unmatched = out[out["bcnt_code"].isna()]
            if len(unmatched):
                print(f"\nUnmatched: {len(unmatched):,} rows. Examples:")
                print(unmatched[["level", "sido", "sigungu", "eupmyeondong"]].head(15).to_string(index=False))

        main()



    def validate_against_moj():
        """Cross-validate MOIS 한국국적미취득자 against MOJ 등록외국인 at 시군구 level.

        Definitions:
        - MOJ = "등록외국인" (registered foreign nationals per 출입국통계연보, KIRD core).
        - MOIS 한국국적미취득_소계 = "한국국적을 가지지 않은 자" = roughly equivalent to MOJ
          registered foreigners, but counted via local government registries (resident
          registration), not immigration registries.

        The two should be CLOSE but not identical — they differ in:
        - short-term visitors / unregistered (MOJ has, MOIS does not)
        - residential vs immigration registration timing
        - different reference dates (MOJ: Dec 31; MOIS: Nov 1 since 2015)

        Output:
        - 03_cleaned_data/mois_moj_validation.csv: year, sido, sigungu, moj_n, mois_n, diff, pct_diff
        - console summary: median pct diff per year, top 20 districts with largest gap
        """
        HERE = os.path.dirname(os.path.abspath(__file__))
        DATA = os.path.join(ROOT, "03_cleaned_data")
        SITE = os.path.join(ROOT, "05_dashboard", "data")

        # Canonicalize sido names — KIRD (MOJ) uses old names; MOIS uses new specialty names from 2023+.
        SIDO_CANON = {
            "강원도": "강원도",
            "강원특별자치도": "강원도",
            "전라북도": "전라북도",
            "전북특별자치도": "전라북도",
            "제주도": "제주특별자치도",
            "제주특별자치도": "제주특별자치도",
            "세종시": "세종특별자치시",
            "세종특별자치시": "세종특별자치시",
        }


        def canon(s):
            return SIDO_CANON.get(s, s)


        def main():
            # ---- Load MOJ region.json ----
            with open(os.path.join(SITE, "region.json"), encoding="utf-8") as f:
                region = json.load(f)["by_sigungu"]

            moj_rows = []
            AGG = {"총계", "계", "소계", "총합계"}
            for year, sidos in region.items():
                for sido, sigungus in sidos.items():
                    for sigungu, countries in sigungus.items():
                        if sigungu in AGG:
                            continue
                        total = sum(v for k, v in countries.items() if k not in AGG)
                        moj_rows.append({"year": int(year), "sido": canon(sido),
                                         "sigungu": sigungu, "moj_n": total})
            moj = pd.DataFrame(moj_rows)
            print(f"MOJ rows: {len(moj):,}, years {moj['year'].min()}–{moj['year'].max()}")

            # ---- Load MOIS 시군구 한국국적미취득 ----
            mois = pd.read_csv(os.path.join(DATA, "mois_population.csv"))
            mois_nat = mois.query(
                "level == 'sigungu' and category == '한국국적미취득_소계' and sex == 'total'"
            )[["year", "sido", "sigungu", "n"]].rename(columns={"n": "mois_n"})
            mois_nat["sido"] = mois_nat["sido"].map(canon)
            print(f"MOIS rows: {len(mois_nat):,}, years {mois_nat['year'].min()}–{mois_nat['year'].max()}")

            # ---- Merge ----
            merged = moj.merge(mois_nat, on=["year", "sido", "sigungu"], how="outer")
            merged["diff"] = merged["mois_n"] - merged["moj_n"]
            merged["pct_diff"] = (merged["diff"] / merged["moj_n"] * 100).round(2)
            print(f"Merged: {len(merged):,} rows.  matched: {merged.dropna(subset=['moj_n','mois_n']).shape[0]:,}")

            merged = merged.sort_values(["year", "sido", "sigungu"])
            merged.to_csv(os.path.join(DATA, "mois_moj_validation.csv"),
                          index=False, encoding="utf-8-sig")

            # ---- Summary ----
            print("\n=== Summary ===")
            print("Median pct_diff (MOIS vs MOJ) by year — MOIS counts as % above/below MOJ:")
            by_yr = merged.dropna(subset=["pct_diff"]).groupby("year")["pct_diff"].describe()[
                ["count", "mean", "50%", "min", "max"]
            ]
            print(by_yr.round(2).to_string())

            # ---- Unmatched rows ----
            only_moj = merged[merged["mois_n"].isna()][["year", "sido", "sigungu"]]
            only_mois = merged[merged["moj_n"].isna()][["year", "sido", "sigungu"]]
            print(f"\nOnly in MOJ (no MOIS match): {len(only_moj):,} district-years")
            if len(only_moj):
                print(only_moj.head(10).to_string(index=False))
            print(f"\nOnly in MOIS (no MOJ match): {len(only_mois):,} district-years")
            if len(only_mois):
                print(only_mois.head(10).to_string(index=False))

            # ---- Top 20 largest gaps for latest year ----
            last_yr = int(merged["year"].max())
            big = merged[(merged["year"] == last_yr) & merged["moj_n"].notna() &
                          merged["mois_n"].notna()].copy()
            big["abs_diff"] = big["diff"].abs()
            print(f"\nTop 15 largest absolute gaps in {last_yr}:")
            print(big.nlargest(15, "abs_diff")[["sido", "sigungu", "moj_n", "mois_n", "diff", "pct_diff"]].to_string(index=False))

        main()

    build_region_keys()
    attach_bcnt_codes()
    validate_against_moj()



def build_layer():
    """Build the MOIS sibling layer for the KIRD dashboard.

    Reads from 03_cleaned_data/mois_*.csv (written by the parsers above, under --reparse),
    writes JSON files to site/data/mois/ with shapes compatible with the existing
    dashboard's loaders.

    This is the orchestrator. Two upstream scripts are dependencies:
    - scripts/mois_validate_against_moj.py   (validation report)
    - scripts/mois_eupmyeondong_indices.py   (read-only; writes its own indices JSON)

    Output files:
      site/data/mois/sigungu_population.json
      site/data/mois/eupmyeondong_population.json
      site/data/mois/sigungu_nationality.json
      site/data/mois/eupmyeondong_nationality.json   (2014-2015 only)
      site/data/mois/children_age_sigungu.json
      site/data/mois/residence_period_sigungu.json
      site/data/mois/multicultural_eupmyeondong.json
      site/data/mois/summary.json
      site/data/mois/manifest.json    (lists all available datasets + years)

    Shape convention (matches KIRD's region.json pattern):
      by_sigungu: { year: { sido: { sigungu: { key: value, ... }, ... }, ... }, ... }
      by_eupmyeondong: { year: { sido: { sigungu: { eupmyeondong: {...} } } } }
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    DATA = os.path.join(ROOT, "03_cleaned_data")
    SITE = os.path.join(ROOT, "05_dashboard", "data", "mois")
    os.makedirs(SITE, exist_ok=True)

    SIDO_CANON = {
        "강원도": "강원도", "강원특별자치도": "강원도",
        "전라북도": "전라북도", "전북특별자치도": "전라북도",
        "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
        "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    }


    def canon(s):
        return SIDO_CANON.get(s, s)


    def nested():
        return defaultdict(nested)


    def to_dict(d):
        if isinstance(d, defaultdict):
            d = {k: to_dict(v) for k, v in d.items()}
        return d


    def _dump(path, obj):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  wrote {os.path.basename(path)}  ({os.path.getsize(path)/1024:.1f} KB)")


    def _load_population():
        return pd.read_csv(os.path.join(DATA, "mois_population.csv"))


    def _load_nationality():
        return pd.read_csv(os.path.join(DATA, "mois_nationality.csv"))


    def build_sigungu_population():
        raw = _load_population()
        df = raw[(raw["level"] == "sigungu") & (raw["sex"] == "total")].copy()
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.category] = int(r.n)
        # 세종특별자치시: the source labels its city row 세종특별자치시, so the parsers
        # emit it at sido level only and no sigungu row exists. Copy the published sido
        # row in as 세종시 (the city IS the province). Do NOT sum its eup/myeon/dong
        # instead — that drops the masked (***) cells and undercounts the components.
        sj = raw[(raw["level"] == "sido") & (raw["sex"] == "total")
                 & (raw["sido"].map(canon) == "세종특별자치시")]
        for _, r in sj.iterrows():
            nest[int(r.year)]["세종특별자치시"]["세종시"].setdefault(r.category, int(r.n))
        # Merge in 주민등록인구 from mois_total_pop.csv if available
        tp_path = os.path.join(DATA, "mois_total_pop.csv")
        if os.path.exists(tp_path):
            tp = pd.read_csv(tp_path)
            tp = tp[tp["level"] == "sigungu"].copy()
            tp["sido"] = tp["sido"].map(canon)
            for _, r in tp.iterrows():
                nest[int(r.year)][r.sido][r.sigungu]["주민등록인구"] = int(r.total_pop)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "sigungu_population.json"), out)


    def build_eupmyeondong_population():
        df = _load_population()
        df = df[(df["level"] == "eupmyeondong")]
        df = df[df["sex"].isna() | (df["sex"] == "total")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong][r.category] = int(r.n)
        # Merge in 주민등록인구 (total_pop) as additional category if available
        tp_path = os.path.join(DATA, "mois_total_pop.csv")
        if os.path.exists(tp_path):
            tp = pd.read_csv(tp_path)
            tp = tp[tp["level"] == "eupmyeondong"].copy()
            tp["sido"] = tp["sido"].map(canon)
            for _, r in tp.iterrows():
                nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong]["주민등록인구"] = int(r.total_pop)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_eupmyeondong": to_dict(nest)}
        _dump(os.path.join(SITE, "eupmyeondong_population.json"), out)


    def build_sigungu_nationality():
        df = _load_nationality()
        df = df[(df["level"] == "sigungu") & (df["sex"] == "total") &
                (df["group"] == "all_foreign")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.country] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "sigungu_nationality.json"), out)


    def build_eupmyeondong_nationality():
        df = _load_nationality()
        df = df[(df["level"] == "eupmyeondong") & (df["sex"] == "total") &
                (df["group"] == "all_foreign")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong][r.country] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_eupmyeondong": to_dict(nest)}
        _dump(os.path.join(SITE, "eupmyeondong_nationality.json"), out)


    def build_children_age_sigungu():
        df = pd.read_csv(os.path.join(DATA, "mois_children_age.csv"))
        df = df[(df["level"] == "sigungu") & (df["sex"] == "total")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][str(int(r.age))] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "children_age_sigungu.json"), out)


    def build_residence_period_sigungu():
        df = pd.read_csv(os.path.join(DATA, "mois_immigration_dynamics.csv"))
        df = df[(df["dimension"] == "residence_period") & (df["sex"] == "total")]
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.dim_value] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_sigungu": to_dict(nest)}
        _dump(os.path.join(SITE, "residence_period_sigungu.json"), out)


    def build_multicultural_eupmyeondong():
        df = pd.read_csv(os.path.join(DATA, "mois_multicultural.csv"))
        df["sido"] = df["sido"].map(canon)
        nest = nested()
        for _, r in df.iterrows():
            nest[int(r.year)][r.sido][r.sigungu][r.eupmyeondong][r.category] = int(r.n)
        out = {"years": sorted(set(int(y) for y in df["year"].unique())),
               "by_eupmyeondong": to_dict(nest)}
        _dump(os.path.join(SITE, "multicultural_eupmyeondong.json"), out)


    def build_summary():
        """Top-line annual summary for landing-page use. Sums 시도-level data."""
        pop = _load_population()
        sido = pop[(pop["level"] == "sido") & (pop["sex"] == "total") &
                    (pop["category"] == "합계")].copy()
        sido["sido"] = sido["sido"].map(canon)
        by_year_national = sido.groupby("year")["n"].sum().astype(int).to_dict()

        breakdown_cats = ["한국국적미취득_소계", "한국국적취득자", "외국인주민자녀"]
        s2 = pop[(pop["level"] == "sido") & (pop["sex"] == "total") &
                  (pop["category"].isin(breakdown_cats))].copy()
        s2["sido"] = s2["sido"].map(canon)
        breakdown = (s2.groupby(["year", "category"])["n"].sum().unstack()
                       .fillna(0).astype(int))

        out = {
            "national_total_by_year": {int(k): int(v) for k, v in by_year_national.items()},
            "breakdown_by_year": {
                int(y): breakdown.loc[y].to_dict() for y in breakdown.index
            },
        }
        _dump(os.path.join(SITE, "summary.json"), out)


    def build_manifest():
        files = sorted(os.listdir(SITE))
        manifest = {
            "datasets": [],
            "source": "행정안전부 「지방자치단체 외국인주민 현황」 (Ministry of the Interior and Safety)",
            "note": "MOIS broad-definition 외국인주민 (외국인 + 한국국적 취득자 + 외국인주민 자녀). NOT directly comparable to MOJ 등록외국인. See mois_moj_validation.csv for cross-source comparison.",
        }
        for f in files:
            if f == "manifest.json" or not f.endswith(".json"):
                continue
            path = os.path.join(SITE, f)
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            manifest["datasets"].append({
                "file": f,
                "size_kb": round(os.path.getsize(path) / 1024, 1),
                "years": d.get("years") if isinstance(d, dict) else None,
            })
        _dump(os.path.join(SITE, "manifest.json"), manifest)


    def main():
        print("Building MOIS sibling layer for KIRD dashboard…\n")
        build_sigungu_population()
        build_eupmyeondong_population()
        build_sigungu_nationality()
        build_eupmyeondong_nationality()
        build_children_age_sigungu()
        build_residence_period_sigungu()
        build_multicultural_eupmyeondong()
        build_summary()
        build_manifest()
        print(f"\nAll JSON files in {SITE}")

    main()



def sejong_patches():
    """세종특별자치시 patches on the MOIS layer.

    Sejong is a self-governing city with no districts below it, so the MOIS parsers
    skip it wherever they key on 시군구, and MOIS lists Sejong only from 2013. Three
    patches put it back, and they have to run in this order because the first two
    both write `children_age_sigungu.json`:

      1. 연기군 backfill. Sejong was created 2012-07-01, mostly out of 연기군 plus
         parts of 공주시 and 청원군. 2006-2012 sigungu_population and 2011-2012
         children_age are copied from 연기군, and the real 2013 Sejong row is pulled
         off the province sheet, where it had been filed for want of a district.
         연기군 stays under 충청남도, which is the historical fact; only the Sejong
         copy is added. The sub-district and multicultural layers start in 2014 and
         2016, so there is no 연기군 predecessor to backfill them from.
      2. Sub-districts. Sejong's 읍면동 rows, extracted with the same parsers and
         injected into `eupmyeondong_population.json`.
      3. Children by age and multicultural households, same treatment.

    No other province is touched by any of the three.
    """
    MOIS = os.path.join(ROOT, "05_dashboard", "data", "mois")
    SP = os.path.join(MOIS, "sigungu_population.json")
    CA = os.path.join(MOIS, "children_age_sigungu.json")
    EMD = os.path.join(MOIS, "eupmyeondong_population.json")
    MC = os.path.join(MOIS, "multicultural_eupmyeondong.json")


    def load(p):
        return json.load(open(p, encoding="utf-8"))


    def save(obj, p):
        json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


    def backfill_from_yeongi():
        print("1) 연기군 -> 세종 backfill")
        sp = load(SP)
        BY = sp["by_sigungu"]
        n_bf = 0
        for y in [str(x) for x in range(2006, 2013)]:
            yg = (BY.get(y, {}).get("충청남도", {}) or {}).get("연기군")
            if yg is None:
                continue
            BY[y].setdefault("세종특별자치시", {})["세종시"] = dict(yg)
            n_bf += 1
        # the real 2013 Sejong, off the province sheet
        rows = _parse_sigungu_or_sido_sheet(RAW_DIR / "2013_외국인주민통계.xlsx", 2013,
                                            "1.조사총괄표(시도)", level="sido")
        rec13 = {r["category"]: r["n"] for r in rows
                 if r.get("sido") == "세종특별자치시" and r.get("sex") == "total"}
        # the province sheet carries only the total; the district sheet's col1
        # (주민등록인구) is 113,117
        rec13.setdefault("주민등록인구", 113117)
        if "세종특별자치시" not in BY.get("2013", {}) and rec13.get("합계"):
            BY.setdefault("2013", {}).setdefault("세종특별자치시", {})["세종시"] = rec13
            print("   sigungu_population 2013 세종:", rec13.get("합계"))
        print(f"   sigungu_population backfilled {n_bf} years (2006-2012)")
        save(sp, SP)

        ca = load(CA)
        CBY = ca["by_sigungu"]
        n_ca = 0
        for y in ["2011", "2012"]:
            yg = (CBY.get(y, {}).get("충청남도", {}) or {}).get("연기군")
            if yg is None:
                continue
            CBY[y].setdefault("세종특별자치시", {})["세종시"] = dict(yg)
            n_ca += 1
        print(f"   children_age backfilled {n_ca} years (2011-2012)")
        save(ca, CA)


    def inject_eupmyeondong():
        print("2) 세종 읍면동 -> eupmyeondong_population.json")
        def collect(rows):
            out = {}
            for r in rows:
                if r.get("sido") != "세종특별자치시":
                    continue
                d = out.setdefault(r["eupmyeondong"], {})
                d[r["category"]] = d.get(r["category"], 0) + r["n"]
            return out

        by_year = {}
        for y in range(2016, 2026):
            # MOIS publishes later than MOJ, so the newest years have no source file
            try:
                by_year[y] = collect(parse_year(y).get("eupmyeondong", []))
            except FileNotFoundError:
                print(f"   skip {y}: no MOIS source file yet")
        by_year[2014] = collect(parse_2014().get("eupmyeondong", []))
        by_year[2015] = collect(parse_2015().get("eupmyeondong", []))

        j = load(EMD)
        emd = j["by_eupmyeondong"]
        added = 0
        for y, dongs in by_year.items():
            yk = str(y)
            if yk not in emd or not dongs:
                if dongs:
                    print(f"   ! year {yk} not in JSON, skipping {len(dongs)} 세종 dongs")
                continue
            emd[yk].setdefault("세종특별자치시", {})["세종시"] = {
                d: {k: v for k, v in vals.items()} for d, vals in dongs.items()}
            added += len(dongs)
            print(f"   {yk}: 세종 {len(dongs)} dongs")
        save(j, EMD)
        print(f"   total dong-years injected: {added}")


    def inject_children_and_multicultural():
        print("3) 세종 children_age + multicultural")
        ca = load(CA)
        ca_added = 0
        for y, info in AGE_SHEETS.items():
            yk = str(y)
            if yk not in ca["by_sigungu"]:
                continue
            fname, sido_sheet, sg = info
            if isinstance(sg, tuple):
                path, sheet = RAW_DIR / sg[0], sg[1]
            else:
                path, sheet = RAW_DIR / fname, sg
            if not sheet:
                continue
            try:
                rows = _parse_age_sheet(path, y, sheet, emit_levels=("sigungu",))
            except Exception as e:
                print(f"   WARN children_age {yk}: {e}")
                continue
            ages = {}
            for r in rows:
                if r["sido"] != "세종특별자치시" or r.get("sex") != "total":
                    continue
                ages[r["age"]] = max(ages.get(r["age"], 0), r["n"])  # duplicate rows: keep the max
            if ages:
                ca["by_sigungu"][yk].setdefault("세종특별자치시", {})["세종시"] = ages
                ca_added += 1
                print(f"   children_age {yk}: 세종 {len(ages)} ages")
        save(ca, CA)

        mc = load(MC)
        mc_added = 0
        for y in range(2016, 2026):
            yk = str(y)
            if yk not in mc["by_eupmyeondong"]:
                continue
            try:
                rows = parse_year(y).get("multicultural", [])
            except Exception as e:
                print(f"   WARN multicultural {yk}: {e}")
                continue
            dongs = {}
            for r in rows:
                if r["sido"] != "세종특별자치시":
                    continue
                dongs.setdefault(r["eupmyeondong"], {})[r["category"]] = r["n"]
            if dongs:
                mc["by_eupmyeondong"][yk].setdefault("세종특별자치시", {})["세종시"] = dongs
                mc_added += 1
                print(f"   multicultural {yk}: 세종 {len(dongs)} dongs")
        save(mc, MC)
        print(f"   children_age years +{ca_added}, multicultural years +{mc_added}")

    backfill_from_yeongi()
    inject_eupmyeondong()
    inject_children_and_multicultural()
    print("done.")



def package_for_release():
    """The MOIS layer packaged for release, as CSV and as Parquet.

    The CSVs stay in 03_cleaned_data for anyone loading them with pandas; the
    release folder also carries Parquet, which is around a tenth of the size and
    faster to read column-wise. The MOIS layer is released beside the KIRD core
    rather than inside it, because it counts a different population.
    """
    def package_release():
        """Package the MOIS layer as a separate `04_dataset_release/mois/` for public release
        (parallel to KIRD core; separate Zenodo DOI recommended due to definition gap).
        """
        root = Path(ROOT)
        DATA = root / "03_cleaned_data"
        OUT = root / "04_dataset_release" / "mois"
        OUT_DATA = OUT / "data"

        TIDY_FILES = [
            "mois_population.csv",
            "mois_nationality.csv",
            "mois_children_age.csv",
            "mois_children_parent.csv",
            "mois_multicultural.csv",
            "mois_immigration_dynamics.csv",
            "mois_eupmyeondong_indices.csv",
            "mois_eupmyeondong_enclaves.csv",
            "mois_region_keys.csv",
            "mois_moj_validation.csv",
            "mois_coverage.csv",
        ]


        def copy_data():
            OUT_DATA.mkdir(parents=True, exist_ok=True)
            for fn in TIDY_FILES:
                src = DATA / fn
                if not src.exists():
                    print(f"  MISSING: {fn}")
                    continue
                shutil.copy2(src, OUT_DATA / fn)
                size_kb = (OUT_DATA / fn).stat().st_size / 1024
                print(f"  copied {fn:<45s} ({size_kb:.1f} KB)")


        README_MD = """# KIRD-MOIS: Korean Foreign Resident Statistics (행정안전부 외국인주민통계) Tidy Dataset, 2006-2024

A long-format, analyst-ready re-release of the 행정안전부 「지방자치단체 외국인주민 현황」
(MOIS Foreign Resident Statistics) covering 2006-2024 at the sub-district level.

**This is a sibling layer to the KIRD core dataset** (which is built on Ministry
of Justice 출입국통계연보). The two should NOT be merged: MOJ counts registered
foreign nationals only; MOIS counts the broader 외국인주민 population which also
includes naturalized Koreans and their domestically-born children.

- **DOI:** TBD (separate Zenodo release recommended)
- **Source:** Ministry of the Interior and Safety (MOIS) annual 외국인주민 현황 surveys
- **Population definition:** 외국인주민 = 한국국적 미취득자 (foreign nationals) +
  한국국적 취득자 (naturalized) + 외국인주민 자녀 (children born to immigrant parents)

## Files (data/)

| File | Unit | Years | Rows |
|---|---|---|---|
| `mois_population.csv` | year × level × region × category × sex | 2006-2024 | 710K |
| `mois_nationality.csv` | year × level × region × group × country × sex | 2009-2024 | 4.1M |
| `mois_children_age.csv` | year × level × region × age × sex | 2011-2024 | 200K |
| `mois_children_parent.csv` | year × level × region × parent_type × country × sex | 2009-2024 | 1.0M |
| `mois_multicultural.csv` | year × eupmyeondong × multicultural-household role | 2016-2024 | 298K |
| `mois_immigration_dynamics.csv` | year × sigungu × dimension × dim_value × sex | 2016-2024 | 47K |
| `mois_eupmyeondong_indices.csv` | year × eupmyeondong diversity indices | 2014-2015 | 7K |
| `mois_eupmyeondong_enclaves.csv` | enclave (LQ≥2, share≥30%, n≥30) tuples | 2014-2015 | 1.5K |
| `mois_region_keys.csv` | unique region keys with first/last year seen | — | 5.5K |
| `mois_moj_validation.csv` | per-district MOJ vs MOIS comparison | 2008-2024 | 4.5K |
| `mois_coverage.csv` | per-year/level/category coverage matrix | — | 49 |

## Long-format schema

All files share the same conventions:
- `year` (int): reference year
- `level` (str): `sido` / `sigungu` / `eupmyeondong`
- `sido` (str): province (canonicalized; 강원특별자치도 → 강원도, 전북특별자치도 → 전라북도,
  제주도 → 제주특별자치도, 세종시 → 세종특별자치시)
- `sigungu` (str): municipality (blank for sido-level rows; 100만-도시 sub-구s are
  rendered as `수원시 장안구` etc. with a space)
- `eupmyeondong` (str): sub-district (blank for higher levels)
- `category` / `country` / `age` / `dim_value` / `parent_type` (varies by file): the
  pivot dimension
- `sex` (str): `total` / `M` / `F`
- `n` (int): count (suppressed `*` values become missing rows, not zeros)

## Six dimensions captured by MOIS that MOJ does not

1. **한국국적취득자 (naturalized Koreans)** at sigungu level, 2006-2024 — MOJ stops
   tracking foreign nationals at naturalization.
2. **외국인주민 자녀 (children of foreign residents)**, by age 0-18, 2011-2024 —
   2nd-generation immigrant population.
3. **Parent type (외국인부모 / 외-한국인부모 / 한국인부모)** — composition of mixed-status
   households.
4. **Sub-district (읍면동) granularity, 2014-2015** — district-below-sigungu detail
   not available in MOJ data.
5. **다문화가구 (multicultural-household members)** by role (한국인배우자, 결혼이민자,
   귀화자, 자녀 등) at the eupmyeondong level, 2016-2024.
6. **귀화자 이전국적 (previous nationality of naturalized Koreans)** at sigungu, 2016-2024.

## Known limitations

- 2016 methodology change: MOIS shifted to a 인구주택총조사 (Population & Housing
  Census) basis, capturing ~30-45% more 한국국적미취득자 than MOJ counts. See
  `mois_moj_validation.csv` for per-district divergence.
- 2008 sigungu-level MOIS data is unavailable in our parse window (sigungu series
  starts 2009).
- 5,226 unique eupmyeondong names; no official BCNT 5-digit administrative codes
  are attached (KIRD geometry joins require external lookup).
- "기타" continent residuals are not disambiguated in `mois_nationality.csv` —
  multiple "기타" sub-categories from different continents lump together.

## Reproducing this dataset

Build from raw Excel yearbooks in `01_raw_data/행정안전부 외국인주민통계/`:

```bash
python 02_code/05_mois_layer.py --reparse   # raw → 03_cleaned_data/mois_*.csv
python 02_code/05_mois_layer.py             # → 05_dashboard/data/mois/ and
                                            #   04_dataset_release/mois/
```

Both live in `02_code/05_mois_layer.py`, whose module docstring carries the
full description of the pipeline.

## Citation

```
Yoo, N. (2026). KIRD-MOIS: Korean Foreign Resident Statistics Tidy Dataset, 2006-2024
[Data set]. Zenodo. https://doi.org/[TBD]
```

## License

CC BY 4.0 (matching KIRD core). Underlying data is published by the Korean
Ministry of the Interior and Safety as open public data.
"""


        CITATION_CFF = """cff-version: 1.2.0
title: "KIRD-MOIS: Korean Foreign Resident Statistics Tidy Dataset, 2006-2024"
message: "If you use this dataset, please cite it as below."
type: dataset
authors:
  - family-names: Yoo
    given-names: Nari
    orcid: "https://orcid.org/0000-0002-9020-8061"
    affiliation: "University of Michigan School of Social Work"
date-released: 2026
repository-code: "https://github.com/nariyoo/kird-korea-immigration"
keywords:
  - immigration
  - foreign residents
  - Korea
  - 외국인주민
  - diversity
  - residential segregation
  - sub-district
  - eupmyeondong
license: CC-BY-4.0
"""


        def write_metadata():
            (OUT / "README.md").write_text(README_MD, encoding="utf-8")
            (OUT / "CITATION.cff").write_text(CITATION_CFF, encoding="utf-8")
            # Copy LICENSE from KIRD core
            src_lic = root / "04_dataset_release" / "LICENSE"
            if src_lic.exists():
                shutil.copy2(src_lic, OUT / "LICENSE")
            print(f"  wrote README.md, CITATION.cff, LICENSE")


        def write_data_dictionary():
            """Long-format data dictionary."""
            import csv
            rows = [
                ("file", "variable", "type", "description"),
                ("(all files)", "year", "integer", "Reference year (2006-2024)"),
                ("(all files)", "level", "string", "Administrative level: sido / sigungu / eupmyeondong"),
                ("(all files)", "sido", "string", "Province name (canonicalized — 강원특별자치도→강원도, 전북특별자치도→전라북도, 제주도→제주특별자치도, 세종시→세종특별자치시)"),
                ("(all files)", "sigungu", "string", "Municipality (blank when level=sido). 100만-도시 sub-구s rendered as '수원시 장안구' etc."),
                ("(all files)", "eupmyeondong", "string", "Sub-district (blank when level≠eupmyeondong)"),
                ("(all files)", "sex", "string", "total / M / F. For rows without sex breakdown, total only."),
                ("(all files)", "n", "integer", "Count. Suppressed source values (*) are excluded as missing rows."),
                # population
                ("mois_population.csv", "category", "string", "합계 (total 외국인주민) / 한국국적미취득_소계 / 외국인근로자 / 결혼이민자 / 유학생 / 외국국적동포 / 기타외국인 / 한국국적취득자 / 혼인귀화자 / 기타귀화자 / 외국인주민자녀 / 자녀_외국인부모 / 자녀_외한국인부모 / 자녀_한국인부모 / 세대수"),
                # nationality
                ("mois_nationality.csv", "group", "string", "Subpopulation: all_foreign / workers / marriage / students / overseas_koreans / other_foreign / naturalized / children / naturalized_prev"),
                ("mois_nationality.csv", "country", "string", "Nationality (Korean label). '기타' may collapse different continent residuals."),
                # children
                ("mois_children_age.csv", "age", "integer", "Age 0-18 (years)"),
                ("mois_children_parent.csv", "parent_type", "string", "외국인부모 / 외-한국인부모 / 한국인부모 (2014-2015 읍면동); 귀화·인지및외국국적 / 국내출생 (2016+ 시군구)"),
                ("mois_children_parent.csv", "country", "string", "Country (only for 2014-2015 읍면동; blank for 2016+ 시군구)"),
                # multicultural
                ("mois_multicultural.csv", "category", "string", "Multicultural household role: 한국인배우자 / 결혼이민자 / 귀화자등 / 자녀_귀화인지외국국적 / 자녀_국내출생 / 기타동거인_내국인 / 기타동거인_외국인 / etc."),
                # immigration_dynamics
                ("mois_immigration_dynamics.csv", "dimension", "string", "residence_period (체류기간) or naturalization_period (국적취득경과기간)"),
                ("mois_immigration_dynamics.csv", "dim_value", "string", "Period label, e.g., '5년이상~10년미만', '10년이상'"),
                # indices
                ("mois_eupmyeondong_indices.csv", "shannon_h", "float", "Shannon entropy over country distribution within the eupmyeondong"),
                ("mois_eupmyeondong_indices.csv", "hhi", "float", "Herfindahl-Hirschman index on nationality shares"),
                ("mois_eupmyeondong_indices.csv", "pielou_evenness", "float", "Pielou's evenness = H / ln(k), k = number of nonzero countries"),
                ("mois_eupmyeondong_indices.csv", "top_country_share", "float", "Share of the largest country in the eupmyeondong"),
                # enclaves
                ("mois_eupmyeondong_enclaves.csv", "lq", "float", "Location quotient: (district country share) / (national country share)"),
                ("mois_eupmyeondong_enclaves.csv", "local_share", "float", "Country's share within the eupmyeondong's foreign population (≥0.30 by criterion)"),
                # region_keys
                ("mois_region_keys.csv", "region_key", "string", "Stable join key: '{sido}|{sigungu}|{eupmyeondong}'"),
                ("mois_region_keys.csv", "first_year/last_year/n_years_seen", "integer", "Temporal coverage of the region across the MOIS series"),
                # validation
                ("mois_moj_validation.csv", "moj_n", "integer", "MOJ 등록외국인 count for the sigungu (from KIRD region.json sum)"),
                ("mois_moj_validation.csv", "mois_n", "integer", "MOIS 한국국적미취득_소계 count (from mois_population.csv)"),
                ("mois_moj_validation.csv", "diff/pct_diff", "float", "mois_n minus moj_n (raw and percentage)"),
            ]
            with (OUT / "data_dictionary.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerows(rows)
            print("  wrote data_dictionary.csv")


        def main():
            print(f"Packaging MOIS layer → {OUT}\n")
            OUT.mkdir(parents=True, exist_ok=True)
            copy_data()
            write_metadata()
            write_data_dictionary()
            print(f"\nDone. {OUT}")

        main()



    def write_parquet():
        """Convert large MOIS CSVs to Parquet for the 04_dataset_release/.

        CSV files stay in 03_cleaned_data/ for analyst friendliness (pandas-load-anywhere),
        but Parquet versions go to 04_dataset_release/mois/data/ for size reduction (~10x)
        and for users wanting faster columnar reads.
        """
        root = Path(ROOT)
        DATA = root / "03_cleaned_data"
        OUT_DATA = root / "04_dataset_release" / "mois" / "data"
        OUT_DATA.mkdir(parents=True, exist_ok=True)

        # All tidy thematic files — convert each
        FILES = [
            "mois_population.csv",
            "mois_nationality.csv",
            "mois_children_age.csv",
            "mois_children_parent.csv",
            "mois_multicultural.csv",
            "mois_immigration_dynamics.csv",
            "mois_eupmyeondong_indices.csv",
            "mois_eupmyeondong_enclaves.csv",
            "mois_moj_validation.csv",
            "mois_region_keys.csv",
            "mois_coverage.csv",
        ]


        def main():
            for fn in FILES:
                src = DATA / fn
                if not src.exists():
                    print(f"  MISSING: {fn}")
                    continue
                df = pd.read_csv(src, low_memory=False)
                # Cast known integer cols where possible to int32 for compression
                for col in ("year", "n"):
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")
                if "age" in df.columns:
                    df["age"] = pd.to_numeric(df["age"], errors="coerce").astype("Int8")
                out = OUT_DATA / (fn.replace(".csv", ".parquet"))
                df.to_parquet(out, engine="pyarrow", compression="zstd", index=False)
                csv_kb = src.stat().st_size / 1024
                pq_kb = out.stat().st_size / 1024
                ratio = csv_kb / pq_kb if pq_kb > 0 else 0
                print(f"  {fn:<42s}  csv {csv_kb:>9.1f} KB  →  parquet {pq_kb:>9.1f} KB  ({ratio:.1f}x)")

        main()

    package_release()
    write_parquet()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reparse", action="store_true",
                    help="원자료 엑셀을 다시 읽어 03_cleaned_data/mois_*.csv 를 새로 쓴다")
    args = ap.parse_args()
    if args.reparse:
        reparse_mois_sources()
    else:
        canonicalize_eupmyeondong_names()
        region_keys_and_validation()
        build_layer()
        sejong_patches()
        package_for_release()
