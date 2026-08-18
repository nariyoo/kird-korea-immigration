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
"""

# ── paths ────────────────────────────────────────────────────────────────────
import os

__all__ = ["ROOT", "RAW", "CLEAN", "SITE", "SITE_DATA", "RELEASE", "RELEASE_DATA",
           "DEPOSIT", "DEPOSIT_DATA", "CODE", "MOIS_SITE"]

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
DEPOSIT = os.path.join(RELEASE, "data deposit", "kird_openicpsr_deposit")
DEPOSIT_DATA = os.path.join(DEPOSIT, "data")


if __name__ == "__main__":
    for name in __all__:
        value = globals()[name]
        print(f"{name:<14} {'ok ' if os.path.isdir(value) else 'MISSING'} {value}")


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
    population. Korean nationals are the residual of the total population.
    """
    f = sum(counts.values())
    if not f or not pop:
        return None
    kor = max(pop - f, 0)
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
    kor = max((pop or ftot) - ftot, 0)
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
