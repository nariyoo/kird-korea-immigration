"""The shared module: paths, reference tables, and the index formulas.

Formerly three files (kird_paths, kird_lookups, kird_indices), merged 2026-08-18
so the bundle carries one module beside the numbered steps.

PATHS. Every location, resolved from the project root, which is found from this
file's own position; set KIRD_ROOT to build a different checkout.

REFERENCE TABLES. The maps that decide how the yearbooks join to each other.
Every step imports the same copy, which is the point: they used to live inside
the parser and fifteen scripts pulled them back out by regex and exec.

  COUNTRY_CANONICAL  variant Korean country names -> one name per country
  COUNTRY_REGION     nationality -> world region
  COUNTRY_LANGUAGE   nationality -> single fallback language, used where
                     Ethnologue has no first-language shares for the country
  LANG_EN_KO         Ethnologue English language name -> Korean label
  SIDO_EN            province -> released romanization (Gyeonggi-do)
  SIDO_EN_SHORT      province -> the dashboard's short form (Gyeonggi)

INDEX FORMULAS. shannon, incl, cont, hhi, pielou, make_record, morans_i. One
copy, so a district in 2009 and the same district in 2019 are measured
identically. The rounding is part of the definition, because the released
columns are rounded and the dashboard reads the same numbers.

ADMINISTRATIVE CODES. The per-year official codes the released tables are joined
on, formerly admin_codes.py, mois_geocode.py and fetch_admin_codes.py, folded in
on 2026-08-20 so the published bundle is the numbered steps plus this module.
The order below is the order a reader needs: the name normalization every layer
shares, then the 2024 boundary anchor, then the 법정동코드 register, then the
per-year resolver built on it, then the fetcher that downloads the register.

  norm, canon_sido            one set of name-normalization rules
  geocode_sido/sgg/emd        name -> 2024 anchor code
  sido_code, sigungu_code     name -> the code that year, 12-31 as the instant
  add_code_columns            sido_code / sigungu_code onto a released table
  year_table                  the code table year by year, saved as JSON

Command line:

  python 02_code/kird.py                 the resolved paths (the default)
  python 02_code/kird.py --fetch-codes   download the 법정동코드 register
  python 02_code/kird.py --code-table    rebuild admin_codes_by_year.json
  python 02_code/kird.py --admin2024     rebuild admin2024.json
"""
from __future__ import annotations

# ── paths ────────────────────────────────────────────────────────────────────
import os

__all__ = ["ROOT", "RAW", "CLEAN", "SITE", "SITE_DATA", "RELEASE", "RELEASE_DATA",
           "DEPOSIT", "DEPOSIT_DATA", "DEPOSIT_PUBLISHED", "CODE", "MOIS_SITE"]

_HERE = os.path.dirname(os.path.abspath(__file__))


def _find_root(start):
    d = start
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "01_raw_data")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    d = start
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "02_code")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.dirname(start)


ROOT = os.path.abspath(os.environ.get("KIRD_ROOT") or _find_root(_HERE))

RAW = os.path.join(ROOT, "01_raw_data")
CODE = os.path.join(ROOT, "02_code")
CLEAN = os.path.join(ROOT, "03_cleaned_data")
RELEASE = os.path.join(ROOT, "04_dataset_release")
RELEASE_DATA = os.path.join(RELEASE, "data")
SITE = os.path.join(ROOT, "05_dashboard")
SITE_DATA = os.path.join(SITE, "data")
MOIS_SITE = os.path.join(SITE_DATA, "mois")
# Staging area for the NEXT deposit version. The sibling folder
# kird_openicpsr_deposit/ is the record of what is already published on openICPSR
# as v1.1.0 (DOI 10.3886/E249944V1), so a rebuild must never write into it; phase 3
# builds a fresh bundle here and that folder is replaced only once a new version is
# actually deposited.
DEPOSIT = os.path.join(RELEASE, "data deposit", "kird_openicpsr_deposit_staging")
DEPOSIT_DATA = os.path.join(DEPOSIT, "data")
# The published bundle, read-only: phase 3 seeds the curated README/LICENSE from it
# and every comparison of a staged file is made against it.
DEPOSIT_PUBLISHED = os.path.join(RELEASE, "data deposit", "kird_openicpsr_deposit")


# ── reference tables ─────────────────────────────────────────────────────────
# Variant Korean names for the same country across editions. Everything keys on
# the canonical name, so a series is not split by a spelling change.
COUNTRY_CANONICAL = {
    "태국": "타이",            # 2017 only used 태국; all other years use 타이
    "터키": "튀르키예",         # renamed officially 2022
    "키르기즈": "키르기스스탄", # 2017+ used 키르기즈; older yrs use 키르기스스탄
    "그루지야": "조지아",       # Korean govt switched ~2011
    "러시아": "러시아(연방)",   # 2008 district table and the 2010 stay table use the short form
    "벨로루시": "벨라루스",     # newer official spelling
    "슬로바크": "슬로바키아",   # 2017 used 슬로바키아; others 슬로바크
    "마케도니아": "북마케도니아", # official rename 2019
    "스와질란드": "에스와티니",  # official rename 2018
    # Zaire -> DR Congo (renamed 1997). The yearbook keeps the legacy code and
    # publishes it beside 콩고민주공화국 (7 people a year on the stay basis).
    # crosswalk_country already gives both the same English label, DR Congo, so
    # the table itself says they are one country. Added 2026-08-26 after a sweep
    # found it was the only English label with two Korean names left in the data.
    # 동독 is NOT merged: its English label is East Germany, a different country.
    "자이르": "콩고민주공화국",
    "미국인근섬": "미국",          # dependent territory → merge into 미국
    "미령버진아일랜드": "미국",
    "미령사모아": "미국",          # American Samoa; first appears in the 2025 4장 table
    "영령인도양섬": "영국",
    "불령가이아나": "가이아나",    # per Nari's request
    "앤티카바부다": "앤티가바부다", # spelling variant
    # Hong Kong: refugees from HK (mostly Indochinese in 80s-90s) ↔ Hong Kong nationals
    "홍콩거주난민": "홍콩",
    # UK: multiple British nationality classes all reported separately; merge
    "영국속국민": "영국",
    "영국보호민": "영국",
    "영국외지민": "영국",
    "영국외지시민": "영국",
    "영국속령지시민": "영국",
    "영국해외영토시민": "영국",
    # Yemen: 2017 used 예멘, all other years use 예멘공화국
    "예멘": "예멘공화국",
    # Timor-Leste: 2019 used 동티모르, others use 티모르민주공화국
    "동티모르": "티모르민주공화국",
}


# World-region classification of nationalities, for region-level segregation.
COUNTRY_REGION = {
    # East Asia
    "중국": "동아시아", "한국계중국인": "동아시아", "일본": "동아시아", "대만": "동아시아",
    "몽골": "동아시아", "홍콩": "동아시아", "마카오": "동아시아",
    # 2026-08-25 에 채운 것. 이 표에 없는 이름은 「기타」로 떨어지는데,
    # 자료가 실제로 쓰는 이름 116개가 빠져 있어 2025년 기준 25,232명이
    # 대륙 지표에서 기타로 잡히고 있었다. 가장 큰 것이 타이완 17,187명으로,
    # 표에는 쓰이지 않는 이름 「대만」만 있었다. 지역 구분은 원고 보충표 2 를
    # 그대로 따랐다. 나라가 아닌 항목만 기타로 남긴다.
    "타이완": "동아시아", "북한": "동아시아",
    "아제르바이잔": "서아시아", "아르메니아": "서아시아", "조지아": "서아시아", "키프로스": "서아시아", "팔레스타인": "서아시아",
    "라트비아": "유럽", "리투아니아": "유럽", "에스토니아": "유럽", "슬로바키아": "유럽", "슬로베니아": "유럽",
    "크로아티아": "유럽", "세르비아": "유럽", "몬테네그로": "유럽", "세르비아몬테네그로": "유럽", "코소보": "유럽",
    "보스니아-헤르체고비나": "유럽", "북마케도니아": "유럽", "알바니아": "유럽", "몰도바": "유럽", "몰타": "유럽",
    "룩셈부르크": "유럽", "리히텐슈타인": "유럽", "모나코": "유럽", "산마리노": "유럽", "안도라": "유럽", "아이슬란드": "유럽",
    "교황청": "유럽", "지브롤터": "유럽", "스발바르": "유럽", "유고슬라비아": "유럽", "동독": "유럽",
    "버뮤다": "북아메리카", "케이맨제도": "북아메리카",
    "가이아나": "중남미", "그레나다": "중남미", "니카라과": "중남미", "도미니카연방": "중남미", "바베이도스": "중남미",
    "바하마": "중남미", "벨리즈": "중남미", "수리남": "중남미", "엘살바도르": "중남미", "온두라스": "중남미", "우루과이": "중남미",
    "자메이카": "중남미", "코스타리카": "중남미", "트리니다드토바고": "중남미", "파나마": "중남미", "파라과이": "중남미",
    "마르티니크": "중남미", "세인트루시아": "중남미", "세인트빈센트그레나딘": "중남미", "세인트크리스토퍼네비스": "중남미",
    "앤티가바부다": "중남미", "아이티": "중남미",
    "가봉": "아프리카", "감비아": "아프리카", "기니": "아프리카", "기니비사우": "아프리카", "나미비아": "아프리카",
    "남수단공화국": "아프리카", "니제르": "아프리카", "라이베리아": "아프리카", "레소토": "아프리카", "르완다": "아프리카",
    "리비아": "아프리카", "마다가스카르": "아프리카", "말라위": "아프리카", "말리": "아프리카", "모리셔스": "아프리카",
    "모리타니": "아프리카", "모잠비크": "아프리카", "베냉": "아프리카", "보츠와나": "아프리카", "부룬디": "아프리카",
    "부르키나파소": "아프리카", "상투메프린시페": "아프리카", "세이셸": "아프리카", "소말리아": "아프리카", "시에라리온": "아프리카",
    "앙골라": "아프리카", "에리트레아": "아프리카", "에스와티니": "아프리카", "잠비아": "아프리카", "적도기니": "아프리카",
    "중앙아프리카공화국": "아프리카", "지부티": "아프리카", "짐바브웨": "아프리카", "차드": "아프리카", "카보베르데": "아프리카",
    "코모로": "아프리카", "코트디부아르": "아프리카", "토고": "아프리카", "튀니지": "아프리카", "자이르": "아프리카",
    "괌": "오세아니아", "나우루": "오세아니아", "마샬군도": "오세아니아", "미이크로네시아": "오세아니아", "바누아투": "오세아니아",
    "사모아": "오세아니아", "솔로몬군도": "오세아니아", "키리바시": "오세아니아", "통가": "오세아니아", "투발루": "오세아니아",
    "파푸아뉴기니": "오세아니아", "팔라우": "오세아니아", "피지": "오세아니아", "크리스마스": "오세아니아",
    # 나라가 아니라 기타가 맞는 것: 국적불명, 무국적, 국제연합, 국제연합전문기구
    # Southeast Asia
    "베트남": "동남아시아", "필리핀": "동남아시아", "타이": "동남아시아", "캄보디아": "동남아시아",
    "인도네시아": "동남아시아", "미얀마": "동남아시아", "라오스": "동남아시아", "말레이시아": "동남아시아",
    "싱가포르": "동남아시아", "티모르민주공화국": "동남아시아", "브루나이": "동남아시아",
    # South Asia
    "네팔": "남아시아", "인도": "남아시아", "방글라데시": "남아시아", "파키스탄": "남아시아",
    "스리랑카": "남아시아", "부탄": "남아시아", "몰디브": "남아시아", "아프가니스탄": "남아시아",
    # Central Asia
    "우즈베키스탄": "중앙아시아", "카자흐스탄": "중앙아시아", "키르기스스탄": "중앙아시아",
    "타지키스탄": "중앙아시아", "투르크메니스탄": "중앙아시아", "한국계러시아인": "중앙아시아",
    # West Asia / Middle East
    "이란": "서아시아", "이라크": "서아시아", "시리아": "서아시아", "사우디아라비아": "서아시아",
    "예멘공화국": "서아시아", "튀르키예": "서아시아", "요르단": "서아시아", "레바논": "서아시아",
    "아랍에미리트연합": "서아시아", "쿠웨이트": "서아시아", "이스라엘": "서아시아", "카타르": "서아시아",
    "바레인": "서아시아", "오만": "서아시아",
    # Europe
    "러시아(연방)": "유럽", "우크라이나": "유럽", "영국": "유럽", "프랑스": "유럽", "독일": "유럽",
    "이탈리아": "유럽", "스페인": "유럽", "네덜란드": "유럽", "폴란드": "유럽", "벨라루스": "유럽",
    "루마니아": "유럽", "불가리아": "유럽", "그리스": "유럽", "스웨덴": "유럽", "노르웨이": "유럽",
    "덴마크": "유럽", "핀란드": "유럽", "체코": "유럽", "헝가리": "유럽", "포르투갈": "유럽",
    "벨기에": "유럽", "오스트리아": "유럽", "스위스": "유럽", "아일랜드": "유럽",
    # North America
    "미국": "북아메리카", "캐나다": "북아메리카", "한국계미국인": "북아메리카",
    # Latin America
    "멕시코": "중남미", "브라질": "중남미", "페루": "중남미", "콜롬비아": "중남미",
    "아르헨티나": "중남미", "칠레": "중남미", "에콰도르": "중남미", "볼리비아": "중남미",
    "베네수엘라": "중남미", "과테말라": "중남미", "쿠바": "중남미", "도미니카공화국": "중남미",
    # Africa
    "나이지리아": "아프리카", "가나": "아프리카", "이집트": "아프리카", "에티오피아": "아프리카",
    "남아프리카공화국": "아프리카", "케냐": "아프리카", "탄자니아": "아프리카", "우간다": "아프리카",
    "콩고민주공화국": "아프리카", "콩고": "아프리카", "카메룬": "아프리카", "모로코": "아프리카",
    "알제리": "아프리카", "수단": "아프리카", "세네갈": "아프리카",
    # Oceania
    "오스트레일리아": "오세아니아", "뉴질랜드": "오세아니아",
}


