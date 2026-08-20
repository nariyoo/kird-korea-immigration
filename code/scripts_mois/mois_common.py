"""Shared helpers for parsing MOIS 외국인주민통계 files (2006-2024).

Output convention:
- Population data → long CSVs by admin level:
  - mois_sido.csv:         year, sido, category, sex, n
  - mois_sigungu.csv:      year, sido, sigungu, category, sex, n
  - mois_eupmyeondong.csv: year, sido, sigungu, eupmyeondong, category, n
- Children:
  - mois_children_sigungu.csv (by parent origin / age group / nationality)
- Multicultural households (2016+):
  - mois_multicultural_eupmyeondong.csv
"""
from __future__ import annotations
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from kird import ROOT as _ROOT  # noqa: E402
import re
from pathlib import Path

RAW_DIR = Path(_ROOT) / "01_raw_data" / "행정안전부 외국인주민통계"
OUT_DIR = Path(_ROOT) / "03_cleaned_data"

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
