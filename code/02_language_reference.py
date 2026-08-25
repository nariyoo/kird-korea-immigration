"""The language reference tables: Korean to English labels, and L1 shares.

LANG_EN_KO in kird.py runs English to Korean and is many-to-one, so the
first pass inverts it and picks one English form per Korean label. The second
builds the weighted country to language shares from the Ethnologue 24 Global
Dataset, which is what turns a nationality composition into implied speakers.
"""
import csv
import json
import os
import re

from kird import COUNTRY_LANGUAGE
from kird import LANG_EN_KO
from kird import ROOT


def build_lang_ko_en():
    """Korean to English language labels, for the dashboard's English mode.

    `LANG_EN_KO` in kird.py runs English to Korean and is many-to-one, so
    this inverts it and picks one English form per Korean label: the short standard
    name, with dialect prefixes stripped.

    Outputs:
      * 03_cleaned_data/lang_ko_en.json — the Python/JSON dict
      * stdout: the JS literal block to paste into site/index.html LANG_KO_EN
    """
    HERE = os.path.dirname(os.path.abspath(__file__))


    # Manual overrides where the auto-derived English form isn't the standard one
    # Nari wants in the panel. Korean -> preferred English.
    OVERRIDE = {
        "한국어": "Korean", "영어": "English", "일본어": "Japanese",
        "중국어": "Chinese", "광둥어": "Cantonese",
        "베트남어": "Vietnamese", "태국어": "Thai", "라오어": "Lao",
        "크메르어": "Khmer", "미얀마어": "Burmese", "몽골어": "Mongolian",
        "인도네시아어": "Indonesian", "말레이어": "Malay",
        "타갈로그어": "Tagalog/Filipino",
        "러시아어": "Russian", "우크라이나어": "Ukrainian",
        "우즈베크어": "Uzbek", "카자흐어": "Kazakh", "키르기스어": "Kyrgyz",
        "타지크어": "Tajik", "투르크멘어": "Turkmen",
        "아제르바이잔어": "Azerbaijani", "조지아어": "Georgian", "아르메니아어": "Armenian",
        "튀르키예어": "Turkish", "터키어": "Turkish",
        "페르시아어": "Persian/Farsi", "다리어": "Dari",
        "쿠르드어": "Kurdish", "파슈토어": "Pashto",
        "아랍어": "Arabic", "히브리어": "Hebrew",
        "힌디어": "Hindi", "벵골어": "Bengali", "우르두어": "Urdu",
        "펀자브어": "Punjabi", "신디어": "Sindhi",
        "타밀어": "Tamil", "텔루구어": "Telugu", "말라얄람어": "Malayalam",
        "구자라트어": "Gujarati", "마라티어": "Marathi", "칸나다어": "Kannada",
        "오리야어": "Odia", "네팔어": "Nepali", "신할라어": "Sinhala",
        "싱할라어": "Sinhala", "디베히어": "Dhivehi", "종카어": "Dzongkha",
        "스페인어": "Spanish", "포르투갈어": "Portuguese", "프랑스어": "French",
        "독일어": "German", "이탈리아어": "Italian", "네덜란드어": "Dutch",
        "폴란드어": "Polish", "루마니아어": "Romanian", "불가리아어": "Bulgarian",
        "세르비아어": "Serbian", "크로아티아어": "Croatian", "보스니아어": "Bosnian",
        "슬로베니아어": "Slovenian", "마케도니아어": "Macedonian",
        "체코어": "Czech", "슬로바키아어": "Slovak", "헝가리어": "Hungarian",
        "그리스어": "Greek", "알바니아어": "Albanian",
        "스웨덴어": "Swedish", "노르웨이어": "Norwegian", "덴마크어": "Danish",
        "핀란드어": "Finnish", "아이슬란드어": "Icelandic",
        "에스토니아어": "Estonian", "라트비아어": "Latvian", "리투아니아어": "Lithuanian",
        "아일랜드어": "Irish",
        "스와힐리어": "Swahili", "암하라어": "Amharic", "티그리냐어": "Tigrinya",
        "오로모어": "Oromo", "소말리아어": "Somali", "하우사어": "Hausa",
        "요루바어": "Yoruba", "이그보어": "Igbo", "줄루어": "Zulu", "코사어": "Xhosa",
        "아프리칸스어": "Afrikaans", "소토어": "Sotho", "쇼나어": "Shona",
        "키냐르완다어": "Kinyarwanda", "키룬디어": "Kirundi",
        "말라가시어": "Malagasy", "월로프어": "Wolof", "풀라어": "Fula",
        "테툼어": "Tetum",
        "베르베르어": "Berber/Amazigh",
        "케추아어": "Quechua", "아이마라어": "Aymara", "과라니어": "Guarani",
        "마야어": "Mayan",
        # West Africa
        "아칸어": "Akan", "에웨어": "Ewe", "다그바니어": "Dagbani",
        "다그메어": "Dangme", "가어": "Ga",
        "바울레어": "Baoulé", "아니어": "Anyin", "줄라어": "Dyula",
        "모시어": "Mòoré", "단어": "Dan", "밤바라어": "Bambara",
        "소닌케어": "Soninke", "만데어": "Maninka", "세레르어": "Serer",
        "만딘카어": "Mandinka", "졸라어": "Jola",
        # East Africa
        "루간다어": "Luganda", "냔콜레어": "Nyankore", "소가어": "Soga",
        "치가어": "Chiga", "아테소어": "Ateso", "루그바라어": "Lugbara",
        "키쿠유어": "Kikuyu", "루오어": "Luo", "캄바어": "Kamba",
        "구시어": "Gusii", "메루어": "Meru", "칼렌진어": "Kalenjin",
        "루히아어": "Luhya", "올루이아어": "Luhya",
        "수쿠마어": "Sukuma", "하야어": "Haya", "마콘데어": "Makonde",
        "냐므웨지어": "Nyamwezi", "하어": "Ha", "헤헤어": "Hehe",
        "냐큐사어": "Nyakyusa", "마사이어": "Maasai", "투르카나어": "Turkana",
        "엠부어": "Embu", "가레어": "Garre", "포코트어": "Pökoot",
        "수바어": "Suba", "아위르어": "Aweer", "쿠리아어": "Kuria",
        "타이타어": "Taita", "포코모어": "Pokomo", "타베타어": "Taveta",
        "츄카어": "Chuka", "타라카어": "Tharaka", "삼부루어": "Samburu",
        "렌딜레어": "Rendille", "마이어": "Maay", "다할로어": "Dahalo",
        "누비어": "Nubi", "미지켄다어": "Mijikenda",
        # Central Africa
        "키투바어": "Kituba", "링갈라어": "Lingala",
        "루바카사이어": "Luba-Kasai", "루바카탕가어": "Luba-Katanga",
        "키콩고어": "Kikongo",
        # Cameroon / Congo
        "음보시어": "Mbosi", "베엠베어": "Beembe", "음베레어": "Mbere",
        "마파어": "Mafa", "불루어": "Bulu", "에원도어": "Ewondo", "에톤어": "Eton",
        "바사어": "Basaa", "콤어": "Kom", "람느소어": "Lamnso",
        "메둠바어": "Medumba", "응이엠본어": "Ngiemboon", "옘바어": "Yemba",
        "티카르어": "Tikar", "투푸리어": "Tupuri", "림붐어": "Limbum",
        "문당어": "Mundang", "뭉가카어": "Mungaka",
        "카메룬 피진어": "Cameroon Pidgin",
        # Southern Africa
        "츠와나어": "Tswana", "총가어": "Tsonga", "벤다어": "Venda", "스와티어": "Swati",
        # Nigeria
        "나이지리아 피진어": "Nigerian Pidgin", "카누리어": "Kanuri",
        "이비비오어": "Ibibio", "티브어": "Tiv", "이존어": "Ijaw",
        "에도어": "Edo", "에산어": "Esan", "우르호보어": "Urhobo",
        "이소코어": "Isoko", "이크웨레어": "Ikwere", "이갈라어": "Igala",
        "이도마어": "Idoma", "베롬어": "Berom", "그바기어": "Gbagyi",
        "그바리어": "Gbari", "누페어": "Nupe", "타로크어": "Tarok",
        "츠얍어": "Tyap", "부라어": "Bura", "마르기어": "Marghi",
        "캄웨어": "Kamwe", "랄라어": "Lala-Roba", "에비라어": "Ebira",
        "칼라바리어": "Kalabari", "키리케어": "Kirike",
        "오고니어": "Ogoni", "아낭어": "Anaang",
        "볼레어": "Bole", "바데어": "Bade", "카레카레어": "Karekare",
        "응가스어": "Angas", "음와그하불어": "Mwaghavul", "탕갈레어": "Tangale",
        "고에마이어": "Goemai", "사야어": "Saya", "만다라어": "Mandara",
        "혼어": "Hone", "주쿤어": "Jukun", "쿠텝어": "Kuteb",
        "에곤어": "Eggon", "무무예어": "Mumuye", "음벰베어": "Mbembe",
        "오그바어": "Ogba", "에키트어": "Ekit", "에차코어": "Etsako",
        "아다라어": "Adara", "햠어": "Hyam", "주어": "Jju",
        "쿠켈레어": "Kukele", "로카어": "Lokaa", "군어": "Gun",
        "이게데어": "Igede", "마다어": "Mada",
        "응가모어": "Ngamo", "페로어": "Pero", "바차마어": "Bachama",
        "바타어": "Bata", "구데어": "Gude",
        # Indonesia
        "미낭카바우어": "Minangkabau", "람풍어": "Lampung", "코메링어": "Komering",
        "크린치어": "Kerinci", "만다일링어": "Mandailing", "토바바탁어": "Toba Batak",
        "카로바탁어": "Karo Batak", "앙콜라어": "Angkola Batak",
        "시말룽운어": "Simalungun Batak", "다이리어": "Dairi Batak",
        "알라스어": "Alas", "베타위어": "Betawi", "사삭어": "Sasak",
        "비마어": "Bima", "망가라이어": "Manggarai", "라마홀롯어": "Lamaholot",
        "숨바와어": "Sumbawa", "캄베라어": "Kambera", "웨제와어": "Wejewa",
        "응가다어": "Ngad'a", "엔데어": "Ende", "리오어": "Li'o",
        "나게어": "Nage", "케오어": "Ke'o", "롱가어": "Rongga", "리웅어": "Riung",
        "헬롱어": "Helong", "다완어": "Uab Meto", "바이케노어": "Baikeno",
        "로테어": "Rote", "하우어": "Hawu", "다오어": "Dhao",
        "치아치아어": "Cia-Cia", "월리오어": "Wolio", "무나어": "Muna",
        "쿨리수수어": "Kulisusu", "톨라키어": "Tolaki", "모리어": "Mori",
        "파모나어": "Pamona", "바자우어": "Bajau",
        "갈렐라어": "Galela", "토벨로어": "Tobelo", "티도레어": "Tidore",
        "테르나테어": "Ternate", "사후어": "Sahu", "불리어": "Buli",
        "할마헤라어": "Halmahera",
        "암본 말레이어": "Ambonese Malay", "마나도 말레이어": "Manado Malay",
        "파푸아 말레이어": "Papuan Malay", "북말루쿠 말레이어": "North Moluccan Malay",
        "쿠팡 말레이어": "Kupang Malay", "라란투카 말레이어": "Larantuka Malay",
        "반다 말레이어": "Banda Malay", "바칸 말레이어": "Bacanese Malay",
        "팔렘방 말레이어": "Palembang Malay", "잠비 말레이어": "Jambi Malay",
        "발리어": "Balinese", "반자르어": "Banjar", "부기스어": "Buginese",
        "마카사르어": "Makassar", "토라자어": "Toraja", "마마사어": "Mamasa",
        "만다르어": "Mandar", "고론탈로어": "Gorontalo", "아체어": "Acehnese",
        # India
        "차티스가르어": "Chhattisgarhi", "마르와리어": "Marwari",
        "와그디어": "Wagdi", "바그리어": "Bagri", "분델리어": "Bundeli",
        "하리안비어": "Haryanvi", "칸나우지어": "Kanauji", "바겔리어": "Bagheli",
        "말비어": "Malvi", "메와티어": "Mewati", "하로티어": "Haroti",
        "둔다리어": "Dhundari", "빌리어": "Bhili", "빌랄리어": "Bhilali",
        "가르왈리어": "Garhwali", "쿠마오니어": "Kumaoni",
        "콘카니어": "Konkani", "칸데시어": "Khandesi", "보즈푸리어": "Bhojpuri",
        "툴루어": "Tulu", "카시미르어": "Kashmiri", "도그리어": "Dogri",
        "산탈리어": "Santali", "호어": "Ho", "문다리어": "Mundari",
        "쿠루크어": "Kurukh", "문다어": "Munda", "카시어": "Khasi",
        "가로어": "Garo", "보도어": "Bodo", "메이테이어": "Meitei",
        "미조어": "Mizo", "나가어": "Naga",
        "렙차어": "Lepcha", "셰르파어": "Sherpa", "부티아어": "Bhutia",
        "시킴어": "Sikkimese", "네와르어": "Newar", "림부어": "Limbu",
        "라이어": "Rai", "마가르어": "Magar", "타망어": "Tamang",
        "구룽어": "Gurung",
        "아디어": "Adi", "니시어": "Nyishi", "아파타니어": "Apatani",
        "미싱어": "Mishing", "카르비어": "Karbi", "티와어": "Tiwa",
        "디마사어": "Dimasa", "코크보로크어": "Kokborok",
        "람바디어": "Lambadi", "곤디어": "Gondi", "쿠이어": "Kui", "쿠비어": "Kuvi",
        "사우라슈트라어": "Saurashtra", "포트와리어": "Pahari-Pothwari",
        "비슈누프리야어": "Bishnupriya", "타루어": "Tharu",
        "바지카어": "Bajjika", "앙기카어": "Angika", "수르자푸리어": "Surjapuri",
        "사드리어": "Sadri", "할비어": "Halbi", "마하수어": "Mahasu Pahari",
        "만데알리어": "Mandeali", "참베알리어": "Chambeali",
        "바티알리어": "Bhattiyali", "캉리어": "Kangri", "가디어": "Gaddi",
        "마우치어": "Mawchi", "멘타와이어": "Mentawai", "니아스어": "Nias",
        "하종어": "Hajong", "라바어": "Rabha",
        # Ethiopia
        "시다마어": "Sidama", "하디야어": "Hadiyya", "가모어": "Gamo",
        "게데오어": "Gedeo", "카파어": "Kafa", "구라게어": "Gurage",
        "월라이타어": "Wolaytta", "아우니어": "Awngi", "베르타어": "Berta",
        "콘소어": "Konso", "누에르어": "Nuer", "메엔어": "Me'en",
        "마장어": "Majang", "구무즈어": "Gumuz", "셰코어": "Sheko",
        "수리어": "Suri", "다우로어": "Dawro", "고파어": "Gofa",
        "벤치어": "Bench", "캄바타어": "Kambaata", "사호어": "Saho",
        "아누아크어": "Anuak", "디라샤어": "Dirasha", "아리어": "Aari",
        "코마어": "Koma", "콰마어": "Gwama", "마오어": "Mao",
        "다사나치어": "Daasanach", "하메르어": "Hamer", "나기아탐어": "Nyangatom",
        "부르지어": "Burji", "알라바어": "Alaba", "리비도어": "Libido",
        "샴탕가어": "Xamtanga", "쿠나마어": "Kunama", "차마이어": "Tsamai",
        "보르나어": "Borna", "바스케토어": "Basketo", "디진어": "Dizin",
        "옘사어": "Yemsa", "셰카초어": "Shekkacho", "티그레어": "Tigre",
        "아파르어": "Afar",
        # Myanmar
        "샨어": "Shan", "카친어": "Kachin", "카렌어": "Karen",
        "카얀어": "Kayan", "카야어": "Kayah",
        "라카인어": "Rakhine", "라후어": "Lahu", "리수어": "Lisu",
        "아카어": "Akha", "파오어": "Pa'o", "므루어": "Mru",
        "다웨이어": "Tavoyan", "와어": "Wa", "마루어": "Maru",
        "라치드어": "Lacid", "아창어": "Ngochang", "팔라웅어": "Palaung",
        "리앙어": "Riang", "두룽어": "Drung", "흐몽어": "Hmong",
        "몬어": "Mon", "버마어": "Burmese", "인타어": "Intha",
        "다나우어": "Danau", "다누어": "Danu", "타웅요어": "Taungyo",
        "아농어": "Anong", "몬크메르어": "Mon-Khmer", "블랑어": "Blang",
        # Iran
        "마잔다란어": "Mazandarani", "길라키어": "Gilaki",
        "바흐티야리어": "Bakhtiari", "로리어": "Luri", "호라산터키어": "Khorasani Turkic",
        "카슈카이어": "Qashqai", "탈리시어": "Talysh", "브라후이어": "Brahui",
        "하자라기어": "Hazaragi", "발루치어": "Balochi", "아이마크어": "Aimaq",
        "셈난어": "Semnani", "타트어": "Tat", "아시리아어": "Assyrian Neo-Aramaic",
        # Afghanistan
        "파샤이어": "Pashai", "누리스타니어": "Nuristani", "와키어": "Wakhi",
        "샤그니어": "Shughni", "문지어": "Munji", "샹글레치어": "Sanglechi",
        "이슈카심어": "Ishkashimi",
        "카라칼파크어": "Karakalpak",
        # Russia
        "타타르어": "Tatar", "체첸어": "Chechen", "바슈키르어": "Bashkir",
        "아바르어": "Avar", "부랴트어": "Buryat", "야쿠트어": "Yakut/Sakha",
        "추바시어": "Chuvash", "카바르딘어": "Kabardian", "레즈긴어": "Lezgi",
        "다르긴어": "Dargwa", "마리어": "Mari", "에르자어": "Erzya",
        "목샤어": "Moksha", "코미어": "Komi", "우드무르트어": "Udmurt",
        "오세트어": "Ossetic", "카라차이발카르어": "Karachay-Balkar",
        "쿠믹어": "Kumyk", "인구시어": "Ingush", "아디게어": "Adyghe",
        "아바자어": "Abaza", "압하스어": "Abkhaz", "투바어": "Tuvan",
        "하카스어": "Khakas", "알타이어": "Altai", "칼미크어": "Kalmyk",
        "노가이어": "Nogai", "락어": "Lak", "타바사란어": "Tabasaran",
        "카렐리아어": "Karelian", "한티어": "Khanty", "만시어": "Mansi",
        "네네츠어": "Nenets", "응가나산어": "Nganasan", "셀쿠프어": "Selkup",
        "벱스어": "Veps", "사미어": "Sami", "축치어": "Chukchi",
        "코랴크어": "Koryak", "에벤어": "Even", "에벤키어": "Evenki",
        "나나이어": "Nanai", "이텔멘어": "Itelmen", "닐히어": "Nivkh",
        "유픽어": "Yupik", "케트어": "Ket", "베즈타어": "Bezhta",
        "히눅어": "Hinukh", "훈지브어": "Hunzib", "지도어": "Tsez",
        "안디어": "Andi",
        # Sudan
        "베자어": "Beja", "푸르어": "Fur", "마살리트어": "Masalit",
        "자가와어": "Zaghawa", "누비아어": "Nubian", "타마어": "Tama",
        "테갈리어": "Tegali", "다주어": "Daju", "누바어": "Nuba",
        "마반어": "Maban", "우두크어": "Uduk", "마바어": "Maba",
        "테다어": "Tedaga", "마라리트어": "Mararit", "아통어": "Atong",
        # misc additions
        "기타": "Other",
    }


    def main():
        # Invert LANG_EN_KO -> Korean -> set of English forms
        inv = {}
        for en, ko in LANG_EN_KO.items():
            inv.setdefault(ko, []).append(en)

        out = {}
        for ko, forms in inv.items():
            if ko in OVERRIDE:
                out[ko] = OVERRIDE[ko]
            else:
                # Pick the shortest non-prefix-laden form.
                forms.sort(key=lambda s: (
                    1 if ("," in s or " " in s and any(p in s for p in
                          ("Northern ", "Southern ", "Eastern ", "Western ",
                           "Central ", "Modern ", "Standard ", "Iranian ",
                           "Egyptian ", "Sudanese "))) else 0,
                    len(s),
                    s))
                out[ko] = forms[0]

        # Add OVERRIDE-only entries (not appearing in LANG_EN_KO).
        for ko, en in OVERRIDE.items():
            out.setdefault(ko, en)

        # Persist as JSON.
        op = os.path.join(ROOT, "03_cleaned_data", "lang_ko_en.json")
        json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        print(f"wrote {op} ({len(out)} entries)")

        # Print JS literal for embedding in site/index.html.
        print("\n// --- paste into site/index.html LANG_KO_EN ---")
        items = sorted(out.items())
        line_buf, lines = [], []
        for ko, en in items:
            e = en.replace('"', '\\"')
            line_buf.append(f'"{ko}":"{e}"')
            if len(line_buf) >= 4:
                lines.append(",".join(line_buf))
                line_buf = []
        if line_buf:
            lines.append(",".join(line_buf))
        print("const LANG_KO_EN = {")
        for ln in lines:
            print("  " + ln + ",")
        print("};")

    main()