# Single fallback language per nationality, used where Ethnologue publishes no
# first-language shares. One assignment per country rather than an equal split:
# the language chosen is the one Korean agencies are most likely to need
# (lingua franca, or the language Danuri supports).
COUNTRY_LANGUAGE = {
    "한국계중국인": "중국어", "중국": "중국어", "타이완": "중국어", "홍콩": "중국어", "마카오": "중국어",
    "베트남": "베트남어",
    "타이": "태국어",
    "미국": "영어", "캐나다": "영어", "영국": "영어", "오스트레일리아": "영어", "뉴질랜드": "영어", "아일랜드": "영어",
    "필리핀": "타갈로그어",
    "우즈베키스탄": "우즈베크어",
    "카자흐스탄": "러시아어", "키르기스스탄": "러시아어", "타지키스탄": "러시아어", "투르크메니스탄": "러시아어",
    "러시아(연방)": "러시아어", "한국계러시아인": "러시아어", "우크라이나": "러시아어",
    "벨라루스": "러시아어", "조지아": "러시아어", "아르메니아": "러시아어", "아제르바이잔": "러시아어",
    "네팔": "네팔어",
    "인도네시아": "인도네시아어",
    "일본": "일본어",
    "캄보디아": "크메르어",
    "몽골": "몽골어",
    "미얀마": "미얀마어",
    "스리랑카": "싱할라어",
    "방글라데시": "벵골어",
    "파키스탄": "우르두어",
    "인도": "영어",
    "말레이시아": "말레이어",
    "싱가포르": "영어",
    "프랑스": "프랑스어", "벨기에": "프랑스어", "스위스": "독일어",
    "독일": "독일어", "오스트리아": "독일어",
    "이탈리아": "이탈리아어",
    "스페인": "스페인어", "멕시코": "스페인어", "콜롬비아": "스페인어", "페루": "스페인어",
    "아르헨티나": "스페인어", "칠레": "스페인어", "에콰도르": "스페인어", "볼리비아": "스페인어",
    "베네수엘라": "스페인어", "과테말라": "스페인어", "쿠바": "스페인어", "도미니카공화국": "스페인어",
    "브라질": "포르투갈어", "포르투갈": "포르투갈어",
    "네덜란드": "네덜란드어",
    "튀르키예": "터키어",
    "이집트": "아랍어", "이라크": "아랍어", "시리아": "아랍어", "사우디아라비아": "아랍어",
    "예멘공화국": "아랍어", "요르단": "아랍어", "리비아": "아랍어", "모로코": "아랍어", "수단": "아랍어",
    "아랍에미리트연합": "아랍어", "쿠웨이트": "아랍어", "레바논": "아랍어", "알제리": "아랍어", "튀니지": "아랍어",
    "이란": "페르시아어", "아프가니스탄": "다리어",
    "나이지리아": "영어", "가나": "영어", "케냐": "영어", "남아프리카공화국": "영어",
    "에티오피아": "암하라어", "탄자니아": "스와힐리어", "우간다": "영어",
    "콩고민주공화국": "프랑스어", "콩고": "프랑스어", "카메룬": "프랑스어",
    "코트디부아르": "프랑스어", "세네갈": "프랑스어", "말리": "프랑스어",
    "라오스": "라오어",
    "티모르민주공화국": "테툼어",
    "부탄": "종카어",
    "몰디브": "디베히어",
    "폴란드": "폴란드어", "체코": "체코어", "슬로바키아": "슬로바키아어", "헝가리": "헝가리어",
    "루마니아": "루마니아어", "불가리아": "불가리아어", "그리스": "그리스어",
    "스웨덴": "스웨덴어", "노르웨이": "노르웨이어", "덴마크": "덴마크어", "핀란드": "핀란드어",
}


# Province English names as the dashboard shows them: the short English form,
# no 시/도 suffix.
SIDO_EN_SHORT = {
    "서울특별시": "Seoul",
    "부산광역시": "Busan",
    "대구광역시": "Daegu",
    "인천광역시": "Incheon",
    "광주광역시": "Gwangju",
    "대전광역시": "Daejeon",
    "울산광역시": "Ulsan",
    "세종특별자치시": "Sejong",
    "경기도": "Gyeonggi",
    "강원도": "Gangwon",
    "충청북도": "North Chungcheong",
    "충청남도": "South Chungcheong",
    "전라북도": "North Jeolla",
    "전라남도": "South Jeolla",
    "경상북도": "North Gyeongsang",
    "경상남도": "South Gyeongsang",
    "제주특별자치도": "Jeju",
}


