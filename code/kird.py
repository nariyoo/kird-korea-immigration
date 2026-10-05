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
shares, then the 2024 boundary anchor, then the '법정동코드' (legal-dong code) register, then the
per-year resolver built on it, then the fetcher that downloads the register.

  norm, canon_sido            one set of name-normalization rules
  geocode_sido/sgg/emd        name -> 2024 anchor code
  sido_code, sigungu_code     name -> the code that year, 12-31 as the instant
  add_code_columns            sido_code / sigungu_code onto a released table
  year_table                  the code table year by year, saved as JSON

Command line:

  python 02_code/kird.py                 the resolved paths (the default)
  python 02_code/kird.py --fetch-codes   download the '법정동코드' register
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
    "태국": "타이",            # 2017 only used '태국'; all other years use '타이'
    "터키": "튀르키예",         # renamed officially 2022
    "키르기즈": "키르기스스탄", # 2017+ used '키르기즈'; older yrs use '키르기스스탄'
    "그루지야": "조지아",       # Korean govt switched ~2011
    "러시아": "러시아(연방)",   # 2008 district table and the 2010 stay table use the short form
    "벨로루시": "벨라루스",     # newer official spelling
    "슬로바크": "슬로바키아",   # 2017 used '슬로바키아'; others '슬로바크'
    # Taiwan: every table prints '타이완', and no edition 2006-2025 prints '대만' anywhere
    # (all 901 yearbook workbooks read, 2026-09-27). A '대만' -> '타이완' line here made
    # crosswalk_country claim a merge no table makes; the key it papered over, a '대만'
    # left in COUNTRY_REGION from an earlier map, is gone too (round 3 cross-check).
    "마케도니아": "북마케도니아", # official rename 2019
    "스와질란드": "에스와티니",  # official rename 2018
    # Zaire -> DR Congo (renamed 1997). The yearbook keeps the legacy code and
    # publishes it beside '콩고민주공화국' (7 people a year on the stay basis).
    # crosswalk_country already gives both the same English label, DR Congo, so
    # the table itself says they are one country. Added 2026-08-26 after a sweep
    # found it was the only English label with two Korean names left in the data.
    # '동독' is NOT merged: its English label is East Germany, a different country.
    "자이르": "콩고민주공화국",
    "미국인근섬": "미국",          # dependent territory → merge into '미국' (USA)
    "미령버진아일랜드": "미국",
    "미령사모아": "미국",          # American Samoa; first appears in the 2025 chapter 4 table
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
    # Yemen: 2017 used '예멘', all other years use '예멘공화국'
    "예멘": "예멘공화국",
    # Timor-Leste: 2019 used '동티모르', others use '티모르민주공화국'
    "동티모르": "티모르민주공화국",
}