def build_language_shares():
    """Build weighted country -> language shares from the Ethnologue 24 Global
    Dataset (SIL International, 2021). The Table_of_LICs.tab file lists every
    language spoken in every country, with separate L1 (mother-tongue) and L2
    speaker counts. We aggregate L1_Users per country, then express each
    language's share of the country's total mother-tongue population.

    This is the cleanest possible methodology for our purpose:
      * L1 speakers only (the actual interpretation-need population)
      * Census/survey-derived counts from SIL's curated database
      * No L2/colonial-language inflation (no CLDR overcount)
      * No %-vs-no-% gap in coverage (no CIA Factbook gap)
      * Uniform schema across all countries

    Output: 03_cleaned_data/country_language_shares.json (same shape as before).
    Hand overrides for non-country aggregates (한국계중국인, 한국계러시아인, etc.)
    are preserved at the end.
    """
    HERE = os.path.dirname(os.path.abspath(__file__))
    LICS = os.path.join(ROOT, "01_raw_data", "ethnologue global dataset",
                        "Table_of_LICs.tab")
    OUT = os.path.join(ROOT, "03_cleaned_data", "country_language_shares.json")


    # ---- Ethnologue Language_Name -> Korean label used in language_demand panels
    # Ethnologue uses uninverted English names (e.g., "Standard Arabic", "Min Nan
    # Chinese", "Mandarin Chinese", "Iranian Persian"). Anything unmapped is kept
    # under its original Ethnologue English name (NO 기타 bucket); only the three
    # non-nationalities 국적불명/무국적/기타 are dropped (see the 기타 filter below).

    OTHER_KO = "기타"

    # ---- Ethnologue ISO-2 country code -> Korean country name
    # Built from intersection with build_dashboard.COUNTRY_LANGUAGE keys.
    CC_KO = {
        "KR": "대한민국", "KP": "조선민주주의인민공화국",
        "US": "미국", "GB": "영국", "CA": "캐나다", "AU": "오스트레일리아",
        "NZ": "뉴질랜드", "IE": "아일랜드",
        "CN": "중국", "JP": "일본", "TW": "타이완", "HK": "홍콩", "MO": "마카오",
        "VN": "베트남", "TH": "타이", "LA": "라오스", "KH": "캄보디아",
        "MM": "미얀마", "MY": "말레이시아", "SG": "싱가포르", "ID": "인도네시아",
        "PH": "필리핀", "BN": "브루나이", "TL": "티모르민주공화국",
        "MN": "몽골",
        "IN": "인도", "PK": "파키스탄", "BD": "방글라데시", "LK": "스리랑카",
        "NP": "네팔", "BT": "부탄", "MV": "몰디브", "AF": "아프가니스탄",
        "RU": "러시아(연방)", "BY": "벨라루스", "UA": "우크라이나", "MD": "몰도바",
        "KZ": "카자흐스탄", "UZ": "우즈베키스탄", "KG": "키르기스스탄",
        "TJ": "타지키스탄", "TM": "투르크메니스탄",
        "AZ": "아제르바이잔", "AM": "아르메니아", "GE": "조지아",
        "TR": "튀르키예", "IR": "이란", "IQ": "이라크", "IL": "이스라엘",
        "JO": "요르단", "LB": "레바논", "SY": "시리아", "YE": "예멘공화국",
        "SA": "사우디아라비아", "AE": "아랍에미리트연합", "QA": "카타르",
        "KW": "쿠웨이트", "BH": "바레인", "OM": "오만",
        "EG": "이집트", "LY": "리비아", "TN": "튀니지", "DZ": "알제리", "MA": "모로코",
        "SD": "수단", "SS": "남수단공화국",
        "ET": "에티오피아", "ER": "에리트레아", "SO": "소말리아", "DJ": "지부티",
        "KE": "케냐", "TZ": "탄자니아", "UG": "우간다", "RW": "르완다", "BI": "부룬디",
        "CD": "콩고민주공화국", "CG": "콩고", "CM": "카메룬", "CF": "중앙아프리카공화국",
        "TD": "차드", "NE": "니제르", "NG": "나이지리아", "BJ": "베냉", "TG": "토고",
        "GH": "가나", "CI": "코트디부아르", "LR": "라이베리아", "SL": "시에라리온",
        "GN": "기니", "GW": "기니비사우", "SN": "세네갈", "ML": "말리",
        "BF": "부르키나파소", "MR": "모리타니", "GM": "감비아", "CV": "카보베르데",
        "ZA": "남아프리카공화국", "LS": "레소토", "SZ": "에스와티니",
        "BW": "보츠와나", "NA": "나미비아", "AO": "앙골라", "ZM": "잠비아",
        "ZW": "짐바브웨", "MW": "말라위", "MZ": "모잠비크", "MG": "마다가스카르",
        "MU": "모리셔스", "SC": "세이셸", "KM": "코모로",
        "GQ": "적도기니", "GA": "가봉", "ST": "상투메프린시페",
        "FR": "프랑스", "DE": "독일", "IT": "이탈리아", "ES": "스페인",
        "PT": "포르투갈", "NL": "네덜란드", "BE": "벨기에", "CH": "스위스",
        "AT": "오스트리아", "SE": "스웨덴", "NO": "노르웨이", "DK": "덴마크",
        "FI": "핀란드", "IS": "아이슬란드",
        "GR": "그리스", "PL": "폴란드", "CZ": "체코", "SK": "슬로바키아",
        "HU": "헝가리", "RO": "루마니아", "BG": "불가리아",
        "RS": "세르비아", "HR": "크로아티아", "BA": "보스니아헤르체고비나",
        "SI": "슬로베니아", "MK": "북마케도니아", "AL": "알바니아",
        "XK": "코소보", "ME": "몬테네그로",
        "EE": "에스토니아", "LV": "라트비아", "LT": "리투아니아", "CY": "키프로스",
        "MT": "몰타", "LU": "룩셈부르크",
        "PG": "파푸아뉴기니", "FJ": "피지", "SB": "솔로몬제도", "VU": "바누아투",
        "WS": "사모아", "TO": "통가", "KI": "키리바시", "TV": "투발루",
        "NR": "나우루", "PW": "팔라우", "MH": "마셜제도", "FM": "미크로네시아연방",
        "MX": "멕시코", "GT": "과테말라", "BZ": "벨리즈", "HN": "온두라스",
        "SV": "엘살바도르", "NI": "니카라과", "CR": "코스타리카", "PA": "파나마",
        "CU": "쿠바", "JM": "자메이카", "HT": "아이티", "DO": "도미니카공화국",
        "BS": "바하마", "BB": "바베이도스", "TT": "트리니다드토바고",
        "GD": "그레나다", "LC": "세인트루시아", "VC": "세인트빈센트그레나딘",
        "KN": "세인트키츠네비스", "AG": "앤티가바부다", "DM": "도미니카연방",
        "BR": "브라질", "AR": "아르헨티나", "CL": "칠레", "PE": "페루",
        "EC": "에콰도르", "CO": "콜롬비아", "VE": "베네수엘라",
        "GY": "가이아나", "SR": "수리남", "PY": "파라과이", "UY": "우루과이",
        "BO": "볼리비아",
    }

    KO_CC = {v: k for k, v in CC_KO.items()}


    def map_lang_ethno(name):
        """Map an Ethnologue Uninverted_Name -> Korean label.

        Ethnologue uses regional / dialect names that explicit-lookup misses
        (e.g., 'Egyptian Spoken Arabic', 'North Levantine Spoken Arabic', 'Iranian
        Persian', 'South Azerbaijani'). Try exact match first, then pattern
        matching on common suffixes / substrings; if still unmatched, keep the
        original Ethnologue English name (NO 기타 bucket).
        """
        if name in LANG_EN_KO:
            v = LANG_EN_KO[name]
            return v if v != OTHER_KO else name   # 명시적 기타 매핑도 원래 이름 유지(기타 버킷 없음)
        n = name.replace("ʼ", "'").replace("’", "'")  # normalize apostrophes
        # Substring patterns (order matters: more specific first).
        if "Arabic" in n:
            return "아랍어"
        if "Chinese" in n:
            # Cantonese (Yue) is split from Mandarin/other Chinese for interpretation
            # purposes; the others lump to 중국어.
            if "Yue" in n or "Cantonese" in n:
                return "광둥어"
            return "중국어"
        if "Kurdish" in n:
            return "쿠르드어"
        if "Persian" in n or "Farsi" in n:
            return "페르시아어"
        if "Azerbaijani" in n or "Azeri" in n:
            return "아제르바이잔어"
        if "Pashto" in n or "Pushto" in n:
            return "파슈토어"
        if "Mongolian" in n or "Mongol" in n:
            return "몽골어"
        if "Albanian" in n:
            return "알바니아어"
        if "Armenian" in n:
            return "아르메니아어"
        if "Greek" in n:
            return "그리스어"
        if "Mongolian" in n:
            return "몽골어"
        if "Norwegian" in n:
            return "노르웨이어"
        if "Romani" in n and "Romanian" not in n:
            return "로마니어"
        if "Romanian" in n or "Moldavian" in n:
            return "루마니아어"
        if "Fulfulde" in n or "Pulaar" in n or "Fulani" in n or "Fula" in n.split():
            return "풀라어"
        if "Tibetan" in n:
            return "티베트어"
        if "Tagalog" in n or "Filipino" in n:
            return "타갈로그어"
        # Lump all Punjabi/Panjabi spellings together (Western Punjabi, Eastern
        # Panjabi, Northern Hindko, etc. are mutually intelligible enough for
        # interpretation purposes).
        if "Punjabi" in n or "Panjabi" in n or "Hindko" in n or "Pahari-Potwari" in n:
            return "펀자브어"
        # Hindi-belt languages spoken across north India / Nepal: Maithili,
        # Bhojpuri, Awadhi/Avadhi, Magahi are closely related to Hindi.
        if n in ("Maithili", "Bhojpuri", "Awadhi", "Avadhi", "Magahi",
                 "Chhattisgarhi", "Marwari", "Rajasthani", "Haryanvi"):
            return "힌디어"
        # Nepal regional: keep close to Nepali if they're in the same family.
        if "Tharu" in n or n == "Dotyali":
            return "네팔어"
        if "Assamese" in n:
            return "벵골어"
        # 방언 변형군은 부모 언어로 통합(통역 목적상 동일군). 과분리 방지.
        if "Karen" in n or "Kayah" in n:
            return "카렌어"           # S'gaw/Pwo Karen 등
        if "Chin" in n or "Mro-Khimi" in n or n == "Zo":
            return "친어"             # Tedim/Hakha/Asho/Falam/Khumi Chin 등
        if "Palaung" in n:
            return "팔라웅어"
        if "Balochi" in n:
            return "발루치어"
        if "Luri" in n:
            return "로리어"
        if "Naga" in n:
            return "나가어"
        if "Kongo" in n:
            return "키콩고어"
        # 한국어 라벨이 없는 소수민족어(통역풀 미정)는 기타로 합치지 않고 원래 이름 그대로 유지
        lab = LANG_EN_KO.get(name)
        return lab if (lab and lab != OTHER_KO) else name


    def main():
        # Aggregate L1_Users by (country_iso2, language_name).
        # Column indices in Table_of_LICs.tab (the first row is the header, the
        # column at index 0 is just a sequence number).
        LICs = {}
        with open(LICS, encoding="utf-8") as f:
            rdr = csv.reader(f, delimiter="\t")
            header = next(rdr)
            # header layout: [seq, ISO_639, Language_Name, Uninverted, Country_Code,
            #                 Country_Name, Region_Code, Region_Name, Area,
            #                 Is_Primary, Is_Indigenous, Is_Established,
            #                 All_Users, L1_Users, L2_Users, ...]
            ic_lang, ic_country, ic_l1 = 2, 3, 12  # Uninverted_Name, Country_Code, L1_Users
            for row in rdr:
                if len(row) < 14:
                    continue
                lang = row[ic_lang].strip()
                cc = row[ic_country].strip()
                l1_raw = row[ic_l1].strip().replace(",", "")
                try:
                    l1 = int(l1_raw)
                except ValueError:
                    continue
                if not lang or not cc or l1 <= 0:
                    continue
                LICs.setdefault(cc, {}).setdefault(lang, 0)
                LICs[cc][lang] += l1

        print(f"Aggregated L1_Users for {len(LICs)} countries")

        # Build {korean_country_name: shares} from Ethnologue.
        by_country = {}
        for ko, cc in KO_CC.items():
            ldata = LICs.get(cc)
            if not ldata:
                continue
            # Convert each Ethnologue language -> Korean label, summing collisions.
            ko_lang = {}
            for lang_en, l1 in ldata.items():
                ko_lab = map_lang_ethno(lang_en)
                ko_lang[ko_lab] = ko_lang.get(ko_lab, 0) + l1
            total = sum(ko_lang.values())
            if total <= 0:
                continue
            # 기타로 묶지 않고 모든 언어를 이름 그대로 유지(큰 언어가 자연히 상위로). 노이즈 방지로
            # 0.05% 미만 극소 long-tail만 드롭(기타 버킷 없이; 누락 최소). 패널은 상위 N개만 표시.
            kept = {k: v for k, v in ko_lang.items() if v / total >= 0.0005}
            ksum = sum(kept.values()) or total
            by_country[ko] = {k: v / ksum for k, v in kept.items()}

        print(f"Ethnologue L1 shares built for {len(by_country)} countries")

        # Hand overrides for non-country aggregates that have no Ethnologue entry.
        # 한국계중국인 / 한국계러시아인 are simplified to a single primary L1 per
        # Nari's call (the previous 60/40 / 95/5 splits were guesses; the simple
        # mapping has no arbitrary parameters and is defensible). Korean labels
        # are filtered out below since "Korean" is the host language and not part
        # of the foreign-language interpretation demand.
        SPECIAL = {
            "한국계중국인": [{"language": "한국어", "share": 1.0}],
            "한국계러시아인": [{"language": "러시아어", "share": 1.0}],
            "국적불명": [{"language": "기타", "share": 1.0}],
            "무국적": [{"language": "기타", "share": 1.0}],
            "국제연합": [{"language": "영어", "share": 1.0}],
            "국제연합전문기구": [{"language": "영어", "share": 1.0}],
            "교황청": [{"language": "이탈리아어", "share": 1.0}],
            "기타": [{"language": "기타", "share": 1.0}],
        }

        out = {}
        for ko, single_lang in COUNTRY_LANGUAGE.items():
            if ko in by_country:
                sh = by_country[ko]
                out[ko] = sorted(
                    ({"language": k, "share": round(v, 4)} for k, v in sh.items()),
                    key=lambda d: -d["share"])
            else:
                out[ko] = [{"language": single_lang, "share": 1.0}]

        for k, v in SPECIAL.items():
            out[k] = v

        # Filter 한국어 AND 기타 from every country's share and renormalize the rest.
        # The language_demand panels track FOREIGN-language interpretation needs in
        # Korea; Korean-speaking immigrants (e.g., 한국계중국인) carry no interpretation
        # demand and should not appear under "한국어". The residual "기타" bucket is also
        # dropped entirely (no 기타 bucket): the only sources are non-nationalities
        # 국적불명/무국적/기타, which cannot be assigned a public-service language, so
        # they contribute nothing to language demand rather than inflating a 기타 row.
        filtered = 0
        for ko, shares in out.items():
            kept = [s for s in shares if s["language"] not in ("한국어", OTHER_KO)]
            if len(kept) == len(shares):
                continue
            ksum = sum(s["share"] for s in kept)
            if ksum <= 0:
                # Country contributes only Korean/기타 speakers; drop entirely so the
                # population doesn't get re-allocated.
                out[ko] = []
                filtered += 1
                continue
            out[ko] = [{"language": s["language"], "share": round(s["share"] / ksum, 4)}
                       for s in kept]
            filtered += 1

        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"wrote {OUT} ({len(out)} entries)")
        print(f"  Ethnologue: {len(by_country)} | single-lang fallback: {len(COUNTRY_LANGUAGE) - len(by_country)} | special: {len(SPECIAL)}")
        print(f"  Korean filtered/renormalized in {filtered} country shares")

    main()


if __name__ == "__main__":
    build_lang_ko_en()
    build_language_shares()