# Ethnologue's English language names to the Korean labels the dashboard shows.
# Many-to-one: several Ethnologue entries collapse onto one Korean label.
LANG_EN_KO = {
    # East Asian
    "Korean": "한국어",
    "Haitian Creole": "아이티크레올어", "Haitian": "아이티크레올어",
    "English": "영어",
    "Mandarin Chinese": "중국어", "Min Nan Chinese": "중국어",
    "Yue Chinese": "광둥어", "Cantonese": "광둥어",
    "Wu Chinese": "중국어", "Hakka Chinese": "중국어",
    "Gan Chinese": "중국어", "Min Bei Chinese": "중국어", "Min Dong Chinese": "중국어",
    "Min Zhong Chinese": "중국어", "Pu-Xian Chinese": "중국어", "Xiang Chinese": "중국어",
    "Huizhou Chinese": "중국어", "Jinyu Chinese": "중국어", "Literary Chinese": "중국어",
    "Japanese": "일본어",
    # Southeast Asian
    "Vietnamese": "베트남어",
    "Thai": "태국어", "Northern Thai": "태국어", "Northeastern Thai": "태국어",
    "Southern Thai": "태국어",
    "Tagalog": "타갈로그어", "Filipino": "타갈로그어", "Cebuano": "타갈로그어",
    "Iloko": "타갈로그어", "Hiligaynon": "타갈로그어", "Bikol Central": "타갈로그어",
    "Waray-Waray": "타갈로그어", "Kapampangan": "타갈로그어", "Pangasinan": "타갈로그어",
    "Ilonggo": "타갈로그어", "Northern Bicolano": "타갈로그어",
    "Indonesian": "인도네시아어", "Javanese": "인도네시아어",
    "Sundanese": "인도네시아어", "Madurese": "인도네시아어",
    "Minangkabau": "인도네시아어", "Buginese": "인도네시아어", "Banjar": "인도네시아어",
    "Balinese": "인도네시아어", "Acehnese": "인도네시아어", "Sasak": "인도네시아어",
    "Malay": "말레이어", "Standard Malay": "말레이어",
    "Burmese": "미얀마어",
    "Khmer": "크메르어", "Central Khmer": "크메르어",
    "Lao": "라오어",
    "Halh Mongolian": "몽골어", "Mongolian": "몽골어", "Peripheral Mongolian": "몽골어",
    # Russian / Slavic / Caucasus
    "Russian": "러시아어", "Belarusian": "러시아어",
    "Ukrainian": "우크라이나어",
    "Uzbek": "우즈베크어", "Northern Uzbek": "우즈베크어", "Southern Uzbek": "우즈베크어",
    "Kazakh": "카자흐어",
    "Kirghiz": "키르기스어", "Kyrgyz": "키르기스어",
    "Tajik": "타지크어",
    "Turkmen": "투르크멘어",
    "North Azerbaijani": "아제르바이잔어", "South Azerbaijani": "아제르바이잔어",
    "Azerbaijani": "아제르바이잔어",
    "Georgian": "조지아어",
    "Armenian": "아르메니아어", "Eastern Armenian": "아르메니아어", "Western Armenian": "아르메니아어",
    # Turkic / Middle Eastern
    "Turkish": "튀르키예어",
    "Iranian Persian": "페르시아어", "Persian": "페르시아어", "Western Farsi": "페르시아어",
    "Dari": "페르시아어",
    "Northern Kurdish": "쿠르드어", "Central Kurdish": "쿠르드어",
    "Southern Kurdish": "쿠르드어", "Kurdish": "쿠르드어",
    "Northern Pashto": "파슈토어", "Southern Pashto": "파슈토어",
    "Central Pashto": "파슈토어", "Pashto": "파슈토어",
    "Standard Arabic": "아랍어", "Modern Standard Arabic": "아랍어",
    "Egyptian Arabic": "아랍어", "Sudanese Arabic": "아랍어",
    "North Levantine Arabic": "아랍어", "South Levantine Arabic": "아랍어",
    "Levantine Arabic": "아랍어", "Mesopotamian Arabic": "아랍어",
    "North Mesopotamian Arabic": "아랍어", "Najdi Arabic": "아랍어",
    "Gulf Arabic": "아랍어", "Hijazi Arabic": "아랍어",
    "Algerian Arabic": "아랍어", "Tunisian Arabic": "아랍어",
    "Moroccan Arabic": "아랍어", "Libyan Arabic": "아랍어",
    "Saidi Arabic": "아랍어", "Sanaani Arabic": "아랍어", "Taizzi-Adeni Arabic": "아랍어",
    "Ta'izzi-Adeni Arabic": "아랍어", "Chadian Arabic": "아랍어",
    "Hadrami Arabic": "아랍어", "Omani Arabic": "아랍어",
    "Baharna Arabic": "아랍어", "Shihhi Arabic": "아랍어",
    "Hebrew": "히브리어",
    # South Asian
    "Hindi": "힌디어",
    "Bengali": "벵골어",
    "Urdu": "우르두어",
    "Punjabi": "펀자브어", "Eastern Panjabi": "펀자브어", "Western Panjabi": "펀자브어",
    "Lahnda": "펀자브어", "Saraiki": "펀자브어",
    "Sindhi": "신디어",
    "Tamil": "타밀어",
    "Telugu": "텔루구어",
    "Malayalam": "말라얄람어",
    "Gujarati": "구자라트어",
    "Marathi": "마라티어",
    "Kannada": "칸나다어",
    "Odia": "오리야어", "Oriya": "오리야어",
    "Assamese": "벵골어",
    "Nepali": "네팔어",
    "Sinhala": "신할라어",
    "Dhivehi": "디베히어",
    "Dzongkha": "종카어",
    # European
    "Spanish": "스페인어", "Castilian": "스페인어",
    "Portuguese": "포르투갈어",
    "French": "프랑스어",
    "German": "독일어", "Standard German": "독일어", "Swiss German": "독일어",
    "Bavarian": "독일어",
    "Italian": "이탈리아어",
    "Dutch": "네덜란드어", "Flemish": "네덜란드어",
    "Polish": "폴란드어",
    "Romanian": "루마니아어", "Moldavian": "루마니아어",
    "Bulgarian": "불가리아어",
    "Serbian": "세르비아어", "Serbo-Croatian": "세르비아어",
    "Croatian": "크로아티아어",
    "Bosnian": "보스니아어",
    "Slovenian": "슬로베니아어",
    "Macedonian": "마케도니아어",
    "Czech": "체코어",
    "Slovak": "슬로바키아어",
    "Hungarian": "헝가리어",
    "Greek": "그리스어", "Modern Greek": "그리스어",
    "Albanian": "알바니아어", "Tosk Albanian": "알바니아어", "Gheg Albanian": "알바니아어",
    "Swedish": "스웨덴어",
    "Norwegian": "노르웨이어", "Norwegian Bokmal": "노르웨이어", "Norwegian Nynorsk": "노르웨이어",
    "Danish": "덴마크어",
    "Finnish": "핀란드어",
    "Icelandic": "아이슬란드어",
    "Estonian": "에스토니아어",
    "Latvian": "라트비아어",
    "Lithuanian": "리투아니아어",
    "Irish": "아일랜드어",
    # African
    "Swahili": "스와힐리어", "Congo Swahili": "스와힐리어",
    "Amharic": "암하라어",
    "Tigrigna": "티그리냐어", "Tigrinya": "티그리냐어", "Tigre": "티그리냐어",
    "Oromo": "오로모어", "West Central Oromo": "오로모어",
    "Eastern Oromo": "오로모어", "Borana-Arsi-Guji Oromo": "오로모어",
    "Somali": "소말리아어",
    "Hausa": "하우사어",
    "Yoruba": "요루바어",
    "Igbo": "이그보어",
    "Zulu": "줄루어",
    "Xhosa": "코사어",
    "Afrikaans": "아프리칸스어",
    "Southern Sotho": "소토어", "Northern Sotho": "소토어",
    "Shona": "쇼나어",
    "Kinyarwanda": "키냐르완다어",
    "Rundi": "키룬디어",
    "Malagasy": "말라가시어",
    "Wolof": "월로프어",
    "Pulaar": "풀라어", "Adamawa Fulfulde": "풀라어",
    "Nigerian Fulfulde": "풀라어", "Western Niger Fulfulde": "풀라어",
    "Central-Eastern Niger Fulfulde": "풀라어",
    # Tetum and other PALOP / SE Asia
    "Tetum": "테툼어", "Tetun Dili": "테툼어",
    # Maldives / Bhutan
    "Maldivian": "디베히어",
    "Tshangla": "창라어",
    # Indonesian regional (Ethnologue uses short forms)
    "Sunda": "인도네시아어", "Madura": "인도네시아어",
    "Betawi": "인도네시아어", "Bugis": "인도네시아어",
    "Aceh": "인도네시아어", "Bali": "인도네시아어",
    "Lampung Api": "인도네시아어", "Toba Batak": "인도네시아어",
    "Makasar": "인도네시아어", "Banjar": "인도네시아어",
    # Philippines (Ethnologue uses short forms)
    "Ilocano": "타갈로그어", "Bikol": "타갈로그어", "Central Bikol": "타갈로그어",
    "Maguindanaon": "타갈로그어", "Maranao": "타갈로그어", "Tausug": "타갈로그어",
    "Chavacano": "타갈로그어",
    # Italian regional dialects (Romance, lumped to standard Italian)
    "Napoletano-Calabrese": "이탈리아어", "Sicilian": "이탈리아어",
    "Venetian": "이탈리아어", "Lombard": "이탈리아어", "Piedmontese": "이탈리아어",
    "Emiliano-Romagnolo": "이탈리아어", "Ligurian": "이탈리아어",
    "Friulian": "이탈리아어", "Sardinian": "이탈리아어",
    # Dutch / Belgian regional
    "Frisian": "네덜란드어", "Limburgish": "네덜란드어",
    "Sallands": "네덜란드어", "Twents": "네덜란드어",
    "Western Flemish": "네덜란드어",
    # Berber / Amazigh family (Morocco / Algeria / Libya / Mali / Niger)
    "Tachelhit": "베르베르어", "Tarifit": "베르베르어",
    "Central Atlas Tamazight": "베르베르어", "Tamazight": "베르베르어",
    "Amazigh": "베르베르어", "Tachawit": "베르베르어",
    "Tamasheq": "베르베르어", "Tahaggart Tamahaq": "베르베르어",
    "Senhaja Berber": "베르베르어", "Tumzabt": "베르베르어",
    # Andean / indigenous Latin America
    "South Bolivian Quechua": "케추아어", "North Bolivian Quechua": "케추아어",
    "Central Aymara": "아이마라어", "Aymara": "아이마라어",
    "Eastern Bolivian Guaraní": "과라니어", "Paraguayan Guaraní": "과라니어",
    # Mayan family (Guatemala / Mexico)
    "Q'eqchi'": "마야어", "K'iche'": "마야어", "Mam": "마야어",
    "Kaqchikel": "마야어", "Q'anjob'al": "마야어", "Achi": "마야어",
    "Ixil": "마야어", "Tz'utujil": "마야어", "Poqomchi'": "마야어",
    "Yucateco": "마야어",
    # West Africa
    "Akan": "아칸어", "Twi": "아칸어", "Fante": "아칸어",
    "Éwé": "에웨어", "Ewe": "에웨어",
    "Dagbani": "다그바니어", "Dangme": "다그메어", "Ga": "가어",
    "Abron": "아칸어",
    "Baoulé": "바울레어", "Anyin": "아니어",
    "Jula": "줄라어", "Dyula": "줄라어",
    "Mòoré": "모시어", "Mooré": "모시어",
    "Dan": "단어",
    "Bamanankan": "밤바라어", "Bambara": "밤바라어",
    "Soninke": "소닌케어",
    "Mamara Sénoufo": "기타", "Xaasongaxango": "기타",
    "Kita Maninkakan": "만데어", "Maninka": "만데어", "Western Maninkakan": "만데어",
    "Serer-Sine": "세레르어", "Mandinka": "만딘카어", "Jola-Fonyi": "졸라어",
    # East Africa
    "Ganda": "루간다어", "Luganda": "루간다어",
    "Nyankore": "냔콜레어", "Soga": "소가어", "Chiga": "치가어",
    "Ateso": "아테소어", "Lugbara": "루그바라어",
    "Gikuyu": "키쿠유어", "Kikuyu": "키쿠유어",
    "Dholuo": "루오어", "Luo": "루오어",
    "Kamba": "캄바어", "Ekegusii": "구시어",
    "Kimîîru": "메루어", "Meru": "메루어",
    "Kipsigis": "칼렌진어", "Bukusu": "루히아어",
    "Sukuma": "수쿠마어", "Haya": "하야어",
    "Makonde": "마콘데어", "Nyamwezi": "냐므웨지어",
    "Ha": "하어", "Hehe": "헤헤어",
    "Nyakyusa-Ngonde": "냐큐사어",
    # Central Africa / Congo basin
    "Kituba": "키투바어",
    "Lingala": "링갈라어",
    "Luba-Kasai": "루바카사이어", "Tshiluba": "루바카사이어",
    "Luba-Katanga": "루바카탕가어",
    "Koongo": "키콩고어", "Kongo": "키콩고어",
    "Suundi": "키콩고어", "Laari": "키콩고어",
    "Mbosi": "기타",
    # Cameroon (mostly small Bantu/Bantoid, lump)
    "Bulu": "기타", "Ewondo": "기타", "Bamun": "기타",
    "Basaa": "기타", "Ghomálá'": "기타",
    # Nigeria additional (besides Hausa/Yoruba/Igbo/Fulfulde)
    "Yerwa Kanuri": "카누리어", "Kanuri": "카누리어",
    "Ibibio": "이비비오어", "Tiv": "티브어", "Anaang": "이비비오어",
    "Izon": "이존어", "Edo": "에도어", "Urhobo": "기타",
    "Igala": "기타", "Nupe": "기타",
    # Southern Africa additional
    "Tswana": "츠와나어", "Tsonga": "총가어",
    "Venda": "벤다어", "Swati": "스와티어",
    # Burundi / Rwanda already covered (Kinyarwanda / Rundi)
    # Madagascar
    "Plateau Malagasy": "말라가시어", "Tandroy-Mahafaly Malagasy": "말라가시어",
    "Tsimihety Malagasy": "말라가시어", "Sakalava Malagasy": "말라가시어",
    "Northern Betsimisaraka Malagasy": "말라가시어", "Bara Malagasy": "말라가시어",
    "Southern Betsimisaraka Malagasy": "말라가시어",
    # Myanmar minority
    "Shan": "샨어", "Jingpho": "카친어", "Kachin": "카친어",
    "S'gaw Karen": "카렌어", "Pwo Eastern Karen": "카렌어",
    "Pwo Western Karen": "카렌어", "Pa'o": "카렌어",
    "Mon": "몬어", "Rakhine": "미얀마어",
    # Laos minority
    "Khmu": "크무어", "Phu Thai": "태국어",
    "Tai Dón": "태국어", "Tai Daeng": "태국어",
    "Hmong Daw": "흐몽어", "Hmong Njua": "흐몽어",
    "Western Bru": "기타", "Eastern Bru": "기타",
    # Ethiopia extra (besides Amharic/Oromo/Tigrinya/Somali)
    "Sidamo": "기타", "Wolaytta": "기타", "Sebat Bet Gurage": "기타",
    "Afar": "아파르어", "Hadiyya": "기타", "Gamo": "기타",
    "Gedeo": "기타", "Kafa": "기타",
    # East Timor (after Tetum)
    "Mambai": "맘바이어", "Mambae": "맘바이어",
    "Makasae": "마카사에어",
    "Baikeno": "바이케노어",
    "Kemak": "케막어",
    "Tukudede": "투쿠데데어",
    "Bunak": "부낙어", "Bunaq": "부낙어",
    "Fataluku": "파탈루쿠어",
    "Galolen": "기타", "Galoli": "기타",
    "Naueti": "기타", "Nauete": "기타",
    "Waima'a": "기타", "Atauran": "기타", "Idaté": "기타",
    "Kairui-Midiki": "기타", "Habun": "기타", "Lakalei": "기타",
    "Makalero": "기타", "Welaun": "기타", "Tetun": "테툼어",
    # Cameroon largest indigenous languages (>100K L1)
    "Mafa": "마파어",
    "Bulu": "불루어",
    "Ewondo": "에원도어", "Eton": "에톤어",
    "Basaa": "바사어",
    "Kom": "콤어",
    "Lamnsoʼ": "람느소어", "Lamnso'": "람느소어", "Lamnso": "람느소어",
    "Medumba": "메둠바어",
    "Ngiemboon": "응이엠본어",
    "Yemba": "옘바어",
    "Tikar": "티카르어",
    "Tupuri": "투푸리어",
    "Limbum": "림붐어",
    "Mundang": "문당어",
    "Mungaka": "뭉가카어",
    "Pidgin, Cameroon": "카메룬 피진어", "Cameroon Pidgin English": "카메룬 피진어",
    "Wes Cos": "카메룬 피진어",
    # Republic of Congo additional
    "Mbosi": "음보시어", "Mbochi": "음보시어",
    "Beembe": "베엠베어",
    "Mbere": "음베레어",
    # Laari / Suundi / Kunyi already covered as part of Kikongo lump
    "Kunyi": "키콩고어",
    # DRC additional small Bantu
    "Pomo": "기타",
    # ---- Nigeria major L1 languages (top 30+) ----
    "Edo": "에도어", "Esan": "에산어", "Urhobo": "우르호보어", "Isoko": "이소코어",
    "Ikwere": "이크웨레어", "Igala": "이갈라어", "Idoma": "이도마어",
    "Berom": "베롬어", "Gbagyi": "그바기어", "Gbari": "그바리어", "Nupe": "누페어",
    "Nupe-Nupe-Tako": "누페어", "Tarok": "타로크어", "Tyap": "츠얍어",
    "Bura-Pabir": "부라어", "Marghi Central": "마르기어",
    "Kamwe": "캄웨어", "Lala-Roba": "랄라어",
    "Ebira": "에비라어", "Kalabari": "칼라바리어", "Kirike": "키리케어",
    "Izon": "이존어", "Ijo, Southeast": "이존어", "Ijaw": "이존어",
    "Khana": "오고니어", "Tèẹ̀": "오고니어",
    "Anaang": "아낭어", "Annang": "아낭어",
    "Bole": "볼레어", "Bade": "바데어", "Karekare": "카레카레어",
    "Ngas": "응가스어", "Angas": "응가스어", "Mwaghavul": "음와그하불어",
    "Tangale": "탕갈레어", "Goemai": "고에마이어", "Saya": "사야어",
    "Wandala": "만다라어", "Mandara": "만다라어",
    "Hõne": "혼어", "Jukun": "주쿤어", "Wapan": "주쿤어",
    "Kuteb": "쿠텝어", "Kutep": "쿠텝어", "Eggon": "에곤어",
    "Mumuye": "무무예어", "Mbembe, Cross River": "음벰베어",
    "Ogbah": "오그바어", "Ekit": "에키트어", "Etsako": "에차코어",
    "Ezaa": "이그보어", "Izii": "이그보어", "Mgbolizhia": "이그보어",
    "Igbo, Mbieri": "이그보어", "Ikwo": "이그보어", "Ukwuani-Aboh-Ndoni": "이그보어",
    "Ika": "이그보어", "Adara": "아다라어", "Hyam": "햠어", "Jju": "주어",
    "Kukele": "쿠켈레어", "Lokaa": "로카어", "Gun": "군어",
    "Igede": "이게데어", "Mada": "마다어", "Mumuye": "무무예어",
    "Tiv": "티브어",
    "Ngamo": "응가모어", "Pero": "페로어", "Bachama": "바차마어", "Bacama": "바차마어",
    "Bata": "바타어", "Gude": "구데어", "Higgi": "캄웨어",
    "Pidgin, Nigerian": "나이지리아 피진어", "Nigerian Pidgin": "나이지리아 피진어",
    "Naijá": "나이지리아 피진어",
    # ---- Indonesia major regional languages (top 30+) ----
    "Minangkabau": "미낭카바우어",
    "Lampung Api": "람풍어", "Lampung Nyo": "람풍어",
    "Komering": "코메링어", "Kerinci": "크린치어",
    "Mandailing": "만다일링어",
    "Batak Toba": "토바바탁어", "Batak Karo": "카로바탁어",
    "Batak Mandailing": "만다일링어", "Batak Angkola": "앙콜라어",
    "Batak Simalungun": "시말룽운어", "Batak Dairi": "다이리어",
    "Batak Alas-Kluet": "알라스어",
    "Betawi": "베타위어",
    "Sasak": "사삭어", "Bima": "비마어",
    "Manggarai": "망가라이어", "Lamaholot": "라마홀롯어", "Adonara": "라마홀롯어",
    "Sumbawa": "숨바와어", "Kambera": "캄베라어", "Wejewa": "웨제와어",
    "Ngad'a": "응가다어", "Ende": "엔데어", "Li'o": "리오어", "Nage": "나게어",
    "Ke'o": "케오어", "Rongga": "롱가어", "Riung": "리웅어",
    "Helong": "헬롱어",
    "Uab Meto": "다완어", "Amarasi": "다완어", "Baikeno": "바이케노어",
    "Rote": "로테어", "Termanu": "로테어", "Lole": "로테어", "Dengka": "로테어",
    "Dela-Oenale": "로테어", "Tii": "로테어", "Rikou": "로테어", "Bilba": "로테어",
    "Hawu": "하우어", "Dhao": "다오어",
    "Mbojo": "비마어",
    "Cia-Cia": "치아치아어", "Wolio": "월리오어",
    "Muna": "무나어", "Kulisusu": "쿨리수수어",
    "Tolaki": "톨라키어", "Mori Bawah": "모리어",
    "Pamona": "파모나어", "Bare'e": "파모나어",
    "Bajau, Indonesian": "바자우어",
    "Galela": "갈렐라어", "Tobelo": "토벨로어", "Tidore": "티도레어",
    "Ternate": "테르나테어", "Sahu": "사후어", "Buli": "불리어",
    "Halmahera": "할마헤라어",
    "Ambonese Malay": "암본 말레이어", "Malay, Ambonese": "암본 말레이어",
    "Malay, Manado": "마나도 말레이어", "Manadonese": "마나도 말레이어",
    "Malay, Papuan": "파푸아 말레이어", "Papuan Malay": "파푸아 말레이어",
    "Malay, North Moluccan": "북말루쿠 말레이어",
    "Malay, Kupang": "쿠팡 말레이어", "Malay, Larantuka": "라란투카 말레이어",
    "Malay, Banda": "반다 말레이어", "Malay, Bacanese": "바칸 말레이어",
    "Malay, Central": "팔렘방 말레이어", "Palembang": "팔렘방 말레이어",
    "Malay, Jambi": "잠비 말레이어",
    "Bali": "발리어", "Balinese": "발리어",
    "Banjar": "반자르어",
    "Bugis": "부기스어", "Makasar": "마카사르어", "Mandar": "만다르어",
    "Toraja-Sa'dan": "토라자어", "Toraja": "토라자어", "Mamasa": "마마사어",
    "Gorontalo": "고론탈로어",
    "Aceh": "아체어",
    "Tetun": "테툼어",
    # ---- India major L1 languages (top 30+) ----
    "Awadhi": "힌디어", "Chhattisgarhi": "차티스가르어",
    "Marwari": "마르와리어", "Mewari": "마르와리어",
    "Wagdi": "와그디어", "Bagri": "바그리어", "Bundeli": "분델리어",
    "Haryanvi": "하리안비어", "Kanauji": "칸나우지어",
    "Bagheli": "바겔리어", "Malvi": "말비어",
    "Mewati": "메와티어", "Haroti": "하로티어", "Dhundari": "둔다리어",
    "Bhili": "빌리어", "Bhilali": "빌랄리어",
    "Garhwali": "가르왈리어", "Kumaoni": "쿠마오니어",
    "Konkani": "콘카니어", "Goan Konkani": "콘카니어",
    "Khandesi": "칸데시어", "Ahirani": "칸데시어",
    "Bhojpuri": "보즈푸리어",
    "Tulu": "툴루어",
    "Kashmiri": "카시미르어", "Dogri": "도그리어",
    "Santali": "산탈리어", "Santhali": "산탈리어",
    "Ho": "호어", "Mundari": "문다리어", "Kurux": "쿠루크어", "Munda": "문다어",
    "Khasi": "카시어",
    "Garo": "가로어", "Boro": "보도어",
    "Meitei": "메이테이어", "Manipuri": "메이테이어",
    "Mizo": "미조어",
    "Naga, Ao": "나가어", "Naga, Angami": "나가어", "Naga, Sumi": "나가어",
    "Naga, Lotha": "나가어", "Naga, Tangkhul": "나가어", "Naga, Konyak": "나가어",
    "Naga, Chang": "나가어", "Naga, Khiamniungan": "나가어", "Naga, Rongmei": "나가어",
    "Naga, Mao": "나가어", "Naga, Poumai": "나가어", "Naga, Tangsa": "나가어",
    "Tangsa": "나가어",
    "Lepcha": "렙차어", "Sherpa": "셰르파어", "Bhutia": "부티아어",
    "Sikkimese": "시킴어",
    "Newar": "네와르어", "Limbu": "림부어", "Rai": "라이어",
    "Magar, Eastern": "마가르어", "Tamang, Eastern": "타망어",
    "Gurung": "구룽어", "Sherpa": "셰르파어",
    "Adi": "아디어", "Adi, Galo": "아디어", "Nyishi": "니시어",
    "Apatani": "아파타니어", "Mising": "미싱어",
    "Karbi": "카르비어", "Tiwa": "티와어", "Dimasa": "디마사어",
    "Kok Borok": "코크보로크어", "Kokborok": "코크보로크어",
    "Lambadi": "람바디어", "Banjari": "람바디어",
    "Gondi": "곤디어", "Gondi, Adilabad": "곤디어", "Gondi, Aheri": "곤디어",
    "Gondi, Northern": "곤디어", "Maria": "곤디어", "Muria, Eastern": "곤디어",
    "Muria, Western": "곤디어",
    "Kui": "쿠이어", "Kuvi": "쿠비어",
    "Saurashtra": "사우라슈트라어",
    "Lambadi": "람바디어",
    "Pahari-Potwari": "포트와리어",
    "Bishnupuriya": "비슈누프리야어",
    "Tharu, Dangaura": "타루어", "Tharu, Rana": "타루어", "Tharu, Kochila": "타루어",
    "Tharu, Kathariya": "타루어", "Tharu, Chitwania": "타루어",
    "Bajjika": "바지카어", "Angika": "앙기카어", "Surjapuri": "수르자푸리어",
    "Sadri": "사드리어", "Nagpuri": "사드리어", "Sadani": "사드리어",
    "Sambalpuri": "오리야어", "Bhatri": "오리야어",
    "Halbi": "할비어",
    "Pahari, Mahasu": "마하수어",
    "Mandeali": "만데알리어", "Chambeali": "참베알리어", "Bhattiyali": "바티알리어",
    "Kangri": "캉리어", "Gaddi": "가디어", "Bhilali": "빌랄리어",
    "Bhili": "빌리어", "Bareli, Pauri": "빌리어", "Bareli, Rathwi": "빌리어",
    "Vasavi": "빌리어", "Dungra Bhil": "빌리어", "Dubli": "빌리어",
    "Garasia, Adiwasi": "빌리어", "Garasia, Rajput": "빌리어",
    "Mawchi": "마우치어", "Noiri": "빌리어",
    "Rathawi": "빌리어", "Bhilodi": "빌리어",
    "Mentawai": "멘타와이어",
    "Nias": "니아스어",
    "Hajong": "하종어",
    "Rabha": "라바어",
    "Mishing": "미싱어", "Mising": "미싱어",
    "Kachari": "보도어",
    # ---- Ethiopia major L1 languages ----
    "Sidaama": "시다마어", "Sidamo": "시다마어",
    "Hadiyya": "하디야어",
    "Gamo": "가모어",
    "Gedeo": "게데오어",
    "Kafa": "카파어",
    "Sebat Bet Gurage": "구라게어", "Inor": "구라게어", "Mesqan": "구라게어",
    "Kistane": "구라게어", "Wolane": "구라게어", "Silt'e": "구라게어",
    "Silt’e": "구라게어",
    "Wolaytta": "월라이타어",
    "Awngi": "아우니어",
    "Berta": "베르타어",
    "Konso": "콘소어",
    "Nuer": "누에르어",
    "Me'en": "메엔어", "Me’en": "메엔어",
    "Majang": "마장어",
    "Gumuz": "구무즈어",
    "Sheko": "셰코어",
    "Suri, Tirmaga-Chai": "수리어", "Suri, Kacipo-Bale": "수리어",
    "Dawro": "다우로어",
    "Gofa": "고파어",
    "Bench": "벤치어",
    "Kambaata": "캄바타어",
    "Saho": "사호어",
    "Anuak": "아누아크어",
    "Dirasha": "디라샤어",
    "Aari": "아리어",
    "Tigrigna": "티그리냐어",
    "Argobba": "아랍어",  # Argobba is heavily Arabized
    "Komo": "코마어",
    "Gwama": "콰마어", "Hozo": "마오어", "Seze": "마오어",
    "Mursi": "수리어",
    "Daasanach": "다사나치어",
    "Hamer-Banne": "하메르어",
    "Nyangatom": "나기아탐어",
    "Burji": "부르지어",
    "Alaba-K'abeena": "알라바어", "Alaba-K’abeena": "알라바어",
    "Libido": "리비도어",
    "Xamtanga": "샴탕가어",
    "Kunama": "쿠나마어",
    "Tsamai": "차마이어", "Tsemai": "차마이어",
    "Mawes Aasse": "마오어",
    "Bambassi": "마오어",
    "Borna": "보르나어",
    "Basketo": "바스케토어",
    "Dizin": "디진어",
    "Yemsa": "옘사어",
    "Shekkacho": "셰카초어",
    "Tigré": "티그레어",
    # Oromo macro - lump
    "Oromo, West Central": "오로모어", "Oromo, Borana-Arsi-Guji": "오로모어",
    "Oromo, Eastern": "오로모어", "Borana-Arsi-Guji Oromo": "오로모어",
    "Eastern Oromo": "오로모어", "West Central Oromo": "오로모어",
    # ---- Kenya major L1 languages (Kikuyu/Kamba/Luo already done) ----
    "Maasai": "마사이어",
    "Bukusu": "올루이아어",  # Luhya cluster lump
    "Luidakho-Luisukha-Lutirichi": "올루이아어",
    "Lukabaras": "올루이아어", "Lulogooli": "올루이아어",
    "Lutachoni": "올루이아어", "Nyala": "올루이아어",
    "Olukhayo": "올루이아어", "Olumarachi": "올루이아어",
    "Olumarama": "올루이아어", "Olunyole": "올루이아어",
    "Olushisa": "올루이아어", "Olutsotso": "올루이아어",
    "Oluwanga": "올루이아어", "Olusamia": "올루이아어",
    "Kigiryama": "미지켄다어", "Chichonyi-Chidzihana-Chikauma": "미지켄다어",
    "Chiduruma": "미지켄다어", "Chidigo": "미지켄다어",
    "Turkana": "투르카나어",
    "Borana": "오로모어",
    "Kiembu": "엠부어",
    "Garre": "가레어",
    "Kipsigis": "칼렌진어", "Nandi": "칼렌진어", "Markweeta": "칼렌진어",
    "Tugen": "칼렌진어", "Keiyo": "칼렌진어", "Terik": "칼렌진어",
    "Sabaot": "칼렌진어", "Okiek": "칼렌진어", "Pökoot": "포코트어",
    "Suba": "수바어",
    "Aweer": "아위르어",
    "Kuria": "쿠리아어",
    "Mwimbi-Muthambi": "메루어",
    "Dawida": "타이타어",
    "Kipfokomu": "포코모어",
    "Sagalla": "타이타어",
    "Taveta": "타베타어",
    "Gichuka": "츄카어",
    "Kitharaka": "타라카어",
    "Samburu": "삼부루어",
    "Rendille": "렌딜레어",
    "Orma": "오로모어",
    "Maay": "마이어", "Bajuni": "스와힐리어", "Kiwilwana": "포코모어",
    "Daahalo": "다할로어", "Dahalo": "다할로어",
    "Nubi": "누비어",
    # ---- Myanmar major L1 languages ----
    "Karen, S'gaw": "카렌어", "Karen, Pwo Eastern": "카렌어",
    "Karen, Pwo Western": "카렌어", "Karen, Geko": "카렌어",
    "Karen, Geba": "카렌어", "Karen, Paku": "카렌어",
    "Karen, Mobwa": "카렌어", "Karen, Bwe": "카렌어",
    "Yinbaw": "카렌어", "Yintale": "카렌어", "Lahta": "카렌어",
    "Zayein": "카렌어", "Kayan": "카얀어", "Kayaw": "카렌어",
    "Kawyaw": "카렌어",
    "Kayah, Eastern": "카야어", "Kayah, Western": "카야어",
    "Rakhine": "라카인어",
    "Lahu": "라후어", "Lahu Shi": "라후어",
    "Lisu": "리수어",
    "Akha": "아카어", "Akeu": "아카어",
    "Pa'o": "파오어", "Pa’o": "파오어",
    "Mru": "므루어",
    "Tavoyan": "다웨이어",
    "Wa, Parauk": "와어", "Wa, Vo": "와어",
    "Khün": "샨어", "Shan": "샨어", "Khamti": "샨어", "Tai Laing": "샨어",
    "Tai Loi": "샨어", "Tai Nüa": "샨어",
    "Lhao Vo": "마루어", "Lacid": "라치드어",
    "Ngochang": "아창어",
    "Palaung, Ruching": "팔라웅어", "Palaung, Rumai": "팔라웅어",
    "Palaung, Shwe": "팔라웅어",
    "Riang Lai": "리앙어", "Riang Lang": "리앙어",
    "Drung": "두룽어",
    "Hmong Njua": "흐몽어",
    "Mon": "몬어",
    "Hpon": "버마어", "Intha": "인타어",
    "Danau": "다나우어", "Danu": "다누어",
    "Taungyo": "타웅요어",
    "Anong": "아농어",
    "Chinese, Hakka": "중국어", "Chinese, Min Nan": "중국어",
    "Mok": "몬크메르어",
    "Muak Sa-aak": "몬크메르어",
    "Blang": "블랑어",
    # ---- Iran major L1 languages ----
    "Azerbaijani, South": "아제르바이잔어", "South Azerbaijani": "아제르바이잔어",
    "Mazandarani": "마잔다란어",
    "Gilaki": "길라키어",
    "Bakhtiâri": "바흐티야리어", "Bakhtiari": "바흐티야리어",
    "Luri, Northern": "로리어", "Luri, Southern": "로리어",
    "Laki": "로리어",
    "Khorasani Turkish": "호라산터키어",
    "Kashkay": "카슈카이어",
    "Talysh": "탈리시어",
    "Brahui": "브라후이어",
    "Hazaragi": "하자라기어",
    "Kurdish, Central": "쿠르드어", "Kurdish, Southern": "쿠르드어",
    "Kurdish, Northern": "쿠르드어",
    "Central Kurdish": "쿠르드어", "Southern Kurdish": "쿠르드어",
    "Northern Kurdish": "쿠르드어",
    "Balochi, Southern": "발루치어", "Balochi, Western": "발루치어",
    "Aimaq": "아이마크어",
    "Iranian Persian": "페르시아어",
    "Semnani": "셈난어", "Sangisari": "셈난어",
    "Lasgerdi": "셈난어", "Shahmirzadi": "셈난어", "Sorkhei": "셈난어",
    "Persian": "페르시아어",
    "Dari": "다리어", "Parsi-Dari": "다리어",
    "Tat, Muslim": "타트어", "Judeo-Tat": "타트어",
    "Pashto, Southern": "파슈토어", "Pashto, Northern": "파슈토어",
    "Southern Pashto": "파슈토어", "Northern Pashto": "파슈토어",
    "Assyrian Neo-Aramaic": "아시리아어",
    # ---- Afghanistan additional ----
    "Pashai, Northeast": "파샤이어", "Pashai, Northwest": "파샤이어",
    "Pashai, Southeast": "파샤이어", "Pashai, Southwest": "파샤이어",
    "Kateviri": "누리스타니어", "Komviri": "누리스타니어",
    "Prasuni": "누리스타니어", "Waigali": "누리스타니어",
    "Tregami": "누리스타니어", "Ashkun": "누리스타니어",
    "Wakhi": "와키어",
    "Shughni": "샤그니어",
    "Munji": "문지어",
    "Sanglechi": "샹글레치어",
    "Ishkashimi": "이슈카심어",
    "Kyrgyz": "키르기스어",
    "Karakalpak": "카라칼파크어",
    "Uzbek, Northern": "우즈베크어", "Uzbek, Southern": "우즈베크어",
    "Northern Uzbek": "우즈베크어", "Southern Uzbek": "우즈베크어",
    # ---- Russia major L1 languages ----
    "Tatar": "타타르어", "Siberian Tatar": "타타르어",
    "Chechen": "체첸어",
    "Bashkort": "바슈키르어", "Bashkir": "바슈키르어",
    "Avar": "아바르어",
    "Buriat, Russia": "부랴트어", "Russia Buriat": "부랴트어",
    "Buriat": "부랴트어",
    "Yakut": "야쿠트어", "Sakha": "야쿠트어",
    "Chuvash": "추바시어",
    "Kabardian": "카바르딘어",
    "Lezgi": "레즈긴어",
    "Dargwa": "다르긴어", "Kaitag": "다르긴어", "Kubachi": "다르긴어",
    "Mari, Meadow": "마리어", "Mari, Hill": "마리어",
    "Meadow Mari": "마리어", "Hill Mari": "마리어",
    "Erzya": "에르자어",
    "Moksha": "목샤어",
    "Komi-Zyrian": "코미어", "Komi-Permyak": "코미어", "Komi": "코미어",
    "Udmurt": "우드무르트어",
    "Ossetic, Iron": "오세트어", "Ossetic, Digor": "오세트어",
    "Karachay-Balkar": "카라차이발카르어",
    "Kumyk": "쿠믹어",
    "Ingush": "인구시어",
    "Adyghe": "아디게어", "Abaza": "아바자어", "Abkhaz": "압하스어",
    "Tuvan": "투바어",
    "Khakas": "하카스어",
    "Altai, Southern": "알타이어", "Altai, Northern": "알타이어",
    "Southern Altai": "알타이어", "Northern Altai": "알타이어",
    "Kalmyk-Oirat": "칼미크어",
    "Nogai": "노가이어",
    "Lak": "락어",
    "Tabasaran": "타바사란어",
    "Karelian": "카렐리아어", "Livvi-Karelian": "카렐리아어",
    "Ludian": "카렐리아어",
    "Pontic": "그리스어",
    "Mongolian, Halh": "몽골어", "Halh Mongolian": "몽골어",
    "Khamnigan Mongol": "몽골어",
    "Khanty": "한티어",
    "Mansi": "만시어",
    "Nenets": "네네츠어",
    "Nganasan": "응가나산어",
    "Selkup": "셀쿠프어",
    "Veps": "벱스어",
    "Saami, Kildin": "사미어", "Saami, Skolt": "사미어",
    "Saami, Akkala": "사미어", "Saami, Ter": "사미어",
    "Chukchi": "축치어",
    "Koryak": "코랴크어",
    "Even": "에벤어",
    "Evenki": "에벤키어",
    "Nanai": "나나이어",
    "Itelmen": "이텔멘어",
    "Nivkh": "닐히어",
    "Yupik, Central Siberian": "유픽어",
    "Yupik, Naukan": "유픽어",
    "Ket": "케트어",
    "Bezhta": "베즈타어", "Hinukh": "히눅어", "Hunzib": "훈지브어",
    "Dido": "지도어",
    "Akhvakh": "안디어", "Andi": "안디어", "Bagvalal": "안디어",
    "Botlikh": "안디어", "Chamalal": "안디어", "Ghodoberi": "안디어",
    "Karata": "안디어", "Tindi": "안디어",
    "Khvarshi": "지도어",
    "Aghul": "레즈긴어", "Archi": "레즈긴어", "Rutul": "레즈긴어",
    "Tsakhur": "레즈긴어", "Udi": "레즈긴어",
    # ---- Sudan major L1 languages ----
    "Bedawiyet": "베자어",
    "Fur": "푸르어",
    "Masalit": "마살리트어",
    "Zaghawa": "자가와어",
    "Midob": "누비아어",
    "Andaandi": "누비아어", "Nobiin": "누비아어",
    "Karko": "누비아어", "Kadaru": "누비아어",
    "Dilling": "누비아어", "Ghulfan": "누비아어",
    "Tama": "타마어",
    "Tegali": "테갈리어",
    "Daju, Dar Fur": "다주어", "Daju, Dar Sila": "다주어",
    "Shatt": "다주어", "Logorik": "다주어",
    "Koalib": "누바어", "Tira": "누바어", "Otoro": "누바어",
    "Moro": "누바어", "Heiban": "누바어", "Laro": "누바어",
    "Logol": "누바어", "Shwai": "누바어", "Lumun": "누바어",
    "Dagik": "누바어", "Ngile": "누바어", "Tocho": "누바어",
    "Acheron": "누바어", "Lafofa": "누바어", "Nding": "누바어",
    "Talodi": "누바어", "Tagoi": "누바어", "Tegali": "누바어",
    "Katcha-Kadugli-Miri": "누바어", "Krongo": "누바어",
    "Tumtum": "누바어", "Tulishi": "누바어", "Kanga": "누바어",
    "Keiga": "누바어", "Tese": "누바어",
    "Ama": "누바어", "Afitti": "누바어",
    "Temein": "누바어",
    "Berta": "베르타어",
    "Gumuz": "구무즈어",
    "Burun": "마반어", "Jumjum": "마반어",
    "Uduk": "우두크어",
    "Komo": "코마어", "Gwama": "콰마어", "Ganza": "마오어",
    "Daatsʼíin": "구무즈어",
    "Beygo": "기타", "Birked": "기타", "Berti": "기타",
    "Sulaihab": "마바어",
    "Kanuri, Yerwa": "카누리어", "Bornu": "카누리어",
    "Kanuri": "카누리어", "Kanuri, Manga": "카누리어",
    "Yerwa Kanuri": "카누리어", "Manga Kanuri": "카누리어",
    "Tedaga": "테다어",
    "Amdang": "기타",
    "Mararit": "마라리트어",
    "Assangori": "타마어",
    "Atong": "아통어",
}