# World-region classification of nationalities, for region-level segregation.
COUNTRY_REGION = {
    # East Asia
    "중국": "동아시아", "한국계중국인": "동아시아", "일본": "동아시아",
    "몽골": "동아시아", "홍콩": "동아시아", "마카오": "동아시아",
    # Filled in on 2026-08-25. A name missing from this table falls into 「기타」
    # (Other), and 116 names the data actually uses were missing, so 25,232 people
    # (2025) were counted as Other in the region indices. The largest was '타이완'
    # (17,187 people); the table had only 「대만」, a name no table uses. The regions
    # follow manuscript Supplementary Table 2. Only entries that are not countries
    # stay in Other.
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
    # Not countries, so Other is correct: '국적불명', '무국적', '국제연합', '국제연합전문기구'
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
    # Countries that no longer exist. Ethnologue has no country code for them, so only
    # a single-language fallback is possible.
    # ('동독' 2009-2010, 3 people; '유고슬라비아' 1; '세르비아몬테네그로' 1. These are old
    # codes left in the yearbook. They are real nationalities, so they are not merged
    # and get that country's language.)
    "동독": "독일어", "유고슬라비아": "세르비아어", "세르비아몬테네그로": "세르비아어",
    # Places with no country-code row in the Ethnologue LICs table
    "코소보": "알바니아어", "스발바르": "노르웨이어",
    "한국계중국인": "중국어", "중국": "중국어", "타이완": "중국어", "홍콩": "중국어", "마카오": "중국어",
    "베트남": "베트남어",
    "타이": "태국어",
    "미국": "영어", "캐나다": "영어", "영국": "영어", "오스트레일리아": "영어", "뉴질랜드": "영어", "아일랜드": "영어",
    "한국계미국인": "영어",   # as '한국계러시아인': the country of residence (2026-09-27)
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
# no '시'/'도' suffix.
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

# Korean labels for the languages that carried an English label into language_demand
# although they appear in a district's top 20, or reach 500 estimated speakers at
# the national or province scope in some year (2026-09-27, round 2 cross-check: the Korean
# column repeated the English name for 1,049 of 1,460 national labels in 2024,
# among them '따이어' 5,782 and '위구르어' 3,153). Where Korean has no settled name the
# label transliterates the Ethnologue name under '외래어 표기법' (the loanword
# orthography rules). Varieties of one
# language that this map already lumps (Tamang, Magar) join that label.
LANG_EN_KO.update({
    "Tày": "따이어", "Nung": "눙어", "Muong": "므엉어", "Tai Dam": "타이담어",
    "Cao Lan": "까오란어", "Koho": "꺼호어", "Jarai": "자라이어", "Bahnar": "바나르어",
    "Rade": "에데어", "Western Cham": "서부 참어", "Phuan": "푸안어",
    "Lü": "타이뤼어", "Kuay": "쿠아이어", "Northern Khmer": "북부 크메르어",
    "Thai Sign Language": "태국 수어",
    "Pattani Malay": "파타니 말레이어", "Kedah Malay": "크다 말레이어",
    "Central Malay": "중부 말레이어", "Musi": "무시어",
    "Capiznon": "카피스논어", "Aklanon": "아클라논어", "Surigaonon": "수리가오논어",
    "Masbatenyo": "마스바테뇨어",
    "Oirat": "오이라트어", "Uyghur": "위구르어", "Crimean Tatar": "크림 타타르어",
    "Zuojiang Zhuang": "쭤장 좡어", "Yongbei Zhuang": "융베이 좡어",
    "Yongnan Zhuang": "융난 좡어", "Liujiang Zhuang": "류장 좡어",
    "Guibei Zhuang": "구이베이 좡어", "Guibian Zhuang": "구이볜 좡어",
    "Youjiang Zhuang": "유장 좡어", "Yang Zhuang": "양 좡어",
    "Eastern Hongshuihe Zhuang": "동부 훙수이허 좡어",
    "Central Hongshuihe Zhuang": "중부 훙수이허 좡어",
    "Southern Pinghua": "남부 핑화", "Northern Pinghua": "북부 핑화",
    "Bouyei": "부이어", "Nuosu": "누오쑤어", "Iu Mien": "이우미엔어",
    "Kim Mun": "킴문어", "Chuanqiandian Cluster Miao": "촨첸뎬 먀오어",
    "Amis": "아미스어", "Central Okinawan": "중부 오키나와어",
    "Chittagonian": "치타공어", "Sylheti": "실헤트어", "Rangpuri": "랑푸리어",
    "Rohingya": "로힝야어",
    "Western Tamang": "타망어", "Northwestern Tamang": "타망어",
    "Western Magar": "마가르어",
    "Bemba": "벰바어", "Kiribati": "키리바시어",
})
# Some keys above are in Ethnologue's inverted form ('Malay, Manado'), which the
# Ethnologue table's uninverted names never match ('Manado Malay'), so twenty
# languages this map names kept their English label. Add the uninverted spelling of
# each; an explicit key above wins (2026-09-27).
for _k, _v in list(LANG_EN_KO.items()):
    if ", " in _k:
        _a, _b = _k.split(", ", 1)
        LANG_EN_KO.setdefault(f"{_b} {_a}", _v)
del _k, _v


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

# Lines in the yearbook that hold people but name no nationality: '무국적' (stateless),
# '미등록국가' and '미상', a single '기타' (other) line or column, and '한국'. The national
# status tables print them as lines, the district tables as columns, and the release
# carries them at every level where the table prints them, so each level adds up to
# the printed total. They are never a nationality: they do not count in
# n_nationalities_observed, are never ranked into an index's top 19, never form an
# enclave and never get a segregation row of their own; the indices' residual bin
# takes them. In the 2008-2013 district tables '기타' is the residual of every
# nationality those editions do not list by name. (2026-09-26)
# '국적불명', '국제연합' and '국제연합전문기구' name no country either (2026-09-26).
RESIDUAL_LINES = frozenset({"무국적", "기타", "미등록국가", "미상", "한국",
                            "국적불명", "국제연합", "국제연합전문기구"})


# ── estimated first-language speakers ────────────────────────────────────────
# language_demand is nationality count x that country's first-language share
# (country_language_shares.json, at most four decimals, the table language_weights.csv
# publishes). It is computed here in integer units of 1/10,000 person, so the result
# does not depend on the order the nationalities are added in, and is rounded once,
# half up, to whole persons. Until 2026-09-27 (round 2 cross-check) the national and
# district scopes of the release were read from a dashboard block already rounded to
# one decimal and rounded again, so about 5% of those rows were one person off a
# re-derivation from the released files and some estimates under one person passed
# the one-person floor.
LANG_UNIT = 10000


def language_estimate(counts, shares, fallback=None):
    """{language: estimated speakers x LANG_UNIT} for {nationality: persons}.

    A nationality in `shares` splits over its list (an empty list is deliberate: a
    wholly Korean-L1 origin, or a line that names no nationality, adds nothing); one
    missing from it goes whole to `fallback[nationality]` when that names a language.
    """
    out = {}
    for c, n in counts.items():
        if not n:
            continue
        n = int(n)
        if c in shares:
            for sh in shares[c]:
                w = int(round(float(sh["share"]) * LANG_UNIT))
                out[sh["language"]] = out.get(sh["language"], 0) + n * w
        elif fallback and fallback.get(c):
            out[fallback[c]] = out.get(fallback[c], 0) + n * LANG_UNIT
    return out


def lang_persons(units):
    """Whole persons from language_estimate units, rounded half up."""
    return (int(units) + LANG_UNIT // 2) // LANG_UNIT


def shannon(counts):
    """Shannon entropy of the nationality composition, natural log, 3 dp."""
    t = sum(counts.values())
    if not t:
        return 0.0
    # + 0.0: a one-nationality unit gives -0.0, which the CSV would print as "-0.0"
    return round(-sum((v / t) * math.log(v / t) for v in counts.values() if v > 0), 3) + 0.0


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
    Korean nationals are added to '동아시아' (East Asia) first.
    """
    reg = {}
    for nm, v in counts.items():
        k = COUNTRY_REGION.get(nm, OTHER_REGION)
        reg[k] = reg.get(k, 0) + v
    ftot = sum(counts.values())
    shares = ({k: round(100 * v / ftot, 3)
               for k, v in sorted(reg.items(), key=lambda x: -x[1])} if ftot else {})
    full_r = dict(reg)
    # The Korean count is the resident registration as is. See the comment in incl()
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
# One set of rules that cleans administrative-area names before codes are attached.
# Every code layer below uses only these rules. The point is not to keep a second
# copy per layer.
import re

SEP = re.compile(r"[\s·.,・ㆍᆞ‧･()]")
def norm(s: str) -> str:
    return SEP.sub("", s or "").strip()

# ---- province alias: MOIS/KIS spelling → 2024 geojson spelling (new names) ----
SIDO_ALIAS = {
    "강원도": "강원특별자치도", "전라북도": "전북특별자치도", "제주도": "제주특별자치도",
    "강원특별자치도": "강원특별자치도", "전북특별자치도": "전북특별자치도", "제주특별자치도": "제주특별자치도",
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "강원": "강원특별자치도", "전북": "전북특별자치도", "제주": "제주특별자치도",
    "경기": "경기도", "충북": "충청북도", "충남": "충청남도",
    "경북": "경상북도", "경남": "경상남도", "전남": "전라남도",
}
# Province names as the release carries them. SIDO_ALIAS gathers names under the new
# names to match the boundary file (2024 geojson), but the release keeps '강원도' and
# '전라북도' under those names after the reorganization (the code is that year's:
# 42->51, 45->52). SIDO_CANONICAL in 01 and 05 puts the data under these names, and
# crosswalks.region_crosswalk writes the target names from this (2026-09-26, round 3
# cross-check: the crosswalk named '강원특별자치도' and '전북특별자치도' as targets,
# names that never appear in the data).
RELEASE_SIDO_NAME = {"강원특별자치도": "강원도", "전북특별자치도": "전라북도"}
# The release's district name for Sejong. The register lookup alias (SGG_NAME_ALIAS)
# gathers it under '세종특별자치시'.
RELEASE_SGG_NAME = {("세종특별자치시", "세종특별자치시"): "세종시"}


def canon_sido(name: str) -> str:
    n = (name or "").strip()
    return SIDO_ALIAS.get(n, n)

# ---- dong name variant candidates ('제N동' ↔ 'N동', '면' ↔ '읍') ----
def dong_variants(dong: str):
    out = {dong}
    m = re.match(r"^(.*?)제(\d+동)$", dong)      # '고덕제1동' -> '고덕1동'
    if m: out.add(m.group(1) + m.group(2))
    m = re.match(r"^(.*?)(\d+동)$", dong)         # '고덕1동' -> '고덕제1동'
    if m and "제" not in m.group(1)[-1:]: out.add(m.group(1) + "제" + m.group(2))
    # Numbered 'N동' → merged dong (when merged by 2024): '고잔1동', '고잔2동' → '고잔동',
    # '가능3동' → '가능동'. (Matches only when the merged dong really exists in 2024,
    # so areas that kept the split are not affected.)
    base = re.sub(r"제?\d+동$", "동", dong)
    if base != dong: out.add(base)
    # '본동' merged form: '원곡본동', '소사본동' → '원곡동', '소사동'
    if dong.endswith("본동"): out.add(dong[:-2] + "동")
    if dong.endswith("면"): out.add(dong[:-1] + "읍")
    elif dong.endswith("읍"): out.add(dong[:-1] + "면")
    return out

# ---- district alias: former Gyeongbuk 'Gunwi-gun' → moved into Daegu in 2023 ----
SGG_SIDO_MOVE = {("경상북도", "군위군"): "대구광역시"}

# ---- district rename/upgrade alias: (normalized sido, normalized sgg) → 2024 sggnm (normalized) ----
SGG_RENAME = {
    ("인천광역시", "남구"): "미추홀구",      # 2018 renamed '미추홀구'
    ("경기도", "여주군"): "여주시",          # 2013 upgraded to city
}

# ---- simple eup/myeon/dong renames (1:1, same boundary). The data has no codes, so
# these match by name. Source: MOIS administrative reorganizations ----
# (sido, old dong name) → 2024 dong name. Only real renames were verified and adopted
# from the 1:1 unmatched candidates across all years (false positives excluded).
_EMD_RENAME_RAW = [
    ("경상북도", "금수면", "금수강산면"),    # Seongju 2016
    ("경상북도", "양북면", "문무대왕면"),    # Gyeongju 2021
    ("경상북도", "부동면", "주왕산면"),      # Cheongsong 2016
    ("경상북도", "사벌면", "사벌국면"),      # Sangju 2018
    ("경상북도", "고령읍", "대가야읍"),      # Goryeong 2015
    ("경기도", "능서면", "세종대왕면"),      # Yeoju 2021
    ("경기도", "석수3동", "충훈동"),         # Anyang Manan 2018
    ("경기도", "하면", "조종면"),            # Gapyeong 2015
    ("강원도", "중동면", "산솔면"),          # Yeongwol 2021
    ("강원도", "수주면", "무릉도원면"),      # Yeongwol 2016
    ("서울특별시", "일원2동", "개포3동"),    # Gangnam 2016 ('일원2동'→'개포3동')
    ("서울특별시", "면목제3.8동", "면목3·8동"),  # Jungnang (spelling difference)
    ("서울특별시", "금호2-3가동", "금호2·3가동"),  # Seongdong (spelling difference)
]
EMD_RENAME = {(norm(canon_sido(sd)), norm(old)): new for sd, old, new in _EMD_RENAME_RAW}


# ── the 2024 boundary anchor ─────────────────────────────────────────────────
# Join system based on administrative codes (2024 anchor, FIPS style).
#
# Builds canonical tables from the official administrative codes in the admdong2024
# source geojson (province 2 digits / district 5 digits / administrative dong 8 digits),
# normalizes the MOIS and KIS names with the alias rules above, and maps them to codes.
# Code joins replace fragile name matching, and items that cannot be mapped are
# reported systematically as missing.
#
# Main parts:
#   build_tables()        -> returns ADMIN (province/district/eup-myeon-dong code tables)
#                            and saves admin2024.json
#   geocode_sido/sgg/emd  -> name → code (alias rules applied). None on failure.
# Old dongs that were gone by 2024 (merged or renamed) have no 2024 code, so they
# return None and are classed as truly missing.

import json

ADMDONG2024_GEOJSON = os.path.join(ROOT, "_emd_geo", "admdong2024.geojson")
ADMIN2024_JSON = os.path.join(ROOT, "05_dashboard", "data", "admin2024.json")


def build_tables():
    src = json.load(open(ADMDONG2024_GEOJSON, encoding="utf-8"))
    sido_t, sgg_t, emd_t = {}, {}, {}
    # name indexes (normalized key → code)
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
        # 'OO시OO구' → child gu codes of the parent city ('OO시'), used to expand
        # city-level reports in the early years
        m = re.match(r"^(.+?시)(.+구)$", sggnm)
        if m:
            si_children.setdefault((sido_c, norm(m.group(1))), set()).add(sgg_c)
    tables = {"sido": sido_t, "sigungu": sgg_t, "emd": emd_t}
    json.dump(tables, open(ADMIN2024_JSON, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return tables, (idx_sido, idx_sgg, idx_emd, idx_emd_loose, {k: sorted(v) for k, v in si_children.items()})


# The indexes are built on the first call. The source geojson is 34MB, so they are
# built lazily, and the code layer below, which only uses the alias rules, does not
# read all of it each time kird is imported.
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
    """Single district code. None when there is no single code, as for 'OO시' (a city with gu); use geocode_sgg_codes then."""
    s = canon_sido(sido)
    s = SGG_SIDO_MOVE.get((sido, (sgg or "").strip()), s)        # moves such as '군위군'
    sg2 = SGG_RENAME.get((norm(s), norm(sgg)), sgg)              # '남구'→'미추홀구' etc.
    key = (norm(s), norm(sg2))
    return _tables()["IDX_SGG"].get(key)


def geocode_sgg_codes(sido: str, sgg: str):
    """District → list of one or more codes. Early-year reports for 'OO시' (a city with gu) expand to all child gu."""
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
    # Priority 1: the original dong name as is (exact match). Always before variants
    # (prevents false matches in areas that kept the split)
    norig = norm(dong)
    if (ns, nsgg, norig) in IDX_EMD:
        return IDX_EMD[(ns, nsgg, norig)]
    if (ns, norig) in IDX_EMD_LOOSE:
        return IDX_EMD_LOOSE[(ns, norig)]
    # Priority 1.5: verified simple renames (1:1). Old name → exact match on the 2024 name.
    ren = EMD_RENAME.get((ns, norig))
    if ren:
        rn = norm(ren)
        if (ns, nsgg, rn) in IDX_EMD:
            return IDX_EMD[(ns, nsgg, rn)]
        if (ns, rn) in IDX_EMD_LOOSE:
            return IDX_EMD_LOOSE[(ns, rn)]
    # Priority 2: structural variants (gu prefix removed, sub-office parent, numbered
    # suffix merged, etc.). Matches only when the name really exists in 2024.
    bases = [dong]
    toks = (sgg or "").split()
    gu = toks[-1] if len(toks) > 1 and toks[-1].endswith("구") else None
    if gu and dong.startswith(gu) and dong != gu:        # (a) sgg gu token glued on, '장안구송죽동'
        bases.append(dong[len(gu):])
    m = re.match(r"^(.+?구)(.+(?:동|읍|면))$", dong)        # (b) any '구' prefix (parent-city report, '덕양구고양동')
    if m:
        bases.append(m.group(2))
    if "출장소" in dong:                                   # (c) '출장소' (sub-office) → added to parent eup/myeon/dong
        pm = re.match(r"^(.*?[읍면동])", dong)
        if pm and pm.group(1) != dong:
            bases.append(pm.group(1))
    cands = []
    for b in bases:
        for d in dong_variants(b):
            if d not in cands:
                cands.append(d)
    for d in cands:                                       # variants: strict first
        if (ns, nsgg, norm(d)) in IDX_EMD:
            return IDX_EMD[(ns, nsgg, norm(d))]
    for d in cands:                                       # variants: loose (district ignored)
        if (ns, norm(d)) in IDX_EMD_LOOSE:
            return IDX_EMD_LOOSE[(ns, norm(d))]
    return None


# ── the '법정동코드' register ────────────────────────────────────────────────
# Per-year administrative code layer: a module for joining on that year's government
# code instead of on names.
#
# Until now the public tables were linked only by Korean place names. Nothing
# guarantees that place names stay the same. Incheon Nam-gu became Michuhol-gu in 2018,
# Gunwi-gun moved from Gyeongbuk to Daegu in 2023, Changwon, Masan and Jinhae merged in
# 2010, Cheongwon-gun joined Cheongju-si in 2014, and the non-autonomous gu of large
# cities are written differently in each edition, as '고양시 덕양구' / '고양시' +
# '덕양구고양동' / '마산합포구'. Each time, the join silently goes wrong. So instead of
# adding one more rule that fixes names, rows are moved onto the code the government
# used that year.
#
# The authoritative source is the full '법정동코드' (legal-dong code) file from the
# MOIS administrative standard code management system ('01_raw_data/행정표준코드/'; the
# README in that folder gives the URL and download date). The 10-digit legal-dong code
# has the structure SS-GGG-EEE-RR, so the first 2 digits are the province and the first
# 5 the district (including non-autonomous gu). These digits take the same values as
# the administrative-dong code system, so the two systems do not diverge at the
# province and district layers. For the eup/myeon/dong layer, the per-year boundary
# snapshots in 05_dashboard/data/emd_years/ already carry that year's codes, so those
# are used as is.
#
# The reference date is 31 December of each year. The data are published as of the
# end of the year, and they already reflect reorganizations within the year
# (2014-07-01 Cheongju-Cheongwon merger, 2023-07-01 Gunwi-gun moved into Daegu).
#
#   sido_code(year, sido)                       2-digit code, None if unresolved
#   sigungu_code(year, sido, sigungu)           5-digit code, None if unresolved
#   eupmyeondong_sigungu_code(y, sd, sg, dong)  5-digit code for an eup/myeon/dong row
#   emd_boundary(year, sido, sigungu, dong)     (province, district name, emd code) in
#                                               that year's boundaries
#   year_table()                                per-year code table, also saved as JSON
#
# Name normalization uses norm and canon_sido from the name normalization section
# above as is. No second copy. Names that cannot be resolved get no invented code;
# they are left blank and collected in unresolved().

import glob
import io
import zipfile
from collections import defaultdict

import pandas as pd

REG_DIR = os.path.join(RAW, "행정표준코드")
REGISTER_CACHE = os.path.join(CLEAN, "admin_code_register.csv")
YEAR_TABLE = os.path.join(SITE_DATA, "admin_codes_by_year.json")

# There are two cut-off years.
#
#   LAST_YEAR          How far the raw data are read. The dashboard (05_dashboard)
#                      shows this far. The last year with an MOJ Statistical Yearbook.
#   RELEASE_LAST_YEAR  Where the release, the deposit and the two papers stop. The
#                      last year with MOIS '외국인주민' (foreign residents) statistics.
#
# They differ because of the publication lag between the two ministries. The
# dashboard has values to show from the MOJ counts alone, but putting that year in
# the release would give rows whose broad-definition columns are all empty.
# When MOIS catches up, raise RELEASE_LAST_YEAR and rerun the pipeline.
FIRST_YEAR, LAST_YEAR = 2006, 2025
RELEASE_LAST_YEAR = 2024

# ---- province lineage ------------------------------------------------------
# Groups only cases where the same province switched codes. Codes on one line are
# one province even when the names differ.
# On 2026-07-01 '전남광주통합특별시' (12) absorbs Gwangju (29) and Jeonnam (46), but
# these data end in 2025, so it is not in the lineage. It must be added when the
# data are extended past 2026.
SIDO_LINEAGE = [
    ("21", "26"),   # '부산직할시' -> '부산광역시' (1995-01-01)
    ("22", "27"),   # '대구직할시' -> '대구광역시' (1995-01-01)
    ("23", "28"),   # '인천직할시' -> '인천광역시' (1995-01-01)
    ("24", "29"),   # '광주직할시' -> '광주광역시' (1995-01-01)
    ("25", "30"),   # '대전직할시' -> '대전광역시' (1995-01-01)
    ("42", "51"),   # '강원도' -> '강원특별자치도' (2023-06-11)
    ("45", "52"),   # '전라북도' -> '전북특별자치도' (2024-01-18)
    ("49", "50"),   # '제주도' -> '제주특별자치도' (2006-07-01)
]

# ---- district lineage ------------------------------------------------------
# Successions where the code changed because the name or the parent province
# changed. The same list the pipeline already declares (08_export_dataset.py
# _RENAMES, 06_build_summaries.py RECOVER, SGG_RENAME / SGG_SIDO_MOVE higher in this
# file). Here it is used in both directions. An old name left in a later year
# resolves to the successor code, and a current name used in an earlier year
# resolves to that year's predecessor code. The second direction is needed in
# particular because the public release labels the whole period with current names
# (a 2014 row may read '미추홀구', but that year's code is Nam-gu 28170).
SGG_LINEAGE = [
    (("인천광역시", "남구"), ("인천광역시", "미추홀구")),          # 2018-07-01 renamed
    (("경상북도", "군위군"), ("대구광역시", "군위군")),            # 2023-07-01 moved into Daegu
    (("충청북도", "청원군"), ("충청북도", "청주시 청원구")),        # 2014-07-01 merged into Cheongju
    (("경상남도", "진해시"), ("경상남도", "창원시 진해구")),        # 2010-07-01 merged into Changwon
    (("충청남도", "당진군"), ("충청남도", "당진시")),              # 2012-01-01 upgraded to city
    (("경기도", "여주군"), ("경기도", "여주시")),                  # 2013-09-23 upgraded to city
    (("경기도", "포천군"), ("경기도", "포천시")),                  # 2003-10-19 upgraded to city
    (("충청남도", "연기군"), ("세종특별자치시", "세종특별자치시")),   # 2012-07-01 Sejong created
]

# Lines the district table prints separately but the release carries on another
# district. Not used for code lookup; carried as rules in crosswalk_region.csv
# (round 1 fix, 2026-09-26: the '화성시동부출장소' and '마산시' lines were missing from
# the crosswalk). The rules are applied by FOLD / SUBOFFICE / FOLD_FROM in
# 04_reconcile_districts.py, for 2008-2013 by REMAP in 03_extend_panel.py and
# _RENAMES in 08_export_dataset.py, and by LINE_TO in check_published_totals.py.
# check_published_totals.district_label_gate checks that every name printed in the
# district table has the same name in the release or a row here.
SGG_LINE_FOLD = [
    (("경기도", "화성시동부출장소"), ("경기도", "화성시"),
     "sub-office (출장소) line of the district table, added to its city"),
    (("경상남도", "마산시"), ("경상남도", "창원시"),
     "line printed after the 2010 merger (2013, 2014), carried on the 창원시 city line"),
    # Round 4 cross-check (2026-09-27): '진해시' had only the lineage pair, no rule row, though
    # the 2008 and 2009 tables print it as a district of its own and the 2011 and 2012
    # tables a residual line of one person, all of it carried on '창원시 진해구'.
    (("경상남도", "진해시"), ("경상남도", "창원시 진해구"),
     "district merged into 창원시 (2010), carried on 창원시 진해구, the gu on its ground: "
     "the whole district in 2008-2009 and a residual line in 2011 and 2012 (1 person each)"),
    (("충청북도", "청원군"), ("충청북도", "청주시 청원구"),
     "residual line of an abolished district, carried on its successor"),
    (("충청남도", "당진군"), ("충청남도", "당진시"),
     "residual line of an abolished district, carried on its successor"),
    (("경기도", "여주군"), ("경기도", "여주시"),
     "residual line of an abolished district, carried on its successor"),
    (("경기도", "포천군"), ("경기도", "포천시"),
     "residual line of an abolished district (2009, 1 person), carried on its successor"),
    (("충청남도", "연기군"), ("세종특별자치시", "세종시"),
     "residual line printed after Sejong's creation (2012-2014), counted in 세종"),
]
# Successions where one city split into several gu. SGG_LINEAGE is for 1:1 code
# lookup, so these are listed separately here. The five gu of the 2010-07-01
# Changwon-Masan-Jinhae merger follow the old city boundaries. TRANSITION in
# 06_build_summaries.py splits the three city rows of MOIS 2010 across these gu.
SGG_SPLIT_LINEAGE = [
    (("경상남도", "마산시"), (("경상남도", "창원시 마산합포구"), ("경상남도", "창원시 마산회원구"))),
    (("경상남도", "창원시"), (("경상남도", "창원시 의창구"), ("경상남도", "창원시 성산구"))),
]

# Aliases the data use in the district slot. Only which cell the name points to is
# translated. Sejong has a single-tier structure, so the legal-dong code register has
# a single district row (3611000000), and its name is the province name.
SGG_NAME_ALIAS = {
    ("세종특별자치시", "세종시"): "세종특별자치시",
    ("세종특별자치시", "총계"): "세종특별자치시",
    ("세종특별자치시", "0"): "세종특별자치시",
}

# Non-autonomous gu that the public release keeps as one district. Bucheon-si's gu
# were abolished on 2016-07-01 and recreated on 2024-01-01, and to keep the panel
# unbroken the release reports the whole period as one '부천시' cell
# (08_export_dataset.py _BUCHEON_GU). So the eup/myeon/dong under it also get the
# Bucheon-si code. That code exists in those years too, so it is not an invented
# value but the code one level up.
_RELEASE_PARENT_RAW = {
    ("경기도", "부천시 원미구"): "부천시",
    ("경기도", "부천시 소사구"): "부천시",
    ("경기도", "부천시 오정구"): "부천시",
    ("경기도", "원미구"): "부천시",
    ("경기도", "소사구"): "부천시",
    ("경기도", "오정구"): "부천시",
}
# Spacing differs by edition and the boundary file writes '부천시소사구' without a
# space, so the keys are normalized
RELEASE_PARENT = dict(((norm(a), norm(b)), c) for (a, b), c in _RELEASE_PARENT_RAW.items())

_UNRESOLVED = defaultdict(int)


def unresolved():
    """Counts of unresolved names by (layer, year, province, name)."""
    return dict(_UNRESOLVED)


def reset_unresolved():
    _UNRESOLVED.clear()


def _ref(year):
    return int(year) * 10000 + 1231


# ---- reading the raw data ----------------------------------------------------
def _latest_zip():
    zs = sorted(glob.glob(os.path.join(REG_DIR, "법정동코드_조회자료_*.zip")))
    if not zs:
        raise SystemExit("The legal-dong code register file is missing. Download it with "
                         "python 02_code/kird.py --fetch-codes (expected location %s)" % REG_DIR)
    return zs[-1]


def _parse_register():
    """Legal-dong code register xlsx -> a flat table keeping only province and district rows."""
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
        # There are 157 records where the register wrote the closing date in the
        # creation-date cell as well (creation date == abolition date). That creation
        # date is not the real establishment date, so it is set to unknown.
        if start is not None and start == end:
            start = None
        rows.append((code, str(name).strip(), level,
                     str(flag).strip() == "현존", start, end))
    df = pd.DataFrame(rows, columns=["code", "name", "level", "alive", "start", "end"])
    os.makedirs(os.path.dirname(REGISTER_CACHE), exist_ok=True)
    df.to_csv(REGISTER_CACHE, index=False, encoding="utf-8-sig")
    print("  legal-dong codes %s -> provinces %d, districts %d (cache %s)"
          % (os.path.basename(src), int((df.level == "sido").sum()),
             int((df.level == "sgg").sum()), os.path.basename(REGISTER_CACHE)))
    return df


def _register():
    src = _latest_zip()
    if os.path.exists(REGISTER_CACHE) and os.path.getmtime(REGISTER_CACHE) >= os.path.getmtime(src):
        return pd.read_csv(REGISTER_CACHE, encoding="utf-8-sig",
                           dtype={"code": str, "name": str, "level": str})
    return _parse_register()


# ---- indexes ----------------------------------------------------------------
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
    """One record that existed at time ref. If none, look once more with the creation date relaxed.

    The register gives five old areas (the three gu of Bucheon-si, Cheongwon-gun,
    Jeonju-si Deokjin-gu) a creation date of 2013-04-02 (the bulk load date), later
    than their real establishment. When the strict check comes up empty, the creation
    date is ignored and only the abolition date is used, and the record closed soonest
    after ref is chosen.

    The second check applies only to records already abolished that have an abolition
    date. The creation dates of current records were never overwritten later, so they
    can be trusted, and relaxing them would revive areas in past years that did not
    exist yet (2026-07-01 '전남광주통합특별시', Incheon '제물포구').
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
    # A province with no province row ending in eight zeros ('세종특별자치시') is built
    # from its district row.
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
    # A record marked abolished with no abolition date (Gyeonggi-do Yeoju-gun) is
    # closed at the next creation date in the same lineage.
    for rs in fam.values():
        for rc in rs:
            if rc.end is None and not rc.alive:
                later = [s.start for s in rs if s.start is not None
                         and (rc.start is None or s.start > rc.start)]
                rc.end = min(later) if later else None

    key_fam = {k: fam[find(k)] for k in recs_by_key}

    # A gu written without its parent city ('마산합포구') -> the only full path within
    # that province. The search stays within the province, so Gwangju Nam-gu is not
    # pulled to Pohang-si Nam-gu.
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
    """2-digit province code as of 12/31 that year. None if unresolved."""
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
    """5-digit district code as of 12/31 that year. None if unresolved.

    With release_grain=True, the gu that the public release keeps as one
    (Bucheon-si Wonmi-gu, Sosa-gu, Ojeong-gu) are raised to the parent city
    (Bucheon-si) code, because the release's district table reports that cell as
    Bucheon-si.
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


# The seventeen province names the release uses ('강원도' and '전라북도' fixed to
# their pre-reorganization names).
RELEASE_SIDO_NAMES = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
    "울산광역시", "세종특별자치시", "경기도", "강원도", "충청북도", "충청남도",
    "전라북도", "전라남도", "경상북도", "경상남도", "제주특별자치도")


def province_that_year(year, sido, sigungu):
    """The province the district actually belonged to that year (release name).

    The district file keeps a district under its 2024 province for the whole panel
    (Gunwi-gun is Daegu in every year, Sejong-si is '세종특별자치시' from 2008). The
    province file follows that year's boundaries (summary_by_sido always did). This
    function links the two. It returns the province given by the first 2 digits of
    that year's district code: Gunwi-gun in 2022 (47720) is Gyeongsangbuk-do, Sejong-si
    in 2011 (44730) is Chungcheongnam-do. If the code is unresolved, the name is kept.
    2026-09-26 (round 3 cross-check): the province nationality and visa-status tables
    added up by name, so Daegu held Gunwi-gun in 2008-2022 and Gyeongsangbuk-do lost it
    (576 people in 2015).
    """
    c = sigungu_code(year, sido, sigungu)
    if not c:
        return sido
    own = sido_code(year, sido)
    if own and own == c[:2]:
        return sido
    for name in RELEASE_SIDO_NAMES:
        if sido_code(year, name) == c[:2]:
            return name
    return sido


# ---- eup/myeon/dong: that year's boundary snapshot ---------------------------
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
    """Split-dong names collapsed into one: '광교1동'/'광교2동' -> '광교동'. Used when the
    raw data and the boundaries record the split state of different years, where only
    the gu the dong belongs to is needed."""
    return _NUM_DONG.sub("동", ndong)


def _emd_index(year):
    lab = _emd_label(year)
    if lab in _EMD_CACHE:
        return _EMD_CACHE[lab]
    path = (os.path.join(SITE_DATA, "korea_emd.json") if lab == "2024"
            else os.path.join(SITE_DATA, "emd_years", "korea_emd_%s.json" % lab))
    ix = {"strict": {}, "part": {}, "loose": {},
          "strict_c": {}, "part_c": {}, "loose_c": {}, "districts": set()}
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    for ft in g["features"]:
        p = ft["properties"]
        v = (p["sido"], p["sg"], p.get("code", ""))
        sg, dong = _emdnorm(p["sg"]), _emdnorm(p["dong"])
        c = _collapse(dong)
        ix["strict"][(p["sido"], sg, dong)] = v
        ix["strict_c"].setdefault((p["sido"], sg, c), v)
        # '고양시덕양구' can be found by the parent city ('고양시') or by the gu ('덕양구'),
        # because each edition writes only one of the two (2014 the city only, 2024
        # the gu only).
        m = _CITY_GU.match(p["sg"])
        halves = [_emdnorm(m.group(1)), _emdnorm(m.group(2))] if m else []
        ix["districts"].update((p["sido"], h) for h in [sg] + halves)
        for h in halves:
            ix["part"].setdefault((p["sido"], h, dong), v)
            ix["part_c"].setdefault((p["sido"], h, c), v)
        for ks, k in (("loose", (p["sido"], dong)), ("loose_c", (p["sido"], c))):
            if k in ix[ks] and ix[ks][k] is not None and ix[ks][k][1] != v[1]:
                ix[ks][k] = None            # the name is in two districts: ambiguous
            elif k not in ix[ks]:
                ix[ks][k] = v
    # 2026-09-25: the province-wide lookup took the first district that had the
    # name (setdefault). 2023 '하남시 풍산동' (renamed '미사3동' in the boundary
    # file of that year) fell through to ('경기도', '풍산동') and came back as '고양시 일산동구':
    # multicultural_households carried Goyang's sigungu_code and adm_code on a
    # Hanam row. A name held by two districts of one province now matches nothing
    # at this step, and _look skips this step altogether when the row's own
    # district is in the boundary file (the dong is then simply not there).
    _EMD_CACHE[lab] = ix
    return ix


def _look(ix, sido, sg, dongs):
    """Tries the name candidates in turn within one year's index: exact -> half -> province."""
    own = (sido, sg) in ix.get("districts", ())
    for keyset in ("strict", "part", "loose", "strict_c", "part_c", "loose_c"):
        if own and keyset.startswith("loose"):
            continue            # the row names a real district; never borrow another's dong
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
    if "출장소" in d:                       # '죽장면상옥출장소' -> '죽장면'
        m = _BRANCH.match(d)
        if m and m.group(1) != d:
            out.append(m.group(1))
    return out


def emd_boundary(year, sido, sigungu, dong):
    """(province, district name that year, emd code that year) from that year's boundary snapshot. None if not found.

    If the district name matches that year's boundaries as is, that is the answer.
    Otherwise it is treated as a case where only the parent city or the gu is written
    and matched on the half name, and failing that it is looked up by dong name alone
    within the province. Because of the half step, 2014 (where the raw data write only
    '고양시') and 2024 (only '마산합포구') do not pull the same dong into different
    districts.
    """
    return _look(_emd_index(year), sido, _emdnorm(sigungu), _dong_candidates(dong))


def boundary_sigungu_name(year, sido, sigungu, dong):
    """Which district the dong was in that year, by name. None if not found.

    Some dongs are missing from that year's snapshot. Suwon Gwanggyo-dong in 2014
    appears in the boundaries only after it split into Gwanggyo 1 and 2 dong from 2015,
    and the same holds for Cheonan Buseong 1 and 2 dong and Buldang-dong. Such dongs
    are looked up in the snapshot of a nearby year. Gu membership does not change in
    between, so only the name is taken and the code is not used (the code is always
    resolved again for the row's own year).
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
    """District code for an eup/myeon/dong row. The gu given by that year's boundaries is used first."""
    b = boundary_sigungu_name(year, sido, sigungu, dong)
    if b:
        c = sigungu_code(year, b[0], b[1])
        if c:
            return c
    return sigungu_code(year, sido, sigungu)


# ---- adding code columns to the public tables ------------------------------
def add_code_columns(df, verbose_name=""):
    """A new DataFrame with sido_code / sigungu_code inserted next to sido_en / sigungu_en.

    If they already exist they are dropped and recomputed (same input, same result,
    so repeated runs agree). For a table with an eupmyeondong column, the district
    code is set from the gu given by that year's boundaries first, to recover the gu
    a dong belongs to in years where the raw data name only the parent city, as in
    '고양시'. Values are strings, and unresolved cells are left blank (no code is
    invented).
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
    # A province that did not exist that year ('세종특별자치시' in 2008-2011) is left
    # blank. Until 2026-09-26 (round 3 cross-check) it was filled from the first 2
    # digits of the district code (44, Chungcheongnam-do), so in the same year and the
    # same file 44 had two names, '충청남도' and '세종특별자치시'. The province
    # tables (nationality_by_sido, visa_by_sido) were already blank. The province code
    # is the code that the line's province name held that year, and if there is none,
    # there is none.

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
        print("  %-38s sido_code + sigungu_code (empty sigungu codes %d)" % (verbose_name, n))
    return df[cols]


# ---- per-year code table ----------------------------------------------------
def year_table(first=FIRST_YEAR, last=LAST_YEAR, save=True):
    """{year: {'sido': {code: name}, 'sigungu': {code: [sido code, full name]}}}"""
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
# Downloads the full legal-dong code file from the MOIS administrative standard code
# management system (run only when needed).
#
# The source is the two buttons at https://www.code.go.kr/stdcode/regCodeL.do.
#
#   '전체자료' (full file)    POST /etc/codeFullDown.do          codeseId='법정동코드'
#              -> '법정동코드 전체자료.txt' (cp949, tab-separated, 3 columns:
#                 code/name/abolished flag)
#   '조회자료' (query file)   POST /stdcode/regCodeFileDown.do   '폐지구분'='전체' + all
#                                                               optional columns
#              -> '법정동코드 조회자료.xlsx' (same records + creation/abolition dates)
#
# The pipeline reads the query file. Resolving per-year codes needs the creation and
# abolition dates, and those two columns come only with the query download. The full
# file is kept as well, as the original exactly as the agency published it.
#
# The downloaded zip is saved with a date stamp in '01_raw_data/행정표준코드/', and the
# README in that folder records the source and download date. If the site blocks
# automatic download, the script prints what blocked it and exits (it does not make up
# codes to fill in).

import datetime as _dt
import warnings

LIST_URL = "https://www.code.go.kr/stdcode/regCodeL.do"
FULL_URL = "https://www.code.go.kr/etc/codeFullDown.do"
QUERY_URL = "https://www.code.go.kr/stdcode/regCodeFileDown.do"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Values of the query form. A checked checkbox is "0" (see func_choice).
# disuseAt=ALL is needed to include abolished codes, and the abolished codes are
# needed to resolve old districts.
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
    s.verify = False          # the code.go.kr certificate chain is not in the requests default bundle
    s.headers.update({"User-Agent": UA, "Referer": LIST_URL})
    s.get(LIST_URL, timeout=60)   # session cookie
    return s


def _save_register_zip(content: bytes, path: str, expect_member: str) -> None:
    if not content[:2] == b"PK":
        raise SystemExit(f"The download is not a zip ({len(content)} bytes). Check whether the site blocked it:\n"
                         + content[:400].decode("cp949", errors="replace"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    if not any(expect_member in n for n in names):
        raise SystemExit(f"{path}: the expected file is missing ({names})")
    print(f"  saved {os.path.basename(path)}  {len(content):,} bytes  {names}")


def fetch_admin_codes(stamp: str | None = None) -> None:
    stamp = stamp or _dt.date.today().strftime("%Y%m%d")
    s = _register_session()
    print(f"Downloading the legal-dong code register ({stamp}) -> {REG_DIR}")

    r = s.post(FULL_URL, data={"codeseId": "법정동코드"}, timeout=600)
    _save_register_zip(r.content, os.path.join(REG_DIR, f"법정동코드_전체자료_{stamp}.zip"), "전체자료")

    # pageSize only takes effect in the URL. Set it well above the record count.
    r = s.post(QUERY_URL + "?cPage=1&pageSize=60000", data=QUERY_FORM, timeout=900)
    _save_register_zip(r.content, os.path.join(REG_DIR, f"법정동코드_조회자료_생성폐지일자포함_{stamp}.zip"), "조회자료")
    print("done.")


# ── entry points ─────────────────────────────────────────────────────────────
# The default checks the resolved paths; the other three are the old __main__ of the
# three scripts this module absorbed.
def _cli(argv):
    flag = argv[0] if argv else ""
    if flag == "--fetch-codes":
        fetch_admin_codes(argv[1] if len(argv) > 1 else None)
        return 0
    if flag == "--code-table":
        t = year_table()
        for y in ("2006", "2015", "2023", "2025"):
            print("  %s: provinces %d, districts %d" % (y, len(t[y]["sido"]), len(t[y]["sigungu"])))
        print("\nManual checks:")
        for y, sd, sg in SPOT_CHECKS:
            print("  %d %s %-16s sido=%s sigungu=%s"
                  % (y, sd, sg, sido_code(y, sd), sigungu_code(y, sd, sg)))
        if unresolved():
            print("\nUnresolved names:", unresolved())
        return 0
    if flag == "--admin2024":
        T = _tables()["ADMIN2024_TABLES"]
        print(f"provinces {len(T['sido'])}, districts {len(T['sigungu'])}, eup/myeon/dong {len(T['emd'])}")
        print("saved:", ADMIN2024_JSON)
        return 0
    if flag:
        print("unknown option: %s (--fetch-codes / --code-table / --admin2024)" % flag)
        return 2
    for name in __all__:
        value = globals()[name]
        print(f"{name:<14} {'ok ' if os.path.isdir(value) else 'MISSING'} {value}")
    return 0


if __name__ == "__main__":
    import sys as _sys

    _sys.exit(_cli(_sys.argv[1:]))



def cut_release_years(folder=None, last=None):
    """Removes rows after RELEASE_LAST_YEAR from the CSVs in the release folder.

    The dashboard shows up to the last year with an MOJ Statistical Yearbook, but the
    release and the deposit stop at the last year both sources cover. Depositing a
    half-empty year would carry rows whose broad-definition columns are all empty.

    It is called right after reconcile_indices in 09. The segregation indices must be
    built through LAST_YEAR and written back to the index files before that, so that
    the last year on the dashboard is not computed differently. The cut comes before
    the codebook, Stata and the audit, so the CSV, the .dta and the audit all see the
    same data.

    Every index is computed separately for each year (the top 19 countries are also
    chosen from that year's national total), so cutting later does not change the
    values of the years that remain.
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