# Province names as the released files romanize them, Revised Romanization with
# the -do suffix. The renamed provinces keep both labels so a row filed under
# either name resolves.
SIDO_EN = {
    "서울특별시": "Seoul", "부산광역시": "Busan", "대구광역시": "Daegu",
    "인천광역시": "Incheon", "광주광역시": "Gwangju", "대전광역시": "Daejeon",
    "울산광역시": "Ulsan", "세종특별자치시": "Sejong", "경기도": "Gyeonggi-do",
    "강원도": "Gangwon-do", "강원특별자치도": "Gangwon-do", "충청북도": "Chungcheongbuk-do",
    "충청남도": "Chungcheongnam-do", "전라북도": "Jeollabuk-do", "전북특별자치도": "Jeollabuk-do",
    "전라남도": "Jeollanam-do", "경상북도": "Gyeongsangbuk-do", "경상남도": "Gyeongsangnam-do",
    "제주특별자치도": "Jeju-do",
}


# ── index formulas ───────────────────────────────────────────────────────────
import math


OTHER_REGION = "기타"
KOREAN_REGION = "동아시아"


def shannon(counts):
    """Shannon entropy of the nationality composition, natural log, 3 dp."""
    t = sum(counts.values())
    if not t:
        return 0.0
    return round(-sum((v / t) * math.log(v / t) for v in counts.values() if v > 0), 3)


def incl(counts, pop):
    """Shannon entropy with Korean nationals as one further group.

    The ethnic diversity of the district as a whole rather than of its foreign
    population. `pop` is the resident-registration population, which is a
    register of Korean nationals and never contained the foreign residents, so
    the Korean count IS `pop` and the total is pop + foreigners. Through v1.1.0
    this subtracted the foreigners from `pop` first, which understated Koreans by
    f and inflated the index wherever the foreign share is high (Ansan Danwon-gu
    2024: 0.659 against 0.598). The segregation family always used the correct
    convention, so the two sat on different footings in one release.
    """
    f = sum(counts.values())
    if not f or not pop:
        return None
    kor = max(pop, 0)
    T = f + kor
    h = 0.0
    for v in list(counts.values()) + [kor]:
        if v > 0:
            p = v / T
            h -= p * math.log(p)
    return round(h, 3)


def cont(counts, pop):
    """(continent entropy, continent shares) for one district.

    The shares are of the foreign population; the entropy is inclusive, so
    Korean nationals are added to 동아시아 first.
    """
    reg = {}
    for nm, v in counts.items():
        k = COUNTRY_REGION.get(nm, OTHER_REGION)
        reg[k] = reg.get(k, 0) + v
    ftot = sum(counts.values())
    shares = ({k: round(100 * v / ftot, 3)
               for k, v in sorted(reg.items(), key=lambda x: -x[1])} if ftot else {})
    full_r = dict(reg)
    # 내국인 수는 주민등록 그대로다. incl() 의 주석 참조
    kor = max(pop if pop else 0, 0)
    full_r[KOREAN_REGION] = full_r.get(KOREAN_REGION, 0) + kor
    T = sum(full_r.values())
    h = 0.0
    for v in full_r.values():
        if v > 0:
            p = v / T
            h -= p * math.log(p)
    return round(h, 4), shares


def hhi(counts):
    """Herfindahl-Hirschman index of the nationality composition, 4 dp."""
    t = sum(counts.values())
    if not t:
        return None
    return round(sum((v / t) ** 2 for v in counts.values()), 4)


def pielou(H, S):
    """Pielou's evenness, `shannon_H / ln(n_nationalities)`."""
    if H is None or not S or S <= 1:
        return None
    return round(H / math.log(S), 3)


def make_record(sido, sigungu, nat, total_pop, lisa=None):
    """One district-year index record, the shape `indices.json` stores."""
    H = shannon(nat)
    S = len(nat)
    cH, shares = cont(nat, total_pop)
    f = sum(nat.values())
    return {"sido": sido, "sigungu": sigungu, "foreign_total": f, "total_pop": total_pop,
            "foreign_share_pct": round(100 * f / total_pop, 2) if total_pop else None,
            "shannon_H": H, "shannon_H_inclusive": incl(nat, total_pop), "continent_H": cH,
            "continent_shares": shares, "HHI": hhi(nat), "n_nationalities": S,
            "lisa": lisa, "evenness": pielou(H, S)}


def morans_i(value_by_key, adjacency):
    """Global Moran's I of a value mapped by sigungu match_key.

    Queen contiguity, binary weights, from the cached adjacency. Returns None
    where fewer than ten districts join to the weights.
    """
    if not adjacency:
        return None
    keys = [k for k in value_by_key if k in adjacency]
    n = len(keys)
    if n < 10:
        return None
    mean = sum(value_by_key[k] for k in keys) / n
    z = {k: value_by_key[k] - mean for k in keys}
    kset = set(keys)
    num = 0.0
    W = 0
    for k in keys:
        for nb in adjacency.get(k, []):
            if nb in kset:
                num += z[k] * z[nb]
                W += 1
    denom = sum(v * v for v in z.values())
    if W == 0 or denom == 0:
        return None
    return (n / W) * (num / denom)


# ── name normalization ───────────────────────────────────────────────────────
# 행정구역 이름을 코드에 붙이기 전에 한 벌로 다듬는 규칙. 아래 코드 층이 전부 이
# 규칙 하나만 쓴다. 층마다 두 벌을 만들지 않는 것이 요점이다.
import re

SEP = re.compile(r"[\s·.,・ㆍᆞ‧･()]")
def norm(s: str) -> str:
    return SEP.sub("", s or "").strip()

# ---- 시도 alias: MOIS/KIS 표기 → 2024 geojson 표기(신명칭) ----
SIDO_ALIAS = {
    "강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도",
    "강원특별자치도": "강원특별자치도", "전북특별자치도": "전북특별자치도", "제주특별자치도": "제주특별자치도",
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "강원": "강원특별자치도", "전북": "전북특별자치도", "제주": "제주특별자치도",
    "경기": "경기도", "충북": "충청북도", "충남": "충청남도",
    "경북": "경상북도", "경남": "경상남도", "전남": "전라남도",
}
def canon_sido(name: str) -> str:
    n = (name or "").strip()
    return SIDO_ALIAS.get(n, n)

# ---- 동명 변형 후보 (제N동 ↔ N동, 면↔읍) ----
def dong_variants(dong: str):
    out = {dong}
    m = re.match(r"^(.*?)제(\d+동)$", dong)      # 고덕제1동 -> 고덕1동
    if m: out.add(m.group(1) + m.group(2))
    m = re.match(r"^(.*?)(\d+동)$", dong)         # 고덕1동 -> 고덕제1동
    if m and "제" not in m.group(1)[-1:]: out.add(m.group(1) + "제" + m.group(2))
    # 숫자접미 N동 → 통합동(2024년 합쳐진 경우): 고잔1동·고잔2동 → 고잔동, 가능3동 → 가능동.
    # (2024에 실제 통합동이 있을 때만 매칭되므로 분동 유지 지역은 영향 없음)
    base = re.sub(r"제?\d+동$", "동", dong)
    if base != dong: out.add(base)
    # '본동' 통합형: 원곡본동·소사본동 → 원곡동·소사동
    if dong.endswith("본동"): out.add(dong[:-2] + "동")
    if dong.endswith("면"): out.add(dong[:-1] + "읍")
    elif dong.endswith("읍"): out.add(dong[:-1] + "면")
    return out

# ---- 시군구(구) alias: 과거 경북 군위군 → 2023 대구 편입 ----
SGG_SIDO_MOVE = {("경상북도", "군위군"): "대구광역시"}

# ---- 시군구 개명/승격 alias: (정규화 sido, 정규화 sgg) → 2024 sggnm(정규화) ----
SGG_RENAME = {
    ("인천광역시", "남구"): "미추홀구",      # 2018 미추홀구 개명
    ("경기도", "여주군"): "여주시",          # 2013 시 승격
}

# ---- 읍면동 단순 개명(1:1, 경계 동일) — 데이터엔 코드가 없어 이름으로 매칭. 행안부 행정구역 개편 근거 ----
# (시도, 옛 동명) → 2024 동명. 전 연도 1:1 미매칭 후보에서 실제 개명만 검증 채택(오탐 제외).
_EMD_RENAME_RAW = [
    ("경상북도", "금수면", "금수강산면"),    # 성주 2016
    ("경상북도", "양북면", "문무대왕면"),    # 경주 2021
    ("경상북도", "부동면", "주왕산면"),      # 청송 2016
    ("경상북도", "사벌면", "사벌국면"),      # 상주 2018
    ("경상북도", "고령읍", "대가야읍"),      # 고령 2015
    ("경기도", "능서면", "세종대왕면"),      # 여주 2021
    ("경기도", "석수3동", "충훈동"),         # 안양 만안 2018
    ("경기도", "하면", "조종면"),            # 가평 2015
    ("강원도", "중동면", "산솔면"),          # 영월 2021
    ("강원도", "수주면", "무릉도원면"),      # 영월 2016
    ("서울특별시", "일원2동", "개포3동"),    # 강남 2016(일원2동→개포3동)
    ("서울특별시", "면목제3.8동", "면목3·8동"),  # 중랑(표기차)
    ("서울특별시", "금호2-3가동", "금호2·3가동"),  # 성동(표기차)
]
EMD_RENAME = {(norm(canon_sido(sd)), norm(old)): new for sd, old, new in _EMD_RENAME_RAW}


# ── the 2024 boundary anchor ─────────────────────────────────────────────────
# 행정구역 코드 기반 join 시스템 (2024 기준 앵커, FIPS식).
#
# admdong2024 소스 geojson의 공식 행정코드(시도 2자리 / 시군구 5자리 / 행정동 8자리)를
# 정규 테이블로 만들고, MOIS·KIS의 '이름'을 위 alias 규칙으로 정규화해 코드로 매핑한다.
# 이름 매칭의 깨지기 쉬움을 코드 join으로 대체하고, 매핑 불가 항목을 체계적으로 missing 리포트.
#
# 핵심:
#   build_tables()        -> ADMIN(시도/시군구/읍면동 코드 테이블) 반환 + admin2024.json 저장
#   geocode_sido/sgg/emd  -> 이름 → 코드 (alias 규칙 적용). 실패 시 None.
# 2024년에 사라진(병합·개명) 과거 동은 2024 코드가 없으므로 None → '진짜 missing'으로 분류.

import json

ADMDONG2024_GEOJSON = os.path.join(ROOT, "_emd_geo", "admdong2024.geojson")
ADMIN2024_JSON = os.path.join(ROOT, "05_dashboard", "data", "admin2024.json")


def build_tables():
    src = json.load(open(ADMDONG2024_GEOJSON, encoding="utf-8"))
    sido_t, sgg_t, emd_t = {}, {}, {}
    # 이름 인덱스 (정규화 키 → 코드)
    idx_sido, idx_sgg, idx_emd, idx_emd_loose, si_children = {}, {}, {}, {}, {}
    for f in src["features"]:
        p = f["properties"]
        sido_c, sgg_c, adm_c = p["sido"], p["sgg"], p["adm_cd"]
        sidonm, sggnm = p["sidonm"], p["sggnm"]
        pre = sidonm + " " + sggnm + " "
        dong = p["adm_nm"][len(pre):] if p["adm_nm"].startswith(pre) else p["adm_nm"].split(" ")[-1]
        sido_t[sido_c] = sidonm
        sgg_t[sgg_c] = {"sido_code": sido_c, "sidonm": sidonm, "sggnm": sggnm}
        emd_t[adm_c] = {"sgg": sgg_c, "sido_code": sido_c, "sidonm": sidonm, "sggnm": sggnm, "dong": dong}
        idx_sido[norm(sidonm)] = sido_c
        idx_sgg[(norm(sidonm), norm(sggnm))] = sgg_c
        idx_emd[(norm(sidonm), norm(sggnm), norm(dong))] = adm_c
        idx_emd_loose.setdefault((norm(sidonm), norm(dong)), adm_c)
        # 'OO시OO구' → 부모 시(OO시)의 자식 구 코드 목록 (초기연도 시-단위 보고 확장용)
        m = re.match(r"^(.+?시)(.+구)$", sggnm)
        if m:
            si_children.setdefault((sido_c, norm(m.group(1))), set()).add(sgg_c)
    tables = {"sido": sido_t, "sigungu": sgg_t, "emd": emd_t}
    json.dump(tables, open(ADMIN2024_JSON, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return tables, (idx_sido, idx_sgg, idx_emd, idx_emd_loose, {k: sorted(v) for k, v in si_children.items()})


# 인덱스는 첫 호출 때 만든다. 소스 geojson이 34MB라, alias 규칙만 가져다 쓰는
# 아래 코드 층이 kird 를 import 한 번에 그걸 다 읽는 일이 없도록 지연 구축한다.
_BUILT = {}
_LAZY = ("ADMIN2024_TABLES", "IDX_SIDO", "IDX_SGG", "IDX_EMD", "IDX_EMD_LOOSE", "SI_CHILDREN")


def _tables():
    if not _BUILT:
        t, (a, b, c, d, e) = build_tables()
        _BUILT.update(ADMIN2024_TABLES=t, IDX_SIDO=a, IDX_SGG=b, IDX_EMD=c,
                      IDX_EMD_LOOSE=d, SI_CHILDREN=e)
    return _BUILT


def __getattr__(name):
    if name in _LAZY:
        return _tables()[name]
    raise AttributeError(name)


def geocode_sido(sido: str):
    return _tables()["IDX_SIDO"].get(norm(canon_sido(sido)))


def geocode_sgg(sido: str, sgg: str):
    """단일 시군구 코드. 'OO시'(구 보유)처럼 단일 코드가 없으면 None → geocode_sgg_codes 사용."""
    s = canon_sido(sido)
    s = SGG_SIDO_MOVE.get((sido, (sgg or "").strip()), s)        # 군위군 등 이동
    sg2 = SGG_RENAME.get((norm(s), norm(sgg)), sgg)              # 남구→미추홀구 등
    key = (norm(s), norm(sg2))
    return _tables()["IDX_SGG"].get(key)


def geocode_sgg_codes(sido: str, sgg: str):
    """시군구 → 1개 이상 코드 목록. 'OO시'(구 보유) 초기연도 보고는 자식 구 전체로 확장."""
    c = geocode_sgg(sido, sgg)
    if c:
        return [c]
    s = canon_sido(sido)
    kids = _tables()["SI_CHILDREN"].get((geocode_sido(sido), norm(sgg)))
    return list(kids) if kids else []


def geocode_emd(sido: str, sgg: str, dong: str):
    T = _tables()
    IDX_EMD, IDX_EMD_LOOSE = T["IDX_EMD"], T["IDX_EMD_LOOSE"]
    s = canon_sido(sido)
    s = SGG_SIDO_MOVE.get((sido, (sgg or "").strip()), s)
    ns = norm(s); nsgg = norm(sgg)
    # 1순위: 원본 동명 그대로(정확 일치) — 변형보다 항상 우선(분동 유지 지역 오매칭 방지)
    norig = norm(dong)
    if (ns, nsgg, norig) in IDX_EMD:
        return IDX_EMD[(ns, nsgg, norig)]
    if (ns, norig) in IDX_EMD_LOOSE:
        return IDX_EMD_LOOSE[(ns, norig)]
    # 1.5순위: 검증된 단순 개명(1:1). 옛 이름 → 2024 이름으로 정확 매칭.
    ren = EMD_RENAME.get((ns, norig))
    if ren:
        rn = norm(ren)
        if (ns, nsgg, rn) in IDX_EMD:
            return IDX_EMD[(ns, nsgg, rn)]
        if (ns, rn) in IDX_EMD_LOOSE:
            return IDX_EMD_LOOSE[(ns, rn)]
    # 2순위: 구조적 변형(구-접두 제거/출장소 부모/숫자접미 통합 등). 2024에 실제 있을 때만 매칭.
    bases = [dong]
    toks = (sgg or "").split()
    gu = toks[-1] if len(toks) > 1 and toks[-1].endswith("구") else None
    if gu and dong.startswith(gu) and dong != gu:        # (a) sgg 구토큰 글루 '장안구송죽동'
        bases.append(dong[len(gu):])
    m = re.match(r"^(.+?구)(.+(?:동|읍|면))$", dong)        # (b) 임의 '구' 접두(부모시 보고 '덕양구고양동')
    if m:
        bases.append(m.group(2))
    if "출장소" in dong:                                   # (c) 출장소→부모 읍/면/동 합산
        pm = re.match(r"^(.*?[읍면동])", dong)
        if pm and pm.group(1) != dong:
            bases.append(pm.group(1))
    cands = []
    for b in bases:
        for d in dong_variants(b):
            if d not in cands:
                cands.append(d)
    for d in cands:                                       # 변형: strict 먼저
        if (ns, nsgg, norm(d)) in IDX_EMD:
            return IDX_EMD[(ns, nsgg, norm(d))]
    for d in cands:                                       # 변형: loose(시군구 무시)
        if (ns, norm(d)) in IDX_EMD_LOOSE:
            return IDX_EMD_LOOSE[(ns, norm(d))]
    return None


# ── the 법정동코드 register ──────────────────────────────────────────────────
# 연도별 행정구역 코드 층 — 이름 대신 그 해 정부 코드로 붙이기 위한 모듈.
#
# 공개 테이블은 지금까지 한글 지명으로만 이어져 있었다. 지명은 안 변한다는 보장이
# 없다. 인천 남구는 2018년 미추홀구가 됐고, 군위군은 2023년 경북에서 대구로 옮겼고,
# 창원·마산·진해는 2010년에 합쳤고, 청원군은 2014년 청주시로 들어갔고, 큰 시의
# 일반구는 판마다 '고양시 덕양구' / '고양시' + '덕양구고양동' / '마산합포구'처럼 다르게
# 적힌다. 그때마다 join이 조용히 어긋난다. 그래서 이름을 고치는 규칙을 하나 더 만드는
# 대신, 그 해 정부가 쓰던 코드로 옮겨 붙인다.
#
# 권위 자료는 행정안전부 행정표준코드관리시스템의 법정동코드 전체자료다
# (01_raw_data/행정표준코드/, 그 폴더 README에 URL과 받은 날짜). 10자리 법정동코드는
# SS-GGG-EEE-RR 구조라 앞 2자리가 시도, 앞 5자리가 시군구(일반구 포함)다. 이 두
# 자리수는 행정동코드 체계와 같은 값을 쓰므로 시도·시군구 층에서는 두 체계가 갈리지
# 않는다. 읍면동 층은 05_dashboard/data/emd_years/ 의 연도별 경계 스냅샷이 그 해
# 코드를 이미 갖고 있어 그쪽을 그대로 쓴다.
#
# 기준 시점은 각 연도의 12월 31일이다. 자료가 그 해 말 기준으로 발행되고, 한 해
# 안에 일어난 개편(2014-07-01 청주·청원 통합, 2023-07-01 군위군 대구 편입)을 그 해
# 자료가 이미 반영하기 때문이다.
#
#   sido_code(year, sido)                       2자리 코드, 못 풀면 None
#   sigungu_code(year, sido, sigungu)           5자리 코드, 못 풀면 None
#   eupmyeondong_sigungu_code(y, sd, sg, dong)  읍면동 행의 5자리 코드
#   emd_boundary(year, sido, sigungu, dong)     그 해 경계의 (시도, 시군구명, 읍면동코드)
#   year_table()                                연도별 코드표, JSON으로도 저장
#
# 이름 정규화는 위 name normalization 절의 norm, canon_sido 를 그대로 쓴다. 두 벌을 만들지
# 않는다. 못 푼 이름은 코드를 지어내지 않고 빈칸으로 두고 unresolved()에 쌓는다.

import glob
import io
import zipfile
from collections import defaultdict

import pandas as pd

REG_DIR = os.path.join(RAW, "행정표준코드")
REGISTER_CACHE = os.path.join(CLEAN, "admin_code_register.csv")
YEAR_TABLE = os.path.join(SITE_DATA, "admin_codes_by_year.json")

# 끊는 해가 둘이다.
#
#   LAST_YEAR          원자료를 어디까지 읽는가. 화면(05_dashboard)이 이만큼
#                      보여 준다. 법무부 연감이 나온 마지막 해다.
#   RELEASE_LAST_YEAR  배포본과 기탁본과 두 논문이 어디서 끊는가. 행정안전부의
#                      외국인주민 통계가 나온 마지막 해다.
#
# 둘이 다른 이유는 두 부처의 발행 시차다. 화면은 법무부 계수만으로도 보여 줄
# 값이 있지만, 배포본에 그 해를 실으면 광의 정의 열이 통째로 빈 행이 된다.
# MOIS 가 따라오면 RELEASE_LAST_YEAR 를 올리고 파이프라인을 다시 돌린다.
FIRST_YEAR, LAST_YEAR = 2006, 2025
RELEASE_LAST_YEAR = 2024

# ---- 시도 계보 -------------------------------------------------------------
# 같은 시도가 코드를 갈아탄 경우만 묶는다. 이름이 달라도 한 줄에 있으면 한 시도다.
# 2026-07-01 전남광주통합특별시(12)는 광주(29)와 전남(46)을 흡수하지만, 이 자료는
# 2025년에서 끝나므로 계보에 넣지 않았다. 2026년 이후로 늘릴 때 넣어야 한다.
SIDO_LINEAGE = [
    ("21", "26"),   # 부산직할시 -> 부산광역시 (1995-01-01)
    ("22", "27"),   # 대구직할시 -> 대구광역시 (1995-01-01)
    ("23", "28"),   # 인천직할시 -> 인천광역시 (1995-01-01)
    ("24", "29"),   # 광주직할시 -> 광주광역시 (1995-01-01)
    ("25", "30"),   # 대전직할시 -> 대전광역시 (1995-01-01)
    ("42", "51"),   # 강원도 -> 강원특별자치도 (2023-06-11)
    ("45", "52"),   # 전라북도 -> 전북특별자치도 (2024-01-18)
    ("49", "50"),   # 제주도 -> 제주특별자치도 (2006-07-01)
]

# ---- 시군구 계보 -----------------------------------------------------------
# 이름이나 상위 시도가 바뀌어 코드가 갈린 승계 관계. 파이프라인이 이미 선언해 둔 것과
# 같은 목록이다(08_export_dataset.py _RENAMES, 06_build_summaries.py RECOVER,
# 이 파일 위쪽 SGG_RENAME / SGG_SIDO_MOVE). 여기서는 양방향으로 쓴다. 옛 이름이
# 뒤 연도에 남아 있으면 후계 코드로, 현행 이름이 앞 연도에 쓰이면 그 해 전신 코드로
# 풀린다. 공개본이 전 기간 현행 이름으로 라벨을 통일해 두었기 때문에 뒤쪽이 특히
# 필요하다(2014년 행이 '미추홀구'라고 적혀 있어도 그 해 코드는 남구 28170이다).
SGG_LINEAGE = [
    (("인천광역시", "남구"), ("인천광역시", "미추홀구")),          # 2018-07-01 개명
    (("경상북도", "군위군"), ("대구광역시", "군위군")),            # 2023-07-01 대구 편입
    (("충청북도", "청원군"), ("충청북도", "청주시 청원구")),        # 2014-07-01 청주 통합
    (("경상남도", "진해시"), ("경상남도", "창원시 진해구")),        # 2010-07-01 창원 통합
    (("충청남도", "당진군"), ("충청남도", "당진시")),              # 2012-01-01 시 승격
    (("경기도", "여주군"), ("경기도", "여주시")),                  # 2013-09-23 시 승격
    (("경기도", "포천군"), ("경기도", "포천시")),                  # 2003-10-19 시 승격
    (("충청남도", "연기군"), ("세종특별자치시", "세종특별자치시")),   # 2012-07-01 세종 출범
]

# 자료가 시군구 자리에 쓰는 별칭. 어느 칸을 가리키는 말인가만 옮긴다.
# 세종은 단층제라 법정동코드에 시군구 행 하나(3611000000)뿐이고 그 이름이 곧 시도명이다.
SGG_NAME_ALIAS = {
    ("세종특별자치시", "세종시"): "세종특별자치시",
    ("세종특별자치시", "총계"): "세종특별자치시",
    ("세종특별자치시", "0"): "세종특별자치시",
}

# 공개본이 하나의 시군구로 유지하는 일반구. 부천시 일반구는 2016-07-01 폐지되고
# 2024-01-01 다시 생겼는데, 공개본은 패널을 끊지 않으려고 전 기간 '부천시' 한 칸으로
# 낸다(08_export_dataset.py _BUCHEON_GU). 그래서 그 밑 읍면동도 부천시 코드를 단다.
# 부천시 코드는 그 해에도 실재하는 코드이므로 지어낸 값이 아니라 한 단계 위 코드다.
_RELEASE_PARENT_RAW = {
    ("경기도", "부천시 원미구"): "부천시",
    ("경기도", "부천시 소사구"): "부천시",
    ("경기도", "부천시 오정구"): "부천시",
    ("경기도", "원미구"): "부천시",
    ("경기도", "소사구"): "부천시",
    ("경기도", "오정구"): "부천시",
}
# 띄어쓰기가 판마다 다르고 경계 파일은 '부천시소사구'처럼 붙여 쓰므로 정규화해 둔다
RELEASE_PARENT = dict(((norm(a), norm(b)), c) for (a, b), c in _RELEASE_PARENT_RAW.items())

_UNRESOLVED = defaultdict(int)


def unresolved():
    """못 푼 (층, 연도, 시도, 이름) 별 건수."""
    return dict(_UNRESOLVED)


def reset_unresolved():
    _UNRESOLVED.clear()


def _ref(year):
    return int(year) * 10000 + 1231


# ---- 원자료 읽기 -----------------------------------------------------------
def _latest_zip():
    zs = sorted(glob.glob(os.path.join(REG_DIR, "법정동코드_조회자료_*.zip")))
    if not zs:
        raise SystemExit("법정동코드 조회자료가 없다. python 02_code/kird.py --fetch-codes 로 "
                         "받아라 (기대 위치 %s)" % REG_DIR)
    return zs[-1]


def _parse_register():
    """법정동코드 조회자료 xlsx -> 시도·시군구 행만 남긴 납작한 표."""
    src = _latest_zip()
    with zipfile.ZipFile(src) as z:
        member = [n for n in z.namelist() if n.endswith(".xlsx")][0]
        raw = pd.read_excel(io.BytesIO(z.read(member)), dtype=str)
    raw = raw.rename(columns=lambda c: str(c).strip())

    def d(x):
        s = "" if pd.isna(x) else str(x).strip()
        return int(s[:8]) if re.fullmatch(r"\d{8}", s[:8]) else None

    rows = []
    cols = ["법정동코드", "법정동명", "폐지구분", "생성일", "폐지일"]
    for code, name, flag, crt, cls in raw[cols].itertuples(index=False):
        code = str(code).strip()
        if len(code) != 10 or not code.isdigit():
            continue
        if code.endswith("00000000"):
            level = "sido"
        elif code.endswith("00000"):
            level = "sgg"
        else:
            continue
        start, end = d(crt), d(cls)
        # 등록기가 코드를 닫은 날을 생성일 칸에도 적어 둔 레코드(생성일 == 폐지일)가
        # 157건 있다. 그 생성일은 실제 설치일이 아니므로 모름으로 둔다.
        if start is not None and start == end:
            start = None
        rows.append((code, str(name).strip(), level,
                     str(flag).strip() == "현존", start, end))
    df = pd.DataFrame(rows, columns=["code", "name", "level", "alive", "start", "end"])
    os.makedirs(os.path.dirname(REGISTER_CACHE), exist_ok=True)
    df.to_csv(REGISTER_CACHE, index=False, encoding="utf-8-sig")
    print("  법정동코드 %s -> 시도 %d, 시군구 %d (캐시 %s)"
          % (os.path.basename(src), int((df.level == "sido").sum()),
             int((df.level == "sgg").sum()), os.path.basename(REGISTER_CACHE)))
    return df


def _register():
    src = _latest_zip()
    if os.path.exists(REGISTER_CACHE) and os.path.getmtime(REGISTER_CACHE) >= os.path.getmtime(src):
        return pd.read_csv(REGISTER_CACHE, encoding="utf-8-sig",
                           dtype={"code": str, "name": str, "level": str})
    return _parse_register()


# ---- 인덱스 ---------------------------------------------------------------
class _Rec(object):
    __slots__ = ("code", "name", "start", "end", "alive")

    def __init__(self, code, name, start, end, alive):
        self.code, self.name, self.alive = code, name, bool(alive)
        self.start = None if pd.isna(start) else int(start)
        self.end = None if pd.isna(end) else int(end)

    def live_at(self, ref, ignore_start=False):
        if not ignore_start and self.start is not None and self.start > ref:
            return False
        if self.end is not None and self.end <= ref:
            return False
        return True

    def __repr__(self):
        return "<%s %s %s~%s>" % (self.code, self.name, self.start, self.end)


def _pick(cands, ref):
    """ref 시점에 있던 레코드 하나. 없으면 생성일을 풀어 한 번 더 본다.

    등록기가 옛 구역 다섯 건(부천시 세 일반구, 청원군, 전주시 덕진구)의 생성일을
    2013-04-02(일괄 적재일)로 적어 두어 실제 설치일보다 늦다. 엄격 판정이 비면
    생성일을 무시하고 폐지일만 보며, 그중 ref 직후에 닫힌 레코드를 고른다.

    두 번째 판정은 이미 폐지됐고 폐지일이 있는 레코드에만 적용한다. 현존 레코드의
    생성일은 뒤에서 덮어쓴 기록이 없어 믿을 수 있고, 풀어 주면 아직 생기지도 않은
    구역이 과거 연도에 되살아난다(2026-07-01 전남광주통합특별시, 인천 제물포구).
    """
    for ignore in (False, True):
        pool = cands if not ignore else [r for r in cands if not r.alive and r.end is not None]
        live = [r for r in pool if r.live_at(ref, ignore)]
        if len(live) == 1:
            return live[0]
        if live:
            return sorted(live, key=lambda r: (r.end if r.end is not None else 99999999,
                                               -(r.start or 0)))[0]
    return None


def _build():
    df = _register()
    grp_of = {}
    for grp in SIDO_LINEAGE:
        for c in grp:
            grp_of[c] = grp[0]

    def gid(c2):
        return grp_of.get(c2, c2)

    sido_recs = defaultdict(list)
    sido_name = {}
    for r in df[df.level == "sido"].itertuples(index=False):
        c2 = r.code[:2]
        sido_recs[c2].append(_Rec(c2, r.name, r.start, r.end, r.alive))
        if r.alive or c2 not in sido_name:
            sido_name[c2] = r.name

    sgg_raw = list(df[df.level == "sgg"].itertuples(index=False))
    # 8자리 0으로 끝나는 시도 행이 없는 시도(세종특별자치시)는 시군구 행에서 세운다.
    for r in sgg_raw:
        c2 = r.code[:2]
        if c2 not in sido_recs:
            head = r.name.split(" ")[0]
            sido_recs[c2].append(_Rec(c2, head, r.start, r.end, r.alive))
            sido_name[c2] = head

    sido_by_name = defaultdict(set)
    for c2, recs in sido_recs.items():
        for rc in recs:
            sido_by_name[norm(rc.name)].add(c2)

    lineage, recs_by_key, path_of = {}, defaultdict(list), {}

    def find(k):
        while lineage.get(k, k) != k:
            k = lineage[k]
        return k

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            lineage[rb] = ra

    for r in sgg_raw:
        c2 = r.code[:2]
        sname = sido_name.get(c2, "")
        full = r.name
        path = full[len(sname) + 1:] if sname and full.startswith(sname + " ") else full
        key = (gid(c2), norm(path))
        recs_by_key[key].append(_Rec(r.code[:5], full, r.start, r.end, r.alive))
        path_of.setdefault(key, path)
        lineage.setdefault(key, key)

    def key_of(sd, sg):
        c2s = sido_by_name.get(norm(sd)) or sido_by_name.get(norm(canon_sido(sd)))
        return (gid(sorted(c2s)[0]), norm(sg)) if c2s else None

    for a, b in SGG_LINEAGE:
        ka, kb = key_of(*a), key_of(*b)
        if ka in lineage and kb in lineage:
            union(ka, kb)

    fam = defaultdict(list)
    for k, rs in recs_by_key.items():
        fam[find(k)].extend(rs)
    # 폐지 표시인데 폐지일이 빈 레코드(경기도 여주군)는 같은 계보의 다음 생성일로 닫는다.
    for rs in fam.values():
        for rc in rs:
            if rc.end is None and not rc.alive:
                later = [s.start for s in rs if s.start is not None
                         and (rc.start is None or s.start > rc.start)]
                rc.end = min(later) if later else None

    key_fam = {k: fam[find(k)] for k in recs_by_key}

    # 부모 시 없이 적힌 일반구('마산합포구') -> 그 시도 안에서 유일한 전체 경로.
    # 시도 안에서만 찾으므로 광주 남구가 포항시 남구로 끌려가지 않는다.
    bare = defaultdict(set)
    for k, path in path_of.items():
        if " " in path:
            bare[(k[0], norm(path.split(" ")[-1]))].add(k)
    bare = dict((b, next(iter(v))) for b, v in bare.items()
                if len(v) == 1 and b not in recs_by_key)

    return {"sido_recs": sido_recs, "sido_name": sido_name, "sido_by_name": sido_by_name,
            "gid": gid, "key_fam": key_fam, "bare": bare, "path_of": path_of,
            "keys": set(recs_by_key)}


_IX = {}


def _ix():
    if not _IX:
        _IX.update(_build())
    return _IX


# ── per-year codes ───────────────────────────────────────────────────────────
def sido_code(year, sido):
    """그 해 12/31 기준 시도 2자리 코드. 못 풀면 None."""
    ix = _ix()
    c2s = ix["sido_by_name"].get(norm(sido)) or ix["sido_by_name"].get(norm(canon_sido(sido)))
    if not c2s:
        _UNRESOLVED[("sido", int(year), "", str(sido))] += 1
        return None
    g = ix["gid"](sorted(c2s)[0])
    cands = [rc for c2, recs in ix["sido_recs"].items() if ix["gid"](c2) == g for rc in recs]
    r = _pick(cands, _ref(year))
    if r is None:
        _UNRESOLVED[("sido", int(year), "", str(sido))] += 1
        return None
    return r.code


def _sgg_key(sido, sgg):
    ix = _ix()
    name = SGG_NAME_ALIAS.get((str(sido).strip(), str(sgg).strip())) or str(sgg).strip()
    c2s = ix["sido_by_name"].get(norm(sido)) or ix["sido_by_name"].get(norm(canon_sido(sido)))
    if not c2s:
        return None
    g = ix["gid"](sorted(c2s)[0])
    k = (g, norm(name))
    if k in ix["keys"]:
        return k
    return ix["bare"].get((g, norm(name)))


def sigungu_code(year, sido, sigungu, release_grain=True):
    """그 해 12/31 기준 시군구 5자리 코드. 못 풀면 None.

    release_grain=True면 공개본이 하나로 유지하는 일반구(부천시 원미·소사·오정구)를
    모시(부천시) 코드로 올린다. 공개본 시군구 표가 그 칸을 부천시로 내기 때문이다.
    """
    sd, sg = str(sido).strip(), str(sigungu).strip()
    if release_grain:
        sg = RELEASE_PARENT.get((norm(sd), norm(sg)), sg)
    k = _sgg_key(sd, sg)
    if k is None:
        _UNRESOLVED[("sigungu", int(year), sd, str(sigungu))] += 1
        return None
    r = _pick(_ix()["key_fam"][k], _ref(year))
    if r is None:
        _UNRESOLVED[("sigungu", int(year), sd, str(sigungu))] += 1
        return None
    return r.code


# ---- 읍면동: 그 해 경계 스냅샷 ---------------------------------------------
_EMD_CACHE = {}
_SEP2 = re.compile(r"[\s·.,・ㆍᆞ‧･]")


def _emdnorm(s):
    return re.sub(r"제(\d)", r"\1", _SEP2.sub("", s or ""))


def _emd_label(y):
    y = int(y)
    return "2014" if y <= 2014 else ("2024" if y >= 2024 else str(y))


_CITY_GU = re.compile(r"^(.+?시)(.+구)$")
_NUM_DONG = re.compile(r"\d+동$")
_BRANCH = re.compile(r"^(.*?[읍면동])")
EMD_YEARS = tuple(range(2014, 2025))


def _collapse(ndong):
    """분동 표기를 하나로: 광교1동/광교2동 -> 광교동. 원자료와 경계가 서로 다른 해의
    분동 상태를 적을 때, 그 동이 어느 일반구인지만 알면 되는 자리에서 쓴다."""
    return _NUM_DONG.sub("동", ndong)


def _emd_index(year):
    lab = _emd_label(year)
    if lab in _EMD_CACHE:
        return _EMD_CACHE[lab]
    path = (os.path.join(SITE_DATA, "korea_emd.json") if lab == "2024"
            else os.path.join(SITE_DATA, "emd_years", "korea_emd_%s.json" % lab))
    ix = {"strict": {}, "part": {}, "loose": {},
          "strict_c": {}, "part_c": {}, "loose_c": {}}
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    for ft in g["features"]:
        p = ft["properties"]
        v = (p["sido"], p["sg"], p.get("code", ""))
        sg, dong = _emdnorm(p["sg"]), _emdnorm(p["dong"])
        c = _collapse(dong)
        ix["strict"][(p["sido"], sg, dong)] = v
        ix["strict_c"].setdefault((p["sido"], sg, c), v)
        # '고양시덕양구'는 모시('고양시')로도, 구('덕양구')로도 찾을 수 있게 둔다.
        # 자료가 판마다 둘 중 하나만 적기 때문이다(2014년은 시만, 2024년은 구만).
        m = _CITY_GU.match(p["sg"])
        halves = [_emdnorm(m.group(1)), _emdnorm(m.group(2))] if m else []
        for h in halves:
            ix["part"].setdefault((p["sido"], h, dong), v)
            ix["part_c"].setdefault((p["sido"], h, c), v)
        ix["loose"].setdefault((p["sido"], dong), v)
        ix["loose_c"].setdefault((p["sido"], c), v)
    _EMD_CACHE[lab] = ix
    return ix


def _look(ix, sido, sg, dongs):
    """한 해 인덱스 안에서 정확 -> 반쪽 -> 시도 순으로, 이름 후보를 차례로 맞춰 본다."""
    for keyset in ("strict", "part", "loose", "strict_c", "part_c", "loose_c"):
        collapsed = keyset.endswith("_c")
        for d in dongs:
            d2 = _collapse(d) if collapsed else d
            k = (sido, d2) if keyset.startswith("loose") else (sido, sg, d2)
            hit = ix[keyset].get(k)
            if hit:
                return hit
    return None


def _dong_candidates(dong):
    d = _emdnorm(dong)
    out = [d]
    if "출장소" in d:                       # 죽장면상옥출장소 -> 죽장면
        m = _BRANCH.match(d)
        if m and m.group(1) != d:
            out.append(m.group(1))
    return out


def emd_boundary(year, sido, sigungu, dong):
    """그 해 경계 스냅샷의 (시도, 그 해 시군구명, 그 해 읍면동 코드). 못 찾으면 None.

    시군구명이 그 해 경계와 그대로 맞으면 거기서 끝이고, 아니면 모시나 구 한쪽만
    적힌 경우로 보고 반쪽 이름으로 맞춰 보고, 그래도 없으면 시도 안에서 동 이름만으로
    찾는다. 반쪽 단계가 있어서 원자료가 '고양시'라고만 적은 2014년과 '마산합포구'라고만
    적은 2024년이 같은 동을 서로 다른 시군구로 끌고 가지 않는다.
    """
    return _look(_emd_index(year), sido, _emdnorm(sigungu), _dong_candidates(dong))


def boundary_sigungu_name(year, sido, sigungu, dong):
    """그 동이 그 해 어느 시군구에 있었는지, 이름으로. 못 찾으면 None.

    그 해 스냅샷에 없는 동이 있다. 2014년 수원 광교동은 2015년부터 광교1·2동으로
    나뉜 뒤에야 경계에 나타나고, 천안 부성1·2동과 불당동도 마찬가지다. 그런 동은
    가까운 해 스냅샷에서 찾는다. 일반구 소속은 그 사이에 바뀌지 않으므로 이름만
    가져오고 코드는 쓰지 않는다(코드는 늘 그 행의 연도로 다시 푼다).
    """
    b = emd_boundary(year, sido, sigungu, dong)
    if b:
        return b[0], b[1]
    y = int(year)
    for other in sorted(EMD_YEARS, key=lambda o: (abs(o - y), o)):
        if other == y:
            continue
        b = _look(_emd_index(other), sido, _emdnorm(sigungu), _dong_candidates(dong))
        if b:
            return b[0], b[1]
    return None


def eupmyeondong_sigungu_code(year, sido, sigungu, dong):
    """읍면동 행의 시군구 코드. 그 해 경계가 말하는 일반구를 먼저 쓴다."""
    b = boundary_sigungu_name(year, sido, sigungu, dong)
    if b:
        c = sigungu_code(year, b[0], b[1])
        if c:
            return c
    return sigungu_code(year, sido, sigungu)


# ---- 공개 테이블에 코드 열 붙이기 ------------------------------------------
def add_code_columns(df, verbose_name=""):
    """sido_code / sigungu_code 를 sido_en / sigungu_en 옆에 끼운 새 DataFrame.

    이미 있으면 지우고 다시 계산한다(같은 입력이면 같은 결과라 몇 번 돌려도 같다).
    eupmyeondong 열이 있는 표는 그 해 경계가 말하는 일반구를 먼저 써서 시군구 코드를
    정한다. 원자료가 '고양시'처럼 모시로만 적은 해에도 동이 속한 구를 되찾기 위해서다.
    값은 문자열이고, 못 푼 자리는 빈칸으로 둔다(코드를 지어내지 않는다).
    """
    if "year" not in df.columns:
        return df
    df = df.drop(columns=[c for c in ("sido_code", "sigungu_code") if c in df.columns])
    if "sido" not in df.columns:
        return df

    years = df["year"].astype(str).str.slice(0, 4)
    sido = df["sido"].fillna("").astype(str)

    if "sigungu" in df.columns:
        sgg = df["sigungu"].fillna("").astype(str)
        if "eupmyeondong" in df.columns:
            dong = df["eupmyeondong"].fillna("").astype(str)
            keys = list(zip(years, sido, sgg, dong))
            cache = {}
            for k in set(keys):
                cache[k] = ("" if not k[1] or not k[2]
                            else (eupmyeondong_sigungu_code(*k) or ""))
        else:
            keys = list(zip(years, sido, sgg))
            cache = {}
            for k in set(keys):
                cache[k] = "" if not k[1] or not k[2] else (sigungu_code(*k) or "")
        sgg_vals = [cache[k] for k in keys]
    else:
        sgg_vals = None

    sd_keys = list(zip(years, sido))
    sd_cache = {}
    for k in set(sd_keys):
        sd_cache[k] = "" if not k[1] else (sido_code(*k) or "")
    sd_vals = [sd_cache[k] for k in sd_keys]
    if sgg_vals is not None:
        # 그 해 없던 시도 이름(2011년 세종특별자치시)은 시군구 코드 앞 2자리로 잇는다
        sd_vals = [a or (b[:2] if b else "") for a, b in zip(sd_vals, sgg_vals)]

    cols = list(df.columns)
    df = df.assign(sido_code=sd_vals)
    cols.insert(cols.index("sido_en") + 1 if "sido_en" in cols else cols.index("sido") + 1,
                "sido_code")
    if sgg_vals is not None:
        df = df.assign(sigungu_code=sgg_vals)
        cols.insert(cols.index("sigungu_en") + 1 if "sigungu_en" in cols
                    else cols.index("sigungu") + 1, "sigungu_code")
    if verbose_name:
        n = sum(1 for v in (sgg_vals or []) if not v)
        print("  %-38s sido_code + sigungu_code (빈 시군구코드 %d)" % (verbose_name, n))
    return df[cols]


# ---- 연도별 코드표 ---------------------------------------------------------
def year_table(first=FIRST_YEAR, last=LAST_YEAR, save=True):
    """{연도: {'sido': {코드: 이름}, 'sigungu': {코드: [시도코드, 전체이름]}}}"""
    ix = _ix()
    out = {}
    for y in range(int(first), int(last) + 1):
        ref = _ref(y)
        sd = {}
        for c2, recs in ix["sido_recs"].items():
            r = _pick(recs, ref)
            if r is not None and r.code == c2:
                sd[c2] = r.name
        sg, seen = {}, set()
        for k, famrecs in ix["key_fam"].items():
            if id(famrecs) in seen:
                continue
            seen.add(id(famrecs))
            r = _pick(famrecs, ref)
            if r is not None:
                sg[r.code] = [r.code[:2], r.name]
        out[str(y)] = {"sido": dict(sorted(sd.items())),
                       "sigungu": dict(sorted(sg.items()))}
    if save:
        os.makedirs(os.path.dirname(YEAR_TABLE), exist_ok=True)
        with open(YEAR_TABLE, "w", encoding="utf-8") as f:
            json.dump({"source": "행정안전부 행정표준코드관리시스템 법정동코드 전체자료",
                       "source_url": "https://www.code.go.kr/stdcode/regCodeL.do",
                       "reference_instant": "12-31 of each year",
                       "years": out}, f, ensure_ascii=False, separators=(",", ":"))
        print("  wrote %s" % YEAR_TABLE)
    return out


SPOT_CHECKS = [
    (2017, "인천광역시", "미추홀구"), (2017, "인천광역시", "남구"),
    (2019, "인천광역시", "미추홀구"),
    (2022, "대구광역시", "군위군"), (2022, "경상북도", "군위군"),
    (2023, "대구광역시", "군위군"),
    (2015, "경상남도", "창원시 마산합포구"), (2015, "경상남도", "마산합포구"),
]


# ── register download ────────────────────────────────────────────────────────
# 행정안전부 행정표준코드관리시스템에서 법정동코드 전체자료를 내려받는다 (필요할 때만 실행).
#
# 받는 곳은 https://www.code.go.kr/stdcode/regCodeL.do 의 두 버튼이다.
#
#   전체자료   POST /etc/codeFullDown.do          codeseId=법정동코드
#              -> '법정동코드 전체자료.txt' (cp949, 탭 구분, 3열: 코드/이름/폐지여부)
#   조회자료   POST /stdcode/regCodeFileDown.do   폐지구분=전체 + 선택 열 전부
#              -> '법정동코드 조회자료.xlsx' (같은 레코드 + 생성일/폐지일)
#
# 파이프라인이 읽는 건 조회자료 쪽이다. 연도별 코드를 풀려면 생성일·폐지일이 있어야
# 하고, 그 두 열은 조회자료 다운로드에만 붙는다. 전체자료는 기관이 공표한 원본
# 그대로라는 뜻으로 같이 보관한다.
#
# 받은 zip은 01_raw_data/행정표준코드/ 에 날짜를 붙여 저장하고, 그 폴더의 README가
# 출처와 받은 날짜를 적어 둔다. 사이트가 자동 다운로드를 막으면 무엇이 막았는지
# 그대로 출력하고 종료한다 (임의로 코드를 만들어 채우지 않는다).

import datetime as _dt
import warnings

LIST_URL = "https://www.code.go.kr/stdcode/regCodeL.do"
FULL_URL = "https://www.code.go.kr/etc/codeFullDown.do"
QUERY_URL = "https://www.code.go.kr/stdcode/regCodeFileDown.do"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 조회 폼의 값. 체크박스는 체크된 상태가 "0"이다 (func_choice 참고).
# disuseAt=ALL 이라야 폐지된 코드까지 나오고, 폐지 코드가 있어야 옛 시군구를 푼다.
QUERY_FORM = {
    "cPage": "1", "regionCd_pk": "", "chkWantCnt": "8",
    "reqSggCd": "", "reqUmdCd": "", "reqRiCd": "", "searchOk": "",
    "codeseId": "00002", "pageSize": "10", "regionCd": "", "locataddNm": "",
    "sidoCd": "", "sggCd": "", "umdCd": "", "riCd": "",
    "disuseAt": "ALL", "stdate": "", "enddate": "",
    "chkHigh": "0", "chkOrder": "0", "chkCrtDt": "0", "chkClsDt": "0",
    "chkLocatDt": "0", "chkLow": "0", "chkJumin": "0", "chkJijuk": "0",
}


def _register_session():
    import requests

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    s = requests.Session()
    s.verify = False          # code.go.kr 인증서 체인이 requests 기본 번들에 없다
    s.headers.update({"User-Agent": UA, "Referer": LIST_URL})
    s.get(LIST_URL, timeout=60)   # 세션 쿠키
    return s


def _save_register_zip(content: bytes, path: str, expect_member: str) -> None:
    if not content[:2] == b"PK":
        raise SystemExit(f"다운로드가 zip이 아니다 ({len(content)} bytes). 사이트가 막았는지 확인:\n"
                         + content[:400].decode("cp949", errors="replace"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if not any(expect_member in n for n in names):
        raise SystemExit(f"{path}: 기대한 파일이 없다 ({names})")
    print(f"  저장 {os.path.basename(path)}  {len(content):,} bytes  {names}")


def fetch_admin_codes(stamp: str | None = None) -> None:
    stamp = stamp or _dt.date.today().strftime("%Y%m%d")
    s = _register_session()
    print(f"행정표준코드 법정동코드 내려받기 ({stamp}) -> {REG_DIR}")

    r = s.post(FULL_URL, data={"codeseId": "법정동코드"}, timeout=600)
    _save_register_zip(r.content, os.path.join(REG_DIR, f"법정동코드_전체자료_{stamp}.zip"), "전체자료")

    # pageSize 는 URL 로만 먹는다. 레코드 수보다 넉넉하게 준다.
    r = s.post(QUERY_URL + "?cPage=1&pageSize=60000", data=QUERY_FORM, timeout=900)
    _save_register_zip(r.content, os.path.join(REG_DIR, f"법정동코드_조회자료_생성폐지일자포함_{stamp}.zip"), "조회자료")
    print("done.")


# ── entry points ─────────────────────────────────────────────────────────────
# 기본은 해석된 경로 확인이고, 나머지 셋은 이 모듈이 흡수한 세 스크립트의 옛 __main__이다.
def _cli(argv):
    flag = argv[0] if argv else ""
    if flag == "--fetch-codes":
        fetch_admin_codes(argv[1] if len(argv) > 1 else None)
        return 0
    if flag == "--code-table":
        t = year_table()
        for y in ("2006", "2015", "2023", "2025"):
            print("  %s: 시도 %d, 시군구 %d" % (y, len(t[y]["sido"]), len(t[y]["sigungu"])))
        print("\n손검증:")
        for y, sd, sg in SPOT_CHECKS:
            print("  %d %s %-16s sido=%s sigungu=%s"
                  % (y, sd, sg, sido_code(y, sd), sigungu_code(y, sd, sg)))
        if unresolved():
            print("\n못 푼 이름:", unresolved())
        return 0
    if flag == "--admin2024":
        T = _tables()["ADMIN2024_TABLES"]
        print(f"시도 {len(T['sido'])}, 시군구 {len(T['sigungu'])}, 읍면동 {len(T['emd'])}")
        print("저장:", ADMIN2024_JSON)
        return 0
    if flag:
        print("모르는 옵션: %s (--fetch-codes / --code-table / --admin2024)" % flag)
        return 2
    for name in __all__:
        value = globals()[name]
        print(f"{name:<14} {'ok ' if os.path.isdir(value) else 'MISSING'} {value}")
    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(_cli(_sys.argv[1:]))



def cut_release_years(folder=None, last=None):
    """배포 폴더의 CSV 에서 RELEASE_LAST_YEAR 뒤의 행을 뺀다.

    화면은 법무부 연감이 나온 마지막 해까지 보여 주지만, 배포본과 기탁본은 두
    출처가 다 있는 해에서 끊는다. 반쯤 빈 해를 기탁하면 광의 정의 열이 통째로
    빈 행이 실린다.

    부르는 자리는 09 의 reconcile_indices 바로 뒤다. 분리지수는 그 전에
    LAST_YEAR 까지 다 지어 지표 파일에 되써야, 화면의 마지막 해만 다른 방식으로
    계산되는 일이 없다. 자르기가 사전·Stata·감사보다 앞이므로 CSV 와 .dta 와
    감사가 모두 같은 자료를 본다.

    지표는 전부 해마다 따로 계산되므로(상위 19개국도 그 해 전국 합에서 고른다)
    나중에 잘라도 남는 해의 값은 달라지지 않는다.
    """
    import csv

    folder = folder or RELEASE_DATA
    last = RELEASE_LAST_YEAR if last is None else last
    print("\n===== cut the release at %d =====" % last, flush=True)
    total = 0
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".csv"):
            continue
        p = os.path.join(folder, f)
        with io.open(p, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        if not rows:
            continue
        head = rows[0]
        if "year" not in head:
            continue
        j = head.index("year")
        keep, dropped = [head], 0
        for row in rows[1:]:
            try:
                y = int(row[j])
            except (ValueError, IndexError):
                keep.append(row)
                continue
            if y > last:
                dropped += 1
            else:
                keep.append(row)
        if not dropped:
            continue
        with io.open(p, "w", encoding="utf-8-sig", newline="") as fh:
            csv.writer(fh).writerows(keep)
        print("  %-34s dropped %d rows past %d" % (f, dropped, last))
        total += dropped
    print("  %d rows removed in all" % total if total
          else "  nothing past %d was written" % last)
    return total